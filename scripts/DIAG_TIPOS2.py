# -*- coding: utf-8 -*-
"""
DIAG_TIPOS2.py - Ver FamilyNames exactos desde instancias existentes
"""

from __future__ import print_function

try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        FilteredElementCollector, FamilyInstance,
    )
except Exception as e:
    print("ERROR imports: {}".format(e))
    revit = None

def main():
    if revit is None: return
    doc = revit.doc
    
    print("FAMILY NAMES DESDE INSTANCIAS EXISTENTES:")
    print("="*60)
    
    instances = FilteredElementCollector(doc).OfClass(FamilyInstance).WhereElementIsNotElementType().ToElements()
    
    seen = set()
    for fi in instances:
        try:
            fam = fi.Symbol.FamilyName
            if fam not in seen:
                seen.add(fam)
                if any(kw in fam for kw in ["M_Toma", "M_Interrupt", "M_Timbre", "M_Climat", "M_Ilumin", "M_Comunic", "Consolidation", "EA", "M_Timbre"]):
                    print("  '{}'".format(fam))
        except:
            pass
    
    print("\nTotal únicas: {}".format(len(seen)))

main()