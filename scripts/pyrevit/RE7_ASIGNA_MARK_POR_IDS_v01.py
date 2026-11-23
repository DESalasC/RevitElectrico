# -*- coding: utf-8 -*-
"""
RE7_ASIGNA_MARK_POR_IDS_v01.py
Asigna el parameter Mark a una lista de ElementIds en Revit.
Entrada: JSON con {"mark": "F17", "ids": [5568808, 5568809, ...]} o {"mark": "F18", "ids": [...]}
Uso:   pyRevit console, cargar el script y pasar el JSON por argumento o editar JSON_PATH.
Escritura solo dentro de una Transaccion.
"""
import json
import sys

# =================== CONFIGURACION (editar o pasar por argumento) ===================
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marcas_por_ids_v01.json"
# Ejemplo de contenido del JSON:
# [
#   {"mark": "F17", "ids": [5568808, 5568809, 5568810]},
#   {"mark": "F18", "ids": [5568837, 5568838, 5568839]}
# ]
# ================================================================================

from Autodesk.Revit.DB import Transaction, BuiltInParameter

doc = __revit__.ActiveUIDocument.Document


def asignar_mark(element_id, valor_mark):
    """
    Asigna el parameter Mark al elemento con el ElementId dado.
    Retorna (ok, mensaje).
    """
    try:
        el = doc.GetElement(element_id)
        if el is None:
            return False, "Elemento no encontrado: %s" % element_id
        param = el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if param is None:
            param = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_MARK)
        if param is None:
            return False, "Sin parameter Mark: %s" % element_id
        if param.IsReadOnly:
            return False, "Mark de solo lectura: %s" % element_id
        param.Set(valor_mark)
        return True, "OK"
    except Exception as ex:
        return False, "Excepcion %s: %s" % (type(ex).__name__, ex)


def main():
    print("=" * 70)
    print("RE7_ASIGNA_MARK_POR_IDS_v01")
    print("=" * 70)

    try:
        with open(JSON_PATH, "r") as f:
            grupos = json.load(f)
    except Exception as ex:
        print("ERROR leyendo JSON %s: %s" % (JSON_PATH, ex))
        print("Crea el archivo JSON con la lista de grupos y sus IDs.")
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
            # Aceptar int o string
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
    print("RESUMEN: %d OK, %d FALLOS" % (total_ok, total_fail))
    print("=" * 70)


if __name__ == "__main__":
    main()
