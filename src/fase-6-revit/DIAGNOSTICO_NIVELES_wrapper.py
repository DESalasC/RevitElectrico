# -*- coding: utf-8 -*-
# Diagnóstico rápido: niveles, LevelIds, muros por nivel, familias cargadas.
# Ejecutar: pyrevit agent run <este_archivo> --mode=query --revit=5500 --timeout=120

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import json, os

SALIDA = r"D:\Work\PROJECTS\RevitElectrico\data\diagnostico_niveles_2026-11-11.json"

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
result = {"documento": doc.Title, "niveles": [], "muros_por_nivel": [], "familias_muestra": [], "conteos_categoria": {}}

# Niveles
for lv in FilteredElementCollector(doc).OfClass(Level):
    result["niveles"].append({"nombre": _nombre(lv), "elev_ft": round(lv.Elevation,3), "elev_m": round(lv.Elevation*0.3048,4), "id": _eid(lv.Id)})

# Muros: contar por nivel (muestra)
from collections import Counter
muros_por_nivel = Counter()
muestras = []
for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls):
    try:
        lid = _eid(w.LevelId)
        muros_por_nivel[lid] += 1
        if len(muestras) < 15:
            loc = w.Location
            p1 = p2 = None
            if loc and hasattr(loc, "Curve"):
                c = loc.Curve
                p1 = c.GetEndPoint(0); p2 = c.GetEndPoint(1)
            muestras.append({"id": _eid(w.Id), "nivel_id": lid, "nivel_nombre": _nombre(w.Level), "p1": [round(p1.X,2),round(p1.Y,2)] if p1 else None, "p2": [round(p2.X,2),round(p2.Y,2)] if p2 else None})
    except Exception:
        continue
result["muros_por_nivel"] = [{"nivel_id": k, "n": v} for k,v in sorted(muros_por_nivel.items())]
result["muestras_muros"] = muestras

# Techos: contar por nivel
techos_por_nivel = Counter()
for c in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings):
    try:
        techos_por_nivel[_eid(c.LevelId)] += 1
    except Exception:
        continue
result["techos_por_nivel"] = [{"nivel_id": k, "n": v} for k,v in sorted(techos_por_nivel.items())]

# Familias cargadas (muestra 40)
for fam in FilteredElementCollector(doc).OfClass(Family):
    result["familias_muestra"].append(_nombre(fam))
    if len(result["familias_muestra"]) >= 40:
        break

# Conteos por categoría rápida
for bcat, nombre_cat in [(BuiltInCategory.OST_Walls,"Muros"),(BuiltInCategory.OST_Ceilings,"Techos"),(BuiltInCategory.OST_GenericModel,"GenericModel"),(BuiltInCategory.OST_Conduit,"Conduit")]:
    try:
        result["conteos_categoria"][nombre_cat] = len(list(FilteredElementCollector(doc).OfCategory(bcat)))
    except Exception:
        result["conteos_categoria"][nombre_cat] = "error"

with open(SALIDA, "w") as f:
    json.dump(result, f, ensure_ascii=True, indent=2)

print("=== DIAGNOSTICO NIVELES ===")
print("Documento: {}".format(doc.Title))
print("Niveles:")
for n in result["niveles"]:
    print("  id={} nombre='{}' elev_ft={} elev_m={}".format(n["id"], n["nombre"], n["elev_ft"], n["elev_m"]))
print("Muros por nivel_id:", result["muros_por_nivel"][:10])
print("Techos por nivel_id:", result["techos_por_nivel"][:10])
print("Familias muestra:", result["familias_muestra"][:20])
print("Conteos:", result["conteos_categoria"])
print("JSON: {}".format(SALIDA))
