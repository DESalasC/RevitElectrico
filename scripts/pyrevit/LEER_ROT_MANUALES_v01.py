# -*- coding: utf-8 -*-
# Leer rotación de los 4 manuales correctos
# Ejecutar en pyRevit

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import ElementId
from System import Int64

doc = __revit__.ActiveUIDocument.Document

ids = [5556292,5556661,5556741,5556779]
for eid in ids:
    el = doc.GetElement(ElementId(Int64(eid)))
    if el and el.Location and hasattr(el.Location, 'Rotation'):
        rot = el.Location.Rotation
        pt = el.Location.Point
        print("Id={} Pt=({:.2f},{:.2f}) rot={:.1f}°".format(eid, pt.X, pt.Y, rot * 57.29578))
    else:
        print("Id={} sin Location.Rotation".format(eid))