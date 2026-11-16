# -*- coding: utf-8 -*-
# RE_AUDITAR_DISPOSITIVOS_v01.py
# Exporta FamilyInstances del modelo Revit activo con los datos necesarios para
# el diff clasificado DXF vs Revit (F2, plan RE_PLAN_CORRECCION_LOCALIZACION_DXF_REVIT_v01.md).
#
# Salida: JSON con family_instances [{id, familia, simbolo, categoria, x, y, z,
#   panel_name, nivel, host_id, host_categoria, host_nivel, orientacion_grados,
#   comentarios, servicio_conduit}] y conduits.
#
# Coordenadas en pies internos de Revit (RE_COMPARAR_INVENTARIO_v01 las pasa a metros).
#
# Ejecutar DENTRO de Revit 2026 (pyRevit Python Shell). No modifica el modelo (solo lectura).
# Compatible con IronPython 2.7: sin parametro encoding en open(), sin f-strings.
#
# Ultimos tres cambios
# --------------------
# 1. 2026-11-12 v01: version inicial. Exporta host, orientacion y parametros por instancia.
# 2. Heredado: regla F2 del plan de correccion DXF->Revit (criterios A1-A8).
# 3. Heredado: sin registro previo disponible.
#
# Uso dentro de pyRevit Python Shell:
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_AUDITAR_DISPOSITIVOS_v01.py")
#   auditar_dispositivos(doc, salida_json=r"D:\...\data\posiciones_revit_export_E06_v01.json",
#                        poligono_json=r"D:\...\data\poligono_E06_pies.json")  # poligono opcional, pies
#
# Fuente de verdad para el diff: el inventario del DXF (un dispositivo por INSERT).

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import os

# ---------------------------------------------------------------------------
# Familia del tablero tal como aparece en Revit 2026 (tras renombrado)
# ---------------------------------------------------------------------------
FAMILIA_TABLERO_REVIT = "E_Distribution Panel"

# ---------------------------------------------------------------------------
# Carga y guardado de JSON (IronPython 2.7: sin parametro encoding)
# ---------------------------------------------------------------------------
def cargar_json(path):
    with open(path, "r") as f:
        return json.load(f)


def guardar_json(path, datos):
    directorio = os.path.dirname(path)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(path, "w") as f:
        json.dump(datos, f, ensure_ascii=True, indent=2)


# ---------------------------------------------------------------------------
# Geometria: punto dentro de poligono (ray casting). Coordenadas en pies.
# ---------------------------------------------------------------------------
def punto_en_poligono(px, py, poligono):
    dentro = False
    j = len(poligono) - 1
    for i in range(len(poligono)):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            dentro = not dentro
        j = i
    return dentro


# ---------------------------------------------------------------------------
# Valor de parametro por nombre (manejo seguro de nulos)
# ---------------------------------------------------------------------------
def obtener_parametro(elemento, nombre_parametro):
    try:
        param = elemento.LookupParameter(nombre_parametro)
        if param is None:
            return None
        if not param.HasValue:
            return None
        if param.StorageType == StorageType.String:
            return param.AsString()
        elif param.StorageType == StorageType.Double:
            return param.AsDouble()
        elif param.StorageType == StorageType.Integer:
            return param.AsInteger()
        elif param.StorageType == StorageType.ElementId:
            eid = param.AsElementId()
            return eid.IntegerValue if eid is not None else -1
        else:
            return str(param.AsValueString())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Orientacion en grados del facing orientation (XY)
# ---------------------------------------------------------------------------
def angulo_orientacion(facing):
    if facing is None:
        return None
    try:
        return round(math.degrees(math.atan2(facing.Y, facing.X)), 2)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Host de una instancia (muro / techo / None)
# ---------------------------------------------------------------------------
def info_host(fi, doc):
    host = fi.Host
    if host is None:
        return None, None, None
    try:
        return host.Id.IntegerValue, host.Category.Name if host.Category else "", \
            host.Level.Name if host.Level else ""
    except Exception:
        return None, None, None


def nivel_de(elemento, doc):
    """Nombre del nivel del elemento.

    FamilyInstance no expone ``.Level`` en IronPython (AttributeError), y como el bucle
    principal descarta el elemento entero ante cualquier excepcion, eso hacia que el
    export saliera con cero instancias en silencio. Se resuelve por LevelId.
    """
    try:
        lid = elemento.LevelId
        if lid is not None and lid != ElementId.InvalidElementId:
            nivel = doc.GetElement(lid)
            if nivel is not None:
                return nivel.Name
    except Exception:
        pass
    return ""


def orientacion_segura(elemento):
    """Angulo de FacingOrientation, o cadena vacia si no es accesible."""
    try:
        return angulo_orientacion(elemento.FacingOrientation)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Listar FamilyInstances con datos para el diff
