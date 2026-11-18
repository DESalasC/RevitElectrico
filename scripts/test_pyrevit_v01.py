# -*- coding: utf-8 -*-
# test_pyrevit_v01.py
import sys
print("Python: " + sys.version)
try:
    _ = doc.Title
    print("doc via global: " + doc.Title)
except:
    doc = __revit__.ActiveUIDocument.Document
    print("doc via __revit__: " + doc.Title)

from Autodesk.Revit.DB import *
print("Revit API OK")
print("Niveles: " + str(len(list(FilteredElementCollector(doc).OfClass(Level).ToElements()))))
print("FIN TEST")