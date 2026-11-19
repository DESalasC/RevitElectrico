# -*- coding: utf-8 -*-
# BUSCAR_BLOQUES_ELECTRICOS_DXF_v01.py - Buscar solo bloques eléctricos/comunicaciones
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Buscar INSERTs con nombres que parezcan eléctricos
keywords = ['toma', 'interrupt', 'luz', 'lamp', 'ventil', 'extractor', 'cp', 'consolid', 
            'telecom', 'datos', 'telefon', 'timbre', 'campana', 'extintor', 'ea']

print("=== INSERCIONES ELÉCTRICAS/COMUNICACIONES ===")
count = 0
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name.lower()
        layer = entity.dxf.layer
        pos = (entity.dxf.insert.x, entity.dxf.insert.y)
        
        if any(k in name for k in ['toma', 'interrupt', 'luz', 'lamp', 'ventil', 'extractor',
                                    'cp', 'consolid', 'telecom', 'datos', 'telefon',
                                    'timbre', 'campana', 'extintor', 'ea', 'm_']):
            attribs = {}
            for attrib in entity.attribs:
                attribs[attrib.dxf.tag] = attrib.dxf.text
            print("  {} | Layer: {} | Pos: ({:.2f},{:.2f}) | Rot: {:.1f} | Attrs: {}".format(
                entity.dxf.name, layer, pos[0], pos[1], entity.dxf.rotation, attribs))
            count += 1

print("\nTotal encontradas: {}".format(count))