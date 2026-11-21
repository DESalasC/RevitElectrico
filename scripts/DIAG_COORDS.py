# -*- coding: utf-8 -*-
"""
DIAG_COORDS.py - Diagnosticar discrepancia de coordenadas
"""

import json

with open('data/maestro_colocacion_piso5.json', 'r') as f:
    maestro = json.load(f)

with open('data/ceilings_mapping_apto.json', 'r') as f:
    ceilings = json.load(f)

FT_TO_M = 0.3048

print("=== ANÁLISIS COORDENADAS F17, F18, E06, E07 ===\n")

for apto in ['F17', 'F18', 'E06', 'E07']:
    m = maestro['apartamentos'].get(apto)
    c = ceilings['mapping'].get(apto)
    
    if not m or not c:
        print("{} : FALTAN DATOS".format(apto))
        continue
    
    # Panel Revit (metros -> pies)
    panel_x_ft = m['panel_revit_m']['x'] / FT_TO_M
    panel_y_ft = m['panel_revit_m']['y'] / FT_TO_M
    
    # Techo bounds (ya en pies, globales DXF)
    b = c['ceiling_bounds_ft']
    techo_xmin, techo_xmax = b['xmin'], b['xmax']
    techo_ymin, techo_ymax = b['ymin'], b['ymax']
    techo_center_x = c['ceiling_center_ft']['x']
    techo_center_y = c['ceiling_center_ft']['y']
    
    # Offset maestro (DXF base -> Revit panel) en metros -> pies
    # El offset en el maestro es: offset_m = panel_revit_m - base_dxf_m
    # Pero necesitamos: techo_local = techo_global + offset
    # Donde offset = panel_revit - (base_dxf en metros)
    
    print("=== {} ===".format(apto))
    print("  Panel Revit: ({:.2f}, {:.2f}) ft".format(panel_x_ft, panel_y_ft))
    print("  Techo Global: Centro=({:.2f}, {:.2f}) Bounds X=[{:.2f},{:.2f}] Y=[{:.2f},{:.2f}]".format(
        techo_center_x, techo_center_y, techo_xmin, techo_xmax, techo_ymin, techo_ymax))
    
    # Calcular offset implícito: panel_revit - techo_center
    dx = panel_x_ft - techo_center_x
    dy = panel_y_ft - techo_center_y
    print("  Delta Panel-Techo_Centro: ({:.2f}, {:.2f}) ft".format(dx, dy))
    
    # Verificar si los dispositivos caen dentro del techo global
    devices = m['dispositivos']
    in_techo = 0
    for dev in devices[:10]:
        x = dev['posicion_revit_m']['x'] / FT_TO_M
        y = dev['posicion_revit_m']['y'] / FT_TO_M
        if techo_xmin <= x <= techo_xmax and techo_ymin <= y <= techo_ymax:
            in_techo += 1
    print("  Dispositivos en techo global (primeros 10): {}/10".format(in_techo))
    print()