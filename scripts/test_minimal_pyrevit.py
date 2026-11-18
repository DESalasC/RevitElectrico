# Test mínimo en pyRevit - verificar que el entorno funciona
from pyrevit import revit
from Autodesk.Revit.DB import (
    XYZ, FilteredElementCollector, FamilySymbol, FamilyInstance,
    Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
)
from Autodesk.Revit.DB.Structure import StructuralType

doc = revit.doc
print("Document:", doc.Title)

# Try to find a symbol
sym = None
for s in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
    if s.FamilyName == "M_Toma doble" and s.Name == "Normal":
        sym = s
        break

if sym:
    print("Found symbol:", sym.FamilyName, sym.Name)
    if not sym.IsActive:
        sym.Activate()
    
    # Get level
    lvl = doc.GetElement(ElementId(192512))
    print("Level:", lvl.Name if lvl else "None")
    
    # Try to create instance at a safe location
    pt = XYZ(10000/304.8, 7000/304.8, 13500/304.8)
    
    with Transaction(doc, "Test Place") as t:
        t.Start()
        try:
            inst = doc.Create.NewFamilyInstance(pt, sym, lvl, StructuralType.NonStructural)
            print("Created element:", inst.Id.IntegerValue)
            loc = inst.Location
            if loc:
                print("Location:", loc.Point.X*304.8, loc.Point.Y*304.8, loc.Point.Z*304.8)
            t.Commit()
        except Exception as e:
            print("ERROR:", e)
            t.RollBack()
else:
    print("Symbol not found")