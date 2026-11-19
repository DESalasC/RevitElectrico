# -*- coding: utf-8 -*-
# VERIFICAR_BLOQUES_DEFINICIONES_ELECTRICOS_v01.py - Ver definiciones de bloques eléctricos
# Ejecutar en Python normal

import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF_PATH)

print("=== DEFINICIONES DE BLOQUES CON PALABRAS ELÉCTRICAS ===")
for block in doc.blocks:
    name = block.name
    name_lower = name.lower()
    if any(k in name_lower for k in ['elec', 'net', 'pau', 'cp', 'consolid', 'telecom', 'datos', 'toma', 'interrupt', 'luz', 'ventil', 'extractor', 'extintor', 'ea', 'timbre', 'campana', 'm_']):
        print("  Block: {} ({} entidades)".format(name, len(block)))

print("\n=== TODOS LOS BLOQUES QUE CONTENGAN 'ELEC' ===")
for block in doc.blocks:
    if 'elec' in block.name.lower() or 'ELEC' in block.name:
        print("  Block: {} ({} entidades)".format(block.name, len(block)))

print("\n=== BLOQUES CON 'NET' O 'PAU' ===")
for block in doc.blocks:
    if 'net' in block.name.lower() or 'pau' in block.name.lower():
        print("  Block: {} ({} entidades)".format(block.name, len(block)))