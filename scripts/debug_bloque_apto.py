# -*- coding: utf-8 -*-
"""
debug_bloque_apto.py - Inspeccionar qué hay dentro de un bloque de apartamento
"""

import ezdxf

MASTER_DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"

doc = ezdxf.readfile(MASTER_DXF)

# Probar con F01
apto_name = "Apartamento Tipo F 01"
block_def = doc.blocks.get(apto_name)

print(f"=== Bloque: {apto_name} ===")
print(f"Entidades en definición: {len(list(block_def))}")

# Contar por tipo
type_counts = {}
name_counts = {}
layer_counts = {}

for e in block_def:
    dtype = e.dxftype()
    type_counts[dtype] = type_counts.get(dtype, 0) + 1
    
    if dtype == 'INSERT':
        name = e.dxf.name if hasattr(e.dxf, 'name') else '?'
        name_counts[name] = name_counts.get(name, 0) + 1
    
    layer = e.dxf.layer if hasattr(e.dxf, 'layer') else '?'
    layer_counts[layer] = layer_counts.get(layer, 0) + 1

print("\n--- Tipos de entidad ---")
for t, c in sorted(type_counts.items()):
    print(f"  {t}: {c}")

print("\n--- Nombres de INSERT (top 30) ---")
for n, c in sorted(name_counts.items(), key=lambda x: -x[1])[:30]:
    print(f"  {n}: {c}")

print("\n--- Layers (top 30) ---")
for l, c in sorted(layer_counts.items(), key=lambda x: -x[1])[:30]:
    print(f"  {l}: {c}")

# Buscar dispositivos eléctricos conocidos
print("\n--- Buscando dispositivos conocidos ---")
known = ["ELEC-T-GFCI-t-15A", "ELEC-T-D-t-15A", "ELEC-TEL", "ELEC-NET-PAU", 
         "ELEC-TIMBRE", "ELEC-CAMPANA", "ELEC-I-S-1-5A", "ELEC-I-S-2-5A",
         "ELEC-F-VENT", "ELEC-F-CONTROL", "Bala Stil Led", "EA", "S3"]
for e in block_def:
    if e.dxftype() == 'INSERT':
        name = e.dxf.name if hasattr(e.dxf, 'name') else ''
        for k in known:
            if k in name:
                print(f"  ENCONTRADO: {name} @ ({e.dxf.insert.x:.2f}, {e.dxf.insert.y:.2f}) layer={e.dxf.layer}")
                break

# Ver si hay bloques anidados (INSERT que a su vez tienen definición con más INSERT)
print("\n--- Bloques anidados (INSERT con definición propia) ---")
for e in block_def:
    if e.dxftype() == 'INSERT':
        name = e.dxf.name if hasattr(e.dxf, 'name') else ''
        try:
            child_def = doc.blocks.get(name)
            if child_def and len(list(child_def)) > 0:
                print(f"  {name}: {len(list(child_def))} entidades en su definición")
        except:
            pass