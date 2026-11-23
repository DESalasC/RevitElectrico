# -*- coding: utf-8 -*-
"""
RE7_BORRAR_EXTRACTORES_ORIGEN_v01.py

Borra los 16 extractores EA 1010 apilados en el origen (125, 0), en UNA
transaccion, con verificacion previa por dispositivo:

  * la posicion debe ser |x - 125| <= 60 mm y |y - 0| <= 60 mm
  * el tipo (SYMBOL_NAME_PARAM) debe ser 'EA 1010'
  * (informativo) categoria, familia, Mark y Comment se reportan

Si un ID no cumple, NO se borra y se informa. Asi el script no puede
llevarse por delante otro elemento por un ID equivocado.

Entorno: pyRevit IronPython 2.7
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
    BuiltInParameter,
    ElementId,
    LocationCurve,
    LocationPoint,
    Transaction,
)
from System import Int64

VERSION = "v01_borrar_ea_origen"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

IDS_EA = [
    5551691, 5551725, 5552287, 5552323, 5552359, 5552395, 5552804, 5552840,
    5552876, 5552942, 5553931, 5553963, 5553993, 5554039, 5557263, 5557331,
]

X_OBJETIVO_MM = 125.0
Y_OBJETIVO_MM = 0.0
TOL_MM = 60.0
TIPO_ESPERADO = "EA 1010"


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
    try:
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


def nombre_familia(el):
    try:
        if el.Symbol is not None and el.Symbol.Family is not None:
            return el.Symbol.Family.Name
    except Exception:
        pass
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
    log("RE7_BORRAR_EXTRACTORES_ORIGEN_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    a_borrar = []
    omitidos = []
    no_existen = []

    for eid in IDS_EA:
        el = doc.GetElement(ElementId(Int64(eid)))
        if el is None:
            no_existen.append(eid)
            log("  NO EXISTE id=%s" % eid)
            continue
        pt = punto_real(el)
        tipo = nombre_tipo(el)
        fam = nombre_familia(el)
        cat = el.Category.Name if el.Category is not None else "?"
        if pt is None:
            omitidos.append({"id": eid, "motivo": "sin Location"})
            log("  OMITIDO id=%s: sin Location" % eid)
            continue
        dx = abs(pt[0] - X_OBJETIVO_MM)
        dy = abs(pt[1] - Y_OBJETIVO_MM)
        if dx > TOL_MM or dy > TOL_MM:
            omitidos.append({
                "id": eid, "motivo": "fuera de (125,0)",
                "x": round(pt[0], 1), "y": round(pt[1], 1),
            })
            log("  OMITIDO id=%s: posicion (%.1f,%.1f) fuera de tolerancia" % (
                eid, pt[0], pt[1]))
            continue
        if (tipo or "").strip().upper() != TIPO_ESPERADO:
            omitidos.append({
                "id": eid, "motivo": "tipo distinto",
                "tipo": tipo, "familia": fam, "categoria": cat,
            })
            log("  OMITIDO id=%s: tipo=%r (esperado %r)" % (eid, tipo, TIPO_ESPERADO))
            continue
        a_borrar.append({
            "id": eid, "x": round(pt[0], 1), "y": round(pt[1], 1), "z": round(pt[2], 1),
            "familia": fam, "tipo": tipo, "categoria": cat,
            "mark": valor_texto(el, ["Mark"]),
            "comment": valor_texto(el, ["Comments"]),
        })

    log("")
    log("Verificados para borrar: %d | omitidos: %d | inexistentes: %d" % (
        len(a_borrar), len(omitidos), len(no_existen)))
    for a in a_borrar:
        log("   BORRAR id=%s [%s | %s] (%.1f,%.1f,%.1f)" % (
            a["id"], a["categoria"], a["tipo"], a["x"], a["y"], a["z"]))

    if not a_borrar:
        log("Nada que borrar.")
        return 1

    borrados = 0
    fallos = []
    trans = Transaction(doc, "RE7_BORRAR_EXTRACTORES_ORIGEN_v01")
    trans.Start()
    try:
        for a in a_borrar:
            try:
                el = doc.GetElement(ElementId(Int64(a["id"])))
                if el is None:
                    fallos.append({"id": a["id"], "error": "desaparecio"})
                    continue
                doc.Delete(el.Id)
                borrados += 1
            except Exception as ex:
                fallos.append({"id": a["id"], "error": str(ex)[:150]})
        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida, no se borro nada.")
        log(traceback.format_exc())
        return 1

    # verificacion: que ya no existan
    quedan = [a["id"] for a in a_borrar
              if doc.GetElement(ElementId(Int64(a["id"]))) is not None]

    log("")
    log("=" * 70)
    log("Borrados: %d | fallos: %d | aun existen: %d" % (
        borrados, len(fallos), len(quedan)))
    for f in fallos:
        log("   FALLO id=%s: %s" % (f["id"], f["error"]))
    if quedan:
        log("   SIGUEN EXISTIENDO: %s" % quedan)
    log("=" * 70)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "objetivo": {"x": X_OBJETIVO_MM, "y": Y_OBJETIVO_MM, "tol_mm": TOL_MM,
                     "tipo": TIPO_ESPERADO},
        "resumen": {
            "ids_solicitados": len(IDS_EA),
            "verificados": len(a_borrar),
            "borrados": borrados,
            "fallos": len(fallos),
            "aun_existen": len(quedan),
            "omitidos": len(omitidos),
            "no_existen": len(no_existen),
        },
        "borrados": a_borrar,
        "omitidos": omitidos,
        "no_existen": no_existen,
        "fallos": fallos,
    }
    out_path = os.path.join(raiz, "data", "f7_borrar_ea_origen_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=1))
        log("JSON: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0 if (borrados == len(a_borrar) and not quedan) else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
