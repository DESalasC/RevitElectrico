# -*- coding: utf-8 -*-
# RE_DIAG_SIMBOLOS_v01.py
# Lista los FamilySymbol disponibles por familia, para corregir el mapeo.
# SOLO LECTURA: no modifica nada en Revit.
#
# Ejecutar en pyRevit Python Shell:
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_DIAG_SIMBOLOS_v01.py")
#   diag_simbolos(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


def diag_simbolos(doc, familias=None):
    print("=== RE_DIAG_SIMBOLOS_v01 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: SOLO LECTURA")

    if familias is None:
        familias = [
            "M_Iluminacion",
            "M_Toma doble",
            "M_Interruptores",
            "M_Comunicaciones",
            "M_Climatizacion",
            "M_ClimatizacionV",
            "M_Zumbador",
            "M_Pulsador - Interruptor",
            "Consolidation_Point",
            "E_Panel Distribucion",
        ]

    for nombre_familia in familias:
        print("\n--- Familia: {} ---".format(nombre_familia))
        simbolos_encontrados = []
        for fam in FilteredElementCollector(doc).OfClass(Family):
            try:
                if fam.Name == nombre_familia:
                    ids = fam.GetFamilySymbolIds()
                    for sid in ids:
                        try:
                            sym = doc.GetElement(sid)
                            if sym is None:
                                continue
                            simbolos_encontrados.append({
                                "id": _eid(sid),
                                "nombre": sym.Name,
                                "activo": sym.IsActive,
                            })
                        except Exception:
                            continue
                    break
            except Exception:
                continue

        if not simbolos_encontrados:
            print("  (no se encontraron símbolos o familia no cargada)")
        else:
            for s in simbolos_encontrados:
                print("  ID={} Nombre='{}' Activo={}".format(
                    s["id"], s["nombre"], s["activo"]))


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        diag_simbolos(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
