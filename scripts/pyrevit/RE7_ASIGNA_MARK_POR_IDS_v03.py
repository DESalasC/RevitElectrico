# -*- coding: utf-8 -*-
"""
RE7_ASIGNA_MARK_POR_IDS_v03.py
Asigna el parameter Mark a una lista de ElementIds en Revit (IronPython 2.7 / pyRevit).
Entrada: JSON con [{"mark": "F17", "ids": [...]}, {"mark": "F18", "ids": [...]}]
Escritura dentro de una Transaccion de Revit.
Nota: ElementId requiere Int64 explicito en IronPython 2.7.
"""
import json
from System import Int64

from Autodesk.Revit.DB import Transaction, BuiltInParameter, ElementId

doc = __revit__.ActiveUIDocument.Document
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marcas_por_ids_v01.json"


def asignar_mark(element_id_int, valor_mark):
    try:
        el = doc.GetElement(ElementId(Int64(element_id_int)))
        if el is None:
            return False, "Elemento no encontrado: %s" % element_id_int
        param = el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if param is None:
            param = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_MARK)
        if param is None:
            return False, "Sin parameter Mark: %s" % element_id_int
        if param.IsReadOnly:
            return False, "Mark de solo lectura: %s" % element_id_int
        param.Set(valor_mark)
        return True, "OK"
    except Exception as ex:
        return False, "Excepcion %s: %s" % (type(ex).__name__, ex)


def main():
    print("=" * 70)
    print("RE7_ASIGNA_MARK_POR_IDS_v03")
    print("Documento: %s" % doc.Title)
    print("JSON: %s" % JSON_PATH)
    print("=" * 70)

    try:
        with open(JSON_PATH, "r") as f:
            grupos = json.load(f)
    except Exception as ex:
        print("ERROR leyendo JSON: %s" % ex)
        return

    total_ok = 0
    total_fail = 0

    t = Transaction(doc, "RE7 Asignar Mark por IDs")
    t.Start()
    for grupo in grupos:
        mark = grupo.get("mark", "")
        ids = grupo.get("ids", [])
        print("")
        print("Grupo %s: %d elementos" % (mark, len(ids)))
        for eid in ids:
            try:
                eid_int = int(eid)
            except Exception:
                print("  ID invalido: %s" % eid)
                total_fail += 1
                continue
            ok, msg = asignar_mark(eid_int, mark)
            if ok:
                total_ok += 1
                print("  OK  %s -> Mark=%s" % (eid_int, mark))
            else:
                total_fail += 1
                print("  FAIL %s -> %s" % (eid_int, msg))
    t.Commit()

    print("")
    print("=" * 70)
    print("RESUMEN: %d asignados OK, %d fallos" % (total_ok, total_fail))
    print("=" * 70)


main()
