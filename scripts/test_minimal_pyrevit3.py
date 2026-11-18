# Test m\u00ednimo en pyRevit - verificar que el entorno funciona
from pyrevit import revit
from Autodesk.Revit.DB import (
    XYZ, FilteredElementCollector, FamilySymbol, FamilyInstance,
    Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
)
from Autodesk.Revit.DB.Structure import StructuralType

doc = revit.doc
print("Document:", doc.Title)

# Try to find a symbol - use FamilyName property directly
sym = None
for s in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
    try:
        fam_name = s.FamilyName  # Direct property
        sym_name = s.Name
        # print("Found:", fam_name, sym_name)
        if fam_name == "M_Toma doble" and sym_name == "Normal":
            sym = s
            break
    except Exception as e:
        print("Error reading symbol:", e)

if sym:
    print("Selected symbol:", sym.FamilyName, sym.Name)
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