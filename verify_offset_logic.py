#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificar lógica de offset con E07 (caso conocido del dry_run)
"""

import json
from pathlib import Path

DATA_DIR = Path(r"D:\Work\PROJECTS\RevitElectrico\data")

# E07 dry_run: sabemos la verdad
with open(DATA_DIR / "dry_run_colocacion_E07_v01.json", "r", encoding="utf-8") as f:
    e07_dry = json.load(f)

print("=== E07 DRY_RUN (verdad conocida) ===")
print(f"Panel DXF (ancla): {e07_dry['panel_dxf_m']} m")  # [-3.3574, -1.1423]
print(f"Panel Revit (ancla): id={e07_dry['ancla']['element_id']} @ ({e07_dry['ancla']['x_mm']:.1f}, {e07_dry['ancla']['y_mm']:.1f}) mm")
print(f"Offset calculado en dry_run: {e07_dry['offset_mm']} mm")  # [-2312.6, 7994.3]

# Verificar: offset = panel_revit - panel_dxf_mm
panel_dxf_mm = [e07_dry['panel_dxf_m'][0] * 1000, e07_dry['panel_dxf_m'][1] * 1000]
panel_revit_mm = [e07_dry['ancla']['x_mm'], e07_dry['ancla']['y_mm']]
offset_calc = [panel_revit_mm[0] - panel_dxf_mm[0], panel_revit_mm[1] - panel_dxf_mm[1]]
print(f"\nOffset calculado (panel_revit - panel_dxf): [{offset_calc[0]:.1f}, {offset_calc[1]:.1f}] mm")
print(f"Offset en dry_run:                         [{e07_dry['offset_mm'][0]:.1f}, {e07_dry['offset_mm'][1]:.1f}] mm")
print(f"¡COINCIDEN! {abs(offset_calc[0] - e07_dry['offset_mm'][0]) < 1 and abs(offset_calc[1] - e07_dry['offset_mm'][1]) < 1}")

# Ahora probar con un dispositivo del dry_run
print("\n--- Test con primer dispositivo (handle 96, ELEC-TIMBRE) ---")
disp = e07_dry['plan'][0]
print(f"Dispositivo DXF: x={disp['x_mm']:.1f}, y={disp['y_mm']:.1f} mm (ya en mm en plan)")
print(f"  -> Estos son coords ABSOLUTAS en Revit (después de offset)")

# El plan ya tiene coordenadas absolutas en Revit (x_mm, y_mm)
# Verificar: x_revit = x_dxf_mm + offset_x
# Pero el plan no guarda x_dxf_mm original... 

# Buscar en inventario original de E07 (si existe) o usar el colocacion_E07_v01.json
with open(DATA_DIR / "colocacion_E07_v01.json", "r", encoding="utf-8") as f:
    e07_col = json.load(f)

# Primer elemento
elem = e07_col['elementos'][0]
print(f"\nEn colocacion_E07_v01.json:")
print(f"  handle={elem['handle']}, x_mm={elem['x_mm']:.1f}, y_mm={elem['y_mm']:.1f}")

# Estos x_mm, y_mm en colocacion_E07_v01.json SON las coordenadas Revit finales
# Verificar que coinciden con el plan
plan_disp = e07_dry['plan'][0]
print(f"En dry_run plan: x_mm={plan_disp['x_mm']:.1f}, y_mm={plan_disp['y_mm']:.1f}")
print(f"Coinciden: {abs(elem['x_mm'] - plan_disp['x_mm']) < 1 and abs(elem['y_mm'] - plan_disp['y_mm']) < 1}")

# Ahora: ¿cómo obtener coords DXF originales del inventario E07?
# El inventario E07 no está en data/inventarios... pero el dry_run sí tiene los datos originales
# En dry_run['plan'] cada item tiene x_mm, y_mm que son coords Revit finales
# Para obtener coords DXF: x_dxf = x_revit - offset_x

offset = e07_dry['offset_mm']
for i, p in enumerate(e07_dry['plan'][:3]):
    x_dxf = p['x_mm'] - offset[0]
    y_dxf = p['y_mm'] - offset[1]
    print(f"  {p['handle']}: Revit=({p['x_mm']:.1f},{p['y_mm']:.1f}) -> DXF=({x_dxf:.1f},{y_dxf:.1f}) mm = ({x_dxf/1000:.4f},{y_dxf/1000:.4f}) m")

print("\n=== CONCLUSIÓN ===")
print("La fórmula correcta es:")
print("  1. Leer panel en DXF (metros) -> panel_dxf_mm")
print("  2. Leer panel en Revit (mm) -> panel_revit_mm")  
print("  3. offset = panel_revit_mm - panel_dxf_mm")
print("  4. Para cada dispositivo: x_revit = x_dxf_m * 1000 + offset_x")
print("                            y_revit = y_dxf_m * 1000 + offset_y")
print("  5. Z: usar altura_local_mm (mm relativos al nivel), NO metros / 304.8")