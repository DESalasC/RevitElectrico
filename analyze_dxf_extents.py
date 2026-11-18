#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analizar extents del DXF F01 y F02 para entender sistema de coordenadas
"""

import ezdxf
from pathlib import Path

DXF_F01 = Path(r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 01.dxf")
DXF_F02 = Path(r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 02.dxf")

CAPAS_ELECTRICAS = [
    "ELEC-APPL-TOMAS",
    "ELEC-APPL-ILUM",
    "ELEC-APPL-NETWORD",
    "ELEC-Data-Service",
    "ELEC-CONTROL ILUM",
]

for name, path in [("F01", DXF_F01), ("F02", DXF_F02)]:
    print(f"\n=== {name}: {path.name} ===")
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')
    has_data = False
    
    # Buscar el panel TB-Panel / TB-Parcial
    for entity in msp:
        if entity.dxftype() == 'INSERT':
            if entity.dxf.name in ('TB-Panel', 'TB-Parcial'):
                x = float(entity.dxf.insert.x)
                y = float(entity.dxf.insert.y)
                print(f"  Panel {entity.dxf.name} @ ({x:.4f}, {y:.4f})")
                for attrib in entity.attribs:
                    print(f"    Attr: {attrib.dxf.tag} = {attrib.dxf.text}")
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                has_data = True
    
    # Ver coordenadas de algunos bloques eléctricos
    print(f"  Primeros 15 bloques eléctricos:")
    count = 0
    for entity in msp:
        if entity.dxftype() == 'INSERT' and count < 15:
            capa = entity.dxf.layer.upper()
            if any(capa.startswith(p) for p in CAPAS_ELECTRICAS):
                x = float(entity.dxf.insert.x)
                y = float(entity.dxf.insert.y)
                print(f"    {entity.dxf.name} @ ({x:.4f}, {y:.4f}) layer={entity.dxf.layer}")
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                has_data = True
                count += 1
    
    if has_data:
        print(f"  Extents (bloques eléctricos): X=[{min_x:.2f}, {max_x:.2f}], Y=[{min_y:.2f}, {max_y:.2f}]")
        centro_x = (min_x + max_x) / 2
        centro_y = (min_y + max_y) / 2
        print(f"  Centro: X={centro_x:.2f}, Y={centro_y:.2f}")
        print(f"  Tamaño: {max_x-min_x:.2f} x {max_y-min_y:.2f} metros")
    else:
        print("  No se encontraron bloques eléctricos")