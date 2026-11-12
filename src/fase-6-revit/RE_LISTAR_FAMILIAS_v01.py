# -*- coding: utf-8 -*-
# RE_LISTAR_FAMILIAS_v01.py
# Lista TODAS las familias cargadas en el documento Revit activo.
# SOLO LECTURA: no modifica nada.
#
# Ejecutar en pyRevit Python Shell:
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_LISTAR_FAMILIAS_v01.py")
#   listar_familias(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


def listar_familias(doc, filtro_texto=None):
    print("=== RE_LISTAR_FAMILIAS_v01 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: SOLO LECTURA")

    familias = []
    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            nombre = fam.Name
            ids = fam.GetFamilySymbolIds()
            n_simbolos = len(ids) if ids else 0
            familias.append((nombre, n_simbolos))
        except Exception:
            continue

    familias.sort(key=lambda x: x[0])

    total = len(familias)
    print("Total familias cargadas: {}".format(total))

    if filtro_texto:
        print("\n--- Familias que contienen '{}' ---".format(filtro_texto))
        encontradas = 0
        for nombre, n_sim in familias:
            if filtro_texto.lower() in nombre.lower():
                print("  '{}' ({} símbolos)".format(nombre, n_sim))
                encontradas += 1
        if encontradas == 0:
            print("  (ninguna)")
    else:
        print("\n--- Todas las familias (primeras 80) ---")
        for i, (nombre, n_sim) in enumerate(familias[:80]):
            print("  {}. '{}' ({} símbolos)".format(i + 1, nombre, n_sim))
        if total > 80:
            print("  ... y {} más".format(total - 80))


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        listar_familias(doc, filtro_texto="electric")
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
