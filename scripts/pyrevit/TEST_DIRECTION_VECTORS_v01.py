# -*- coding: utf-8 -*-
# TEST_DIRECTION_VECTORS_v01.py - Level-based con direction/normal vectors

import clr, math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, FamilySymbol, FamilyInstance,
    Transaction)
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
    # Probar NewFamilyInstance con direction + normal
    pt = XYZ(34.44, 5.03, 44.35)
    
    # Para toma en muro X=34.44 (normal hacia -X, hacia habitación)
    direction = XYZ(-1, 0, 0)  # frente hacia habitación
    normal = XYZ(0, 0, 1)      # arriba vertical -> placa horizontal
    
    t = Transaction(doc, "Test Direction Vectors"); t.Start()
    try:
        if not s.IsActive: s.Activate()
        inst = doc.Create.NewFamilyInstance(pt, s, direction, normal, StructuralType.NonStructural)
        print("SUCCESS con direction/normal!")
        print("Inst Id: {}".format(int(inst.Id.Value)))
    except Exception as e:
        print("Error: {}".format(e))
    t.Commit()