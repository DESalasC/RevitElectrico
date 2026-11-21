# -*- coding: utf-8 -*-
"""
DIAG_BYTES.py - Ver bytes exactos de FamilyNames
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
    
    target_families = [
        "M_Toma doble", "M_Comunicaciones", "M_Interruptores",
        "M_Timbre", "M_Pulsador - Interruptor", "M_ClimatizacionV",
        "M_Iluminacion", "EA", "Consolidation_Point",
        "M_Climatizacion", "M_Timbre - Campanilla",
        "M_Caja de conexiones hexagonal",
    ]
    
    print("BYTES EXACTOS:")
    print("="*60)
    
    for fam_name in target_families:
        target_bytes = fam_name.encode('utf-8')
        print("\nBuscando: '{}' -> bytes: {}".format(fam_name, target_bytes))
        
        found = False
        for s in symbols:
            try:
                fam = s.FamilyName
                fam_bytes = fam.encode('utf-8')
                if fam_bytes == target_bytes:
                    print("  MATCH EXACTO: '{}' -> {}".format(fam, fam_bytes))
                    print("    TypeName: '{}'".format(s.Name))
                    found = True
                    break
            except:
                pass
        
        if not found:
            print("  NO MATCH EXACTO - buscando por similitud...")
            for s in symbols:
                try:
                    fam = s.FamilyName
                    if all(kw.lower() in fam.lower() for kw in fam_name.split()):
                        fam_bytes = fam.encode('utf-8')
                        print("  SIMILAR: '{}' -> bytes: {}".format(fam, fam_bytes))
                        print("    TypeName: '{}'".format(s.Name))
                except:
                    pass

main()