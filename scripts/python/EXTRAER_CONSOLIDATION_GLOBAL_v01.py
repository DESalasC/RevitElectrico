# -*- coding: utf-8 -*-
# EXTRAER_CONSOLIDATION_GLOBAL_v01.py - Obtener coordenadas globales de CP
# Ejecutar en Python normal

import ezdxf
import json
import math

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# 1. Coordenadas locales de ELEC-NET-PAU por bloque de apartamento (del script anterior)
cp_local = {
    "Apartamento Tipo F 17": (2.16, -2.75),
    "Apartamento Tipo F 17a": (2.20, -2.75),
    "Apartamento Tipo E 06": (2.82, 2.02),
    "Apartamento Tipo E 07": (-2.27, -2.02),
    "Apartamento Tipo E 07a": (-1.97, -2.02),
    "Apartamento Tipo E 08": (-3.11, 1.94),
    "Apartamento Tipo E 08a": (-2.86, 1.94),
    "Apartamento Tipo F 01": (-2.30, -2.84),
    "Apartamento Tipo F 01a": (-2.36, -2.83),
    "Apartamento Tipo F 01b": (-2.36, -2.83),
    "Apartamento Tipo F 02": (-2.34, 2.84),
    "Apartamento Tipo F 02a": (-2.37, 2.84),
    "Apartamento Tipo F 02b": (-2.34, 2.84),
    "ELEC-Apartamento Tipo D 13": (3.84, 2.02),
    "ELEC-Apartamento Tipo C 14": (0.84, 0.26),
    "Apartamento Tipo B 16": (-2.05, 2.00),
    "Apartamento Tipo B 15": (-2.13, -2.00),
}

# 2. Mapear bloques DXF -> JSON keys
block_to_json = {
    "Apartamento Tipo F 01": "F01",
    "Apartamento Tipo F 01a": "F01",
    "Apartamento Tipo F 01b": "F01",
    "Apartamento Tipo F 02": "F02",
    "Apartamento Tipo F 02a": "F02",
    "Apartamento Tipo F 02b": "F02",
    "Apartamento Tipo F 17": "F17",
    "Apartamento Tipo F 17a": "F17",
    "Apartamento Tipo F 18": "F18",
    "Apartamento Tipo F 18a": "F18",
    "Apartamento Tipo E 06": "E06",
    "Apartamento Tipo E 07": "E07",
    "Apartamento Tipo E 07a": "E07",
    "Apartamento Tipo E 08": "E08",
    "Apartamento Tipo E 08a": "E08",
    "ELEC-Apartamento Tipo D 13": "D13",
    "ELEC-Apartamento Tipo C 14": "C14",
    "Apartamento Tipo B 15": "B15",
    "Apartamento Tipo B 16": "B16",
}

# 3. Buscar instancias de bloques de apartamento en modelspace
apto_instances = {}  # block_name -> list of (x, y, rotation)
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        if name in block_to_json:
            pos = (entity.dxf.insert.x, entity.dxf.insert.y)
            rot = entity.dxf.rotation
            json_key = block_to_json[name]
            if json_key not in apto_instances:
                apto_instances[json_key] = []
            apto_instances[json_key].append((pos[0], pos[1], rot))
            print("Instancia {}: {} -> JSON {} @ ({:.2f},{:.2f}) rot={:.1f}".format(
                name, entity.dxf.handle, json_key, pos[0], pos[1], rot))

print("\n=== RESUMEN INSTANCIAS ===")
for json_key, instances in apto_instances.items():
    print("  {}: {} instancia(s)".format(json_key, len(instances)))
    for i, (x, y, rot) in enumerate(instances):
        print("    [{}] @ ({:.2f},{:.2f}) rot={:.1f}".format(i, x, y, rot))

# 4. Calcular coordenadas globales de CP para cada apartamento JSON
cp_global = {}
for json_key, instances in apto_instances.items():
    if json_key not in cp_global:
        cp_global[json_key] = []
    
    # Buscar el nombre del bloque DXF para este JSON
    dxf_names = [k for k, v in block_to_json.items() if v == json_key]
    
    for dxf_name in dxf_names:
        if dxf_name in cp_local:
            local_x, local_y = cp_local[dxf_name]
            for inst_x, inst_y, inst_rot in instances:
                # Rotar coordenadas locales según rotación del apartamento
                # Nota: rotación del bloque en DXF
                rad = math.radians(inst_rot)
                cos_r = math.cos(rad)
                sin_r = math.sin(rad)
                
                # Rotar punto local
                global_x = inst_x + local_x * cos_r - local_y * sin_r
                global_y = inst_y + local_x * sin_r + local_y * cos_r
                
                cp_global[json_key].append({
                    'x': global_x,
                    'y': global_y,
                    'rotation': 0,  # CP no tiene rotación específica
                    'source_block': dxf_name
                })
                print("CP global {}: ({:.2f},{:.2f}) <- local ({:.2f},{:.2f}) + apto ({:.2f},{:.2f}) rot={:.1f}".format(
                    json_key, global_x, global_y, local_x, local_y, inst_x, inst_y, inst_rot))

print("\n=== CP GLOBALES POR APTO JSON ===")
for json_key, cps in cp_global.items():
    print("  {}: {} CP(s)".format(json_key, len(cps)))
    for cp in cps:
        print("    ({:.2f}, {:.2f})".format(cp['x'], cp['y']))

# 5. Actualizar JSON
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

for json_key, cps in cp_global.items():
    if json_key in data['apartamentos']:
        for cp in cps:
            # Verificar si ya existe
            exists = any(d['familia_revit'] == 'Consolidation_Point' for d in data['apartamentos'][json_key]['devices'])
            if not exists:
                data['apartamentos'][json_key]['devices'].append({
                    'familia_revit': 'Consolidation_Point',
                    'tipo_revit': 'CPB12BL',  # tipo por defecto
                    'x': cp['x'],
                    'y': cp['y'],
                    'rotation': 0,
                    'id_bloque': 'CP_01'
                })
                print("  Agregado CP a {}".format(json_key))
            else:
                print("  CP ya existe en {}".format(json_key))

# Guardar JSON actualizado
with open(JSON_PATH, 'w') as f:
    json.dump(data, f, indent=2)
print("\nJSON actualizado guardado.")