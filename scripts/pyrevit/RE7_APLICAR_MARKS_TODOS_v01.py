# -*- coding: utf-8 -*-
"""
RE7_APLICAR_MARKS_TODOS_v01.py

Aplica los Marks propuestos (data/f7_marks_propuestos_todos_v02.json) a los
dispositivos del documento activo, en UNA sola transaccion, y verifica leyendo
de vuelta el parametro.

Ademas marca Comment='Cocina' a:
  * dispositivos de familia Campana
  * dispositivos a <= 1000 mm (XY) de una Campana del mismo apartamento
solo si su Comment esta vacio (no se sobrescribe nada).

Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import math
import os
import sys
import traceback
from collections import defaultdict

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    Transaction,
)
from System import Int64

VERSION = "v01_aplicar_todos"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

PROPUESTA = os.path.join(DEFAULT_ROOT, "data", "f7_marks_propuestos_todos_v02.json")
OUT_JSON = os.path.join(DEFAULT_ROOT, "data", "f7_marks_aplicados_todos_v01.json")

RADIO_COCINA_MM = 1000.0

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
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


def punto_real(el):
    loc = el.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        return [p.X * FT_A_MM, p.Y * FT_A_MM, p.Z * FT_A_MM]
    if isinstance(loc, LocationCurve):
        c = loc.Curve
        p0 = c.GetEndPoint(0)
        p1 = c.GetEndPoint(1)
        return [
            0.5 * (p0.X + p1.X) * FT_A_MM,
            0.5 * (p0.Y + p1.Y) * FT_A_MM,
            0.5 * (p0.Z + p1.Z) * FT_A_MM,
        ]
    return None


def param_escribible(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None and not p.IsReadOnly:
                return p
        except Exception:
            continue
    return None


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


def main():
    log("=" * 70)
    log("RE7_APLICAR_MARKS_TODOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    try:
        with open(PROPUESTA) as f:
            data = json.load(f)
    except Exception as ex:
        log("ERROR leyendo %s: %s" % (PROPUESTA, ex))
        return 1

    propuestas_todas = data.get("propuestas", [])
    propuestas = [q for q in propuestas_todas if q.get("aplicable", True)]
    no_aplicables = [q for q in propuestas_todas if not q.get("aplicable", True)]
    log("Propuestas totales: %d | aplicables: %d | a revisar: %d" % (
        len(propuestas_todas), len(propuestas), len(no_aplicables)))
    for q in no_aplicables:
        log("   REVISAR id=%s mark=%r motivo=%s" % (
            q["id"], q.get("mark"), q.get("motivo_no_aplicable")))

    # --- dispositivos del documento (para cocina y verificacion) ---
    disp = {}
    campanas = defaultdict(list)
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto_real(el)
            if pt is None:
                continue
            eid = id_de(el)
            fam = ""
            try:
                if el.Symbol is not None and el.Symbol.Family is not None:
                    fam = el.Symbol.Family.Name
            except Exception:
                fam = ""
            disp[eid] = {"el": el, "pt": pt, "familia": fam}
            if "campana" in (fam or "").lower():
                campanas[None].append({"id": eid, "pt": pt})

    log("Dispositivos en documento: %d | campanas: %d" % (
        len(disp), len(campanas[None])))

    ok = 0
    fallos = 0
    no_encontrados = 0
    comentarios_cocina = 0
    resultados = []
    aplicados = {}

    trans = Transaction(doc, "RE7_APLICAR_MARKS_TODOS_v01")
    trans.Start()
    try:
        for prop in propuestas:
            eid = int(prop["id"])
            info = disp.get(eid)
            if info is None:
                no_encontrados += 1
                continue
            el = info["el"]
            mark = prop["mark"]
            p = param_escribible(el, ["Mark"])
            if p is None:
                fallos += 1
                resultados.append({"id": eid, "ok": False, "error": "sin parametro Mark"})
                continue
            try:
                p.Set(mark)
                leido = None
                try:
                    leido = p.AsString()
                except Exception:
                    leido = None
                if leido == mark:
                    ok += 1
                    aplicados[eid] = mark
                    resultados.append({"id": eid, "ok": True, "mark": mark})
                else:
                    fallos += 1
                    resultados.append({
                        "id": eid, "ok": False,
                        "error": "lectura distinta: %r" % (leido,), "mark": mark,
                    })
            except Exception as ex:
                fallos += 1
                resultados.append({"id": eid, "ok": False, "error": str(ex)[:120]})

        # --- Comment = Cocina ---
        for prop in propuestas:
            eid = int(prop["id"])
            info = disp.get(eid)
            if info is None:
                continue
            el = info["el"]
            actual = valor_texto(el, ["Comments"])
            if actual:
                continue
            es_campana = "campana" in (info["familia"] or "").lower()
            cerca = False
            for c in campanas[None]:
                if math.hypot(c["pt"][0] - info["pt"][0], c["pt"][1] - info["pt"][1]) <= RADIO_COCINA_MM:
                    cerca = True
                    break
            if not (es_campana or cerca):
                continue
            pc = param_escribible(el, ["Comments"])
            if pc is None:
                continue
            try:
                pc.Set("Cocina")
                comentarios_cocina += 1
            except Exception:
                pass

        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida, no se aplico nada.")
        log(traceback.format_exc())
        return 1

    log("")
    log("=" * 70)
    log("Mark aplicado y verificado: %d" % ok)
    log("Fallos: %d | no encontrados en el documento: %d" % (fallos, no_encontrados))
    log("Comment='Cocina' asignado: %d" % comentarios_cocina)
    log("=" * 70)

    # --- verificacion global: cuantos dispositivos quedan con Mark completo ---
    con_apto = 0
    sin_apto = 0
    for eid in disp.keys():
        mk = aplicados.get(eid)
        if mk is None:
            mk = valor_texto(disp[eid]["el"], ["Mark"])
        if mk and "|" in mk:
            con_apto += 1
        else:
            sin_apto += 1
    log("Tras aplicar: %d con Mark de apartamento | %d sin Mark" % (con_apto, sin_apto))

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "propuestas": len(propuestas),
            "propuestas_totales": len(propuestas_todas),
            "no_aplicables": len(no_aplicables),
            "aplicados_ok": ok,
            "fallos": fallos,
            "no_encontrados": no_encontrados,
            "comment_cocina": comentarios_cocina,
            "con_mark_apartamento": con_apto,
            "sin_mark": sin_apto,
        },
        "resultados": resultados,
        "no_aplicables": [{"id": q["id"], "mark": q.get("mark"),
                           "motivo": q.get("motivo_no_aplicable")} for q in no_aplicables],
    }
    out_path = os.path.join(raiz, "data", "f7_marks_aplicados_todos_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=1))
        log("JSON: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0 if fallos == 0 and no_encontrados == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
