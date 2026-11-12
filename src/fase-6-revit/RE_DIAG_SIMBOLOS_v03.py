# -*- coding: utf-8 -*-
# RE_DIAG_SIMBOLOS_v03.py
# Lista los FamilySymbol por nombre dentro de cada familia cargada.
# Usa BuiltInParameter.SYMBOL_NAME_PARAM para obtener el nombre de forma segura en IronPython 2.7.
# SOLO LECTURA: no modifica nada en Revit.
#
# Ejecutar en pyRevit Python Shell:
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_DIAG_SIMBOLOS_v03.py")
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


def _nombre_simbolo(sym):
    """Obtiene el nombre del FamilySymbol de forma segura en IronPython 2.7."""
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


def diag_simbolos(doc):
    print("=== RE_DIAG_SIMBOLOS_v03 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: SOLO LECTURA")

    familias_objetivo = [
        "M_Iluminacion",
        "M_Toma doble",
        "M_Interruptores",
        "M_Comunicaciones",
        "M_Climatizacion",
        "M_ClimatizacionV",
        "M_Zumbador",
        "M_Pulsador - Interruptor",
        "M_Timbre",
        "Consolidation_Point",
        "E_Panel Distribucion",
        "M_Interruptores de iluminación",
        "M_Toma resistente a la intemperie",
        "M_Toma de teléfono - Datos",
        "M_Toma - 220V",
    ]

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
            print("  (familia no encontrada o sin símbolos)")
        else:
            for s in simbolos:
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
