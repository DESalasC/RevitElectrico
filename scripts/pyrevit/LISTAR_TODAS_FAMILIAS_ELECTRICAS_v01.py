# -*- coding: utf-8 -*-
# LISTAR_TODAS_FAMILIAS_ELECTRICAS_v01.py - Ver todas las familias eléctricas disponibles

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (FilteredElementCollector, FamilySymbol, BuiltInCategory,
    BuiltInParameter)

doc = __revit__.ActiveUIDocument.Document

print("=== TODAS LAS FAMILIAS ELÉCTRICAS ===\n")

count = 0
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol):
            cat = elem.Category
            if cat and cat.Id.IntegerValue == int(BuiltInCategory.OST_ElectricalFixtures):
                fam_name = elem.FamilyName
                sym_name = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
                print("{} | {}".format(fam_name, sym_name))
                count += 1
    except: pass

print("\nTotal: {} tipos".format(count))