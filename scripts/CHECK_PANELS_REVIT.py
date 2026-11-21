# -*- coding: utf-8 -*-
"""
CHECK_PANELS_REVIT.py - Verificar nombres REALES de paneles en el modelo Revit
"""

try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        FilteredElementCollector, BuiltInCategory, FamilyInstance,
    )
except Exception as e:
    print("ERROR imports: {}".format(e))
    revit = None

def main():
    if revit is None: return
    doc = revit.doc
    
    print("PANELES EN REVIT (OST_ElectricalEquipment):")
    print("="*60)
    
    panels = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType().ToElements()
    
    for p in panels:
        fi = p
        pname = ""
        param = fi.LookupParameter("Panel Name")
        if param and param.HasValue:
            pname = param.AsString() or ""
        loc = fi.Location
        pt = loc.Point if hasattr(loc, 'Point') else None
        print("  Panel Name: '{}' | Id: {} | Pos: {}".format(pname, fi.Id.IntegerValue, pt))

main()