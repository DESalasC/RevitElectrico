# -*- coding: utf-8 -*-
"""Consulta minima: documento activo."""
doc = None
try:
    doc = __revit__.ActiveUIDocument.Document
except Exception:
    pass
if doc is None:
    from pyrevit import revit as _revit
    doc = _revit.doc
print("TITLE=%r" % doc.Title)
print("PATH=%r" % doc.PathName)
print("ISMODIFIED=%s" % doc.IsModified)
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector
print("CONDUITS=%d" % FilteredElementCollector(doc).OfCategory(
    BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().GetElementCount())
