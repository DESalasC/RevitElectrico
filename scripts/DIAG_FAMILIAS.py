# -*- coding: utf-8 -*-
"""
DIAG_FAMILIAS.py - Diagnóstico de FamilySymbols en el documento
"""

from __future__ import print_function

try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        FilteredElementCollector, FamilySymbol, FamilyInstance,
        BuiltInCategory, ElementId,
    )
    from Autodesk.Revit.DB.Structure import StructuralType
except Exception as e:
    print("ERROR imports: {}".format(e))
    revit = None

def main():
    if revit is None: return
    doc = revit.doc
    print("Documento: {}".format(doc.Title))
    print("="*60)
    
    # 1. FamilySymbols (tipos de familia)
    print("\n1. FAMILY SYMBOLS (tipos):")
    symbols = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
    print("   Total: {}".format(len(symbols)))
    
    # Filtrar solo eléctricas relevantes
    electric_fams = set()
    for s in symbols:
        try:
            fam = s.FamilyName
            if any(kw in fam for kw in ["M_Toma", "M_Interrupt", "M_Timbre", "M_Climat", "M_Ilumin", "M_Comunic", "Consolidation", "EA"]):
                electric_fams.add(fam)
                print("   {} : {}".format(fam, s.Name))
        except: pass
    
    print("\n   Familias eléctricas únicas: {}".format(len(electric_fams)))
    for f in sorted(electric_fams):
        print("     - {}".format(f))
    
    # 2. FamilyInstances ya colocadas (F01, F02, E06)
    print("\n2. FAMILY INSTANCES (ya colocadas):")
    instances = FilteredElementCollector(doc).OfClass(FamilyInstance).WhereElementIsNotElementType().ToElements()
    print("   Total instancias: {}".format(len(instances)))
    
    fam_counts = {}
    for fi in instances:
        try:
            fam = fi.Symbol.FamilyName
            fam_counts[fam] = fam_counts.get(fam, 0) + 1
        except: pass
    
    for fam, count in sorted(fam_counts.items()):
        print("   {} : {} instancias".format(fam, count))
    
    # 3. Paneles con Panel Name
    print("\n3. PANELES (OST_ElectricalEquipment):")
    panels = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType().ToElements()
    for p in panels:
        fi = p
        pname = ""
        param = fi.LookupParameter("Panel Name")
        if param and param.HasValue: pname = param.AsString() or ""
        loc = fi.Location
        pt = loc.Point if isinstance(loc, LocationPoint) else None
        level_id = fi.LevelId.IntegerValue if fi.LevelId else -1
        print("   Panel Name: '{}' | LevelId: {} | Pos: {}".format(pname, level_id, pt))
    
    # 4. Niveles
    print("\n4. NIVELES:")
    from Autodesk.Revit.DB import Level
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    for l in levels:
        print("   {} : Elev={} ft ({} m) | Id={}".format(l.Name, l.Elevation, l.Elevation*0.3048, l.Id.IntegerValue))

main()