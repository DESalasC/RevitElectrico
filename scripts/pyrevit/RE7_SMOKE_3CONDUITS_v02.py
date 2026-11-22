# -*- coding: utf-8 -*-
"""
RE7_SMOKE_3CONDUITS_v02.py
Etapa 1 del ruteo F7: smoke test de creacion de 3 conduits en Revit.
Escribe log a archivo desde el inicio (por si la consola no muestra print).

NO ejecutar en CENTRA_V02-f.rvt (referencia intocable).
Piloto recomendado: E06 (sandbox).

Uso (consola Python de Revit):
    exec(open(r"D:\Work\PROJECTS\RevitElectrico\scripts\pyrevit\RE7_SMOKE_3CONDUITS_v02.py").read())
"""
import datetime
import json
import math
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
from System import Int64, IO

VERSION = "v02"
FT_A_MM = 304.8
DOC_PROHIBIDO = "V02-f"  # referencia intocable
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

LOG_PATH = None


def _raiz():
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz and os.path.exists(raiz):
        return raiz
    return DEFAULT_ROOT


def _iniciar_log():
    global LOG_PATH
    raiz = _raiz()
    carpeta = os.path.join(raiz, "data")
    try:
        if not os.path.exists(carpeta):
            os.makedirs(carpeta)
    except Exception:
        carpeta = os.environ.get("TEMP", ".")
    LOG_PATH = os.path.join(carpeta, "f7_smoke_pyrevit.log")
    try:
        with open(LOG_PATH, "a") as f:
            f.write("[{}] INICIO RE7_SMOKE_3CONDUITS_{}\n".format(
                datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), VERSION))
    except Exception:
        pass


def log(msg):
    """Imprime y persiste en archivo, sin poder fallar."""
    try:
        print(msg)
    except Exception:
        pass
    try:
        sys.stdout.flush()
    except Exception:
        pass
    if LOG_PATH:
        try:
            with open(LOG_PATH, "a") as f:
                f.write("[{}] {}\n".format(
                    datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), msg))
        except Exception:
            pass


def escribir_archivo_binario(ruta, contenido_bytes):
    """Escribe bytes a disco usando System.IO (evita códec de IronPython)."""
    try:
        IO.File.WriteAllBytes(ruta, contenido_bytes)
        return True
    except Exception:
        return False


def obtener_doc():
    try:
        app = __revit__
        if app is not None and hasattr(app, "ActiveUIDocument"):
            return app.ActiveUIDocument.Document
    except Exception:
        pass
    try:
        from pyrevit import revit as _revit
        if getattr(_revit, "doc", None) is not None:
            return _revit.doc
    except Exception:
        pass
    return None


def id_de(elemento):
    eid_val = elemento.Id
    if hasattr(eid_val, "IntegerValue"):
        return int(eid_val.IntegerValue)
    return int(eid_val.Value)


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz_mm(x_mm, y_mm, z_mm):
    return XYZ(mm_a_ft(x_mm), mm_a_ft(y_mm), mm_a_ft(z_mm))


def buscar_nivel(doc, nombre_esperado="Piso 5", elevacion_m=13.22, tolerancia_mm=5.0):
    mejor = None
    mejor_delta = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        delta = abs(lvl.Elevation * FT_A_MM - elevacion_m * 1000.0)
        if mejor_delta is None or delta < mejor_delta:
            mejor = lvl
            mejor_delta = delta
        if lvl.Name == nombre_esperado or delta <= tolerancia_mm:
            return lvl
    return mejor


def buscar_tipo_conduit(doc, type_id=112216):
    for t in FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
        if id_de(t) == type_id:
            return t
    for t in FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
        try:
            if Conduit.IsValidConduitType(doc, t.Id):
                return t
        except Exception:
            continue
    return None


def definir_tramos_prueba():
    return [
        {"id": "SMOKE-T01", "a_mm": [3000.0, 16000.0, 15930.0], "b_mm": [6000.0, 16000.0, 15930.0]},
        {"id": "SMOKE-T02", "a_mm": [6000.0, 16000.0, 15930.0], "b_mm": [6000.0, 19000.0, 15930.0]},
        {"id": "SMOKE-T03", "a_mm": [6000.0, 19000.0, 15930.0], "b_mm": [9000.0, 19000.0, 15930.0]},
    ]


def crear_conduit(doc, tipo_id, level_id, a_mm, b_mm):
    return Conduit.Create(doc, ElementId(Int64(tipo_id)), xyz_mm(*a_mm), xyz_mm(*b_mm), ElementId(Int64(level_id)))


