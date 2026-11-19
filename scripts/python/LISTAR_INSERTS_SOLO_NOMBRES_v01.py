# -*- coding: utf-8 -*-
# LISTAR_INSERTS_SOLO_NOMBRES_v01.py - Solo nombres de INSERTs únicos
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Nombres claros de apartamentos/mobiliario/estructura - solo prefijos
known_prefixes = [
    'Apartamento', 'Apartamentos', 'ELEC-Apartamento', 'ApaRtamento',
    'FJR_A_', 'Hormigón', 'Railing', 'Top Rail', 'Grid', 'Level', 'View',
    'Section', 'Callout', 'Title', 'Spot', 'Elevation', 'Symbol',
    'Detail', 'Profile', 'Baluster', 'Stair', 'Landing', 'Run', 'Riser',
    'Cable', 'Conduit', 'Wire', 'Pipe', 'Duct', 'Fitting', 'Structural',
    'Column', 'Beam', 'Foundation', 'Floor', 'Roof', 'Wall', 'Door',
    'Window', 'Curtain', 'Mullion', 'Panel', 'Family', 'Type', 'Schedule',
    'Legend', 'Color', 'Fill', 'Zone', 'System', 'Piping', 'Mechanical',
    'Equipment', 'Set', 'Analytical', 'Connection', 'Handrail', 'Tread',
    'Riser', 'Stringer', 'Carriage', 'Support', 'Category', 'Template',
    'Reference', 'Viewport', 'Label', 'Mark', 'Tag', 'Keynote',
    'Dimension', 'Text', 'Note', 'Mass', 'Opening', 'Soffit', 'Edge',
    'Gutter', 'Fascia', 'Pad', 'Site', 'Property', 'Link', 'RVT'
]

print("=== INSERT NO RECONOCIDOS ===")
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        if not any(name.startswith(p) for p in known_prefixes):
            print("  {} | Layer: {} | ({:.2f}, {:.2f})".format(
                entity.dxf.name, entity.dxf.layer, entity.dxf.insert.x, entity.dxf.insert.y))