# -*- coding: utf-8 -*-
"""
RE7_EXPORTAR_CONDUITS_REVIT_v01.py
Exporta todos los conduits del modelo Revit activo a JSON para validacion RE-P-068.

Lee:  modelo Revit activo (CENTRAL-V01b)
Escribe: data/f7_conduits_desde_revit_v01.json  (todos los conduits del modelo)

Uso (consola Python de Revit, IronPython 2.7):
    exec(open(r"D:\Work\PROJECTS\RevitElectrico\scripts\pyrevit\RE7_EXPORTAR_CONDUITS_REVIT_v01.py").read())
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
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    XYZ,
    BuiltInParameter,
)
from Autodesk.Revit.DB.Electrical import Conduit

VERSION = "v01"
FT_A_MM = 304.8
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
    LOG_PATH = os.path.join(carpeta, "f7_exportar_conduits.log")
    try:
        with open(LOG_PATH, "a") as f:
            f.write("[{}] INICIO RE7_EXPORTAR_CONDUITS_REVIT_{}\n".format(
                datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), VERSION))
    except Exception:
        pass


def log(msg):
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


def escribir_archivo_texto(ruta, contenido_texto):
    try:
        with open(ruta, "w") as f:
            f.write(contenido_texto)
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


def dist_3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def main():
    _iniciar_log()
    log("=" * 60)
    log("RE7_EXPORTAR_CONDUITS_REVIT_{} - Exportar conduits a JSON".format(VERSION))
    log("ejecutado_utc={}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo de Revit.")
        return 1

    titulo = doc.Title
    log("documento={!r}".format(titulo))

    # Colectar todos los conduits
    conduits = list(FilteredElementCollector(doc).OfClass(Conduit).ToElements())
    log("Conduits encontrados en el modelo: {}".format(len(conduits)))

    conduits_list = []
    for c in conduits:
        cid = id_de(c)
        loc = c.Location
        a_mm = b_mm = None
        largo_mm = None
        if isinstance(loc, LocationCurve):
            curva = loc.Curve
            p0 = curva.GetEndPoint(0)
            p1 = curva.GetEndPoint(1)
            a_mm = [p0.X * FT_A_MM, p0.Y * FT_A_MM, p0.Z * FT_A_MM]
            b_mm = [p1.X * FT_A_MM, p1.Y * FT_A_MM, p1.Z * FT_A_MM]
            largo_mm = dist_3d(a_mm, b_mm)

        # Obtener diametro del tipo
        tipo = doc.GetElement(c.GetTypeId())
        diametro_mm = None
        try:
            p = tipo.get_Parameter(BuiltInParameter.CONDUIT_DIAMETER)
            if p is not None:
                diametro_mm = p.AsDouble() * FT_A_MM
        except Exception:
            diametro_mm = None

        conduits_list.append({
            "conduit_id": cid,
            "a_mm": [round(v, 3) for v in a_mm] if a_mm else None,
            "b_mm": [round(v, 3) for v in b_mm] if b_mm else None,
            "largo_mm": round(largo_mm, 3) if largo_mm is not None else None,
            "diametro_mm": round(diametro_mm, 3) if diametro_mm is not None else None,
        })

    # Ordenar por id para salida determinista
    conduits_list.sort(key=lambda x: x["conduit_id"])

    reporte = {
        "version": VERSION,
        "script": "RE7_EXPORTAR_CONDUITS_REVIT_v01",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "resumen": {"total_conduits": len(conduits_list)},
        "conduits": conduits_list,
    }

    raiz = _raiz()
    out_json = os.path.join(raiz, "data", "f7_conduits_desde_revit_v01.json")
    try:
        contenido = json.dumps(reporte, ensure_ascii=True, indent=2)
        if escribir_archivo_texto(out_json, contenido):
            log("Reporte guardado en: {}".format(out_json))
        else:
            log("ERROR: no se pudo escribir el reporte JSON.")
    except Exception as e:
        log("ERROR al escribir reporte JSON: {}".format(e))

    log("RESULTADO: {} conduits exportados.".format(len(conduits_list)))
    log("FIN")
    log("=" * 60)
    return 0


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
