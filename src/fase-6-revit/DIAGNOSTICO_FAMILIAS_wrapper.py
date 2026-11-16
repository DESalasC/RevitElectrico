# -*- coding: utf-8 -*-
# DIAGNOSTICO_FAMILIAS_wrapper.py
# Lista TODAS las familias cargadas en Revit con nombre, para mapear a dispositivos DXF.
# Ejecutar: pyrevit agent run <este_archivo> --mode=query --revit=5500 --timeout=300

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import json, os

SALIDA = r"D:\Work\PROJECTS\RevitElectrico\data\diagnostico_familias_2026-11-11.json"

def _eid(eid):
    try: return int(eid.IntegerValue)
    except Exception: return int(str(eid))

def _nombre(e):
    try:
        s = e.Name
    except Exception:
        return ""
    if not isinstance(s, str):
        s = str(s)
    return s.encode("ascii","replace").decode("ascii")

doc = __revit__.ActiveUIDocument.Document
familias = []
for fam in FilteredElementCollector(doc).OfClass(Family):
    try:
        simbolos = []
        for sid in fam.GetFamilySymbolIds():
            sym = doc.GetElement(sid)
            if sym:
                simbolos.append(_nombre(sym))
        familias.append({
            "familia": _nombre(fam),
            "id": _eid(fam.Id),
            "simbolos": simbolos,
        })
    except Exception as ex:
        familias.append({"familia": _nombre(fam), "id": _eid(fam.Id), "simbolos": [], "error": str(ex)})

# Orden alfabético
familias.sort(key=lambda f: f["familia"].lower())

result = {
    "documento": doc.Title,
    "total_familias": len(familias),
    "familias": familias,
}

with open(SALIDA, "w") as f:
    json.dump(result, f, ensure_ascii=True, indent=2)

print("=== DIAGNOSTICO FAMILIAS ===")
print("Documento: {}".format(doc.Title))
print("Total familias cargadas: {}".format(len(familias)))
for f in familias:
    print("  - '{}' (id={}) simbolos={}".format(f["familia"], f["id"], f["simbolos"][:5]))
print("JSON: {}".format(SALIDA))
