# -*- coding: utf-8 -*-
# LISTAR_TODOS_INSERTS_DXF_v01.py - Listar TODOS los INSERT con sus nombres
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

print("=== TODOS LOS INSERT EN MODELSPACE ===")
names = {}
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        layer = entity.dxf.layer
        names[name] = names.get(name, 0) + 1

for name, count in sorted(names.items(), key=lambda x: -x[1]):
    print("  {} : {}".format(name, count))