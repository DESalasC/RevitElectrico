# -*- coding: utf-8 -*-
# INSPECCIONAR_DXF_BLOQUES_v01.py - Listar bloques en el DXF original
# Ejecutar en Python normal (fuera de pyRevit) con ezdxf instalado

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# 1. Listar TODAS las definiciones de bloques
print("=== DEFINICIONES DE BLOQUES ===")
for block in doc.blocks:
    print("  Block: {} ({} entidades)".format(block.name, len(block)))

# 2. Listar TODAS las inserciones de bloques en modelspace con sus atributos
print("\n=== INSERCIONES EN MODELSPACE ===")
block_counts = {}
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        layer = entity.dxf.layer
        pos = (entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.insert.z)
        rotation = entity.dxf.rotation
        block_counts[name] = block_counts.get(name, 0) + 1
        # Atributos
        attribs = {}
        for attrib in entity.attribs:
            attribs[attrib.dxf.tag] = attrib.dxf.text
        print("  {} | Layer: {} | Pos: ({:.2f},{:.2f}) | Rot: {:.1f} | Attrs: {}".format(
            name, layer, pos[0], pos[1], rotation, attribs))

print("\n=== RESUMEN CONTEOS ===")
for name, count in sorted(block_counts.items(), key=lambda x: -x[1]):
    print("  {} : {}".format(name, count))

# 3. Buscar específicamente bloques que puedan ser Consolidation Point
print("\n=== BUSCANDO 'CP', 'CONSOLIDATION', 'TELECOM', 'DATOS' ===")
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name.lower()
        if any(k in name for k in ['cp', 'consolid', 'telecom', 'datos', 'punto', 'consol']):
            print("  CANDIDATO: {} | Layer: {} | Pos: ({:.2f},{:.2f})".format(
                entity.dxf.name, entity.dxf.layer, entity.dxf.insert.x, entity.dxf.insert.y))