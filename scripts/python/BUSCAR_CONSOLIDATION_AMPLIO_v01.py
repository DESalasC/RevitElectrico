# -*- coding: utf-8 -*-
# BUSCAR_CONSOLIDATION_AMPLIO_v01.py - Búsqueda amplia de puntos de consolidación
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Buscar todos los INSERT únicos que no sean apartamentos/puertas/ventanas/muebles
exclude_keywords = ['apartament', 'puerta', 'ventana', 'mueble', 'sanitario', 'closet', 
                    'meson', 'espejo', 'perfil', 'railing', 'top rail', 'pilar', 'hormigon',
                    'ducha', 'jabonera', 'toallero', 'portarrollos', 'percha', 'ascensor',
                    'shower', 'drain', 'grid', 'level', 'view', 'section', 'callout',
                    'title', 'profile', 'baluster', 'stair', 'landing', 'run', 'riser',
                    'cable', 'conduit', 'wire', 'pipe', 'duct', 'fitting', 'cable tray',
                    'structural', 'column', 'beam', 'foundation', 'floor', 'roof', 'wall',
                    'door', 'window', 'curtain', 'mullion', 'panel', 'family', 'type',
                    'shut', 'celosia', 'antisplash', 'antipanico', 'deslizante', 'plegable',
                    'corrediza', 'batiente', 'corona', 'palma', 'aluvia', 'quarztone',
                    'grisclasico', 'marolsinu', 'cinza', 'cobalto', 'ducha', 'monocontrol',
                    'palma', 'pro', 'shower', 'screen', 'duscholux', 'pivot', 'twin',
                    'elevator', 'lift', 'escalera', 'rampa', 'baranda', 'pasamanos',
                    'extremo', 'revision', 'cloud', 'spot', 'elevation', 'symbol',
                    'annotation', 'detail', 'item', 'component', 'mass', 'opening',
                    'soffit', 'edge', 'gutter', 'fascia', 'pad', 'site', 'property',
                    'link', 'rvt', 'schedule', 'legend', 'color', 'fill', 'zone',
                    'system', 'piping', 'mechanical', 'equipment', 'set', 'analytical',
                    'connection', 'handrail', 'tread', 'riser', 'stringer', 'carriage',
                    'support', 'category', 'template', 'view', 'reference', 'viewport',
                    'label', 'mark', 'tag', 'keynote', 'dimension', 'text', 'note']

print("=== INSERT POTENCIALEMENTE ELÉCTRICOS ===")
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        # Filtrar nombres conocidos de apartamentos/mobiliario
        if not any(k in name.lower() for k in exclude_keywords):
            # Ver si parece eléctrico
            name_lower = name.lower()
            if any(k in name_lower for k in ['elec', 'elec-', 'm_', 'toma', 'interrupt', 'luz', 'ventil', 'extractor', 
                                             'cp', 'consolid', 'telecom', 'datos', 'telefon', 'timbre', 'campana', 
                                             'extintor', 'ea', 'net', 'pau', 'consolid', 'punto', 'conexion',
                                             'caja', 'registro', 'derivacion', 'punto', 'consolidation']):
                print("  {} | Layer: {} | Pos: ({:.2f},{:.2f})".format(
                    entity.dxf.name, entity.dxf.layer, entity.dxf.insert.x, entity.dxf.insert.y))

print("\n=== TAMBIÉN BUSCAR POR LAYER ELÉCTRICO ===")
# Buscar layers que parezcan eléctricos
elec_layers = set()
for entity in msp:
    if entity.dxftype() == 'INSERT':
        layer = entity.dxf.layer.lower()
        if any(k in layer for k in ['elec', 'electric', 'telecom', 'data', 'voz', 'datos', 'red', 'network']):
            elec_layers.add(entity.dxf.layer)

print("Layers eléctricos: {}".format(sorted(elec_layers)))