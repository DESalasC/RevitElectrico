# -*- coding: utf-8 -*-
"""
RE7_VERIFICAR_RED_v01.py

Verifica, leyendo el modelo, la red de conduits recien creada:

  * numero de conduits por tipo/diametro (lee el parametro real)
  * empareja cada tramo del plan (data/f7_creado_ruteo_<APTOS>_v09.json)
    con un conduit del modelo por sus extremos (tolerancia 2 mm)
  * reporta tramos del plan sin conduit, conduits fuera de plan y diferencias
  * rango Z y longitudes

Entorno: pyRevit IronPython 2.7. Uso: pyrevit agent run ... --mode=query
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

VERSION = "v01_verificar_red"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
TOL_MM = 2.0
NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size", "Diametro"]

PLAN = os.path.join(DEFAULT_ROOT, "data", "f7_creado_ruteo_F01_F02_v09.json")
OUT = os.path.join(DEFAULT_ROOT, "data", "f7_verificacion_red_v01.json")


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
            return ([a.X * FT_A_MM, a.Y * FT_A_MM, a.Z * FT_A_MM],
                    [b.X * FT_A_MM, b.Y * FT_A_MM, b.Z * FT_A_MM])
    except Exception:
        pass
    return (None, None)


def diametro(el):
    """Diametro en mm: primero en la instancia, luego en el tipo."""
    for fuente in ("instancia", "tipo"):
        objetivo = el
        if fuente == "tipo":
            try:
                objetivo = el.Document.GetElement(el.GetTypeId())
            except Exception:
                objetivo = None
        if objetivo is None:
            continue
        for n in NOMBRES_DIAM:
            try:
                p = objetivo.LookupParameter(n)
                if p is not None and p.StorageType.ToString() == "Double":
                    v = p.AsDouble() * FT_A_MM
                    if v > 0.1:
                        return round(v, 1), "%s:%s" % (fuente, n)
            except Exception:
                pass
    # ultimo recurso: cualquier parametro double con "diam" en el nombre
    try:
        for p in el.Parameters:
            try:
                nom = p.Definition.Name
            except Exception:
                continue
            if "diam" in (nom or "").lower() and p.StorageType.ToString() == "Double":
                v = p.AsDouble() * FT_A_MM
                if v > 0.1:
                    return round(v, 1), "instancia:%s" % nom
    except Exception:
        pass
    return None, None


def cargar_plan():
    with open(PLAN) as f:
        return json.load(f)


def cerca(a, b):
    return (abs(a[0] - b[0]) <= TOL_MM and abs(a[1] - b[1]) <= TOL_MM
            and abs(a[2] - b[2]) <= TOL_MM)


def main():
    log("=" * 76)
    log("RE7_VERIFICAR_RED_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    conductos = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().ToElements():
        a, b = extremos(el)
        if a is None:
            continue
        d, fuente = diametro(el)
        conductos.append({"id": id_de(el), "a": a, "b": b,
                          "diam_mm": d, "fuente_diam": fuente})
    log("conduits en el modelo: %d" % len(conductos))

    por_diam = {}
    sin_diam = 0
    for c in conductos:
        if c["diam_mm"] is None:
            sin_diam += 1
        else:
            k = str(c["diam_mm"])
            por_diam[k] = por_diam.get(k, 0) + 1
    log("por diametro: %s | sin diametro legible: %d" % (por_diam, sin_diam))
    fuentes = {}
    for c in conductos:
        fuentes[c["fuente_diam"]] = fuentes.get(c["fuente_diam"], 0) + 1
    log("fuente del diametro: %s" % fuentes)

    zs = [min(c["a"][2], c["b"][2]) for c in conductos] or [0]
    zt = [max(c["a"][2], c["b"][2]) for c in conductos] or [0]
    log("Z: min=%.0f mm max=%.0f mm" % (min(zs), max(zt)))
    largos = [math.sqrt(sum((c["b"][i] - c["a"][i]) ** 2 for i in range(3)))
              for c in conductos]
    log("longitud total: %.2f m | tramo medio %.2f m | minimo %.1f mm" % (
        sum(largos) / 1000.0, sum(largos) / len(largos) / 1000.0, min(largos)))

    plan = cargar_plan()
    tramos = plan["tramos"]
    log("tramos en el plan: %d" % len(tramos))

    usados = set()
    emparejados = []
    sin_conduit = []
    for t in tramos:
        pa = [float(v) for v in t["a"]]
        pb = [float(v) for v in t["b"]]
        hallado = None
        for i in range(len(conductos)):
            if i in usados:
                continue
            c = conductos[i]
            if ((cerca(pa, c["a"]) and cerca(pb, c["b"])) or
                    (cerca(pa, c["b"]) and cerca(pb, c["a"]))):
                hallado = i
                break
        if hallado is None:
            sin_conduit.append(t)
        else:
            usados.add(hallado)
            c = conductos[hallado]
            emparejados.append({"tipo": t["tipo"], "plan_id": t.get("conduit_id"),
                                "modelo_id": c["id"], "diam_plan": t.get("diam_mm"),
                                "diam_modelo": c["diam_mm"]})

    sobrantes = [conductos[i] for i in range(len(conductos)) if i not in usados]
    mal_diam = [e for e in emparejados
                if e["diam_plan"] is not None and e["diam_modelo"] is not None
                and abs(e["diam_plan"] - e["diam_modelo"]) > 0.6]

    log("")
    log("EMPAREJAMIENTO plan <-> modelo")
    log("  emparejados .......... %d / %d" % (len(emparejados), len(tramos)))
    log("  del plan sin conduit . %d" % len(sin_conduit))
    log("  conduits fuera de plan %d" % len(sobrantes))
    log("  diametro distinto .... %d" % len(mal_diam))
    for t in sin_conduit[:8]:
        log("    sin conduit: %s %s -> %s" % (t["tipo"], t["a"], t["b"]))
    for e in mal_diam[:8]:
        log("    diam: %s plan=%s modelo=%s" % (e["tipo"], e["diam_plan"], e["diam_modelo"]))

    ok = (len(sin_conduit) == 0 and len(sobrantes) == 0 and len(mal_diam) == 0)
    log("")
    log("VEREDICTO: %s" % ("OK" if ok else "REVISAR"))

    try:
        with open(OUT, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "conduits_modelo": len(conductos),
                "por_diametro": por_diam,
                "sin_diametro_legible": sin_diam,
                "z_min_mm": round(min(zs), 1), "z_max_mm": round(max(zt), 1),
                "longitud_total_m": round(sum(largos) / 1000.0, 2),
                "plan": PLAN,
                "tramos_plan": len(tramos),
                "emparejados": len(emparejados),
                "sin_conduit": len(sin_conduit),
                "fuera_de_plan": len(sobrantes),
                "diametro_distinto": len(mal_diam),
                "detalle_diametro_distinto": mal_diam,
                "veredicto": "OK" if ok else "REVISAR",
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
