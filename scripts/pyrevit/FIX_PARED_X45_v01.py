# -*- coding: utf-8 -*-
# Aplicar rotación 240° a todos los outlets en pared X≈45.39
# Ejecutar en pyRevit

import clr, math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (ElementId, BuiltInCategory, FilteredElementCollector,
                                ElementTransformUtils, Line, XYZ)
from System import Int64

doc = __revit__.ActiveUIDocument.Document

# Buscar TODAS las tomas del modelo (M_Toma doble)
tomas = []
for el in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalFixtures).WhereElementIsNotElementType().ToElements():
    try:
        fam = el.Symbol.FamilyName
        if "M_Toma doble" in fam and el.Location:
            pt = el.Location.Point if hasattr(el.Location, 'Point') else el.Location.Curve.Evaluate(0.5, True)
            if abs(pt.X - 45.39) < 0.5:  # misma pared X≈45.39
                tomas.append((el.Id, pt))
    except: pass

print("Tomas en pared X≈45.39: {}".format(len(tomas)))
for eid, pt in tomas:
    print("  Id={} Pt=({:.2f},{:.2f})".format(int(eid.Value), pt.X, pt.Y))

# Aplicar rotación 240°
target_rot = math.radians(240)
t = Transaction(doc, "Fix Tomas Pared X45.39"); t.Start()
fixed = 0
for eid, pt in tomas:
    try:
        axis = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1))
        ElementTransformUtils.RotateElement(doc, eid, axis, target_rot)
        fixed += 1
    except Exception as e:
        print("  Err {}: {}".format(int(eid.Value), e))
t.Commit()
print("\nCorregidas: {}".format(fixed))