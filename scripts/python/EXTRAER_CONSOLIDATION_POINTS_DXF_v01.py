# -*- coding: utf-8 -*-
# EXTRAER_CONSOLIDATION_POINTS_DXF_v01.py - Extraer ELEC-NET-PAU por apartamento
# Ejecutar en Python normal

import ezdxf
import json

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Cargar JSON existente
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

# Mapear nombres de apartamentos en JSON vs DXF
# En DXF: "Apartamento Tipo F 01", "Apartamento Tipo F 01a", etc.
# En JSON: "F01", "F02", "E06", "E07", "E08", "F17", "F18", "D13", "C14", "B15", "B16"

apto_map = {
    "Apartamento Tipo F 01": "F01",
    "Apartamento Tipo F 01a": "F01",
    "Apartamento Tipo F 01b": "F01",
    "Apartamento Tipo F 02": "F02",
    "Apartamento Tipo F 02a": "F02",
    "Apartamento Tipo F 02b": "F02",
    "Apartamentos Tipo F 17": "F17",
    "Apartamento Tipo F 17a": "F17",
    "Apartamentos Tipo F 18": "F18",
    "Apartamentos Tipo F 18a": "F18",
    "Apartamento Tipo E 06": "E06",
    "Apartamento Tipo E 07": "E07",
    "Apartamento Tipo E 07a": "E07",
    "Apartamento Tipo E 08": "E08",
    "Apartamento Tipo E 08a": "E08",
    "ELEC-Apartamento Tipo D 13": "D13",
    "ELEC-Apartamento Tipo C 14": "C14",
    "Apartamento Tipo B 15": "B15",
    "Apartamento Tipo B 16": "B16",
    "Apartamento Tipo E 05": "E05",  # si existe
}

# Extraer ELEC-NET-PAU
cp_by_apto = {}
for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name
        if "ELEC-NET-PAU" in name:
            pos = (entity.dxf.insert.x, entity.dxf.insert.y)
            rotation = entity.dxf.rotation
            # Atributos
            attribs = {}
            for attrib in entity.attribs:
                attribs[attrib.dxf.tag] = attrib.dxf.text
            
            # Determinar apartamento por proximity o layer
            layer = entity.dxf.layer
            # Buscar a qué apartamento pertenece (por layer name que contiene "Apartamento")
            apto_key = None
            for apto_dxf, apto_json in apto_map.items():
                if apto_dxf in layer or apto_dxf.lower() in layer.lower():
                    apto_key = apto_json
                    break
            
            if not apto_key:
                # Fallback: proximity to apartment label INSERTs
                pass
            
            if apto_key:
                if apto_key not in cp_by_apto:
                    cp_by_apto[apto_key] = []
                cp_by_apto[apto_key].append({
                    'x': pos[0],
                    'y': pos[1],
                    'rotation': rotation,
                    'layer': layer,
                    'attribs': attribs
                })
                print("  {} -> {} @ ({:.2f}, {:.2f}) rot={:.1f}".format(
                    apto_key, name, pos[0], pos[1], rotation))

print("\n=== RESUMEN ===")
for apto, cps in cp_by_apto.items():
    print("  {}: {} CP(s)".format(apto, len(cps)))
    for cp in cps:
        print("    ({:.2f}, {:.2f}) rot={:.1f}".format(cp['x'], cp['y'], cp['rotation']))