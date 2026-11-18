# Test m\u00ednimo en pyRevit - fix ElementId constructor
from pyrevit import revit
from Autodesk.Revit.DB import (
    XYZ, FilteredElementCollector, FamilySymbol, FamilyInstance,
    Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
)
from Autodesk.Revit.DB.Structure import StructuralType

doc = revit.doc
print("Document:", doc.Title)

# Find symbol
sym = None
collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
for s in collector:
    try:
        fam_name = s.FamilyName
        if fam_name == "M_Toma doble":
            sym = s
            print("Found M_Toma doble:", sym.FamilyName)
            break
    except Exception as e:
        print("Error:", e)

if sym:
    print("Selected symbol:", sym.FamilyName)
    if not sym.IsActive:
        sym.Activate()
    
    # Get level - use explicit Int64 to avoid overload ambiguity
    lvl_id = ElementId(Int64(192512))
    lvl = doc.GetElement(lvl_id)
    print("Level:", lvl.Name if lvl else "None")
    
    # Try to create instance
    pt = XYZ(10000/304.8, 7000/304.8, 13500/304.8)
    
    with Transaction(doc, "Test Place") as t:
        t.Start()
        try:
            inst = doc.Create.NewFamilyInstance(pt, sym, lvl, StructuralType.NonStructural)
            print("Created element:", int(inst.Id))
            loc = inst.Location
            if loc:
                p = loc.Point
                print("Location:", p.X*304.8, p.Y*304.8, p.Z*304.8)
            t.Commit()
        except Exception as e:
            print("ERROR:", e)
            t.RollBack()
else:
    print("Symbol not found")