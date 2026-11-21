with open(r'D:\Work\PROJECTS\RevitElectrico\scripts\RE6_COLOCAR_TODOS_v01.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """try:
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

new_block = """try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
        Plane, SketchPlane, LocationCurve, LocationPoint,
        Electrical, Mechanical, Structure,
        ElementTransformUtils,
    )
    # Conduit classes - try Electrical namespace (Revit 2022+)
    try:
        from Autodesk.Revit.DB.Electrical import Conduit, ConduitType, ConduitRun
    except ImportError:
        Conduit = ConduitType = ConduitRun = None
    from Autodesk.Revit.DB.Structure import StructuralType
    from System import Int64
except Exception as e:
    print("[ERROR] Imports fallaron. Ejecuta dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(e))
    revit = None"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(r'D:\Work\PROJECTS\RevitElectrico\scripts\RE6_COLOCAR_TODOS_v01.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed!")
else:
    print("Pattern not found")
    idx = content.find("from pyrevit import revit")
    if idx >= 0:
        print(content[idx:idx+500])