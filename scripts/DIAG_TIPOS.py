# -*- coding: utf-8 -*-
"""
DIAG_TIPOS.py - Ver TypeNames para cada familia eléctrica
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
    
    target_families = [
        "M_Toma doble", "M_Comunicaciones", "M_Interruptores",
        "M_Timbre", "M_Pulsador - Interruptor", "M_ClimatizacionV",
        "M_Iluminacion", "EA", "Consolidation_Point",
        "M_Climatizacion", "M_Timbre - Campanilla",
        "M_Toma - 220V", "M_Toma-Rango"
    ]
    
    print("TIPOS POR FAMILIA:")
    print("="*60)
    
    symbols = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
    for fam_name in target_families:
        types = []
        for s in symbols:
            try:
                if s.FamilyName == fam_name:
                    types.append(s.Name)
            except:
                pass
        if types:
            print("\n{} ({} tipos):".format(fam_name, len(types)))
            for t in sorted(types):
                print("  - {}".format(t))
        else:
            print("\n{} : NO ENCONTRADA".format(fam_name))

main()