#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Encontrar offset correcto F01: comparar inventario vs V02-f por matching de dispositivos
"""

import json
from pathlib import Path

DATA_DIR = Path(r"D:\Work\PROJECTS\RevitElectrico\data")

with open(DATA_DIR / "inventarios" / "inventario_dispositivos_F01_v1.1_20261117_190929.json", "r", encoding="utf-8") as f:
    inv = json.load(f)

with open(DATA_DIR / "v02f" / "dispositivos_v01.json", "r", encoding="utf-8") as f:
    v02f = json.load(f)

inv_devices = inv["dispositivos"]

# Filtrar V02-f: solo F01 (Y > 9000, X > 8000 aprox)
v02f_f01 = [d for d in v02f if d.get("y", 0) > 9000 and d.get("x", 0) > 8000]

print(f"Inventario F01: {len(inv_devices)} dispositivos")
print(f"V02-f candidatos F01: {len(v02f_f01)} dispositivos\n")

# Mapear familia/tipo inventario -> V02-f
fam_map = {
    "M_Toma doble": "M_Toma doble",
    "M_Interruptores": "M_Interruptores",
    "M_Iluminacion": "M_Iluminacion",
    "M_Comunicaciones": "M_Comunicaciones",
    "M_Climatizacion": "M_Climatizacion",
    "M_ClimatizacionV": "M_ClimatizacionV",
    "M_Timbre": "M_Zumbador",  # Campana -> Zumbador
    "Consolidation_Point": "Consolidation_Point",
    "M_Pulsador - Interruptor": "M_Pulsador - Interruptor",
    "M_Toma - 220V": "M_Toma - 220V",
    "EA": "M_Toma resistente a la intemperie",  # ELEC-EXT -> Intemperie
}

# Buscar matches por familia+tipo y calcular offset candidato
matches = []

for inv_d in inv_devices:
    if not inv_d.get("familia_revit"):
        continue
    
    inv_fam = inv_fam = inv_d["familia_revit"]
    inv_tipo = inv_d["tipo_revit"]
    inv_x_mm = inv_d["x"] * 1000
    inv_y_mm = inv_d["y"] * 1000
    
    v02f_fam = fam_map.get(inv_fam, inv_fam)
    
    # Buscar en V02-f misma familia+tipo
    candidates = [d for d in v02f_f01 
                  if d.get("fam") == v02f_fam and d.get("tipo") == inv_tipo]
    
    for cand in candidates:
        dx = cand["x"] - inv_x_mm
        dy = cand["y"] - inv_y_mm
        matches.append({
            "handle": inv_d["handle"],
            "familia": inv_fam,
            "tipo": inv_tipo,
            "dx": round(dx, 1),
            "dy": round(dy, 1),
            "v02f_x": cand["x"],
            "v02f_y": cand["y"],
            "inv_x": inv_x_mm,
            "inv_y": inv_y_mm,
        })

# Agrupar offsets y encontrar el más frecuente
from collections import Counter
offset_counter = Counter((m["dx"], m["dy"]) for m in matches)

print("Top 10 offsets candidatos:")
for (dx, dy), count in offset_counter.most_common(10):
    print(f"  Offset ({dx:>8.1f}, {dy:>8.1f}) mm -> {count} matches")

if offset_counter:
    best_offset = offset_counter.most_common(1)[0][0]
    print(f"\n>>> MEJOR OFFSET: X={best_offset[0]:.1f}, Y={best_offset[1]:.1f} mm")
    
    # Validar con este offset
    print(f"\nValidación con offset ({best_offset[0]:.1f}, {best_offset[1]:.1f}):")
    coinciden = 0
    for inv_d in inv_devices:
        if not inv_d.get("familia_revit"):
            continue
        inv_x = inv_d["x"] * 1000 + best_offset[0]
        inv_y = inv_d["y"] * 1000 + best_offset[1]
        
        # Buscar match en V02-f
        v02f_fam = fam_map.get(inv_d["familia_revit"], inv_d["familia_revit"])
        candidates = [d for d in v02f_f01 
                      if d.get("fam") == v02f_fam and d.get("tipo") == inv_d["tipo_revit"]]
        
        best_match = None
        best_dist = float("inf")
        for cand in candidates:
            dist = ((inv_x - cand["x"])**2 + (inv_y - cand["y"])**2)**0.5
            if dist < best_dist:
                best_dist = dist
                best_match = cand
        
        if best_match and best_dist <= 50:
            coinciden += 1
            status = "✓"
        else:
            status = "✗"
        
        if best_match:
            print(f"  {inv_d['handle']:>5} {inv_d['familia_revit']:>25} {inv_d['tipo_revit']:>15} | inv=({inv_x:>7.0f},{inv_y:>7.0f}) v02f=({best_match['x']:>7.0f},{best_match['y']:>7.0f}) dist={best_dist:.0f} {status}")
        else:
            print(f"  {inv_d['handle']:>5} {inv_d['familia_revit']:>25} {inv_d['tipo_revit']:>15} | inv=({inv_x:>7.0f},{inv_y:>7.0f}) NO MATCH")
    
    print(f"\n>>> COINCIDENCIAS: {coinciden}/{len([d for d in inv_devices if d.get('familia_revit')])}")