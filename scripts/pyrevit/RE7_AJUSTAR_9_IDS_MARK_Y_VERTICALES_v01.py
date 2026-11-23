# -*- coding: utf-8 -*-
"""
RE7_AJUSTAR_9_IDS_MARK_Y_VERTICALES_v01.py
Asigna Marks a 9 ElementIds específicos y crea conduits verticales
desde cada uno hasta plenum Z=15930.

Entrada: data/f7_marks_ajuste_9_ids_v01.json
Entorno: pyRevit IronPython 2.7
"""
import json
import math
import os
import sys
import datetime
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
    LocationPoint,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit
from System import Int64

VERSION = "v01_ajuste_9_ids"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_ajuste_9_ids_v01.json"

Z_PLENUM_MM = 15930.0
OFFSET_COMMS_MM = 40.0
VERIF_TOL_MM = 10.0
LARGO_MIN_MM = 3.0

TUBO_E_ID = 112216


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


def dist3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def mm_a_ft(mm):
    return mm / 304.8


def xyz_mm(x_mm, y_mm, z_mm):
    return XYZ(mm_a_ft(x_mm), mm_a_ft(y_mm), mm_a_ft(z_mm))


def punto_real(el):
    loc = el.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        return [p.X * 304.8, p.Y * 304.8, p.Z * 304.8]
    return None


