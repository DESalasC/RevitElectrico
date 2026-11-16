# -*- coding: utf-8 -*-
# Wrapper: consultar estado del modelo Revit activo (PID 5500) para F2 auditoría.
# Versión optimizada: filtros de categoría + WhereElementIsNotElementType.
#
# Ejecutar: pyrevit agent run <este_archivo> --mode=query --revit=5500 --timeout=300

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from System import Int64

import json
import os

SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\auditoria_modelo_revit_2026-11-11.json"


def _eid(element_id):
    """Convierte ElementId a int de forma segura en IronPython 2.7."""
    try:
        return int(element_id.IntegerValue)
    except Exception:
        return int(str(element_id))


def guardar_json(path, datos):
    directorio = os.path.dirname(path)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(path, "w") as f:
        json.dump(datos, f, ensure_ascii=True, indent=2)


doc = __revit__.ActiveUIDocument.Document
app = doc.Application

result = {
    "documento": doc.Title,
    "ruta": doc.PathName,
    "familias_cargadas": [],
    "niveles": [],
    "muros_piso5": [],
    "techos_piso5": [],
    "family_instances_rango": [],
    "resumen": {},
}

# --- Familias cargadas ---
try:
    for fam in FilteredElementCollector(doc).OfClass(Family):
        result["familias_cargadas"].append({
            "nombre": fam.Name,
            "id": _eid(fam.Id),
            "cantidad_simbolos": len(list(fam.GetFamilySymbolIds())) if hasattr(fam, "GetFamilySymbolIds") else 0,
        })
except Exception as exc:
    result["error_familias"] = str(exc)

# --- Niveles ---
try:
    for lv in FilteredElementCollector(doc).OfClass(Level):
        result["niveles"].append({
            "nombre": lv.Name,
            "elevacion_ft": lv.Elevation,
            "elevacion_m": round(lv.Elevation * 0.3048, 4),
            "id": _eid(lv.Id),
        })
except Exception as exc:
    result["error_niveles"] = str(exc)

# Nivel Piso 5
nivel_piso5 = None
for lv in result["niveles"]:
    if lv["nombre"] == "Piso 5":
        nivel_piso5 = doc.GetElement(ElementId(Int64(lv["id"])))
        break

# --- Muros del nivel Piso 5 (solo instancias, no tipos) ---
if nivel_piso5:
    try:
        cat_filter = ElementCategoryFilter(BuiltInCategory.OST_Walls)
        not_type_filter = WhereElementIsNotElementTypeFilter()
        level_filter = ElementLevelFilter(nivel_piso5.Id)
        collector = FilteredElementCollector(doc).WherePasses(cat_filter).WherePasses(not_type_filter).WherePasses(level_filter)
        for w in collector:
            try:
                loc = w.Location
                pts = []
                if loc and hasattr(loc, "Curve"):
                    c = loc.Curve
                    pts = [{"x": round(p.X, 4), "y": round(p.Y, 4), "z": round(p.Z, 4)}
                           for p in c.GetEndPoints()]
                result["muros_piso5"].append({
                    "id": _eid(w.Id),
                    "nombre": w.Name,
                    "tipo": w.WallType.Name if w.WallType else "",
                    "nivel": w.Level.Name if w.Level else "",
                    "puntos": pts,
                    "altura": round(w.Height * 0.3048, 4) if hasattr(w, "Height") else None,
                })
            except Exception:
                continue
    except Exception as exc:
        result["error_muros"] = str(exc)

# --- Techos del nivel Piso 5 ---
if nivel_piso5:
    try:
        cat_filter = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
        not_type_filter = WhereElementIsNotElementTypeFilter()
        level_filter = ElementLevelFilter(nivel_piso5.Id)
        collector = FilteredElementCollector(doc).WherePasses(cat_filter).WherePasses(not_type_filter).WherePasses(level_filter)
        for c in collector:
            try:
                loc = c.Location
                pts = []
                if loc and hasattr(loc, "Point"):
                    p = loc.Point
                    pts = [{"x": round(p.X, 4), "y": round(p.Y, 4), "z": round(p.Z, 4)}]
                result["techos_piso5"].append({
                    "id": _eid(c.Id),
                    "nombre": c.Name,
                    "tipo": c.CeilingType.Name if c.CeilingType else "",
                    "nivel": c.Level.Name if c.Level else "",
                    "puntos": pts,
                    "altura": round(c.Height * 0.3048, 4) if hasattr(c, "Height") else None,
                })
            except Exception:
                continue
    except Exception as exc:
        result["error_techos"] = str(exc)

# --- FamilyInstances en rango E06 (pies) ---
try:
    collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    for fi in collector:
        try:
            fam_name = fi.Symbol.Family.Name if fi.Symbol and fi.Symbol.Family else ""
            loc = fi.Location
            if loc and hasattr(loc, "Point"):
                pt = loc.Point
                if 0 <= pt.X <= 30 and 0 <= pt.Y <= 40:
                    result["family_instances_rango"].append({
                        "id": _eid(fi.Id),
                        "familia": fam_name,
                        "simbolo": fi.Symbol.Name if fi.Symbol else "",
                        "categoria": fi.Category.Name if fi.Category else "",
                        "x": round(pt.X, 4),
                        "y": round(pt.Y, 4),
                        "z": round(pt.Z, 4),
                        "nivel": fi.Level.Name if fi.Level else "",
                    })
        except Exception:
            continue
except Exception as exc:
    result["error_instances"] = str(exc)

result["resumen"] = {
    "total_familias": len(result["familias_cargadas"]),
    "total_niveles": len(result["niveles"]),
    "total_muros_piso5": len(result["muros_piso5"]),
    "total_techos_piso5": len(result["techos_piso5"]),
    "total_family_instances_rango": len(result["family_instances_rango"]),
}

guardar_json(SALIDA_JSON, result)
print("=== RE_AUDITAR_MODELO_REVIT_v01 ===")
print("Documento: {}".format(doc.Title))
print("Familias cargadas: {}".format(result["resumen"]["total_familias"]))
print("Niveles: {}".format(result["resumen"]["total_niveles"]))
print("Muros Piso 5: {}".format(result["resumen"]["total_muros_piso5"]))
print("Techos Piso 5: {}".format(result["resumen"]["total_techos_piso5"]))
print("FamilyInstances rango E06: {}".format(result["resumen"]["total_family_instances_rango"]))
print("JSON guardado en: {}".format(SALIDA_JSON))
