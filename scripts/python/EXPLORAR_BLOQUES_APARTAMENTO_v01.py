# -*- coding: utf-8 -*-
# EXPLORAR_BLOQUES_APARTAMENTO_v01.py - Explorar bloques de apartamento anidados
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)

# Buscar bloques de apartamento
apto_blocks = []
for block in doc.blocks:
    name = block.name
    if name.startswith("ELEC-Apartamento Tipo") or "Apartamento Tipo" in name:
        apto_blocks.append(block)
        print("Block: {} ({} entidades)".format(name, len(block)))

# Explorar uno de ellos para ver entidades anidadas
for block in apto_blocks[:2]:  # Solo los primeros 2
    print("\n=== EXPLORANDO: {} ===".format(block.name))
    for entity in block:
        if entity.dxftype() == 'INSERT':
            print("  INSERT anidado: {} | Pos: ({:.2f},{:.2f}) | Layer: {}".format(
                entity.dxf.name, entity.dxf.insert.x, entity.dxf.insert.y, entity.dxf.layer))
        else:
            print("  {}: {}".format(entity.dxftype(), getattr(entity.dxf, 'layer', 'N/A')))

# Buscar específicamente ELEC-NET-PAU anidado
print("\n=== BUSCANDO ELEC-NET-PAU ANIDADO ===")
for block in apto_blocks:
    for entity in block:
        if entity.dxftype() == 'INSERT' and 'NET-PAU' in entity.dxf.name:
            print("  En {}: {} @ ({:.2f},{:.2f})".format(
                block.name, entity.dxf.name, entity.dxf.insert.x, entity.dxf.insert.y))