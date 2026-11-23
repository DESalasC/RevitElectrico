# -*- coding: utf-8 -*-
"""
RE7_BORRAR_CONDUITS_RESIDUALES_v01.py

Borra los conduits (y sus accesorios) que quedaron de corridas anteriores,
dejando la red vacia antes de rutear.

Seguridad:
  * Exige inputs = {"confirmar": true}; sin eso no toca nada.
  * Exporta la lista completa ANTES de borrar (id, categoria, extremos en mm).
  * GUARD DE GRUPOS: omite cualquier elemento con GroupId valido (> 0).
    Borrar un miembro de grupo lo quita de la definicion y de todas las
    instancias colocadas (incidente 2026-11-22).
  * Una sola transaccion nombrada; no toca ninguna otra categoria.

Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    LocationCurve,
    Transaction,
)

VERSION = "v01_borrar_conduits_residuales"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

CATEGORIAS = [
    ("conduit", BuiltInCategory.OST_Conduit),
    ("conduit_fitting", BuiltInCategory.OST_ConduitFitting),
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


def id_num(v):
    """Numero entero de un ElementId (Revit 2024+ usa Value)."""
    try:
        if hasattr(v, "IntegerValue"):
            return int(v.IntegerValue)
        if hasattr(v, "Value"):
            return int(v.Value)
    except Exception:
        pass
    return None


def group_id_de(el):
    try:
        n = id_num(el.GroupId)
        return -1 if n is None else n
    except Exception:
        return -1


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


def leer_inputs():
    try:
        g = globals().get("inputs")
        if isinstance(g, dict):
            return g
    except Exception:
        pass
    return {}


def recolectar(doc, cat):
    out = []
    for el in FilteredElementCollector(doc).OfCategory(cat) \
            .WhereElementIsNotElementType().ToElements():
        a, b = extremos(el)
        tipo_id = None
        try:
            tipo_id = id_num(el.GetTypeId())
        except Exception:
            pass
        out.append({"id": id_de(el), "categoria": str(cat),
                    "grupo": group_id_de(el),
                    "a": a, "b": b,
                    "tipo_id": tipo_id})
    return out


def main():
    log("=" * 74)
    log("RE7_BORRAR_CONDUITS_RESIDUALES_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)
    if "STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01c" not in doc.Title:
        log("ABORTADO: el documento activo no es el de trabajo "
            "(CENTRAL-V01c). No se toca %r." % doc.Title)
        return 1

    inp = leer_inputs()
    if not inp.get("confirmar"):
        log("ABORTADO: falta inputs={'confirmar': true}.")
        return 1

    inventario = []
    for nombre, cat in CATEGORIAS:
        items = recolectar(doc, cat)
        log("  %-16s %d" % (nombre, len(items)))
        inventario.extend(items)

    reservados = [q for q in inventario if q["grupo"] is not None and q["grupo"] > 0]
    borrables = [q for q in inventario if not (q["grupo"] is not None and q["grupo"] > 0)]
    log("grupo valido (no se tocan): %d" % len(reservados))
    log("a borrar: %d" % len(borrables))

    out = os.path.join(DEFAULT_ROOT, "data", "f7_conduits_residuales_v01.json")
    try:
        with open(out, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "inventario": inventario,
                "reservados_por_grupo": reservados,
            }, ensure_ascii=True, indent=1))
        log("inventario exportado: %s" % out)
    except Exception as ex:
        log("ERROR exportando inventario (no se borra nada): %s" % ex)
        return 1

    borrados = []
    fallos = []
    trans = Transaction(doc, "RE7_BORRAR_CONDUITS_RESIDUALES_v01")
    trans.Start()
    try:
        for q in borrables:
            try:
                doc.Delete(_id(q["id"]))
                borrados.append(q["id"])
            except Exception as ex:
                fallos.append({"id": q["id"], "err": str(ex)[:110]})
        trans.Commit()
        log("transaccion COMMIT")
    except Exception:
        try:
            trans.RollBack()
        except Exception:
            pass
        log("ERROR: transaccion revertida")
        log(traceback.format_exc())
        return 1

    restantes = 0
    for nombre, cat in CATEGORIAS:
        restantes += int(FilteredElementCollector(doc).OfCategory(cat)
                         .WhereElementIsNotElementType().GetElementCount())
    log("")
    log("RESULTADO: borrados=%d | fallos=%d | quedan en el documento=%d" % (
        len(borrados), len(fallos), restantes))
    for f in fallos[:8]:
        log("   %s" % f)

    try:
        with open(out, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "inventario": inventario,
                "reservados_por_grupo": reservados,
                "borrados": borrados,
                "fallos": fallos,
                "restantes": restantes,
            }, ensure_ascii=True, indent=1))
    except Exception as ex:
        log("ERROR guardando JSON final: %s" % ex)
    log("=" * 74)
    return 0


def _id(v):
    """ElementId compatible con Revit 2024+ (Value) y anteriores (IntegerValue)."""
    try:
        from Autodesk.Revit.DB import ElementId
        try:
            from System import Int64
            return ElementId(Int64(v))
        except Exception:
            return ElementId(v)
    except Exception:
        return v


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
