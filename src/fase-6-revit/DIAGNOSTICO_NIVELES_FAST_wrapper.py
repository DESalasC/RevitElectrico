# -*- coding: utf-8 -*-
# Diagnóstico ultra-ligero: conteos por nivel usando filtros nativos de Revit (sin iterar en Python).
# Ejecutar: pyrevit agent run <este_archivo> --mode=query --revit=5500 --timeout=180

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from System import Int64
import json, os

SALIDA = r"D:\Work\PROJECTS\RevitElectrico\data\diagnostico_niveles_fast_2026-11-11.json"

def _eid(eid):
    try: return int(eid.IntegerValue)
    except Exception: return int(str(eid))

def _lid(int_val):
    return ElementId(Int64(int_val))

def _nombre(e):
    try:
        s = e.Name
    except Exception:
        return ""
    if not isinstance(s, str):
        s = str(s)
    return s.encode("ascii","replace").decode("ascii")

doc = __revit__.ActiveUIDocument.Document
result = {"documento": doc.Title, "niveles": [], "detalle_nivel": []}

def contar_con_filtro(level_int_id, builtin_cat, max_items=3):
    """Cuenta elementos de una categoría en un nivel dado usando filtro nativo."""
    level_filter = ElementLevelFilter(_lid(level_int_id))
    cat_filter = ElementCategoryFilter(builtin_cat)
    collector = FilteredElementCollector(doc).WherePasses(cat_filter).WherePasses(level_filter)
    items = []
    count = 0
    for e in collector:
        count += 1
        if len(items) < max_items:
            try:
                items.append({"id": _eid(e.Id), "nombre": _nombre(e)})
            except Exception:
                items.append({"id": _eid(e.Id), "nombre": ""})
    return {"count": count, "muestra": items}

for lv in FilteredElementCollector(doc).OfClass(Level):
    lid = _eid(lv.Id)
    nombre = _nombre(lv)
    muros = contar_con_filtro(lid, BuiltInCategory.OST_Walls)
    techos = contar_con_filtro(lid, BuiltInCategory.OST_Ceilings)
    result["niveles"].append({"nombre": nombre, "id": lid, "elev_m": round(lv.Elevation*0.3048,4)})
    result["detalle_nivel"].append({
        "nivel": nombre, "id": lid,
        "muros": muros,
        "techos": techos,
    })

# Familias cargadas (solo nombres, límite 50)
familias = []
for fam in FilteredElementCollector(doc).OfClass(Family):
    familias.append(_nombre(fam))
    if len(familias) >= 50:
        break
result["familias_muestra"] = familias

with open(SALIDA, "w") as f:
    json.dump(result, f, ensure_ascii=True, indent=2)

print("=== DIAGNOSTICO NIVELES FAST ===")
print("Documento: {}".format(doc.Title))
for d in result["detalle_nivel"]:
    print("  Nivel '{}' (id={}): muros={}, techos={}".format(d["nivel"], d["id"], d["muros"]["count"], d["techos"]["count"]))
print("Familias muestra:", familias[:20])
print("JSON: {}".format(SALIDA))
