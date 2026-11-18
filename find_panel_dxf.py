#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Encontrar panel en DXF F01 y F02
"""

import ezdxf
from pathlib import Path

DXF_F01 = Path(r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 01.dxf")
DXF_F02 = Path(r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 02.dxf")

for name, path in [("F01", DXF_F01), ("F02", DXF_F02)]:
    print(f"\n=== {name}: {path.name} ===")
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    
    # Buscar bloques que puedan ser paneles (ELEC-PANEL, T01, TF01, etc.)
    panel_candidates = []
    for entity in msp:
        if entity.dxftype() == 'INSERT':
            block_name = entity.dxf.name
            x, y = entity.dxf.insert.x, entity.dxf.insert.y
            # Buscar nombres que contengan PANEL, T01, TF, TABLERO, etc.
            if any(kw in block_name.upper() for kw in ['PANEL', 'T01', 'TF', 'TABLERO', 'BOARD', 'CUADRO']):
                panel_candidates.append((block_name, x, y))
                print(f"  INSERT: {block_name} @ ({x:.4f}, {y:.4f})")
    
    if not panel_candidates:
        # Listar todos los bloques INSERT únicos
        blocks = {}
        for entity in msp:
            if entity.dxftype() == 'INSERT':
                blocks[entity.dxf.name] = blocks.get(entity.dxf.name, 0) + 1
        print(f"  Bloques INSERT únicos ({len(blocks)}):")
        for b, count in sorted(blocks.items()):
            print(f"    {b}: {count} instancias")
    
    # También buscar textos con "T01", "TF01", "PANEL"
    print(f"  Textos relevantes:")
    for entity in msp:
        if entity.dxftype() in ('TEXT', 'MTEXT'):
            text = entity.plain_text() if entity.dxftype() == 'MTEXT' else entity.dxf.text
            if any(kw in text.upper() for kw in ['T01', 'TF01', 'PANEL', 'TABLERO', 'F 01', 'F01']):
                x, y = entity.dxf.insert.x, entity.dxf.insert.y
                print(f"    \"{text}\" @ ({x:.4f}, {y:.4f})")