#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validar offsets comparando vectores relativos al panel (device - panel)
"""

import json
from pathlib import Path

DATA_DIR = Path(r"D:\Work\PROJECTS\RevitElectrico\data")

# Panel positions
panel_revit_f01 = (11591.4, 7505.8)   # mm (TF 01 en CENTRAL-V01)
panel_revit_f02 = (11597.1, 10160.3)  # mm (TF 02 en CENTRAL-V01)
panel_dxf_f01 = (-2399.5, -504.8)     # mm (DXF local)
panel_dxf_f02 = (-2440.3, 505.6)      # mm (DXF local)

# Offset DXF->Revit
offset_f01 = (panel_revit_f01[0] - panel_dxf_f01[0], panel_revit_f01[1] - panel_dxf_f01[1])
offset_f02 = (panel_revit_f02[0] - panel_dxf_f02[0], panel_revit_f02[1] - panel_dxf_f02[1])

print(f"Offset F01: ({offset_f01[0]:.1f}, {offset_f01[1]:.1f}) mm")
print(f"Offset F02: ({offset_f02[0]:.1f}, {offset_f02[1]:.1f}) mm")

# Cargar datos
with open(DATA_DIR / "inventarios" / "inventario_dispositivos_F01_v1.1_20261117_190929.json", "r", encoding="utf-8") as f:
    inv_f01 = json.load(f)

with open(DATA_DIR / "inventarios" / "inventario_dispositivos_F02_v1.1_20261117_190933.json", "r", encoding="utf-8") as f:
    inv_f02 = json.load(f)

with open(DATA_DIR / "v02f" / "dispositivos_v01.json", "r", encoding="utf-8") as f:
    v02f = json.load(f)

# Filtrar V02-f
v02f_f01 = [d for d in v02f if d.get("y", 0) > 9000 and d.get("x", 0) > 8000]
v02f_f02 = [d for d in v02f if d.get("y", 0) < 9000 and d.get("y", 0) > 3000 and d.get("x", 0) > 8000]

# Estimar panel en V02-f promediando dispositivos de "panel-like" (cajas de conexiones, etc.)
# O mejor: usar el centroide de dispositivos de F01/F02 en V02-f como proxy del panel
def estimate_panel_v02f(devices):
    if not devices:
        return (0, 0)
    xs = [d["x"] for d in devices]
    ys = [d["y"] for d in devices]
    return (sum(xs)/len(xs), sum(ys)/len(ys))

panel_v02f_f01 = estimate_panel_v02f(v02f_f01)
panel_v02f_f02 = estimate_panel_v02f(v02f_f02)

print(f"\nPanel estimado V02-f F01: ({panel_v02f_f01[0]:.1f}, {panel_v02f_f01[1]:.1f}) mm")
print(f"Panel estimado V02-f F02: ({panel_v02f_f02[0]:.1f}, {panel_v02f_f02[1]:.1f}) mm")

# Calcular vectores relativos al panel en V02-f
v02f_rel_f01 = {}
v02f_rel_f02 = {}

fam_map = {
    "M_Toma doble": "M_Toma doble",
    "M_Interruptores": "M_Interruptores",
    "M_Iluminacion": "M_Iluminacion",
    "M_Comunicaciones": "M_Comunicaciones",
    "M_Climatizacion": "M_Climatizacion",
    "M_ClimatizacionV": "M_ClimatizacionV",
    "M_Timbre": "M_Zumbador",
    "Consolidation_Point": "Consolidation_Point",
    "M_Pulsador - Interruptor": "M_Pulsador - Interruptor",
    "M_Toma - 220V": "M_Toma - 220V",
    "EA": "M_Toma resistente a la intemperie",
}

for d in v02f_f01:
    v02f_fam = fam_map.get(d.get("fam", ""), d.get("fam", ""))
    key = f"{v02f_fam}_{d.get('tipo', '')}"
    rel_x = d["x"] - panel_v02f_f01[0]
    rel_y = d["y"] - panel_v02f_f01[1]
    if key not in v02f_rel_f01:
        v02f_rel_f01[key] = []
    v02f_rel_f01[key].append((rel_x, rel_y, d))

for d in v02f_f02:
    v02f_fam = fam_map.get(d.get("fam", ""), d.get("fam", ""))
    key = f"{v02f_fam}_{d.get('tipo', '')}"
    rel_x = d["x"] - panel_v02f_f02[0]
    rel_y = d["y"] - panel_v02f_f02[1]
    if key not in v02f_rel_f02:
        v02f_rel_f02[key] = []
    v02f_rel_f02[key].append((rel_x, rel_y, d))

# Promediar vectores relativos por familia+tipo en V02-f
v02f_avg_rel_f01 = {}
for key, vals in v02f_rel_f01.items():
    avg_x = sum(v[0] for v in vals) / len(vals)
    avg_y = sum(v[1] for v in vals) / len(vals)
    v02f_avg_rel_f01[key] = (avg_x, avg_y, len(vals))

v02f_avg_rel_f02 = {}
for key, vals in v02f_rel_f02.items():
    avg_x = sum(v[0] for v in vals) / len(vals)
    avg_y = sum(v[1] for v in vals) / len(vals)
    v02f_avg_rel_f02[key] = (avg_x, avg_y, len(vals))

print(f"\nVectores relativos promedio V02-f F01 ({len(v02f_avg_rel_f01)} tipos):")
for key, (rx, ry, cnt) in sorted(v02f_avg_rel_f01.items()):
    print(f"  {key}: ({rx:.1f}, {ry:.1f}) mm [{cnt}]")

print(f"\nVectores relativos promedio V02-f F02 ({len(v02f_avg_rel_f02)} tipos):")
for key, (rx, ry, cnt) in sorted(v02f_avg_rel_f02.items()):
    print(f"  {key}: ({rx:.1f}, {ry:.1f}) mm [{cnt}]")

# Ahora calcular vectores relativos del inventario (usando offset)
print(f"\n=== VALIDACIÓN VECTORES RELATIVOS F01 ===")
coinciden_f01 = 0
total_f01 = 0

for d in inv_f01["dispositivos"]:
    if not d.get("familia_revit"):
        continue
    total_f01 += 1
    
    x_dxf = d["x"] * 1000
    y_dxf = d["y"] * 1000
    
    # Vector relativo al panel en DXF
    rel_x_dxf = x_dxf - panel_dxf_f01[0]
    rel_y_dxf = y_dxf - panel_dxf_f01[1]
    
    # Vector relativo en Revit (después de offset)
    x_revit = x_dxf + offset_f01[0]
    y_revit = y_dxf + offset_f01[1]
    rel_x_revit = x_revit - panel_revit_f01[0]
    rel_y_revit = y_revit - panel_revit_f01[1]
    
    # Comparar con V02-f
    key = f"{d['familia_revit']}_{d['tipo_revit']}"
    v02f_rel = v02f_avg_rel_f01.get(key)
    
    if v02f_rel:
        vx, vy, cnt = v02f_rel
        dx = abs(rel_x_revit - vx)
        dy = abs(rel_y_revit - vy)
        dist = (dx**2 + dy**2)**0.5
        ok = dist <= 100  # tolerancia 100mm para vectores relativos
        status = "✓" if ok else "✗"
        if ok:
            coinciden_f01 += 1
        print(f"  {d['handle']:>5} {key:>30} | rel_revit=({rel_x_revit:>7.1f},{rel_y_revit:>7.1f}) rel_v02f=({vx:>7.1f},{vy:>7.1f}) delta=({dx:.1f},{dy:.1f}) dist={dist:.1f} {status}")
    else:
        print(f"  {d['handle']:>5} {key:>30} | rel_revit=({rel_x_revit:>7.1f},{rel_y_revit:>7.1f}) NO MATCH V02-f")

print(f"\nF01: {coinciden_f01}/{total_f01} = {coinciden_f01/total_f01*100:.1f}%")

# F02
print(f"\n=== VALIDACIÓN VECTORES RELATIVOS F02 ===")
coinciden_f02 = 0
total_f02 = 0

for d in inv_f02["dispositivos"]:
    if not d.get("familia_revit"):
        continue
    total_f02 += 1
    
    x_dxf = d["x"] * 1000
    y_dxf = d["y"] * 1000
    
    rel_x_dxf = x_dxf - panel_dxf_f02[0]
    rel_y_dxf = y_dxf - panel_dxf_f02[1]
    
    x_revit = x_dxf + offset_f02[0]
    y_revit = y_dxf + offset_f02[1]
    rel_x_revit = x_revit - panel_revit_f02[0]
    rel_y_revit = y_revit - panel_revit_f02[1]
    
    key = f"{d['familia_revit']}_{d['tipo_revit']}"
    v02f_rel = v02f_avg_rel_f02.get(key)
    
    if v02f_rel:
        vx, vy, cnt = v02f_rel
        dx = abs(rel_x_revit - vx)
        dy = abs(rel_y_revit - vy)
        dist = (dx**2 + dy**2)**0.5
        ok = dist <= 100
        status = "✓" if ok else "✗"
        if ok:
            coinciden_f02 += 1
        print(f"  {d['handle']:>5} {key:>30} | rel_revit=({rel_x_revit:>7.1f},{rel_y_revit:>7.1f}) rel_v02f=({vx:>7.1f},{vy:>7.1f}) delta=({dx:.1f},{dy:.1f}) dist={dist:.1f} {status}")
    else:
        print(f"  {d['handle']:>5} {key:>30} | rel_revit=({rel_x_revit:>7.1f},{rel_y_revit:>7.1f}) NO MATCH V02-f")

print(f"\nF02: {coinciden_f02}/{total_f02} = {coinciden_f02/total_f02*100:.1f}%")
print(f"\nTotal: {coinciden_f01+coinciden_f02}/{total_f01+total_f02} = {(coinciden_f01+coinciden_f02)/(total_f01+total_f02)*100:.1f}%")