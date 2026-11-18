#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validar offsets correctos: panel_revit - panel_dxf_local
"""

import json
from pathlib import Path

DATA_DIR = Path(r"D:\Work\PROJECTS\RevitElectrico\data")

# ─── Offsets CORRECTOS ───
# Panel en DXF (coordenadas locales, metros)
panel_dxf_f01 = (-2.3995, -0.5048)  # m
panel_dxf_f02 = (-2.4403, 0.5056)   # m

# Panel en Revit (mm) - por PanelName
panel_revit_f01 = (11591.4, 7505.8)   # mm (TF 01)
panel_revit_f02 = (11597.1, 10160.3)  # mm (TF 02)

# Offset = Revit - DXF_local
offset_f01 = (panel_revit_f01[0] - panel_dxf_f01[0] * 1000, panel_revit_f01[1] - panel_dxf_f01[1] * 1000)
offset_f02 = (panel_revit_f02[0] - panel_dxf_f02[0] * 1000, panel_revit_f02[1] - panel_dxf_f02[1] * 1000)

print("=== OFFSETS CORRECTOS ===")
print(f"F01: DXF_local=({panel_dxf_f01[0]:.4f}, {panel_dxf_f01[1]:.4f}) m = ({panel_dxf_f01[0]*1000:.1f}, {panel_dxf_f01[1]*1000:.1f}) mm")
print(f"     Revit=({panel_revit_f01[0]:.1f}, {panel_revit_f01[1]:.1f}) mm")
print(f"     Offset = ({offset_f01[0]:.1f}, {offset_f01[1]:.1f}) mm")
print(f"F02: DXF_local=({panel_dxf_f02[0]:.4f}, {panel_dxf_f02[1]:.4f}) m = ({panel_dxf_f02[0]*1000:.1f}, {panel_dxf_f02[1]*1000:.1f}) mm")
print(f"     Revit=({panel_revit_f02[0]:.1f}, {panel_revit_f02[1]:.1f}) mm")
print(f"     Offset = ({offset_f02[0]:.1f}, {offset_f02[1]:.1f}) mm")

# ─── Cargar inventarios y V02-f ───
with open(DATA_DIR / "inventarios" / "inventario_dispositivos_F01_v1.1_20261117_190929.json", "r", encoding="utf-8") as f:
    inv_f01 = json.load(f)

with open(DATA_DIR / "inventarios" / "inventario_dispositivos_F02_v1.1_20261117_190933.json", "r", encoding="utf-8") as f:
    inv_f02 = json.load(f)

with open(DATA_DIR / "v02f" / "dispositivos_v01.json", "r", encoding="utf-8") as f:
    v02f = json.load(f)

# Filtrar V02-f por apartamento
v02f_f01 = [d for d in v02f if d.get("y", 0) > 9000 and d.get("x", 0) > 8000]
v02f_f02 = [d for d in v02f if d.get("y", 0) < 9000 and d.get("y", 0) > 3000 and d.get("x", 0) > 8000]

print(f"\nV02-f F01 candidatos: {len(v02f_f01)}")
print(f"V02-f F02 candidatos: {len(v02f_f02)}")

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

def test_apartamento(nombre, inv, offset, v02f_ref):
    print(f"\n=== VALIDACIÓN {nombre} ===")
    print(f"Offset: ({offset[0]:.1f}, {offset[1]:.1f}) mm")
    print("Dispositivo | Inventario DXF (m)    | Revit calc (mm)     | V02-f (mm)          | Delta (mm)")
    print("-" * 110)
    
    coinciden = 0
    total_con_mapeo = 0
    
    for d in inv["dispositivos"]:
        if not d.get("familia_revit"):
            continue
        total_con_mapeo += 1
        
        x_dxf_m = d["x"]
        y_dxf_m = d["y"]
        
        x_revit = x_dxf_m * 1000 + offset[0]
        y_revit = y_dxf_m * 1000 + offset[1]
        
        v02f_fam = fam_map.get(d["familia_revit"], d["familia_revit"])
        candidates = [v for v in v02f_ref 
                      if v.get("fam") == v02f_fam and v.get("tipo") == d["tipo_revit"]]
        
        best_match = None
        best_dist = float("inf")
        for cand in candidates:
            dist = ((x_revit - cand["x"])**2 + (y_revit - cand["y"])**2)**0.5
            if dist < best_dist:
                best_dist = dist
                best_match = cand
        
        if best_match and best_dist <= 50:
            coinciden += 1
            status = "✓"
        else:
            status = "✗"
        
        if best_match:
            print(f"{d['handle']:>10} | ({x_dxf_m:>7.4f}, {y_dxf_m:>7.4f}) | ({x_revit:>7.1f}, {y_revit:>7.1f}) | ({best_match['x']:>7.1f}, {best_match['y']:>7.1f}) | ({abs(x_revit-best_match['x']):>5.1f}, {abs(y_revit-best_match['y']):>5.1f}) {status}")
        else:
            print(f"{d['handle']:>10} | ({x_dxf_m:>7.4f}, {y_dxf_m:>7.4f}) | ({x_revit:>7.1f}, {y_revit:>7.1f}) | NO MATCH V02-f    | --- {status}")
    
    print(f"\n>>> {nombre}: {coinciden}/{total_con_mapeo} coinciden (≤50mm) = {coinciden/total_con_mapeo*100:.1f}%")
    return coinciden, total_con_mapeo

c1, t1 = test_apartamento("F01", inv_f01, offset_f01, v02f_f01)
c2, t2 = test_apartamento("F02", inv_f02, offset_f02, v02f_f02)

print(f"\n=== RESUMEN FINAL ===")
print(f"F01: {c1}/{t1} = {c1/t1*100:.1f}%")
print(f"F02: {c2}/{t2} = {c2/t2*100:.1f}%")
print(f"Total: {c1+c2}/{t1+t2} = {(c1+c2)/(t1+t2)*100:.1f}%")