# -*- coding: utf-8 -*-
"""
DIAG_TIPOS5.py - Ver TODOS los FamilyNames en FamilySymbol
"""

from __future__ import print_function

try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        FilteredElementCollector, FamilySymbol,
    )
except Exception as e:
    print("ERROR imports: {}".format(e))
    revit = None

def main():
    if revit is None: return
    doc = revit.doc
    
    symbols = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
    
    print("TODOS LOS FAMILYNAMES EN SYMBOLS (primeros 100):")
    print("="*60)
    
    seen = set()
    count = 0
    for s in symbols:
        try:
            fam = s.FamilyName
            if fam not in seen:
                seen.add(fam)
                print("  '{}'".format(fam))
                count += 1
                if count >= 100:
                    break
        except:
            pass
    
    print("\nTotal únicos: {}".format(len(seen)))

main()