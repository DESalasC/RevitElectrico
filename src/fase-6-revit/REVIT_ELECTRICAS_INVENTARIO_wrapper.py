# -*- coding: utf-8 -*-
# Wrapper: listar FamilyInstances eléctricas y Conduits de Revit 2026 (PID 5500)
# usando OST_GenericModel y OST_Conduit (categorías disponibles sin RevitAPIMEP).
# Ejecutar: pyrevit agent run <este_archivo> --mode=query --revit=5500 --timeout=120

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import json, os

SALIDA = r"D:\Work\PROJECTS\RevitElectrico\data\revit_electricas_inventario_2026-11-11.json"

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

def _pt(loc):
    try:
        if loc and hasattr(loc, "Point"):
            p = loc.Point
            return {"x": round(p.X,3), "y": round(p.Y,3), "z": round(p.Z,3)}
    except Exception:
        pass
    return None

doc = __revit__.ActiveUIDocument.Document

palabras = ["ELEC","BALA","S3","GFCI","TEL","NET","VENT","CONTROL","TIMBRE","CAMPANA","I-S","T-D","PANEL","DISTRIBUTION"]

result = {
    "documento": doc.Title,
    "family_instances_electricas": [],
    "conduits_muestra": [],
    "resumen": {},
}

# FamilyInstances en OST_GenericModel (22 en el modelo)
try:
    collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_GenericModel)
    for e in collector:
        try:
            fam = e.Symbol.Family.Name if e.Symbol and e.Symbol.Family else ""
        except Exception:
            fam = ""
        texto = "{} {}".format(_nombre(e), fam).upper()
        if any(p in texto for p in palabras):
            loc = e.Location
            pt = _pt(loc)
            result["family_instances_electricas"].append({
                "id": _eid(e.Id),
                "familia": fam.encode("ascii","replace").decode("ascii"),
                "nombre": _nombre(e),
                "posicion": pt,
                "nivel": e.Level.Name.encode("ascii","replace").decode("ascii") if e.Level else "",
                "host": str(e.Host.Id.IntegerValue) if e.Host else "",
            })
except Exception:
    pass

# Conduits: muestra limitada
try:
    collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit)
    for c in collector:
        try:
            loc = c.Location
            pt = None
            if loc and hasattr(loc, "Curve"):
                curve = loc.Curve
                if curve:
                    p = curve.Evaluate(0.5, True)
                    pt = {"x": round(p.X,3), "y": round(p.Y,3), "z": round(p.Z,3)}
        except Exception:
            pt = None
        result["conduits_muestra"].append({
            "id": _eid(c.Id),
            "posicion_punto_medio": pt,
            "diametro": c.Diameter if hasattr(c, "Diameter") else None,
        })
        if len(result["conduits_muestra"]) >= 30:
            break
except Exception:
    pass

result["resumen"] = {
    "total_family_instances_electricas": len(result["family_instances_electricas"]),
    "conduits_muestra": len(result["conduits_muestra"]),
}

with open(SALIDA, "w") as f:
    json.dump(result, f, ensure_ascii=True, indent=2)

print("=== REVIT_ELECTRICAS_INVENTARIO ===")
print("Documento: {}".format(doc.Title))
print("FamilyInstances electricas: {}".format(result["resumen"]["total_family_instances_electricas"]))
print("Conduits muestra: {}".format(result["resumen"]["conduits_muestra"]))
print("JSON: {}".format(SALIDA))
for fi in result["family_instances_electricas"]:
    print("  ID={} fam={} nombre={} pos={} nivel={} host={}".format(
        fi["id"], fi["familia"], fi["nombre"], fi["posicion"], fi["nivel"], fi["host"]))
