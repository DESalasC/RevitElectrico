# -*- coding: utf-8 -*-
"""Consulta sellada: parametro Servicio_Conduit en CENTRAL-V01c (disco)."""
import sys
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

RUTA = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01c.rvt"


def app_de():
    try:
        return __revit__.Application
    except Exception:
        pass
    from pyrevit import revit as _revit
    return _revit.app


app = app_de()
doc = app.OpenDocumentFile(RUTA)
print("documento: %r" % doc.Title)
conduits = FilteredElementCollector(doc).OfCategory(
    BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().ToElements()
print("conduits en disco: %d" % len(conduits))
el = None
for c in conduits:
    el = c
    break
if el is not None:
    nombres = []
    for p in el.Parameters:
        try:
            nombres.append(p.Definition.Name)
        except Exception:
            pass
    print("Servicio_Conduit presente: %s" % ("Servicio_Conduit" in nombres))
    p = el.LookupParameter("Servicio_Conduit")
    if p is not None:
        print("  storage: %s | valor ejemplo: %r" % (
            p.StorageType.ToString(),
            p.AsString() if p.StorageType.ToString() == "String" else "(no string)"))
    print("  todos los parametros: %s" % sorted(set(nombres)))
try:
    doc.Close(False)
    print("cerrado sin guardar")
except Exception as ex:
    print("no se pudo cerrar (queda en memoria): %s" % str(ex)[:80])
