# -*- coding: utf-8 -*-
# TEST_SIMPLE_PLACEMENT_v01.py - Ver qué overloads acepta

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, FamilySymbol, FamilyInstance,
    Transaction, Wall)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

doc = __revit__.ActiveUIDocument.Document

# Buscar símbolo M_Toma doble
s = None
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol) and "M_Toma doble" in elem.FamilyName:
            s = elem
            break
    except: pass

if not s:
    print("Símbolo no encontrado")
else:
    wall = doc.GetElement(ElementId(Int64(5349586)))
    pt = XYZ(34.44, 5.03, 44.35)
    
    t = Transaction(doc, "Test Simple"); t.Start()
    try:
        if not s.IsActive: s.Activate()
        # Overload más simple: (XYZ, FamilySymbol, Element host, StructuralType)
        inst = doc.Create.NewFamilyInstance(pt, s, wall, StructuralType.NonStructural)
        print("SUCCESS simple con host!")
        print("Inst Id: {}".format(int(inst.Id.Value)))
    except Exception as e:
        print("Error simple: {}".format(e))
    t.Commit()