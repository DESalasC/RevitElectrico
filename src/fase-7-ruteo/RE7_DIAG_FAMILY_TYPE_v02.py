# -*- coding: utf-8 -*-
"""
RE7_DIAG_FAMILY_TYPE_v02.py — Diagnóstico del FamilyPlacementType (v02: usa fs.Family).

USO (desde pyRevit Python Shell dentro de Revit 2026):
  exec(open(r"D:/Work/PROJECTS/RevitElectrico/src/fase-7-ruteo/RE7_DIAG_FAMILY_TYPE_v02.py").read())
  doc = __revit__.ActiveUIDocument.Document
  diagnosticar_tipo_familia(doc)
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FamilySymbol,
    FamilyInstance,
    BuiltInCategory,
    FamilyPlacementType,
)
from Autodesk.Revit.DB.Electrical import Conduit


def diagnosticar_tipo_familia(doc):
    print("=" * 60)
    print("RE7_DIAG_FAMILY_TYPE_v02 - FamilyPlacementType de conduit fittings")
    print("=" * 60)

    nombres_buscar = [
        "M_Codo de tubo - Extremo abocardado - PVC",
        "M_Casquillo reductor de tubo - PVC",
        "M_Caja de conexiones de tubo - Te - PVC",
        "M_Caja de conexiones de tubo - Cruz - PVC",
    ]

    for nombre_buscar in nombres_buscar:
        print("\n--- Familia: {}".format(nombre_buscar))
        encontrado = False
        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        for fs in collector:
            try:
                nom_fam = fs.Family.Name
            except Exception:
                continue
            if nombre_buscar.lower() in nom_fam.lower():
                try:
                    nom_tipo = fs.Name
                except Exception:
                    nom_tipo = "?"
                try:
                    placement = fs.Family.FamilyPlacementType
                except Exception as ex:
                    placement = "ERROR: {}".format(str(ex))
                try:
                    categoria = fs.Family.Category.Name
                except Exception:
                    categoria = "?"
                print("   Tipo='{}' | PlacementType={} | Categoria={}".format(
                    nom_tipo, placement, categoria))
                encontrado = True
                break
        if not encontrado:
            print("   NO ENCONTRADO")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        diagnosticar_tipo_familia(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso: exec(open(ruta_script).read())")
        print("     doc = __revit__.ActiveUIDocument.Document")
        print("     diagnosticar_tipo_familia(doc)")
