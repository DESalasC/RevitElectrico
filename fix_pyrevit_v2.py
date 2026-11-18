with open("D:/Work/PROJECTS/RevitElectrico/scripts/F6_COLOCAR_PYREVIT_v01.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix 1: Import StructuralType from correct namespace
old_import = '''    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId, StructuralType,
        LocationCurve, LocationPoint, Level, BuiltInParameter,
        Plane, SketchPlane,
    )'''

new_import = '''    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId,
        LocationCurve, LocationPoint, Level, BuiltInParameter,
        Plane, SketchPlane,
    )
    from Autodesk.Revit.DB.Structure import StructuralType'''

content = content.replace(old_import, new_import)

# Fix 2: Replace all {**d, ...} patterns
# There are multiple patterns, let me do them one by one

# Pattern 1: results.append({**d, "status": "skip", "error": "Sin mapeo Revit"})
content = content.replace(
    'results.append({**d, "status": "skip", "error": "Sin mapeo Revit"})',
    'r = dict(d); r["status"] = "skip"; r["error"] = "Sin mapeo Revit"; results.append(r)'
)

# Pattern 2: results.append({**d, "status": "error", "error": "Symbol not found: {} / {}".format(fam, tip)})
content = content.replace(
    'results.append({**d, "status": "error", "error": "Symbol not found: {} / {}".format(fam, tip)})',
    'r = dict(d); r["status"] = "error"; r["error"] = "Symbol not found: {} / {}".format(fam, tip); results.append(r)'
)

# Pattern 3: results.append({**d, **result})
content = content.replace(
    'results.append({**d, **result})',
    'r = dict(d); r.update(result); results.append(r)'
)

# Also fix any other dict merging with **
# Search for any remaining ** in dict context
import re
# Find patterns like {**var, ...}
pattern = r'\{(\*\*[a-zA-Z_][a-zA-Z0-9_]*),'
matches = re.findall(pattern, content)
if matches:
    print("Remaining ** patterns found:", matches)
    # Fix them manually
    for m in matches:
        var = m[2:]  # remove **
        old = '{**%s, ' % var
        new = 'r = dict(%s); ' % var
        content = content.replace(old, new)

with open("D:/Work/PROJECTS/RevitElectrico/scripts/F6_COLOCAR_PYREVIT_v01.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed imports and dict unpacking")