# List all FamilySymbols in the document - with debug
from pyrevit import revit
from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol
import sys

doc = revit.doc
print("Document:", doc.Title)
sys.stdout.flush()

collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
elements = collector.ToElements()
print("Elements count:", len(elements))
sys.stdout.flush()

symbols = []
for i, s in enumerate(elements):
    try:
        fam = s.FamilyName
        tname = s.Name
        print("  [{}] {} / {}".format(i, fam, tname))
        symbols.append((fam, tname))
    except Exception as e:
        print("  [{}] ERROR: {}".format(i, e))
    sys.stdout.flush()

print("Total symbols found:", len(symbols))
sys.stdout.flush()

# Group by family
by_fam = {}
for fam, tname in symbols:
    if fam not in by_fam:
        by_fam[fam] = []
    by_fam[fam].append(tname)

print("\n=== GROUPED ===")
for fam in sorted(by_fam.keys()):
    print(fam + ":")
    for t in sorted(by_fam[fam]):
        print("  - " + t)
sys.stdout.flush()