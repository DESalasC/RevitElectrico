# -*- coding: utf-8 -*-
# BUSCAR_TODOS_M_COMUNICACIONES_v01.py - Buscar M_Comunicaciones en TODAS las categorías
# Ejecutar en pyRevit

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (FilteredElementCollector, FamilySymbol, BuiltInParameter,
    BuiltInCategory)

doc = __revit__.ActiveUIDocument.Document

# Buscar en TODAS las categorías
all_cats = [
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_MechanicalEquipment,
    BuiltInCategory.OST_FireAlarmDevices,
    BuiltInCategory.OST_LightingFixtures,
]

print("=== BUSCANDO 'M_Comunicaciones' EN TODAS LAS CATS ===")
for cat in all_cats:
    found = False
    for elem in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsElementType().ToElements():
        try:
            if isinstance(elem, FamilySymbol):
                fam = elem.FamilyName
                if "comunicac" in fam.lower():
                    p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                    typ = p.AsString() if p and p.HasValue else "SinNombre"
                    cat_name = elem.Category.Name if elem.Category else "SinCat"
                    print("  [{}] {} | {} : {}".format(cat_name, fam, typ, int(elem.Id.Value)))
                    found = True
        except: pass
    if not found:
        cat_name = doc.Settings.Categories.get_Item(cat).Name
        print("  [{}] - NO ENCONTRADO".format(cat_name))