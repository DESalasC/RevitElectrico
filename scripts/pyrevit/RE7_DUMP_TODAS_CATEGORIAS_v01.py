# -*- coding: utf-8 -*-
"""
RE7_DUMP_TODAS_CATEGORIAS_v01.py
SOLO LECTURA. Vuelca TODAS las categorias de dispositivos electricos y de
comunicaciones en zonas F17/F18, impreso categoria por categoria con ElementId.
Esto permite verificar cuales dispositivos del DXF (ELEC-TEL, ELEC-TIMBRE,
ELEC-CAMPANA, etc.) ya estan colocados en Revit y bajo que nombre/familia.

Entrada: nada (lee del modelo activo de Revit)
Salida: solo consola (categoria por categoria) + JSON en data/
Entorno: pyRevit IronPython 2.7 (consola de Revit)
"""
import datetime
import json
import os
import sys

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    StorageType,
)
from System import Int64

VERSION = "v01"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_SecurityDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]

ZONAS = {
    "F17": {"x_min": 6500.0, "x_max": 11000.0, "y_min": 500.0, "y_max": 8800.0},
    "F18": {"x_min": 6500.0, "x_max": 11000.0, "y_min": 8800.0, "y_max": 17000.0},
}


def _raiz():
    r = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if r and os.path.exists(r):
        return r
    return DEFAULT_ROOT


def log(msg):
    print(msg)
    try:
        sys.stdout.flush()
    except Exception:
        pass


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


def id_de(el):
    v = el.Id
    if hasattr(v, "IntegerValue"):
        return int(v.IntegerValue)
    return int(v.Value)


def apto_de(x_mm, y_mm):
    for nombre in ZONAS:
        z = ZONAS[nombre]
        if z["x_min"] <= x_mm <= z["x_max"] and z["y_min"] <= y_mm <= z["y_max"]:
            return nombre
    return None


def punto_loc(loc):
    if loc is None:
        return None
    pt = None
    if isinstance(loc, LocationPoint):
        pt = loc.Point
    else:
        try:
            pt = loc.Point
        except Exception:
            pt = None
    if pt is None:
        return None
    return pt.X * FT_A_MM, pt.Y * FT_A_MM, pt.Z * FT_A_MM


def familia_tipo(el):
    fam, tip = None, None
    try:
        sym = el.Symbol
        if sym is not None:
            try:
                fam = sym.Family.Name
            except Exception:
                fam = None
            try:
                tip = sym.get_Parameter(
                    BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
            except Exception:
                tip = None
    except Exception:
        pass
    return fam, tip


def categoria_nombre(cat):
    try:
        return str(cat)
    except Exception:
        return None


def main():
    log("=" * 80)
    log("RE7_DUMP_TODAS_CATEGORIAS_%s  (SOLO LECTURA)" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    salida = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "categorias": {},
    }

    total = 0
    for cat in CATEGORIAS:
        nombre_cat = categoria_nombre(cat)
        if nombre_cat is None:
            continue
        dispositivos = []
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            try:
                xyz = punto_loc(el.Location)
                if xyz is None:
                    continue
                x_mm, y_mm, z_mm = xyz
                apto = apto_de(x_mm, y_mm)
                if apto is None:
                    continue
                fam, tip = familia_tipo(el)
                dispositivos.append({
                    "id": id_de(el),
                    "familia": fam,
                    "tipo": tip,
                    "x_mm": round(x_mm, 3),
                    "y_mm": round(y_mm, 3),
                    "z_mm": round(z_mm, 3),
                    "apto": apto,
                })
            except Exception:
                continue
        if len(dispositivos) == 0:
            continue
        total += len(dispositivos)
        salida["categorias"][nombre_cat] = dispositivos
        log("")
        log("=" * 80)
        log("CATEGORIA: %s  (%d dispositivos en F17/F18)" % (nombre_cat, len(dispositivos)))
        log("=" * 80)
        for d in sorted(dispositivos, key=lambda x: (x["apto"], x["familia"] or "", x["tipo"] or "", x["x_mm"], x["y_mm"])):
            log("  id=%-9s %-30s %-26s %s  (x=%-8.1f, y=%-8.1f, z=%-7.1f)" % (
                d["id"], d.get("familia") or "?", d.get("tipo") or "?",
                d["apto"], d["x_mm"], d["y_mm"], d["z_mm"]))

    log("")
    log("=" * 80)
    log("TOTAL dispositivos en zonas F17/F18: %d" % total)
    log("=" * 80)

    raiz = _raiz()
    ruta_json = os.path.join(raiz, "data", "f7_todas_categorias_v01.json")
    try:
        with open(ruta_json, "w") as f:
            f.write(json.dumps(salida, ensure_ascii=True, indent=2))
        log("JSON guardado: %s" % ruta_json)
    except Exception:
        log("ERROR guardando JSON:")

    log("FIN (solo lectura, modelo sin modificar)")
    log("=" * 80)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    import traceback
    traceback.print_exc()
    raise SystemExit(1)
