# -*- coding: utf-8 -*-
"""
RE7_CREAR_RUTEO_F17_F18_v09_corregido.py
Ejecuta el plan v08 corregido en Revit: borra conduits existentes en F17/F18 y crea los
conduits del plan corregido (tipo TuboE = 112216), verificando extremos.

DESTRUCTIVO: borra todos los conduits de OST_Conduit cuya ubicacion caiga en
las zonas F17/F18, incluidos los creados por v09 previa.

Entrada: data/f7_plan_ruteo_f17_f18_v08_corregido.json  (plan offline corregido)
Salida:  data/f7_ruteo_ejecutado_f17_f18_v09_corregido.json  (reporte de creacion)
Entorno: pyRevit IronPython 2.7 (consola de Revit)
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
from Autodesk.Revit.DB.Electrical import Conduit
from System import Int64

VERSION = "v09_corregido"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

ZONAS = {
    "F17": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 1000.0, "y_max": 8500.0},
    "F18": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 9000.0, "y_max": 16500.0},
}

TUBO_E_ID = 112216  # tipo de conduit para luz/fuerza (hipotesis: Ø21)
LARGO_MIN_MM = 3.0
VERIF_TOL_MM = 10.0  # tolerancia de verificacion por extremo


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


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz_mm(x_mm, y_mm, z_mm):
    return XYZ(mm_a_ft(x_mm), mm_a_ft(y_mm), mm_a_ft(z_mm))


def dist3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def buscar_nivel(doc, nombre_esperado="Piso 5", elevacion_m=13.22):
    mejor = None
    mejor_delta = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        delta = abs(lvl.Elevation * FT_A_MM - elevacion_m * 1000.0)
        if mejor_delta is None or delta < mejor_delta:
            mejor = lvl
            mejor_delta = delta
        if lvl.Name == nombre_esperado:
            return lvl
    return mejor


def en_zona(x_mm, y_mm):
    return apto_de(x_mm, y_mm) is not None


def borrar_conduits_zonas(doc):
    """Borra todos los conduits cuya ubicacion este en F17 o F18."""
    ids = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        try:
            loc = el.Location
            if not isinstance(loc, LocationCurve):
                continue
            c = loc.Curve
            p0 = c.GetEndPoint(0)
            p1 = c.GetEndPoint(1)
            xm = 0.5 * (p0.X + p1.X) * FT_A_MM
            ym = 0.5 * (p0.Y + p1.Y) * FT_A_MM
            if en_zona(xm, ym):
                ids.append(id_de(el))
        except Exception:
            continue
    borrados = 0
    if ids:
        trans = Transaction(doc, "RE7_BORRAR_CONDUITS_F17_F18_v09c")
        trans.Start()
        try:
            for cid in ids:
                try:
                    el = doc.GetElement(ElementId(Int64(cid)))
                    if el is not None:
                        doc.Delete(el.Id)
                        borrados = borrados + 1
                except Exception:
                    pass
            trans.Commit()
        except Exception:
            trans.RollBack()
            raise
    log("Conduits borrados en zonas F17/F18: %d (de %d candidatos)" % (borrados, len(ids)))
    return borrados


def crear_conduits(doc, nivel_id, conduits_plan):
    """Crea conduits del plan y verifica extremos."""
    creados = []
    fallos = []
    verif_fallos = []
    trans = Transaction(doc, "RE7_CREAR_RUTEO_F17_F18_v09c")
    trans.Start()
    try:
        for c in conduits_plan:
            try:
                a = c["a"]
                b = c["b"]
                if dist3d(a, b) < LARGO_MIN_MM:
                    fallos.append({"index": c.get("index"), "error": "largo < minimo"})
                    continue
                conduit = Conduit.Create(
                    doc, ElementId(Int64(TUBO_E_ID)),
                    xyz_mm(a[0], a[1], a[2]),
                    xyz_mm(b[0], b[1], b[2]),
                    ElementId(Int64(nivel_id)))
                cid = id_de(conduit)
                # verificacion post-creacion
                loc = conduit.Location
                ok = False
                da = db = None
                ra = rb = None
                if isinstance(loc, LocationCurve):
                    curva = loc.Curve
                    ep0 = curva.GetEndPoint(0)
                    ep1 = curva.GetEndPoint(1)
                    ra = [ep0.X * FT_A_MM, ep0.Y * FT_A_MM, ep0.Z * FT_A_MM]
                    rb = [ep1.X * FT_A_MM, ep1.Y * FT_A_MM, ep1.Z * FT_A_MM]
                    da = dist3d(ra, a)
                    db = dist3d(rb, b)
                    ok = da < VERIF_TOL_MM and db < VERIF_TOL_MM
                creados.append({
                    "conduit_id": cid,
                    "apto": c.get("apto"),
                    "layer": c.get("layer"),
                    "type_id": c.get("type_id"),
                    "a_plan": [round(v, 3) for v in a],
                    "b_plan": [round(v, 3) for v in b],
                    "a_real": [round(v, 3) for v in ra] if ra else None,
                    "b_real": [round(v, 3) for v in rb] if rb else None,
                    "dist_a_mm": round(da, 3) if da is not None else None,
                    "dist_b_mm": round(db, 3) if db is not None else None,
                    "verificado": ok,
                    "largo_plan_mm": c.get("largo_mm"),
                    "segmentos_raw": c.get("segmentos_raw", 0),
                })
                if not ok:
                    verif_fallos.append(cid)
                    log("  VERIF FALLO conduit %s: dist_a=%s dist_b=%s" % (
                        cid, da, db))
            except Exception as e:
                fallos.append({"index": c.get("index"), "error": str(e)[:200]})
                log("  ERROR creando conduit: %s" % str(e)[:100])
        trans.Commit()
        log("Transaccion COMMIT: %d conduits creados, %d fallos, %d verificacion FALLO." % (
            len(creados), len(fallos), len(verif_fallos)))
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return [], fallos, verif_fallos
    return creados, fallos, verif_fallos


def main():
    log("=" * 66)
    log("RE7_CREAR_RUTEO_F17_F18_%s  (EJECUCION EN REVIT)" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    titulo = doc.Title
    if "V02-f" in titulo:
        log("ERROR: documento prohibido: %r" % titulo)
        return 1
    log("documento=%r" % titulo)

    nivel = buscar_nivel(doc)
    if nivel is None:
        log("ERROR: no se encontro nivel Piso 5.")
        return 1
    elev_mm = int(float(nivel.Elevation) * FT_A_MM)
    log("nivel: {!r} id={} elevacion={} mm".format(nivel.Name, id_de(nivel), elev_mm))

    # --- paso 1: borrar conduits existentes en zonas F17/F18 ---
    borrados = borrar_conduits_zonas(doc)

    # --- paso 2: cargar plan corregido y crear conduits ---
    raiz = _raiz()
    plan_path = os.path.join(raiz, "data", "f7_plan_ruteo_f17_f18_v08_corregido.json")
    with open(plan_path) as f:
        plan = json.load(f)

    conduits_plan = []
    for apto in ["F17", "F18"]:
        for c in plan["apartamentos"][apto]["conduits"]:
            conduits_plan.append(c)
            c["apto"] = apto
    log("Conduits en plan corregido: %d" % len(conduits_plan))

    creados, fallos, verif_fallos = crear_conduits(doc, id_de(nivel), conduits_plan)

    # --- reporte ---
    verif_ok = sum(1 for c in creados if c["verificado"])
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "nivel": {"id": id_de(nivel), "nombre": nivel.Name,
                  "elevacion_mm": round(float(nivel.Elevation) * FT_A_MM, 3)},
        "tipo_conduit": {"id": TUBO_E_ID, "nombre": "TuboE (hipotesis Ø21)"},
        "borrados_zonas_f17_f18": borrados,
        "plan_total": len(conduits_plan),
        "resumen": {
            "creados": len(creados),
            "fallos_creacion": len(fallos),
            "verificados_ok": verif_ok,
            "verificados_fallo": len(creados) - verif_ok,
        },
        "creados": creados,
        "fallos": fallos,
    }
    ruta_out = os.path.join(raiz, "data", "f7_ruteo_ejecutado_f17_f18_v09_corregido.json")
    try:
        with open(ruta_out, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=2))
        log("REPORTE guardado: %s" % ruta_out)
    except Exception:
        log("ERROR escribiendo reporte:")
        log(traceback.format_exc())

    log("RESULTADO: %d borrados, %d creados, %d verificados OK, %d fallos verificacion." % (
        borrados, len(creados), verif_ok, len(creados) - verif_ok))
    log("FIN")
    log("=" * 66)
    return 0 if len(fallos) == 0 and len(creados) - verif_ok == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
