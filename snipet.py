import json
import math

# Cargar JSON
with open(r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json", 'r') as f:
    data = json.load(f)

# Coordenadas globales calculadas manualmente para F18
# Apartamentos Tipo F 18 @ (6489.30, 9672.66) rot=0
# NET-PAU local (2.13, 2.83)
cp_f18_1 = {
    'x': 6489.30 + 2.13,
    'y': 9672.66 + 2.83,
    'rotation': 0,
    'id_bloque': 'CP_01'
}

# Apartamentos Tipo F 18a @ (-19403.13, 9682.38) rot=0
# NET-PAU local (2.18, 2.83)
cp_f18_2 = {
    'x': -19403.13 + 2.18,
    'y': 9682.38 + 2.83,
    'rotation': 0,
    'id_bloque': 'CP_01'
}

for apto in ['F18']:
    # Verificar si ya existe
    exists = any(d['familia_revit'] == 'Consolidation_Point' for d in data['apartamentos'][apto]['devices'])
    if not exists:
        data['apartamentos'][apto]['devices'].append({
            'familia_revit': 'Consolidation_Point',
            'tipo_revit': 'CPB12BL',
            'x': cp_f18_1['x'],
            'y': cp_f18_1['y'],
            'rotation': 0,
            'id_bloque': 'CP_01'
        })
        print("Agregado CP a F18 (instancia 1)")
    # Para segunda instancia, crear otro CP o ignorar (normalmente 1 por apto)

with open(r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json", 'w') as f:
    json.dump(data, f, indent=2)
print("F18 actualizado")
