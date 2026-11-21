# -*- coding: utf-8 -*-
"""
DIAG_TIPOS4.py - Buscar símbolos por coincidencia parcial
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
    
    print("TODOS LOS FAMILYNAMES EN SYMBOLS (filtrando eléctricos):")
    print("="*60)
    
    electric_kw = ["TOMA", "COMUNIC", "INTERRUPT", "TIMBRE", "CLIMAT", "ILUMIN", "CONSOLIDATION", "EA", "CAMPANILLA"]
    
    for s in symbols:
        try:
            fam = s.FamilyName
            if any(kw in fam.upper() for kw in electric_kw):
                print("  FamilyName='{}' | TypeName='{}'".format(fam, s.Name))
        except:
            pass

main()