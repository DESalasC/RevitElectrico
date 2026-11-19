# -*- coding: utf-8 -*-
# DEBUG_ELEC_NET_PAY_v01.py - Ver capas de ELEC-NET-PAU
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Buscar ELEC-NET-PAU y ver sus layers
print("=== BUSCANDO ELEC-NET-PAU ===")
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        if "ELEC-NET-PAU" in name:
            print("  Name: {}".format(name))
            print("  Layer: {}".format(entity.dxf.layer))
            print("  Pos: ({:.2f}, {:.2f})".format(entity.dxf.insert.x, entity.dxf.insert.y))
            print("  Rot: {:.1f}".format(entity.dxf.rotation))
            print("  Handle: {}".format(entity.dxf.handle))
            attribs = {}
            for attrib in entity.attribs:
                attribs[attrib.dxf.tag] = attrib.dxf.text
            print("  Attrs: {}".format(attribs))
            print()

# También ver qué layers existen
print("\n=== LAYERS CON 'ELEC' O 'APARTAMENTO' ===")
layers_seen = set()
for entity in msp:
    if entity.dxftype() == 'INSERT':
        layer = entity.dxf.layer
        if 'elec' in layer.lower() or 'apartament' in layer.lower() or 'tipo' in layer.lower():
            layers_seen.add(layer)

for l in sorted(layers_seen):
    print("  {}".format(l))