# ---------------------------------------------------------------------------
def listar_family_instances(doc, poligono_pies=None):
    instancias = []
    collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    for fi in collector:
        try:
            fam_name = fi.Symbol.Family.Name if fi.Symbol and fi.Symbol.Family else ""
            sym_name = fi.Symbol.Name if fi.Symbol else ""
            cat_name = fi.Category.Name if fi.Category else ""

            loc = fi.Location
            x = y = z = None
            if loc and hasattr(loc, "Point"):
                pt = loc.Point
                if poligono_pies is not None and not punto_en_poligono(pt.X, pt.Y, poligono_pies):
                    continue
                x, y, z = pt.X, pt.Y, pt.Z

            panel_name = obtener_parametro(fi, "Panel Name")
            if panel_name is None:
                panel_name = obtener_parametro(fi, "TABLERO")

            host_id, host_cat, host_nivel = info_host(fi, doc)

            instancias.append({
                "id": fi.Id.IntegerValue,
                "familia": fam_name,
                "simbolo": sym_name,
                "categoria": cat_name,
                "x": x,
                "y": y,
                "z": z,
                "panel_name": panel_name if panel_name else "",
                "nivel": nivel_de(fi, doc),
                "es_tablero": (fam_name == FAMILIA_TABLERO_REVIT),
                "host_id": host_id,
                "host_categoria": host_cat,
                "host_nivel": host_nivel,
                "orientacion_grados": orientacion_segura(fi),
                "comentarios": obtener_parametro(fi, "Comments"),
                "servicio_conduit": obtener_parametro(fi, "Servicio_Conduit"),
            })
        except Exception:
            continue
    return instancias


# ---------------------------------------------------------------------------
# Listar Conduits con posicion (punto medio de la curva)
# ---------------------------------------------------------------------------
def listar_conduits(doc, poligono_pies=None):
    conduits = []
    collector = FilteredElementCollector(doc).OfClass(Conduit)
    for cond in collector:
        try:
            system_name = cond.GetMEPSystemType().Name if cond.GetMEPSystemType() else ""
            x = y = z = None
            loc = cond.Location
            if loc and hasattr(loc, "Curve"):
                curve = loc.Curve
                if curve is not None:
                    pt_mid = curve.Evaluate(0.5, True)
                    if poligono_pies is None or punto_en_poligono(pt_mid.X, pt_mid.Y, poligono_pies):
                        x, y, z = pt_mid.X, pt_mid.Y, pt_mid.Z
                    else:
                        continue
            panel_name = obtener_parametro(cond, "Panel Name")
            if panel_name is None:
                panel_name = obtener_parametro(cond, "TABLERO")
            conduits.append({
                "id": cond.Id.IntegerValue,
                "tipo": "conduit",
                "sistema": system_name,
                "categoria": cond.Category.Name if cond.Category else "",
                "x": x,
                "y": y,
                "z": z,
                "panel_name": panel_name if panel_name else "",
                "diametro": cond.Diameter if hasattr(cond, "Diameter") else None,
            })
        except Exception:
            continue
    return conduits


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------
def auditar_dispositivos(doc, salida_json=None, poligono_json=None):
    print("=== RE_AUDITAR_DISPOSITIVOS_v01 ===")
    print("Documento: {}".format(doc.Title))
    print("Ruta: {}".format(doc.PathName))

    poligono_pies = None
    if poligono_json:
        try:
            pol_data = cargar_json(poligono_json)
            poligono_pies = pol_data.get("poligono", [])
            print("Poligono filtro: {} puntos".format(len(poligono_pies)))
        except Exception as exc:
            print("ADVERTENCIA: no se cargo poligono: {}".format(exc))

    instancias = listar_family_instances(doc, poligono_pies)
    conduits = listar_conduits(doc, poligono_pies)

    print("\nTotal FamilyInstances exportadas: {}".format(len(instancias)))
    print("Total Conduits exportados: {}".format(len(conduits)))

    tableros = [i for i in instancias if i["es_tablero"]]
    print("Tableros ({}) encontrados:".format(len(tableros)))
    for t in tableros:
        print("  ID={} | panel_name='{}' | X={:.3f} Y={:.3f} Z={:.3f}".format(
            t["id"], t["panel_name"], t["x"] or 0, t["y"] or 0, t["z"] or 0))

    from collections import Counter
    paneles_inst = Counter(i["panel_name"] for i in instancias if i["panel_name"])
    paneles_cond = Counter(c["panel_name"] for c in conduits if c["panel_name"])
    print("\nPanel Names en FamilyInstances:")
    for p, c in paneles_inst.most_common():
        print("  '{}': {}".format(p, c))
    print("Panel Names en Conduits:")
    for p, c in paneles_cond.most_common():
        print("  '{}': {}".format(p, c))

    datos = {
        "documento": doc.Title,
        "ruta_documento": doc.PathName,
        "fecha_export": "2026-11-12",
        "nivel": "Piso 5",
        "familia_tablero_revit": FAMILIA_TABLERO_REVIT,
        "unidades": "pies_internos_revit",
        "family_instances": instancias,
        "conduits": conduits,
        "resumen": {
            "total_family_instances": len(instancias),
            "total_conduits": len(conduits),
            "tableros_encontrados": len(tableros),
            "paneles_unicos": len(set([i["panel_name"] for i in instancias if i["panel_name"]] +
                                      [c["panel_name"] for c in conduits if c["panel_name"]])),
        },
    }

    if salida_json:
        try:
            guardar_json(salida_json, datos)
            print("\nJSON guardado en: {}".format(salida_json))
        except Exception as exc:
            print("ERROR guardando JSON: {}".format(exc))

    return datos


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        auditar_dispositivos(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit Python Shell).")
        print("Variable __revit__ no definida.")
