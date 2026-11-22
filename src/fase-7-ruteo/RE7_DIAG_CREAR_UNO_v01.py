# -*- coding: utf-8 -*-
"""
RE7_DIAG_CREAR_UNO_v01.py — Diagnóstico: intenta crear UN conduit fitting
para identificar el error exacto de creación en IronPython 2.7.

USO (desde pyRevit Python Shell dentro de Revit 2026):
  exec(open(r"D:/Work/PROJECTS/RevitElectrico/src/fase-7-ruteo/RE7_DIAG_CREAR_UNO_v01.py").read())
  doc = __revit__.ActiveUIDocument.Document
  diagnosticar_crear_uno(doc)
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FamilySymbol,
    FamilyInstance,
    Transaction,
    ElementId,
    BuiltInCategory,
    XYZ,
    Level,
)
from Autodesk.Revit.DB.Electrical import Conduit
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

import traceback


def diagnosticar_crear_uno(doc):
    print("=" * 60)
    print("RE7_DIAG_CREAR_UNO_v01 - Diagnóstico de creación de un fitting")
    print("=" * 60)

    # 1. Buscar el símbolo de codo
    print("\n1. Buscando símbolo: M_Codo de tubo - Extremo abocardado - PVC")
    simbolo = None
    collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
    for fs in collector:
        try:
            nom_fam = fs.Family.Name
        except Exception:
            continue
        if "Codo de tubo" in nom_fam and "abocardado" in nom_fam:
            try:
                nom_tipo = fs.Name
            except Exception:
                nom_tipo = "?"
            print("   Encontrado: Familia='{}' | Tipo='{}'".format(nom_fam, nom_tipo))
            simbolo = fs
            break

    if simbolo is None:
        print("   NO se encontró el símbolo de codo.")
        return

    # 2. Activar símbolo
    print("\n2. Activando símbolo...")
    try:
        if not simbolo.IsActive:
            simbolo.Activate()
        print("   Símbolo activo: {}".format(simbolo.IsActive))
    except Exception as ex:
        print("   ERROR al activar: {}".format(str(ex)))
        traceback.print_exc()

    # 3. Buscar nivel
    print("\n3. Buscando nivel...")
    nivel = None
    try:
        for lv in FilteredElementCollector(doc).OfClass(Level).ToElements():
            nivel = lv
            print("   Nivel: {} (Id={})".format(lv.Name, lv.Id))
            break
    except Exception as ex:
        print("   ERROR al buscar nivel: {}".format(str(ex)))
        traceback.print_exc()

    # 4. Intentar crear una instancia en un punto conocido
    print("\n4. Intentando crear FamilyInstance en (12884, 9607, 15920) mm...")
    xyz = XYZ(12884.0 / 304.8, 9607.77 / 304.8, 15920.0 / 304.8)

    try:
        if nivel is not None:
            instancia = doc.Create.NewFamilyInstance(
                xyz, simbolo, nivel.Id, StructuralType.NonStructural)
            print("   OK: instancia creada con nivel.Id. Id={}".format(instancia.Id))
        else:
            instancia = doc.Create.NewFamilyInstance(
                xyz, simbolo, StructuralType.NonStructural)
            print("   OK: instancia creada sin nivel. Id={}".format(instancia.Id))
    except Exception as ex:
        print("   ERROR al crear instancia: {}".format(str(ex)))
        traceback.print_exc()
        return

    print("\n" + "=" * 60)
    print("Diagnóstico completado.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        diagnosticar_crear_uno(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso: exec(open(ruta_script).read())")
        print("     doc = __revit__.ActiveUIDocument.Document")
        print("     diagnosticar_crear_uno(doc)")
