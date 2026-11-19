# -*- coding: utf-8 -*-
# LISTAR_TODOS_SIMBOLOS_v01.py - Listar todos los FamilySymbol del proyecto

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (FilteredElementCollector, FamilySymbol, BuiltInParameter)

doc = __revit__.ActiveUIDocument.Document

print("=== TODOS LOS FAMILY SYMBOLS ===\n")

count = 0
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol):
            fam_name = elem.FamilyName
            sym_name = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
            cat = elem.Category
            cat_name = cat.Name if cat else "Sin categoría"
            print("{} | {} | {}".format(cat_name, fam_name, sym_name))
            count += 1
    except: pass

print("\nTotal: {} tipos".format(count))