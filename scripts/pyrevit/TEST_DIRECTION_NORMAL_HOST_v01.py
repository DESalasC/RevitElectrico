# -*- coding: utf-8 -*-
# TEST_DIRECTION_NORMAL_HOST_v01.py - NewFamilyInstance(XYZ, Symbol, Element host, direction, normal, StructuralType) - 6 args
# Ejecutar en pyRevit

import clr, math
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
    if not wall:
        print("Muro no encontrado")
    else:
        pt = XYZ(34.44, 5.03, 44.35)
        direction = XYZ(-1, 0, 0)
        normal = XYZ(0, 0, 1)
        
        t = Transaction(doc, "Test Direction/Normal Host"); t.Start()
        try:
            if not s.IsActive: s.Activate()
            # 6 args: pt, symbol, host, direction, normal, structuralType
            inst = doc.Create.NewFamilyInstance(pt, s, wall, direction, normal, StructuralType.NonStructural)
            print("SUCCESS 6 args con host!")
            print("Inst Id: {}".format(int(inst.Id.Value)))
        except Exception as e:
            print("Error: {}".format(e))
        t.Commit()