def main():
    _iniciar_log()
    log("=" * 60)
    log("RE7_SMOKE_3CONDUITS_{} - Etapa 1 F7".format(VERSION))
    log("ejecutado_utc={}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo de Revit.")
        return 1

    titulo = doc.Title
    if DOC_PROHIBIDO in titulo:
        log("ERROR: documento prohibido para escritura: {!r}".format(titulo))
        log("     El piloto de creacion va en E06 (sandbox), no en V02-f (referencia).")
        return 1

    try:
        app_version = doc.Application.Version
    except Exception:
        app_version = "?"
    log("documento={!r} version_revit={} modificado={}".format(titulo, app_version, bool(doc.IsModified)))
    log("=" * 60)

    nivel = buscar_nivel(doc)
    if nivel is None:
        log("ERROR: no se encontro nivel Piso 5.")
        return 1
    log("nivel: {!r} id={} elevacion={} mm".format(nivel.Name, id_de(nivel), round(nivel.Elevation * FT_A_MM, 3)))

    tipo = buscar_tipo_conduit(doc)
    if tipo is None:
        log("ERROR: no se encontro tipo de conduit valido.")
        return 1
    try:
        nombre_tipo = tipo.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
    except Exception:
        nombre_tipo = tipo.Name
    log("   nombre_tipo: {!r}".format(nombre_tipo))

    tramos = definir_tramos_prueba()
    creados = []
    trans = Transaction(doc, "RE7_SMOKE_3CONDUITS_v02")
    trans.Start()
    try:
        for t in tramos:
            c = crear_conduit(doc, id_de(tipo), id_de(nivel), t["a_mm"], t["b_mm"])
            creados.append({"id_t": t["id"], "conduit": c, "a_mm": t["a_mm"], "b_mm": t["b_mm"]})
            log("creado {!r} id={}".format(t["id"], id_de(c)))
        trans.Commit()
        log("Transaccion COMMIT: {} conduits creados.".format(len(creados)))
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    # Verificacion post-creacion
    reporte = {
        "version": VERSION,
        "script": "RE7_SMOKE_3CONDUITS_v02",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "nivel": {"id": id_de(nivel), "nombre": nivel.Name, "elevacion_mm": round(nivel.Elevation * FT_A_MM, 3)},
        "tipo_conduit": {"id": id_de(tipo), "nombre": nombre_tipo},
        "tramos": [],
    }

    for item in creados:
        c = item["conduit"]
        cid = id_de(c)
        loc = c.Location
        a_real = b_real = None
        if isinstance(loc, LocationCurve):
            curva = loc.Curve
            a_real = [curva.GetEndPoint(0).X * FT_A_MM, curva.GetEndPoint(0).Y * FT_A_MM, curva.GetEndPoint(0).Z * FT_A_MM]
            b_real = [curva.GetEndPoint(1).X * FT_A_MM, curva.GetEndPoint(1).Y * FT_A_MM, curva.GetEndPoint(1).Z * FT_A_MM]

        def dist(p, q):
            return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)
        da = dist(a_real, item["a_mm"]) if a_real else None
        db = dist(b_real, item["b_mm"]) if b_real else None
        ok = (da is not None and db is not None and da < 10.0 and db < 10.0)
        item_reporte = {
            "id": item["id_t"],
            "conduit_id": cid,
            "a_mm_esperado": item["a_mm"],
            "b_mm_esperado": item["b_mm"],
            "a_mm_real": [round(v, 3) for v in a_real] if a_real else None,
            "b_mm_real": [round(v, 3) for v in b_real] if b_real else None,
            "dist_a_mm": round(da, 3) if da is not None else None,
            "dist_b_mm": round(db, 3) if db is not None else None,
            "verificado": ok,
        }
        reporte["tramos"].append(item_reporte)
        log("verificacion {!r}: dist_a={} dist_b={} OK={}".format(
            item["id_t"], item_reporte["dist_a_mm"], item_reporte["dist_b_mm"], ok))

    raiz = _raiz()
    out_json = os.path.join(raiz, "data", "f7_smoke_3conduits_v02.json")
    try:
        contenido = json.dumps(reporte, ensure_ascii=True, indent=2).encode("utf-8")
        if escribir_archivo_binario(out_json, contenido):
            log("Reporte guardado en: {}".format(out_json))
        else:
            log("ERROR: no se pudo escribir el reporte JSON.")
    except Exception as e:
        log("ERROR al escribir reporte JSON: {}".format(e))

    todos_ok = all(t["verificado"] for t in reporte["tramos"])
    log("RESULTADO: {} de {} conduits verificados OK.".format(
        sum(1 for t in reporte["tramos"] if t["verificado"]), len(reporte["tramos"])))
    log("FIN")
    log("=" * 60)
    return 0 if todos_ok else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    try:
        log("EXCEPCION NO CONTROLADA:\n" + traceback.format_exc())
    except Exception:
        pass
    raise SystemExit(1)
