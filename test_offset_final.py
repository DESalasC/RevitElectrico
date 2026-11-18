#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test rápido: verificar offset F01/F02 con datos reales
"""

import json
import ezdxf
from pathlib import Path

DATA_DIR = Path(r"D:\Work\PROJECTS\RevitElectrico\data")
ARCHIVOS_BASE_DIR = Path(r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase")

# 1. Panel en Revit (consultado via MCP)
panel_revit = {
    "F 01": {"name": "TF 01", "x": 11591.4, "y": 7505.8, "levelId": 192512, "id": 5501141},
    "F 02": {"name": "TF 02", "x": 11597.1, "y": 10160.3, "levelId": 192512, "id": 5481263},
}

# 2. Panel en DXF local (leído del archivo)
for apto in ["F 01", "F 02"]:
    target = panel_revit[apto]["name"]
    dxf_file = f"Apartamento Tipo {apto}.dxf"
    dxf_path = ARCHIVOS_BASE_DIR / dxf_file
    
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    
    panel_dxf = None
    for entity in msp:
        if entity.dxftype() == 'INSERT' and entity.dxf.name in ('TB-Panel', 'TB-Parcial'):
            for attrib in entity.attribs:
                if attrib.dxf.tag.upper() == 'TABLERO' and attrib.dxf.text.strip() == target:
                    panel_dxf = (float(entity.dxf.insert.x), float(entity.dxf.insert.y))
                    break
    
    if panel_dxf:
        panel_dxf_mm = (panel_dxf[0] * 1000, panel_dxf[1] * 1000)
        panel_rev = (panel_revit[apto]["x"], panel_revit[apto]["y"])
        offset = (panel_rev[0] - panel_dxf_mm[0], panel_rev[1] - panel_dxf_mm[1])
        
        print(f"\n{apto}:")
        print(f"  Panel Revit ({target}): ({panel_rev[0]:.1f}, {panel_rev[1]:.1f}) mm")
        print(f"  Panel DXF local: ({panel_dxf[0]:.4f}, {panel_dxf[1]:.4f}) m = ({panel_dxf_mm[0]:.1f}, {panel_dxf_mm[1]:.1f}) mm")
        print(f"  Offset = ({offset[0]:.1f}, {offset[1]:.1f}) mm")
        
        # Verificar: panel_revit = panel_dxf_mm + offset
        check = (panel_dxf_mm[0] + offset[0], panel_dxf_mm[1] + offset[1])
        print(f"  Check (DXF+Offset): ({check[0]:.1f}, {check[1]:.1f}) = Revit? {abs(check[0]-panel_rev[0])<1 and abs(check[1]-panel_rev[1])<1}")
        
        # Test con un dispositivo del inventario
        inv_file = f"inventario_dispositivos_{apto.replace(' ', '')}_v1.1_20261117_190929.json" if apto == "F 01" else f"inventario_dispositivos_{apto.replace(' ', '')}_v1.1_20261117_190933.json"
        with open(DATA_DIR / "inventarios" / inv_file, "r", encoding="utf-8") as f:
            inv = json.load(f)
        
        # Primer dispositivo con mapeo
        for d in inv["dispositivos"]:
            if d.get("familia_revit"):
                x_revit = d["x"] * 1000 + offset[0]
                y_revit = d["y"] * 1000 + offset[1]
                print(f"  Test {d['handle']}: DXF=({d['x']:.4f},{d['y']:.4f})m -> Revit=({x_revit:.1f},{y_revit:.1f})mm")
                break
    else:
        print(f"\n{apto}: NO se encontró panel {target} en DXF")