#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test aislado: validar transformación de coordenadas F01/F02
===========================================================
Verifica que la conversión metros(DXF) + offset_panel(mm) -> Revit(mm) produce
coordenadas correctas comparando contra referencia V02-f.
"""

import json
from pathlib import Path

REVITELECTRICO_ROOT = Path(r"D:\Work\PROJECTS\RevitElectrico")
DATA_DIR = REVITELECTRICO_ROOT / "data"

# ─── Cargar inventario F01 ───
INVENTARIO_F01 = DATA_DIR / "inventarios" / "inventario_dispositivos_F01_v1.1_20261117_190929.json"
V02F_REF = DATA_DIR / "v02f" / "dispositivos_v01.json"

with open(INVENTARIO_F01, "r", encoding="utf-8") as f:
    inv = json.load(f)

with open(V02F_REF, "r", encoding="utf-8") as f:
    v02f = json.load(f)

dispositivos = inv["dispositivos"]
meta = inv["metadatos"]

# Panel objetivo para F01 (según análisis previo: id=5501141 @ X=11591.4, Y=7505.8 mm)
PANEL_OFFSET_X_MM = 11591.4
PANEL_OFFSET_Y_MM = 7505.8

print(f"=== TEST TRANSFORMACIÓN COORDENADAS F01 ===\n")
print(f"Panel offset: X={PANEL_OFFSET_X_MM:.1f}, Y={PANEL_OFFSET_Y_MM:.1f} mm")
print(f"Nivel elevación: {meta['nivel_elevacion_m']} m = {meta['nivel_elevacion_m']*1000:.0f} mm\n")

# ─── Indexar referencia V02-f por handle aproximado ───
# V02-f usa coordenadas en mm, inventario en metros
v02f_index = {}
for d in v02f:
    # Filtrar solo dispositivos que parecen ser de F01 (Y ~ 7500-16000)
    if d.get("y", 0) > 7000:
        key = f"{d.get('fam','')}_{d.get('tipo','')}_{round(d.get('x',0))}_{round(d.get('y',0))}"
        v02f_index[key] = d

print(f"Referencia V02-f indexada: {len(v02f_index)} dispositivos candidatos F01\n")

# ─── Test transformación ───
print("Dispositivo | Inventario (m)     | +Offset (mm)  | Revit XY (mm)   | V02-f XY (mm)   | Delta XY (mm)")
print("-" * 120)

errores = 0
coincidencias = 0

for d in dispositivos:
    # Inventario: x, y en METROS relativos al origen apartamento (DXF)
    x_m = d["x"]
    y_m = d["y"]
    
    # Transformación CORREGIDA: metros -> mm + offset panel
    x_revit_mm = x_m * 1000 + PANEL_OFFSET_X_MM
    y_revit_mm = y_m * 1000 + PANEL_OFFSET_Y_MM
    
    # Buscar en V02-f por proximidad (clave aproximada)
    key = f"{d['familia_revit']}_{d['tipo_revit']}_{round(x_revit_mm)}_{round(y_revit_mm)}"
    ref = v02f_index.get(key)
    
    if ref:
        dx = abs(x_revit_mm - ref.get("x", 0))
        dy = abs(y_revit_mm - ref.get("y", 0))
        ok = dx <= 50 and dy <= 50  # tolerancia 50mm
        status = "✓" if ok else "✗"
        if ok:
            coincidencias += 1
        else:
            errores += 1
        print(f"{d['handle']:>10} | ({x_m:>7.4f}, {y_m:>7.4f}) | (+{PANEL_OFFSET_X_MM:>7.1f},+{PANEL_OFFSET_Y_MM:>7.1f}) | ({x_revit_mm:>7.1f},{y_revit_mm:>7.1f}) | ({ref.get('x',0):>7.1f},{ref.get('y',0):>7.1f}) | ({dx:>5.1f},{dy:>5.1f}) {status}")
    else:
        # Sin match en V02-f, solo mostrar transformación
        print(f"{d['handle']:>10} | ({x_m:>7.4f}, {y_m:>7.4f}) | (+{PANEL_OFFSET_X_MM:>7.1f},+{PANEL_OFFSET_Y_MM:>7.1f}) | ({x_revit_mm:>7.1f},{y_revit_mm:>7.1f}) | (no match)     | ---")

print(f"\n=== RESUMEN ===")
print(f"Total dispositivos: {len(dispositivos)}")
print(f"Con match en V02-f: {coincidencias + errores}")
print(f"✓ Coinciden (≤50mm): {coincidencias}")
print(f"✗ Fuera de tolerancia: {errores}")

# ─── Test Z (altura) ───
print(f"\n=== TEST ALTURA (Z) ===")
print("Dispositivo | altura_local_m | z_absoluta_m | Z esperado Revit (mm) | Z V02-f (mm)")
print("-" * 85)

for d in dispositivos[:10]:  # muestra primera decena
    h_local_mm = d["altura_local_m"] * 1000
    z_abs_mm = d["z_absoluta_m"] * 1000
    # En Revit level-based: Z = altura_local_m (relativa al nivel)
    # En V02-f: Z absoluta del proyecto
    nivel_mm = meta["nivel_elevacion_m"] * 1000  # 13220 mm
    z_revit_rel_mm = h_local_mm  # relativa al nivel
    
    key = f"{d['familia_revit']}_{d['tipo_revit']}_{round(PANEL_OFFSET_X_MM + d['x']*1000)}_{round(PANEL_OFFSET_Y_MM + d['y']*1000)}"
    ref = v02f_index.get(key)
    z_ref = ref.get("z", 0) if ref else "N/A"
    
    print(f"{d['handle']:>10} | {d['altura_local_m']:>13.3f} | {d['z_absoluta_m']:>11.3f} | {z_revit_rel_mm:>18.0f} (rel) | {z_ref}")

# ─── Verificar bug anterior (Z en metros dividido por 304.8) ───
print(f"\n=== BUG ANTERIOR: Z en metros / 304.8 ===")
for d in dispositivos[:5]:
    z_m = d["altura_local_m"]  # ej: 0.3
    z_bug_feet = z_m / 304.8  # 0.3 / 304.8 = 0.00098 ft
    z_bug_mm = z_bug_feet * 304.8  # 0.3 mm
    z_correct_feet = z_m * 3.28084  # 0.3 m = 0.984 ft
    z_correct_mm = z_correct_feet * 304.8  # 300 mm
    print(f"  {d['handle']}: altura_local={z_m}m -> BUG Z={z_bug_mm:.1f}mm | CORRECTO Z={z_correct_mm:.0f}mm (rel nivel)")

print(f"\n✅ Test completado. Si coincidencias ≥ 30/34, transformación XY es correcta.")
print(f"⚠ Z debe enviarse en mm (altura_local_mm) para consistencia, no en metros.")