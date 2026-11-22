# -*- coding: utf-8 -*-
"""
RE7_DIAG_CREAR_UNO_v02.py — Diagnóstico paso a paso de creación de un conduit fitting.

Aísla exactamente qué acceso a atributo o qué llamada falla en IronPython 2.7.

USO (desde pyRevit Python Shell dentro de Revit 2026):
  exec(open(r"D:/Work/PROJECTS/RevitElectrico/src/fase-7-ruteo/RE7_DIAG_CREAR_UNO_v02.py").read())
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


def _seguro(obj, nombre_attr, valor_defecto="?"):
    """Intenta acceder a un atributo de forma segura, devolviendo valor_defecto si falla."""
    try:
        return getattr(obj, nombre_attr)
    except Exception as ex:
        return "ERROR({}): {}".format(nombre_attr, str(ex))


def diagnosticar_crear_uno(doc):
    print("=" * 60)
    print("RE7_DIAG_CREAR_UNO_v02 - Diagnóstico paso a paso")
    print("=" * 60)

    # 1. Buscar el símbolo de codo
    print("\n1. Buscando símbolo: M_Codo de tubo - Extremo abocardado - PVC")
    simbolo = None
    try:
        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        for fs in collector:
            try:
                nom_fam = _seguro(fs.Family, "Name")
            except Exception:
                continue
            if isinstance(nom_fam, str) and "Codo de tubo" in nom_fam and "abocardado" in nom_fam:
                simbolo = fs
                print("   Encontrado: Familia='{}'".format(nom_fam))
                try:
                    print("   Tipo (fs.Name): '{}'".format(_seguro(fs, "Name")))
                except Exception as ex:
                    print("   ERROR al leer fs.Name: {}".format(str(ex)))
                break
    except Exception as ex:
        print("   ERROR en búsqueda: {}".format(str(ex)))
        traceback.print_exc()

    if simbolo is None:
        print("   NO se encontró el símbolo.")
        return

    # 2. Activar símbolo
    print("\n2. Activando símbolo...")
    try:
        activo = simbolo.IsActive
        print("   IsActive antes: {}".format(activo))
        if not activo:
            simbolo.Activate()
        print("   IsActive después: {}".format(simbolo.IsActive))
    except Exception as ex:
        print("   ERROR al activar: {}".format(str(ex)))
        traceback.print_exc()

    # 3. Buscar nivel
    print("\n3. Buscando nivel...")
    nivel = None
    try:
        for lv in FilteredElementCollector(doc).OfClass(Level).ToElements():
            nivel = lv
            print("   Nivel: '{}' (Id={})".format(_seguro(lv, "Name"), lv.Id))
            break
    except Exception as ex:
        print("   ERROR al buscar nivel: {}".format(str(ex)))
        traceback.print_exc()

    # 4. Preparar XYZ
    print("\n4. Preparando XYZ en (12884, 9607, 15920) mm...")
    try:
        xyz = XYZ(12884.0 / 304.8, 9607.77 / 304.8, 15920.0 / 304.8)
        print("   XYZ creado: X={:.4f}, Y={:.4f}, Z={:.4f}".format(xyz.X, xyz.Y, xyz.Z))
    except Exception as ex:
        print("   ERROR al crear XYZ: {}".format(str(ex)))
        traceback.print_exc()
        return

    # 5. Crear FamilyInstance con nivel (objeto, no Id)
    print("\n5. Intentando NewFamilyInstance(xyz, simbolo, nivel, StructuralType.NonStructural)...")
    try:
        instancia = doc.Create.NewFamilyInstance(
            xyz, simbolo, nivel, StructuralType.NonStructural)
        print("   OK: instancia creada. Id={}".format(instancia.Id))
    except Exception as ex:
        print("   ERROR al crear: {}".format(str(ex)))
        traceback.print_exc()
        return

    # 6. Verificar la instancia
    print("\n6. Verificando instancia creada...")
    try:
        print("   Categoría: {}".format(instancia.Category.Name if instancia.Category else "None"))
        print("   Symbol: {}".format(instancia.Symbol.Name if instancia.Symbol else "None"))
        print("   Location: {}".format(instancia.Location.Point if instancia.Location and instancia.Location.Point else "None"))
    except Exception as ex:
        print("   ERROR al verificar: {}".format(str(ex)))
        traceback.print_exc()

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
