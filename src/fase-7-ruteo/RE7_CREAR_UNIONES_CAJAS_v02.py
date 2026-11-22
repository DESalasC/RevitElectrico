# -*- coding: utf-8 -*-
"""
RE7_CREAR_UNIONES_CAJAS_v02.py — Crea uniones/cajas de empate (conduit fittings)
en los puntos de conexión detectados entre conductos existentes en Revit.

Corregido v02:
  - Nombres de familia reales de CENTRA_V02-f (modelo de referencia validado).
  - Estructura importada desde Autodesk.Revit.DB.Structure (IronPython 2.7).
  - Diagnóstico busca por categoría OST_ConduitFitting (no por nombre 'conduit').

USO (desde pyRevit Python Shell dentro de Revit 2026):
  exec(open(r"D:/Work/PROJECTS/RevitElectrico/src/fase-7-ruteo/RE7_CREAR_UNIONES_CAJAS_v02.py").read())
  doc = __revit__.ActiveUIDocument.Document
  diagnosticar_familias_conduit(doc)
  crear_uniones_cajas(doc, json_path="data/f7_uniones_detectadas_v01.json",
                      primeros=20, solo_primeros=False)
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FamilySymbol,
    FamilyInstance,
    Transaction,
    ElementId,
    BuiltInCategory,
    XYZ,
    Level,
    ConnectorSet,
    Connector,
)
from Autodesk.Revit.DB.Electrical import Conduit
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

import json
import os
import sys
from datetime import datetime

FT_A_MM = 304.8  # pies a milímetros


def _raiz_proyecto():
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz and os.path.exists(raiz):
        return raiz
    return r"D:\Work\PROJECTS\RevitElectrico"


def _resolver_ruta(p):
    p = p.strip()
    if os.path.isabs(p):
        return p
    return os.path.join(_raiz_proyecto(), p)


def _mm_a_pie(mm):
    """Convierte milímetros a pies (unidad interna de Revit)."""
    return mm / FT_A_MM


def _punto_revit(x_mm, y_mm, z_mm):
    """Crea un XYZ de Revit a partir de coordenadas en milímetros."""
    return XYZ(_mm_a_pie(x_mm), _mm_a_pie(y_mm), _mm_a_pie(z_mm))


def _buscar_simbolo_familia(doc, nombre_familia, nombre_tipo=None):
    """Busca un FamilySymbol por nombre de familia y opcionalmente por nombre de tipo."""
    collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
    for fs in collector:
        try:
            nombre_fam = fs.Family.Name
        except Exception:
            continue
        if nombre_familia.lower() not in nombre_fam.lower():
            continue
        if nombre_tipo is not None:
            try:
                nombre_sym = fs.Name
            except Exception:
                nombre_sym = ""
            if nombre_tipo.lower() not in nombre_sym.lower():
                continue
        return fs
    return None


def _mapeo_tipo_a_familia(tipo_accesorio):
    """Mapea el tipo de accesorio recomendado a un patrón de nombre de familia Revit.

    Los nombres de familia son los reales de CENTRA_V02-f (modelo de referencia
    validado), no nombres genéricos en inglés.
    """
    mapeo = {
        "Conduit Coupling": ("M_Casquillo reductor de tubo - PVC", None),
        "Conduit Elbow": ("M_Codo de tubo - Extremo abocardado - PVC", None),
        "Conduit Junction Box - Tee": ("M_Caja de conexiones de tubo - Te - PVC", None),
        "Conduit Junction Box - Cross": ("M_Caja de conexiones de tubo - Cruz - PVC", None),
    }
    return mapeo.get(tipo_accesorio, (None, None))


def _obtener_conductos_en_punto(doc, conduit_ids):
    """Obtiene los elementos Conduit de Revit por sus IDs (enteros)."""
    conductos = []
    for cid in conduit_ids:
        try:
            eid = ElementId(Int64(int(cid)))
            elem = doc.GetElement(eid)
            if elem is not None and isinstance(elem, Conduit):
                conductos.append(elem)
        except Exception:
            continue
    return conductos


def _conectar_conductos_al_accesorio(doc, accesorio, conductos):
    """Intenta conectar los conectores de los conductos al accesorio colocado."""
    conectados = 0
    if accesorio is None:
        return conectados

    try:
        mep_model = accesorio.MEPModel
        if mep_model is None:
            return conectados
        conectores_accesorio = list(mep_model.ConnectorSet)
    except Exception:
        conectores_accesorio = []

    for cond in conductos:
        try:
            cm = cond.ConnectorManager
            if cm is None:
                continue
            conectores_cond = list(cm.Connectors)
        except Exception:
            continue

        try:
            loc = cond.Location
            if loc is None:
                continue
            punto_cond = None
            if hasattr(loc, "Point") and loc.Point is not None:
                punto_cond = loc.Point
            elif hasattr(loc, "Curve") and loc.Curve is not None:
                curva = loc.Curve
                punto_cond = curva.Evaluate(0.5, True)
            else:
                continue
        except Exception:
            continue

        punto_acc = None
        try:
            punto_acc = accesorio.Location.Point
        except Exception:
            pass

        mejor_conector = None
        mejor_dist = float("inf")
        for cn in conectores_cond:
            try:
                origen = cn.Origin
                if punto_acc is not None:
                    d = punto_acc.DistanceTo(origen)
                else:
                    d = punto_cond.DistanceTo(origen)
                if d < mejor_dist:
                    mejor_dist = d
                    mejor_conector = cn
            except Exception:
                continue

        if mejor_conector is None:
            continue

        for cn_acc in conectores_accesorio:
            try:
                if cn_acc.IsConnected:
                    continue
                mejor_conector.ConnectTo(cn_acc)
                conectados += 1
                break
            except Exception:
                continue

    return conectados


def diagnosticar_familias_conduit(doc):
    """Lista todas las familias y símbolos de conduit cargados en el modelo.

    Busca por categoría OST_ConduitFitting (no por nombre 'conduit'),
    porque los nombres reales están en español.
    """
    print("=" * 60)
    print("DIAGNOSTICO: Familias de conduit cargadas en el modelo")
    print("=" * 60)
    collector = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_ConduitFitting)
        .OfClass(FamilySymbol)
    )
    simbolos = list(collector.ToElements())
    encontrados = []
    for fs in simbolos:
        try:
            nom_fam = fs.Family.Name
            nom_tipo = fs.Name
        except Exception:
            continue
        encontrados.append((nom_fam, nom_tipo))
    if not encontrados:
        print("  No se encontraron familias en categoria OST_ConduitFitting.")
    else:
        for nom_fam, nom_sym in sorted(encontrados):
            print("  Familia: {:<45} | Tipo: {}".format(nom_fam, nom_sym))
    print("=" * 60)
    return encontrados


def crear_uniones_cajas(doc, json_path="data/f7_uniones_detectadas_v01.json",
                        primeros=0, solo_primeros=False):
    """Crea uniones/cajas de empate en los puntos de conexión detectados."""
    ruta_json = _resolver_ruta(json_path)
    if not os.path.exists(ruta_json):
        raise IOError("No existe el archivo JSON: {}".format(ruta_json))

    with open(ruta_json, "r") as f:
        reporte = json.load(f)

    puntos_union = reporte.get("puntos_union", [])
    if not puntos_union:
        print("RE7_CREAR_UNIONES_CAJAS_v02: no hay puntos de unión en el JSON.")
        return {"ok": 0, "fallidos": 0, "saltados": 0, "total": 0, "detalles": []}

    # Filtrar por primeros conduits si se solicita
    puntos_a_procesar = []
    ids_primeros = set()
    if primeros and primeros > 0:
        todos_ids = sorted(set(
            cid for p in puntos_union for cid in p["conduit_ids"]
        ))
        ids_primeros = set(todos_ids[:primeros])

    for p in puntos_union:
        ids = p["conduit_ids"]
        if primeros and primeros > 0:
            if solo_primeros:
                if not all(cid in ids_primeros for cid in ids):
                    continue
            else:
                if not any(cid in ids_primeros for cid in ids):
                    continue
        puntos_a_procesar.append(p)

    print("=" * 60)
    print("RE7_CREAR_UNIONES_CAJAS_v02 - Creación de uniones/cajas de empate")
    print("ejecutado_utc={}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 60)
    print("Puntos de unión en JSON: {}".format(len(puntos_union)))
    print("Puntos a procesar: {}".format(len(puntos_a_procesar)))
    if primeros:
        print("Filtro primeros {} conduit(s): {}".format(
            primeros, "solo_primeros={}".format(solo_primeros)))
    print("")

    resultados = {"ok": 0, "fallidos": 0, "saltados": 0, "total": len(puntos_a_procesar), "detalles": []}

    t = Transaction(doc, "RE7 Crear uniones y cajas de empate")
    t.Start()

    try:
        for idx, p in enumerate(puntos_a_procesar):
            punto_mm = p["punto_mm"]
            ids_conduits = p["conduit_ids"]
            tipo_accesorio = p["tipo_accesorio_recomendado"]

            # Mapear tipo a familia
            patron_familia, nombre_tipo = _mapeo_tipo_a_familia(tipo_accesorio)
            if patron_familia is None:
                resultados["saltados"] += 1
                resultados["detalles"].append({
                    "punto": punto_mm,
                    "tipo": tipo_accesorio,
                    "estado": "saltado",
                    "motivo": "tipo de accesorio no mapeado",
                })
                continue

            # Buscar símbolo de familia
            simbolo = _buscar_simbolo_familia(doc, patron_familia, nombre_tipo)
            if simbolo is None:
                resultados["fallidos"] += 1
                resultados["detalles"].append({
                    "punto": punto_mm,
                    "tipo": tipo_accesorio,
                    "estado": "fallido",
                    "motivo": "familia no encontrada: {}".format(patron_familia),
                })
                continue

            # Activar símbolo si es necesario
            try:
                if not simbolo.IsActive:
                    simbolo.Activate()
            except Exception:
                pass

            # Obtener nivel del documento (primer nivel disponible)
            nivel = None
            try:
                nivel_collector = FilteredElementCollector(doc).OfClass(Level)
                for lv in nivel_collector:
                    nivel = lv
                    break
            except Exception:
                pass

            # Crear el punto XYZ en Revit
            xyz = _punto_revit(punto_mm[0], punto_mm[1], punto_mm[2])

            # Colocar FamilyInstance
            simbolo_nombre = simbolo.Name if simbolo else None
            familia_nombre = simbolo.Family.Name if simbolo else None
            try:
                if nivel is not None:
                    instancia = doc.Create.NewFamilyInstance(
                        xyz, simbolo, nivel, StructuralType.NonStructural)
                else:
                    instancia = doc.Create.NewFamilyInstance(
                        xyz, simbolo, StructuralType.NonStructural)
            except Exception as ex:
                resultados["fallidos"] += 1
                resultados["detalles"].append({
                    "punto": punto_mm,
                    "tipo": tipo_accesorio,
                    "estado": "fallido",
                    "motivo": "error al crear instancia: {}".format(str(ex)),
                    "familia": familia_nombre,
                    "simbolo": simbolo_nombre,
                })
                continue

            # Obtener los elementos Conduit de Revit y tratar de conectar
            conductos = _obtener_conductos_en_punto(doc, ids_conduits)
            conectados = 0
            if conductos:
                try:
                    conectados = _conectar_conductos_al_accesorio(
                        doc, instancia, conductos)
                except Exception:
                    conectados = 0

            resultados["ok"] += 1
            resultados["detalles"].append({
                "punto": punto_mm,
                "tipo": tipo_accesorio,
                "estado": "ok",
                "conduit_ids": ids_conduits,
                "conectores_conectados": conectados,
                "familia": simbolo.Family.Name if simbolo else None,
                "simbolo": simbolo.Name if simbolo else None,
            })

            if (idx + 1) % 10 == 0:
                print("  Procesados {}/{}...".format(
                    idx + 1, len(puntos_a_procesar)))

    except Exception as ex:
        t.RollBack()
        print("ERROR: transacción revertida: {}".format(str(ex)))
        raise

    t.Commit()

    print("")
    print("RESULTADOS:")
    print("  OK:       {}".format(resultados["ok"]))
    print("  Fallidos: {}".format(resultados["fallidos"]))
    print("  Saltados: {}".format(resultados["saltados"]))
    print("  Total:    {}".format(resultados["total"]))
    print("")

    # Mostrar detalles de fallos y saltos
    if resultados["fallidos"] > 0 or resultados["saltados"] > 0:
        print("DETALLES DE FALLOS / SALTOS:")
        for d in resultados["detalles"]:
            if d["estado"] in ("fallido", "saltado"):
                print("  punto={} tipo={} estado={} motivo={} familia={} simbolo={}".format(
                    d["punto"], d["tipo"], d["estado"],
                    d.get("motivo", ""),
                    d.get("familia", ""), d.get("simbolo", "")))
    print("=" * 60)

    return resultados


# Si se ejecuta directamente en pyRevit sin pasar doc, intentar obtenerlo de __revit__
if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        diagnosticar_familias_conduit(doc)
        resultado = crear_uniones_cajas(doc)
        print("Resumen: {} OK, {} fallidos, {} saltados de {} totales".format(
            resultado["ok"], resultado["fallidos"], resultado["saltados"], resultado["total"]))
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso: exec(open(ruta_script).read())")
        print("     doc = __revit__.ActiveUIDocument.Document")
        print("     crear_uniones_cajas(doc, json_path=..., primeros=...)")

