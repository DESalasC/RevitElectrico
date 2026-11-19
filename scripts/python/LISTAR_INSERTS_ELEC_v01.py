# -*- coding: utf-8 -*-
# LISTAR_TODOS_INSERTS_CON_ELEC_v01.py - Listar todos los INSERT que contengan "NET" o "PAU"
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Buscar cualquier INSERT con NET, PAU, CP, CONSOLID
keywords = ['net', 'pau', 'cp', 'consolid', 'elec']

print("=== BUSCANDO INSERTS CON PALABRAS CLAVE ===")
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name.lower()
        if any(k in name for k in ['net', 'pau', 'cp', 'consolid', 'elec']):
            print("  {} | Layer: {} | Pos: ({:.2f},{:.2f})".format(
                entity.dxf.name, entity.dxf.layer, entity.dxf.insert.x, entity.dxf.insert.y))

# Si no encuentra, listar todos los nombres únicos que contengan "ELEC"
print("\n=== TODOS LOS NOMBRES CON 'ELEC' ===")
names = set()
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        if 'elec' in name.lower() or 'ELEC' in name:
            names.add(name)

for n in sorted(names):
    print("  {}".format(n))