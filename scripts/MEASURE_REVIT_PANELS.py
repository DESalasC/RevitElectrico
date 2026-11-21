# -*- coding: utf-8 -*-
"""
MEASURE_REVIT_PANELS.py - Medir paneles desde esquina NE en Revit
"""

try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        FilteredElementCollector, BuiltInCategory, FamilyInstance, LocationPoint,
    )
except Exception as e:
    print("ERROR imports: {}".format(e))
    revit = None

def main():
    if revit is None: return
    doc = revit.doc
    
    panels = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType().ToElements()
    
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    
    panel_data = []
    
    for p in panels:
        fi = p
        loc = fi.Location
        if not isinstance(loc, LocationPoint): continue
        pt = loc.Point
        
        min_x = min(min_x, pt.X); min_y = min(min_y, pt.Y); min_z = min(min_z, pt.Z)
        max_x = max(max_x, pt.X); max_y = max(max_y, pt.Y); max_z = max(max_z, pt.Z)
        
        pname = ""
        param = fi.LookupParameter("Panel Name")
        if param and param.HasValue:
            pname = param.AsString() or ""
        
        panel_data.append((pname, pt.X, pt.Y, pt.Z))
    
    print("MODEL_BOUNDS: min=({:.3f},{:.3f},{:.3f}) max=({:.3f},{:.3f},{:.3f})".format(min_x, min_y, min_z, max_x, max_y, max_z))
    print("NE_CORNER: ({:.3f}, {:.3f})".format(max_x, max_y))
    print()
    
    for pname, x, y, z in panel_data:
        if abs(z - 47.3) < 1.0:
            dx = max_x - x
            dy = max_y - y
            print("PANEL: {} pos=({:.3f},{:.3f}) from_NE=({:.3f},{:.3f})".format(pname, x, y, dx, dy))

main()