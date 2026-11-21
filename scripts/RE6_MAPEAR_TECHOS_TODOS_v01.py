# -*- coding: utf-8 -*-
"""
RE6_MAPEAR_TECHOS_TODOS_v01.py
===============================
Mapa completo de techos para LOS 20 APARTAMENTOS del Piso 5.
Usa panel position (maestro) para encontrar techo que lo contiene.
Extrae 4 esquinas + Z cara inferior + ID.

Ejecutar en pyRevit Python Shell con CENTRAL-V01a.rvt.
"""

import json
import os
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, Ceiling, Level,
    ElementId, Options, XYZ, PlanarFace, Solid
)
from System import Int64

doc = __revit__.ActiveUIDocument.Document

REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")
MAESTRO_PATH = os.path.join(DATA_DIR, "maestro_colocacion_piso5.json")
OUT_PATH = os.path.join(DATA_DIR, "ceilings_mapping_apto_v02.json")

# CARGAR MAESTRO (tiene panel_revit_m para cada apartamento)
with open(MAESTRO_PATH, 'r') as f:
    maestro = json.load(f)

print("=== MAPEO TECHOS TODOS LOS APARTAMENTOS ===")

# 1. RECOLECTAR TODOS LOS TECHOS DEL NIVEL PISO 5
nivel5_id = 192512
nivel5_z = 43.37

techos = []
for c in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType().ToElements():
    try:
        # Verificar que esté en Piso 5
        bp = c.get_Parameter(c.LookupParameter("Level").Id if c.LookupParameter("Level") else None)
        lvl_id = c.LevelId.IntegerValue if c.LevelId else 0
        
        # O por elevación
        opt = Options(); opt.ComputeReferences = True
        geom = c.get_Geometry(opt)
        if not geom:
            continue
        
        # Buscar cara inferior (normal -Z)
        face = None
        face_ref = None
        for obj in geom:
            if isinstance(obj, Solid):
                for f in obj.Faces:
                    if isinstance(f, PlanarFace) and f.FaceNormal.Z < -0.9:
                        face = f
                        break
                if face:
                    break
        
        if not face:
            continue
        
        bbox = face.GetBoundingBox()
        z_face = face.Origin.Z  # Z de la cara
        
        # 4 esquinas en UV -> XYZ
        uv_corners = [
            UV(bbox.Min.U, bbox.Min.V),
            UV(bbox.Max.U, bbox.Min.V),
            UV(bbox.Max.U, bbox.Max.V),
            UV(bbox.Min.U, bbox.Max.V),
        ]
        corners_xyz = [face.Evaluate(uv) for uv in uv_corners]
        
        xmin = min(p.X for p in corners_xyz)
        xmax = max(p.X for p in corners_xyz)
        ymin = min(p.Y for p in corners_xyz)
        ymax = max(p.Y for p in corners_xyz)
        
        techos.append({
            "id": c.Id.IntegerValue,
            "name": c.Name,
            "level_id": lvl_id,
            "face_z_ft": z_face,
            "bounds_ft": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax},
            "center_ft": {"x": (xmin+xmax)/2, "y": (ymin+ymax)/2, "z": z_face},
        })
    except Exception as e:
        continue

print("Techos encontrados en Piso 5: {}".format(len(techos)))

# 2. PARA CADA APARTAMENTO, ENCONTRAR TECHO QUE CONTIENE SU PANEL
mapping = {}
for apto_key, apto_data in sorted(maestro["apartamentos"].items()):
    panel_x = apto_data["panel_revit_m"]["x"] * 3.280839895  # m -> ft
    panel_y = apto_data["panel_revit_m"]["y"] * 3.280839895
    panel_name = apto_data["panel_name_revit"]
    
    # Buscar techo que contenga el panel (con tolerancia)
    best = None
    best_area = float('inf')
    
    for t in techos:
        b = t["bounds_ft"]
        # Tolerancia de 2 pies alrededor del panel
        if (b["xmin"] - 2 <= panel_x <= b["xmax"] + 2 and 
            b["ymin"] - 2 <= panel_y <= b["ymax"] + 2):
            area = (b["xmax"] - b["xmin"]) * (b["ymax"] - b["ymin"])
            if area < best_area:
                best_area = area
                best = t
    
    if best:
        mapping[apto_key] = {
            "panel_name": panel_name,
            "panel_pos_ft": {"x": panel_x, "y": panel_y},
            "ceiling_id": best["id"],
            "ceiling_name": best["name"],
            "ceiling_face_z_ft": best["face_z_ft"],
            "ceiling_bounds_ft": best["bounds_ft"],
            "ceiling_center_ft": best["center_ft"],
            "confirmed": False,
        }
        print("  {} -> Techo ID {} ({}) | Z={:.2f}ft | Bounds X[{:.2f},{:.2f}] Y[{:.2f},{:.2f}]".format(
            apto_key, best["id"], best["name"], best["face_z_ft"],
            best["bounds_ft"]["xmin"], best["bounds_ft"]["xmax"],
            best["bounds_ft"]["ymin"], best["bounds_ft"]["ymax"]))
    else:
        print("  {} -> NO HAY TECHO (panel @ {:.2f},{:.2f}ft)".format(apto_key, panel_x, panel_y))

# 3. GUARDAR
output = {
    "generated": "2026-11-19",
    "source": "Revit CENTRAL-V01a - Piso 5 techos + maestro panel positions",
    "mapping": mapping,
}
with open(OUT_PATH, 'w') as f:
    json.dump(output, f, indent=2)

print("\n[OK] Guardado: {}".format(OUT_PATH))
print("Apartamentos con techo: {} / 20".format(len(mapping)))