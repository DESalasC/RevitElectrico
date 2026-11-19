# -*- coding: utf-8 -*-
# LISTAR_INSERTS_DESCONOCIDOS_v01.py - Listar INSERTs que no sean muebles/puertas/etc
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Nombres claros de apartamentos/mobiliario/estructura
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

print("=== INSERT DESCONOCIDOS (posiblemente eléctricos) ===")
unknown = []
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        if not any(name.startswith(p) for p in known_prefixes):
            # También excluir si contiene palabras clave de mobiliario
            name_lower = name.lower()
            furniture_keywords = ['mueble', 'closet', 'meson', 'espejo', 'sanitario', 
                                  'ducha', 'jabonera', 'toallero', 'portarrollos', 'percha',
                                  'lavamanos', 'lavabo', 'inodoro', 'bidet', 'bañera',
                                  'espejo', 'celosia', 'perfil', 'sanitario', 'aluvia',
                                  'corona', 'palma', 'quarztone', 'grisclasico', 'marolsinu',
                                  'cinza', 'cobalto', 'ducha', 'monocontrol', 'palma',
                                  'pro', 'shower', 'screen', 'duscholux', 'pivot', 'twin',
                                  'elevator', 'lift', 'ascensor', 'puerta', 'ventana',
                                  'corrediza', 'batiente', 'plegable', 'antisplash',
                                  'antipanico', 'deslizante', 'rejilla', 'corrediza',
                                  'revestimiento', 'ceramico', 'porcelanato', 'madera',
                                  'aluminio', 'hierro', 'acero', 'vidrio', 'cristal']
            if not any(k in name.lower() for k in furniture_keywords):
                unknown.append((entity.dxf.name, entity.dxf.layer, entity.dxf.insert.x, entity.dxf.insert.y))

for name, layer, x, y in sorted(unknown):
    print("  {} | Layer: {} | ({:.2f}, {:.2f})".format(name, layer, x, y))