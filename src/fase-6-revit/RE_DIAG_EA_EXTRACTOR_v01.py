# -*- coding: utf-8 -*-
# RE_DIAG_EA_EXTRACTOR_v01.py
# Verifica si existe la familia 'EA' y sus FamilySymbol, incluido 'M_Extractor'.
# SOLO LECTURA: no modifica nada en Revit.
#
# Ejecutar en pyRevit Python Shell:
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_DIAG_EA_EXTRACTOR_v01.py")
#   diag_ea_extractor(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


def _nombre_simbolo(sym):
    try:
        return sym.Name
    except Exception:
        pass
    try:
        param = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if param:
            return param.AsString()
    except Exception:
        pass
    return "Desconocido"


def diag_ea_extractor(doc):
    print("=== RE_DIAG_EA_EXTRACTOR_v01 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: SOLO LECTURA")

    familias_objetivo = ["EA", "M_Extractor"]

    for nombre_familia in familias_objetivo:
        print("\n--- Familia: '{}' ---".format(nombre_familia))
        simbolos = []
        for fam in FilteredElementCollector(doc).OfClass(Family):
            try:
                if fam.Name == nombre_familia:
                    ids = fam.GetFamilySymbolIds()
                    if not ids:
                        print("  (sin símbolos)")
                        continue
                    for sid in ids:
                        try:
                            sym = doc.GetElement(sid)
                            if sym is None:
                                continue
                            simbolos.append({
                                "id": _eid(sid),
                                "nombre": _nombre_simbolo(sym),
                                "activo": sym.IsActive,
                            })
                        except Exception as ex:
                            print("  ERROR símbolo: {}".format(ex))
                            continue
                    break
            except Exception:
                continue

        if not simbolos:
            print("  (familia NO encontrada en el modelo)")
        else:
            for s in simbolos:
                print("  ID={} Nombre='{}' Activo={}".format(
                    s["id"], s["nombre"], s["activo"]))


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        diag_ea_extractor(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
