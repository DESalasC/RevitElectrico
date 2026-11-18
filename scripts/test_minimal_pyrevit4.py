# Test m\u00ednimo en pyRevit - acceso seguro a propiedades
from pyrevit import revit
from Autodesk.Revit.DB import (
    XYZ, FilteredElementCollector, FamilySymbol, FamilyInstance,
    Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
)
from Autodesk.Revit.DB.Structure import StructuralType

doc = revit.doc
print("Document:", doc.Title)

# Try to find a symbol - use OfClass and cast properly
sym = None
collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
for s in collector:
    try:
        # s is already a FamilySymbol due to OfClass
        fam_name = s.FamilyName
        # Don't access s.Name - some symbols might not have it accessible
        # Just match by FamilyName and take the first one
        if fam_name == "M_Toma doble":
            sym = s
            print("Found M_Toma doble:", sym.FamilyName)
            break
    except Exception as e:
        print("Error:", e)

if not sym:
    print("M_Toma doble not found, trying any symbol...")
    for s in collector:
        try:
            fam_name = s.FamilyName
            print("Available:", fam_name)
        except:
            pass
else:
    print("Selected symbol:", sym.FamilyName)
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