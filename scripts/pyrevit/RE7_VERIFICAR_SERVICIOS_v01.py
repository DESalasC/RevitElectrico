# -*- coding: utf-8 -*-
"""
RE7_VERIFICAR_SERVICIOS_v01.py

Verifica, leyendo el modelo, la red por servicios recien creada contra el
plan (data/f7_creado_servicios_F01_F02_v01.json), emparejando por conduit_id:

  * el conduit existe, con extremos a +-2 mm y diametro igual al plan
  * el parametro Servicio_Conduit tiene el valor del plan
  * reporta tramos sin conduit y conduits sin dueño en el plan

Entorno: pyRevit IronPython 2.7 (query)
"""
import datetime
import json
import math
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    LocationCurve,
)

VERSION = "v01_verificar_servicios"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
PLAN = os.path.join(DEFAULT_ROOT, "data", "f7_creado_servicios_F01_F02_v01.json")
OUT = os.path.join(DEFAULT_ROOT, "data", "f7_verificacion_servicios_v01.json")
TOL_MM = 2.0
NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size"]


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


def extremos(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            a = c.GetEndPoint(0)
            b = c.GetEndPoint(1)
            return ([round(a.X * FT_A_MM, 1), round(a.Y * FT_A_MM, 1),
                     round(a.Z * FT_A_MM, 1)],
                    [round(b.X * FT_A_MM, 1), round(b.Y * FT_A_MM, 1),
                     round(b.Z * FT_A_MM, 1)])
    except Exception:
        pass
    return (None, None)


def diametro(el):
    for objetivo in (el,):
        for n in NOMBRES_DIAM:
            try:
                p = objetivo.LookupParameter(n)
                if p is not None and p.StorageType.ToString() == "Double":
                    v = p.AsDouble() * FT_A_MM
                    if v > 0.1:
                        return round(v, 1)
            except Exception:
                pass
    return None


def servicio(el):
    try:
        p = el.LookupParameter("Servicio_Conduit")
        if p is not None and p.StorageType.ToString() == "String":
            return p.AsString()
    except Exception:
        pass
    return None


def cerca(a, b):
    return (abs(a[0] - b[0]) <= TOL_MM and abs(a[1] - b[1]) <= TOL_MM
            and abs(a[2] - b[2]) <= TOL_MM)


def verificar(tramos, modelo_por_id):
    """Empareja por conduit_id y compara extremos/diametro/servicio."""
    ok = 0
    mal_extremos = []
    mal_diam = []
    mal_servicio = []
    sin_conduit = []
    for t in tramos:
        cid = t.get("conduit_id")
        m = modelo_por_id.get(cid)
        if m is None:
            sin_conduit.append(t)
            continue
        if not ((cerca(t["a"], m["a"]) and cerca(t["b"], m["b"])) or
                (cerca(t["a"], m["b"]) and cerca(t["b"], m["a"]))):
            mal_extremos.append({"id": cid, "tipo": t["tipo"]})
        elif t.get("diam_mm") is not None and m["diam"] is not None \
                and abs(t["diam_mm"] - m["diam"]) > 0.6:
            mal_diam.append({"id": cid, "plan": t["diam_mm"],
                             "modelo": m["diam"]})
        elif (t.get("servicio") or "") != (m["servicio"] or ""):
            mal_servicio.append({"id": cid, "plan": t.get("servicio"),
                                 "modelo": m["servicio"]})
        else:
            ok += 1
    sobrantes = [cid for cid in modelo_por_id
                 if cid not in set(t.get("conduit_id") for t in tramos)]
    return {"ok": ok, "sin_conduit": sin_conduit, "mal_extremos": mal_extremos,
            "mal_diam": mal_diam, "mal_servicio": mal_servicio,
            "sobrantes": sobrantes}


def main():
    log("=" * 76)
    log("RE7_VERIFICAR_SERVICIOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    doc = obtener_doc()
    if doc is None:
        log("ERROR: sin documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    with open(PLAN) as f:
        plan = json.load(f)
    tramos = plan["tramos"]
    log("tramos en el plan: %d" % len(tramos))

    modelo = {}
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().ToElements():
        a, b = extremos(el)
        if a is None:
            continue
        modelo[id_de(el)] = {"a": a, "b": b, "diam": diametro(el),
                             "servicio": servicio(el)}
    log("conduits en el modelo: %d" % len(modelo))

    rep = verificar(tramos, modelo)
    log("")
    log("EMPAREJAMIENTO por conduit_id")
    log("  ok ................. %d / %d" % (rep["ok"], len(tramos)))
    log("  sin conduit ........ %d" % len(rep["sin_conduit"]))
    log("  extremos distintos . %d" % len(rep["mal_extremos"]))
    log("  diametro distinto .. %d" % len(rep["mal_diam"]))
    log("  servicio distinto .. %d" % len(rep["mal_servicio"]))
    log("  conduits sobrantes . %d" % len(rep["sobrantes"]))
    for e in rep["mal_servicio"][:6]:
        log("    servicio: %s" % e)
    for e in rep["mal_extremos"][:6]:
        log("    extremos: %s" % e)

    ok_total = (len(rep["sin_conduit"]) == 0 and
                len(rep["mal_extremos"]) == 0 and
                len(rep["mal_diam"]) == 0 and
                len(rep["mal_servicio"]) == 0 and
                len(rep["sobrantes"]) == 0)
    log("")
    log("VEREDICTO: %s" % ("OK" if ok_total else "REVISAR"))

    try:
        with open(OUT, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "plan": PLAN,
                "conduits_modelo": len(modelo),
                "por_servicio_modelo": sorted(
                    set((m["servicio"] or "") for m in modelo.values())),
                "resultado": rep,
                "veredicto": "OK" if ok_total else "REVISAR",
            }, ensure_ascii=True, indent=1))
        log("JSON: %s" % OUT)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)
    log("=" * 76)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
