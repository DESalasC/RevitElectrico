# -*- coding: utf-8 -*-
# RE_EXPORTAR_POSICIONES_REVIT_v01.py
# Exporta posiciones de FamilyInstances y Conduits modelados en Revit a JSON para contraste con DXF.
# Los elementos ya están modelados; este script SOLO lee y exporta (no modifica nada).
#
# Ejecutar dentro de Revit 2026 (pyRevit Python Shell).
# Compatible con IronPython 2.7: sin parámetro 'encoding' en open().
#
# Uso dentro de pyRevit Python Shell:
#   execfile(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_EXPORTAR_POSICIONES_REVIT_v01.py")
#   exportar_posiciones(doc, salida_json=r"D:\...\data\posiciones_revit_export.json")

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import os

# ---------------------------------------------------------------------------
# Parámetros de configuración (ajustar según necesidad)
# ---------------------------------------------------------------------------
# Familia del tablero tal como aparece en Revit 2026 (tras renombrado)
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
# Obtener valor de un parámetro por nombre (manejo seguro de valores nulos)
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
            return str(param.AsElementId())
        else:
            return str(param.AsValueString())
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Listar FamilyInstances existentes con sus parámetros relevantes
# ---------------------------------------------------------------------------
def listar_family_instances(doc):
    """Retorna lista de FamilyInstances con familia, símbolo, posición y parámetros.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""
    instancias = []
    collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    for fi in collector:
        try:
            fam_name = fi.Symbol.Family.Name if fi.Symbol and fi.Symbol.Family else ""
            sym_name = fi.Symbol.Name if fi.Symbol else ""
            cat_name = fi.Category.Name if fi.Category else ""

            # Posición
            x = y = z = None
            loc = fi.Location
            if loc and hasattr(loc, "Point"):
                pt = loc.Point
                x, y, z = pt.X, pt.Y, pt.Z

            # Parámetro 'Panel Name' (clave para emparejar con el DXF/TABLERO)
            panel_name = obtener_parametro(fi, "Panel Name")
            if panel_name is None:
                panel_name = obtener_parametro(fi, "TABLERO")

            instancias.append({
                "id": int(fi.Id),
                "familia": fam_name,
                "simbolo": sym_name,
                "categoria": cat_name,
                "x": x,
                "y": y,
                "z": z,
                "panel_name": panel_name if panel_name else "",
                "nivel": fi.Level.Name if fi.Level else "",
                "es_tablero": (fam_name == FAMILIA_TABLERO_REVIT),
            })
        except Exception:
            continue
    return instancias

# ---------------------------------------------------------------------------
# Listar Conduit (tuberías) con posición y parámetros
# ---------------------------------------------------------------------------
def listar_conduits(doc):
    """Retorna lista de Conduit con sistema, posición y parámetros."""
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
                    x, y, z = pt_mid.X, pt_mid.Y, pt_mid.Z

            panel_name = obtener_parametro(cond, "Panel Name")
            if panel_name is None:
                panel_name = obtener_parametro(cond, "TABLERO")

            conduits.append({
                "id": int(cond.Id),
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
# Función principal
# ---------------------------------------------------------------------------
def exportar_posiciones(doc, salida_json=None):
    print("=== RE_EXPORTAR_POSICIONES_REVIT_v01 ===")
    print("Documento: {}".format(doc.Title))
    print("Ruta: {}".format(doc.PathName))

    instancias = listar_family_instances(doc)
    conduits = listar_conduits(doc)

    print("\nTotal FamilyInstances exportadas: {}".format(len(instancias)))
    print("Total Conduits exportados: {}".format(len(conduits)))

    # Contar tableros encontrados
    tableros = [i for i in instancias if i["es_tablero"]]
    print("Tableros ({}) encontrados:".format(len(tableros)))
    for t in tableros:
        print("  ID={} | panel_name='{}' | X={:.3f} Y={:.3f} Z={:.3f}".format(
            t["id"], t["panel_name"], t["x"] or 0, t["y"] or 0, t["z"] or 0))

    # Agrupar por panel_name para diagnóstico rápido
    from collections import Counter
    paneles_inst = Counter(i["panel_name"] for i in instancias if i["panel_name"])
    paneles_cond = Counter(c["panel_name"] for c in conduits if c["panel_name"])
    print("\nPanel Names en FamilyInstances:")
    for p, c in paneles_inst.most_common():
        print("  '{}': {}".format(p, c))
    print("Panel Names en Conduits:")
    for p, c in paneles_cond.most_common():
        print("  '{}': {}".format(p, c))

    # Estructura de salida
    datos = {
        "documento": doc.Title,
        "ruta_documento": doc.PathName,
        "fecha_export": "2026-10-28",
        "nivel": "Piso 5",
        "familia_tablero_revit": FAMILIA_TABLERO_REVIT,
        "transformacion_referencia": {
            "TX": 6.49,
            "TY": 10.2234,
            "tipo": "traslacion_pura_sin_espejo"
        },
        "family_instances": instancias,
        "conduits": conduits,
        "resumen": {
            "total_family_instances": len(instancias),
            "total_conduits": len(conduits),
            "tableros_encontrados": len(tableros),
            "paneles_unicos": len(set([i["panel_name"] for i in instancias if i["panel_name"]] +
                                      [c["panel_name"] for c in conduits if c["panel_name"]]))
        }
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
        exportar_posiciones(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit Python Shell).")
        print("Variable __revit__ no definida.")
