# -*- coding: utf-8 -*-
"""Explorar definiciones de bloque para encontrar dispositivos eléctricos anidados"""

import ezdxf

MASTER_DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(MASTER_DXF)

# Obtener nombres de bloques correctamente
block_names = list(doc.blocks.block_names())
print("Total block definitions: {}".format(len(block_names)))

# Buscar bloques de apartamento Tipo F
apto_blocks = []
for bn in block_names:
    if "Apartamento Tipo F" in bn:
        apto_blocks.append(bn)

print("\nBloques de apartamento Tipo F:")
for b in apto_blocks:
    print("  " + b)

# Explorar recursivamente un bloque
def explore_block(block, prefix="", level=0):
    indent = "  " * level
    entities = []
    for e in block:
        if e.dxftype() == "INSERT":
            block_ref = doc.blocks.get(e.dxf.name)
            if block_ref:
                entities.append((prefix + e.dxf.name, e.dxf.insert.x, e.dxf.insert.y, e.dxf.rotation if hasattr(e.dxf, 'rotation') else 0))
                # Recursivo
                sub_entities = explore_block(block_ref, prefix + e.dxf.name + "->", level + 1)
                entities.extend(sub_entities)
            else:
                entities.append((prefix + e.dxf.name + " (NO BLOCK DEF)", e.dxf.insert.x, e.dxf.insert.y, 0))
        elif e.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC"):
            pass  # geometría, no dispositivos
    return entities

for apto_block_name in ["Apartamento Tipo F 01", "Apartamento Tipo F 02"]:
    if apto_block_name in doc.blocks:
        block = doc.blocks[apto_block_name]
        print("\n=== CONTENIDO DE {} ===".format(apto_block_name))
        nested = explore_block(block)
        elec_items = [n for n in nested if "ELEC" in n[0].upper()]
        print("  Dispositivos ELEC encontrados: {}".format(len(elec_items)))
        for name, x, y, rot in elec_items[:50]:
            print("    {} @ ({:.1f}, {:.1f}) rot={}".format(name, x, y, rot))
        if len(elec_items) > 50:
            print("    ... y {} más".format(len(elec_items) - 50))
    else:
        print("\nBloque {} NO ENCONTRADO en definiciones".format(apto_block_name))

# También buscar bloques que contengan "ELEC" en su nombre
print("\n=== BLOQUES CON 'ELEC' EN NOMBRE ===")
for block_name in block_names:
    if "ELEC" in block_name.upper():
        print("  " + block_name)