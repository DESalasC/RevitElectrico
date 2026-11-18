# List all FamilySymbols in the document
from pyrevit import revit
from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol

doc = revit.doc
print("Document:", doc.Title)

symbols = []
for s in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
    try:
        fam = s.FamilyName
        tname = s.Name
        symbols.append((fam, tname))
    except:
        pass

# Group by family
by_fam = {}
for fam, tname in symbols:
    if fam not in by_fam:
        by_fam[fam] = []
    by_fam[fam].append(tname)

print("\n=== FAMILY SYMBOLS ===")
for fam in sorted(by_fam.keys()):
    print(fam + ":")
    for t in sorted(by_fam[fam]):
        print("  - " + t)