# -*- coding: utf-8 -*-
# BUSCAR_TODAS_FAMILIAS_TODAS_CATS_v01.py - Buscar TODAS las familias en TODAS las categorías
# Ejecutar en pyRevit

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (FilteredElementCollector, FamilySymbol, BuiltInParameter,
    BuiltInCategory)

doc = __revit__.ActiveUIDocument.Document

# TODAS las BuiltInCategory relacionadas con eléctrico/comunicaciones
all_cats = [
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_MechanicalEquipment,
    BuiltInCategory.OST_FireAlarmDevices,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_TelephoneDevices,  # Por si existe
]

print("=== BUSCANDO 'Comunicaciones' o 'Datos' o 'Telefono' EN TODAS ===")
for cat in all_cats:
    found_any = False
    for elem in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsElementType().ToElements():
        try:
            if isinstance(elem, FamilySymbol):
                fam = elem.FamilyName
                p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                typ = p.AsString() if p and p.HasValue else "SinNombre"
                if ("comunicac" in fam.lower() or 
                    "datos" in typ.lower() or 
                    "telefon" in typ.lower() or
                    "telefon" in fam.lower()):
                    cat_name = doc.Settings.Categories.get_Item(cat).Name
                    print("  [{}] {} | {} : {}".format(cat_name, fam, typ, int(elem.Id.Value)))
                    found_any = True
        except: pass
    if not found_any:
        cat_name = doc.Settings.Categories.get_Item(cat).Name
        print("  [{}] - SIN COINCIDENCIAS".format(cat_name))

# También listar TODAS las categorías disponibles
print("\n=== TODAS LAS CATS CON ELEMENTOS TIPO ===")
for cat_id in BuiltInCategory.GetValues(BuiltInCategory):
    try:
        cat = doc.Settings.Categories.get_Item(cat_id)
        if cat:
            count = FilteredElementCollector(doc).OfCategory(cat_id).WhereElementIsElementType().ToElements().Count
            if count > 0:
                print("  {} ({}) : {} tipos".format(cat.Name, cat_id, count))
    except: pass