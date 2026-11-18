#!/usr/bin/env python3
"""Fix inventarios F01/F02: CA -> M_Climatizacion|Interruptor Ventilador"""
import json
from pathlib import Path

def fix_inventario(path):
    with open(path, "r", encoding="utf-8") as f:
        inv = json.load(f)
    
    changes = 0
    for d in inv["dispositivos"]:
        if d["handle"] == "CA" and d["nombre_dxf"] == "ELEC-F-CONTROL":
            print(f"  {path.name}: CA ELEC-F-CONTROL: {d['familia_revit']}|{d['tipo_revit']} -> M_Climatizacion|Interruptor Ventilador")
            d["familia_revit"] = "M_Climatizacion"
            d["tipo_revit"] = "Interruptor Ventilador"
            changes += 1
    
    if changes:
        # Update hash to force re-validation (or keep same since DXF unchanged)
        # Just save
        with open(path, "w", encoding="utf-8") as f:
            json.dump(inv, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Guardado: {changes} cambios")
    else:
        print(f"  Sin cambios")

fix_inventario(Path("data/inventarios/inventario_dispositivos_F01_v1.1_20261117_190929.json"))
fix_inventario(Path("data/inventarios/inventario_dispositivos_F02_v1.1_20261117_190933.json"))