def obtener_parametro(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None and not p.IsReadOnly:
                return p
        except Exception:
            continue
    return None


def obtener_valor_parametro(el, nombres):
    p = obtener_parametro(el, nombres)
    if p is not None:
        try:
            return p.AsString()
        except Exception:
            pass
    return None


def familia_tipo(el):
    try:
        sym = el.Symbol
        if sym is not None:
            from Autodesk.Revit.DB import BuiltInParameter
            pname = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if pname is not None:
                nom = pname.AsString()
            else:
                nom = str(sym.Id)
            return "%s" % nom
    except Exception:
        pass
    return el.Category.Name


def cargar_json(path):
    with open(path, "r") as f:
        return json.load(f)


def existe_conduit_en_posicion(doc, x_mm, y_mm, z_mm):
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        try:
            loc = el.Location
            if not isinstance(loc, LocationCurve):
                continue
            c = loc.Curve
            for i in (0, 1):
                p = c.GetEndPoint(i)
                px = p.X * 304.8
                py = p.Y * 304.8
                pz = p.Z * 304.8
                if abs(px - x_mm) < 5.0 and abs(py - y_mm) < 5.0 and abs(pz - z_mm) < 5.0:
                    return True
        except Exception:
            continue
    return False


def crear_conduit(doc, nivel_id, a, b, etiqueta):
    if dist3d(a, b) < LARGO_MIN_MM:
        log("  SKIP %s: largo muy corto (%.1f mm)" % (etiqueta, dist3d(a, b)))
        return False, None
    try:
        conduit = Conduit.Create(
            doc, ElementId(Int64(TUBO_E_ID)),
            xyz_mm(a[0], a[1], a[2]),
            xyz_mm(b[0], b[1], b[2]),
            ElementId(Int64(nivel_id)))
        cid = id_de(conduit)
        loc = conduit.Location
        ok = False
        if isinstance(loc, LocationCurve):
            curva = loc.Curve
            ep0 = curva.GetEndPoint(0)
            ep1 = curva.GetEndPoint(1)
            ra = [ep0.X * 304.8, ep0.Y * 304.8, ep0.Z * 304.8]
            rb = [ep1.X * 304.8, ep1.Y * 304.8, ep1.Z * 304.8]
            da = dist3d(ra, a)
            db = dist3d(rb, b)
            ok = da < VERIF_TOL_MM and db < VERIF_TOL_MM
            if not ok:
                log("  VERIF FALLO %s: dist_a=%.1f dist_b=%.1f" % (etiqueta, da, db))
        return True, cid
    except Exception as e:
        log("  ERROR creando %s: %s" % (etiqueta, str(e)[:150]))
        return False, None


def main():
    log("=" * 70)
    log("RE7_AJUSTAR_9_IDS_MARK_Y_VERTICALES_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    log("=" * 70)

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    nivel = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if lvl.Name == "Piso 5":
            nivel = lvl
            break
    if nivel is None:
        log("ERROR: no se encontro nivel Piso 5.")
        return 1
    log("nivel: {!r} id={}".format(nivel.Name, id_de(nivel)))

    # 1. Cargar JSON de ajuste
    raiz = _raiz()
    try:
        ajuste = cargar_json(JSON_PATH)
    except Exception as ex:
        log("ERROR cargando JSON: %s" % ex)
        return 1
    log("IDs en JSON: %d" % len(ajuste))

    # 2. Asignar Marks en Revit
    ok_mark = 0
    fail_mark = 0

    t1 = Transaction(doc, "RE7_AJUSTAR_9_IDS_Mark")
    t1.Start()
    try:
        for item in ajuste:
            eid = item["id"]
            mark = item["mark"]
            comment = item.get("comment")

            el = doc.GetElement(ElementId(Int64(eid)))
            if el is None:
                fail_mark += 1
                log("  FAIL id=%s: elemento no encontrado" % eid)
                continue

            pt = punto_real(el)
            if pt is None:
                fail_mark += 1
                log("  FAIL id=%s: sin Location.Point" % eid)
                continue

            p_mark = obtener_parametro(el, ["Mark"])
            if p_mark is None:
                fail_mark += 1
                log("  FAIL id=%s: sin parameter Mark" % eid)
                continue
            p_mark.Set(mark)

            if comment is not None:
                p_com = obtener_parametro(el, ["Comments"])
                if p_com is not None:
                    p_com.Set(comment)

            ok_mark += 1
            log("  OK id=%s -> Mark=%r (%.1f,%.1f,%.1f)" % (
                eid, mark, pt[0], pt[1], pt[2]))
        t1.Commit()
    except Exception:
        t1.RollBack()
        log("ERROR: transaccion de Mark revertida.")
        traceback.print_exc()
        return 1

    # 3. Crear verticales para estos 9 dispositivos
    creados = 0
    fallos = 0
    saltados = 0

    t2 = Transaction(doc, "RE7_AJUSTAR_9_IDS_Verticales")
    t2.Start()
    try:
        for item in ajuste:
            eid = item["id"]
            el = doc.GetElement(ElementId(Int64(eid)))
            if el is None:
                continue

            pt = punto_real(el)
            if pt is None:
                continue

            x, y, z = pt
            familia = familia_tipo(el)
            etiqueta = "ajuste %s (%.1f,%.1f,%.1f)->plenum" % (item["mark"], x, y, z)

            if abs(z - Z_PLENUM_MM) < 5.0:
                saltados += 1
                log("  SKIP %s: ya en plenum" % etiqueta)
                continue

            if existe_conduit_en_posicion(doc, x, y, z):
                saltados += 1
                log("  SKIP %s: conduit ya existe" % etiqueta)
                continue

            b = [x, y, Z_PLENUM_MM]

            es_comms = "Comunicaciones" in familia or "Datos" in familia
            if es_comms:
                ok1, cid1 = crear_conduit(doc, id_de(nivel),
                                          [x, y - OFFSET_COMMS_MM / 2.0, z],
                                          [x, y - OFFSET_COMMS_MM / 2.0, Z_PLENUM_MM],
                                          etiqueta + " comms-1")
                ok2, cid2 = crear_conduit(doc, id_de(nivel),
                                          [x, y + OFFSET_COMMS_MM / 2.0, z],
                                          [x, y + OFFSET_COMMS_MM / 2.0, Z_PLENUM_MM],
                                          etiqueta + " comms-2")
                if ok1 or ok2:
                    creados += 1
                else:
                    fallos += 1
            else:
                ok, cid = crear_conduit(doc, id_de(nivel), [x, y, z], b, etiqueta)
                if ok:
                    creados += 1
                else:
                    fallos += 1
        t2.Commit()
    except Exception:
        t2.RollBack()
        log("ERROR: transaccion de verticales revertida.")
        traceback.print_exc()
        return 1

    log("")
    log("=" * 70)
    log("RESULTADO: Marks OK=%d, fallos=%d | Verticales creados=%d, fallos=%d, saltados=%d" % (
        ok_mark, fail_mark, creados, fallos, saltados))
    log("=" * 70)
    return 0 if fail_mark == 0 and fallos == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
