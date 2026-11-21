import re

path = r"D:\Work\PROJECTS\RevitElectrico\scripts\RE6_COLOCAR_TODOS_v01.py"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the import block
old = """try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
        Plane, SketchPlane, LocationCurve, LocationPoint,
        Electrical, Mechanical, Structure,
        ElementTransformUtils,
    )
    from Autodesk.Revit.DB.Electrical import Conduit, ConduitType, ConduitRun
    from Autodesk.Revit.DB import ConduitFitting
    from Autodesk.Revit.DB.Structure import StructuralType
    from System import Int64
except Exception as e:
    print("[ERROR] Imports fallaron. Ejecuta dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(e))
    revit = None"""

new = """try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
        Plane, SketchPlane, LocationCurve, LocationPoint,
        Electrical, Mechanical, Structure,
        ElementTransformUtils,
        ConduitFitting,
    )
    from Autodesk.Revit.DB.Electrical import Conduit, ConduitType, ConduitRun
    from Autodesk.Revit.DB.Structure import StructuralType
    from System import Int64
except Exception as e:
    print("[ERROR] Imports fallaron. Ejecuta dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(e))
    revit = None"""

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed!")
else:
    print("Old pattern not found")
    # Show what's there
    idx = content.find("from pyrevit import revit")
    if idx >= 0:
        print(content[idx:idx+600])