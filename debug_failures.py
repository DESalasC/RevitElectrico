#!/usr/bin/env python3
"""Debug wall search for failing interruptores"""
import json
from pathlib import Path

# Load inventario
with open("data/inventarios/inventario_dispositivos_F01_v1.1_20261117_190929.json", "r", encoding="utf-8") as f:
    inv = json.load(f)

# Load muros from last run (we need to get them from MCP)
# For now, just show the failing devices
meta = inv["metadatos"]
apartamento = meta["apartamento_tipo"]
offset_x = 13990.9
offset_y = 8010.6
nivel_elevacion = meta["nivel_elevacion_m"]
panel_level = 192512

failing = ["A4", "AF", "B7", "BF"]
for d in inv["dispositivos"]:
    if d["handle"] in failing:
        x_mm = d["x"] * 1000 + offset_x
        y_mm = d["y"] * 1000 + offset_y
        z_mm = (nivel_elevacion + d["altura_local_m"]) * 1000
        print(f"\n{d['handle']} {d['nombre_dxf']}: {d['familia_revit']}|{d['tipo_revit']}")
        print(f"  DXF local: ({d['x']:.4f}, {d['y']:.4f}) m")
        print(f"  Proyecto: ({x_mm:.1f}, {y_mm:.1f}, {z_mm:.1f}) mm")
        print(f"  Rotación final: {d['rotacion_final_grados']}°")
        print(f"  Altura local: {d['altura_local_m']}m")
        print(f"  Nivel: {panel_level}")

print("\n--- Estos dispositivos necesitan muro que los 'mire' (dot > 0.5) ---")
print("Si el muro más cercano es paralelo al vector (punto - proyección), falla.")