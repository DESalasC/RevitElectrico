# -*- coding: utf-8 -*-
"""
RE7_ASIGNA_MARK_CONVENCION_VAULT_v01.py
Asigna el parameter Mark y Comments a dispositivos electricos de Revit
siguiendo la convencion del vault: apartamento|tablero|circuito.

Entrada: JSON con lista de {"id": <ElementId>, "mark": "<apartamento|tablero|circuito>", "comment": "<texto o null>"}
Ejemplo: [{"id": 5568808, "mark": "F17|T1-05|C1", "comment": null},
          {"id": 5568838, "mark": "F18|T1-07|C3", "comment": "Cocina"}]

Entorno: pyRevit IronPython 2.7
"""
import json
import datetime
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    Transaction,
)
from System import Int64

VERSION = "v01_conv_vault"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_conven_v01.json"


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


def asignar_mark_comment(el, valor_mark, valor_comment):
    """
    Asigna el parameter Mark y Comments al elemento.
    Retorna (ok, mensaje).
    """
    try:
        # Mark: ALL_MODEL_MARK o ALL_INSTANCE_MARK
        param_mark = el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if param_mark is None:
            param_mark = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_MARK)

        # Comments: ALL_INSTANCE_COMMENTS o ALL_MODEL_COMMENTS
        param_comment = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_COMMENTS)
        if param_comment is None:
            param_comment = el.get_Parameter(BuiltInParameter.ALL_MODEL_COMMENTS)

        if param_mark is None:
            return False, "Sin parameter Mark: %s" % id_de(el)
        if param_mark.IsReadOnly:
            return False, "Mark de solo lectura: %s" % id_de(el)

        # Asignar Mark
        param_mark.Set(valor_mark)

        # Asignar Comment si se proporciona
        if valor_comment is not None and param_comment is not None:
            if not param_comment.IsReadOnly:
                param_comment.Set(valor_comment)

        return True, "OK"
    except Exception as ex:
        return False, "Excepcion %s: %s" % (type(ex).__name__, ex)


def main():
    log("=" * 70)
    log("RE7_ASIGNA_MARK_CONVENCION_VAULT_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    log("=" * 70)

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    raiz = _raiz()
    json_path = os.path.join(raiz, "data", "f7_marks_conven_v01.json")

    try:
        with open(json_path, "r") as f:
            mapeo = json.load(f)
    except Exception as ex:
        log("ERROR leyendo JSON %s: %s" % (json_path, ex))
        log("Crea el archivo con la lista de dispositivos y sus Marks.")
        return 1

    total_ok = 0
    total_fail = 0
    total_sin_mark = 0

    t = Transaction(doc, "RE7 Asignar Mark Convenio Vault")
    t.Start()
    try:
        for item in mapeo:
            eid = item.get("id")
            mark = item.get("mark", "")
            comment = item.get("comment", None)

            if eid is None:
                total_fail += 1
                log("  FAIL: item sin 'id': %s" % item)
                continue

            try:
                eid_int = int(eid)
            except Exception:
                total_fail += 1
                log("  FAIL: id invalido: %s" % eid)
                continue

            el = doc.GetElement(ElementId(Int64(eid_int)))
            if el is None:
                total_fail += 1
                log("  FAIL: elemento no encontrado: %s" % eid_int)
                continue

            # Si no hay mark definido, saltar (no asignar vacio)
            if mark is None or mark == "":
                total_sin_mark += 1
                log("  SKIP (sin mark): %s" % eid_int)
                continue

            ok, msg = asignar_mark_comment(el, mark, comment)
            if ok:
                total_ok += 1
                log("  OK  %s -> Mark=%r Comment=%r" % (eid_int, mark, comment))
            else:
                total_fail += 1
                log("  FAIL %s -> %s" % (eid_int, msg))
        t.Commit()
    except Exception:
        t.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    log("")
    log("=" * 70)
    log("RESUMEN: %d OK, %d fallos, %d sin mark (saltados)" % (
        total_ok, total_fail, total_sin_mark))
    log("=" * 70)
    return 0 if total_fail == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
