# -*- coding: utf-8 -*-
# BUSCAR_TELEPHONE_DEVICES_v01.py - Buscar SÓLO en Telephone Devices
# Ejecutar en pyRevit

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (FilteredElementCollector, FamilySymbol, BuiltInParameter,
    BuiltInCategory)

doc = __revit__.ActiveUIDocument.Document

cat = BuiltInCategory.OST_CommunicationDevices

print("=== TELEPHONE DEVICES (OST_CommunicationDevices) ===")
for elem in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol):
            fam = elem.FamilyName
            p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            typ = p.AsString() if p and p.HasValue else "SinNombre"
            print("  {} | {} : {}".format(fam, typ, int(elem.Id.Value)))
    except: pass