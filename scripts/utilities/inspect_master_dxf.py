# -*- coding: utf-8 -*-
"""Inspeccionar coordenadas de INSERT en DXF maestro"""

import ezdxf

MASTER_DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(MASTER_DXF)
msp = doc.modelspace()

inserts = []
for e in msp:
    if e.dxftype() == "INSERT":
        x, y = e.dxf.insert.x, e.dxf.insert.y
        inserts.append((e.dxf.name, x, y))

print("Total INSERTs: {}".format(len(inserts)))
if inserts:
    xs = [i[1] for i in inserts]
    ys = [i[2] for i in inserts]
    print("X range: {:.2f} a {:.2f}".format(min(xs), max(xs)))
    print("Y range: {:.2f} a {:.2f}".format(min(ys), max(ys)))
    print()
    # Mostrar primeros 30
    for name, x, y in inserts[:30]:
        print("  {} @ ({:.2f}, {:.2f})".format(name, x, y))
    if len(inserts) > 30:
        print("  ... y {} más".format(len(inserts) - 30))
    
    # Agrupar por nombre de bloque
    from collections import defaultdict
    by_block = defaultdict(list)
    for name, x, y in inserts:
        by_block[name].append((x, y))
    
    print("\n--- BLOQUES ÚNICOS Y CANTIDAD ---")
    for name, coords in sorted(by_block.items()):
        xs_b = [c[0] for c in coords]
        ys_b = [c[1] for c in coords]
        print("  {}: {} instancias, X[{:.1f},{:.1f}] Y[{:.1f},{:.1f}]".format(
            name, len(coords), min(xs_b), max(xs_b), min(ys_b), max(ys_b)))