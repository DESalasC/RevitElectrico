# -*- coding: utf-8 -*-
# Wrapper ultraligero: estado rápido de Revit 2026 (PID 5500) sin iterar todas las FamilyInstances.
# Ejecutar: pyrevit agent run <este_archivo> --mode=query --revit=5500 --timeout=90

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import json, os

SALIDA = r"D:\Work\PROJECTS\RevitElectrico\data\revit_estado_actual_2026-11-11.json"

def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))

def _nombre(e):
    try:
        s = e.Name
    except Exception:
        return ""
    if not isinstance(s, str):
        s = str(s)
    return s.encode("ascii", "replace").decode("ascii")

doc = __revit__.ActiveUIDocument.Document

niveles = [{"nombre": lv.Name.encode("ascii","replace").decode("ascii"),
            "elev_m": round(lv.Elevation*0.3048,4), "id": _eid(lv.Id)}
           for lv in FilteredElementCollector(doc).OfClass(Level)]

def mostrar(builtin_cat, max_muestra=5):
    collector = FilteredElementCollector(doc).OfCategory(builtin_cat)
    items = []
    count = 0
    for e in collector:
        count += 1
        if len(items) < max_muestra:
            items.append({"id": _eid(e.Id), "nombre": _nombre(e)})
    return {"total_estimado": count, "muestra": items}

nivel_piso5 = None
for lv in FilteredElementCollector(doc).OfClass(Level):
    if lv.Name == "Piso 5":
        nivel_piso5 = lv
        break

resumen = {
    "documento": doc.Title.encode("ascii","replace").decode("ascii"),
    "ruta": doc.PathName,
    "niveles": niveles,
    "nivel_piso5_id": _eid(nivel_piso5.Id) if nivel_piso5 else None,
    "conteos": {
        "Muros": mostrar(BuiltInCategory.OST_Walls),
        "Techos": mostrar(BuiltInCategory.OST_Ceilings),
        "FamilyInstances": mostrar(BuiltInCategory.OST_GenericModel),
        "Conduits": mostrar(BuiltInCategory.OST_Conduit),
    },
}

with open(SALIDA, "w") as f:
    json.dump(resumen, f, ensure_ascii=True, indent=2)

print("=== REVIT_ESTADO_ACTUAL ===")
print("Documento: {}".format(resumen["documento"]))
print("Niveles: {}".format([n["nombre"] for n in niveles]))
print("Nivel Piso 5: {}".format(resumen["nivel_piso5_id"]))
print("Conteos: {}".format({k: v["total_estimado"] if v else None for k,v in resumen["conteos"].items()}))
print("JSON: {}".format(SALIDA))
