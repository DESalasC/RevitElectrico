# -*- coding: utf-8 -*-
"""
RE7_LISTAR_SIN_LOCATION_v01.py

SOLO LECTURA. Lista los dispositivos electricos que NO tienen Location
utilizable (ni LocationPoint ni LocationCurve), que son los que no se pueden
emparejar con el DXF ni rutear.

Reporta por dispositivo: id, categoria, familia, tipo, Mark, Comment, nivel,
host (si es FamilyInstance hosteada) y bbox si existe.

Salida: data/f7_sin_location_v01.json
Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import os
import sys
import traceback
from collections import defaultdict

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
)

VERSION = "v01_sin_location"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

CATEGORIAS = [
    ("ElectricalFixtures", BuiltInCategory.OST_ElectricalFixtures),
    ("LightingFixtures", BuiltInCategory.OST_LightingFixtures),
    ("DataDevices", BuiltInCategory.OST_DataDevices),
    ("TelephoneDevices", BuiltInCategory.OST_TelephoneDevices),
    ("CommunicationDevices", BuiltInCategory.OST_CommunicationDevices),
    ("MechanicalEquipment", BuiltInCategory.OST_MechanicalEquipment),
]


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


def valor_texto(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None:
                s = p.AsString()
                if s is not None:
                    return s
        except Exception:
            pass
    return None


def nombre_familia(el):
    try:
        if el.Symbol is not None and el.Symbol.Family is not None:
            return el.Symbol.Family.Name
    except Exception:
        pass
    return None


def nombre_tipo(el):
    try:
        if el.Symbol is not None:
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                return p.AsString()
    except Exception:
        pass
    return None


def nombre_nivel(el):
    try:
        lid = el.LevelId
        if lid is not None and lid.IntegerValue > 0:
            lvl = el.Document.GetElement(lid)
            if lvl is not None:
                return lvl.Name
    except Exception:
        pass
    return None


def host_id(el):
    try:
        h = el.Host
        if h is not None:
            return id_de(h)
    except Exception:
        pass
    return None


def bbox_mm(el):
    try:
        bb = el.get_BoundingBox(None)
        if bb is None:
            return None
        return {
            "min": [round(bb.Min.X * FT_A_MM, 1), round(bb.Min.Y * FT_A_MM, 1),
                    round(bb.Min.Z * FT_A_MM, 1)],
            "max": [round(bb.Max.X * FT_A_MM, 1), round(bb.Max.Y * FT_A_MM, 1),
                    round(bb.Max.Z * FT_A_MM, 1)],
        }
    except Exception:
        return None


def es_localizable(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            return True
        if isinstance(loc, LocationCurve):
            return True
    except Exception:
        pass
    return False


def main():
    log("=" * 70)
    log("RE7_LISTAR_SIN_LOCATION_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    sin_loc = []
    por_cat = defaultdict(int)
    total = 0

    for (nombre_cat, bic) in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(bic).ToElements():
            total += 1
            if es_localizable(el):
                continue
            eid = id_de(el)
            d = {
                "id": eid,
                "categoria": nombre_cat,
                "familia": nombre_familia(el),
                "tipo": nombre_tipo(el),
                "mark": valor_texto(el, ["Mark"]),
                "comment": valor_texto(el, ["Comments"]),
                "nivel": nombre_nivel(el),
                "host_id": host_id(el),
                "bbox": bbox_mm(el),
            }
            sin_loc.append(d)
            por_cat[nombre_cat] += 1

    log("Dispositivos revisados: %d" % total)
    log("Sin Location utilizable: %d" % len(sin_loc))
    log("")
    if sin_loc:
        log("%-10s %-22s %-26s %-22s %-8s %s" % (
            "ID", "CATEGORIA", "FAMILIA", "TIPO", "NIVEL", "HOST/BBOX"))
        for d in sin_loc:
            log("%-10s %-22s %-26s %-22s %-8s host=%s bb=%s" % (
                d["id"], d["categoria"], (d["familia"] or "-")[:26],
                (d["tipo"] or "-")[:22], (d["nivel"] or "-"),
                d["host_id"], "si" if d["bbox"] else "no"))
        log("")
        log("Solo IDs:")
        log(",".join(str(d["id"]) for d in sin_loc))
        log("")
        log("Por categoria: %s" % dict(por_cat))

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "revisados": total,
            "sin_location": len(sin_loc),
            "por_categoria": dict(por_cat),
        },
        "sin_location": sin_loc,
    }
    out_path = os.path.join(raiz, "data", "f7_sin_location_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=1))
        log("JSON: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    log("=" * 70)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
