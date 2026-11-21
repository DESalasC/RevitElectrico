# -*- coding: utf-8 -*-
"""
EXTRAER_DXF_COORDENADAS_ABSOLUTAS_v02.py
=========================================
Extrae TODOS los dispositivos eléctricos con coordenadas ABSOLUTAS (mm)
usando los paneles que están DENTRO de cada bloque de apartamento.
"""

import ezdxf
import json
import math

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_dispositivos_absolutos_v02.json"

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

print("Leyendo DXF:", DXF_PATH)
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Mapeo DXF -> Revit
DXF_TO_REVIT = {
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    "ELEC-T-220": ("M_Toma - 220V", "220V"),
    "ELEC-EXT": ("EA", "Extractor"),
    "ELEC-TEL": ("M_Comunicaciones", "Datos"),
    "ELEC-NET-PAU": ("M_Comunicaciones", "Datos"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
    "ELEC-ZUMBADOR": ("M_Timbre", "Campana"),
    "ELEC-CAMPANA": ("M_Timbre", "Campana"),
    "ELEC-I-S-1-5A": ("M_Interruptores", "Simple"),
    "ELEC-I-S-2-5A": ("M_Interruptores", "Doble"),
    "ELEC-I-S-C1-5A": ("M_Interruptores", "Triple conmutable"),
    "ELEC-F-CONTROL": ("M_Interruptores", "Simple conmutable"),
    "ELEC-F-VENT": ("M_ClimatizacionV", "Ventilador"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "EA": ("EA", "Extractor"),
    "S3": ("M_Interruptores", "Simple"),
}

# 1. Detectar bloques de apartamentos en modelspace + su panel interno
APTO_KEYWORDS = ['APARTAMENTO', 'TIPO', 'E 0', 'F 0', 'B 1', 'C 1', 'D 1', 'E 1', 'E 2']

apto_data = []  # lista de dicts: name, insert, panel_internal, panel_absoluto

for e in msp.query('INSERT'):
    name = clean(e.dxf.name)
    if any(kw.upper() in name.upper() for kw in APTO_KEYWORDS):
        apto_insert = (e.dxf.insert.x, e.dxf.insert.y)
        
        # Buscar panel DENTRO de la definición del bloque
        block_def = doc.blocks.get(name)
        panel_internal = None
        if block_def:
            for ent in block_def:
                if ent.dxftype() == 'INSERT':
                    ent_name = clean(ent.dxf.name)
                    if 'PANEL' in ent_name.upper() or 'TB-PANEL' in ent_name.upper() or 'TB-PARCIAL' in ent_name.upper():
                        panel_internal = (ent.dxf.insert.x, ent.dxf.insert.y)
                        break
        
        if panel_internal:
            panel_abs = (apto_insert[0] + panel_internal[0], apto_insert[1] + panel_internal[1])
        else:
            panel_abs = apto_insert  # fallback
            panel_internal = (0, 0)
        
        apto_data.append({
            'name': name,
            'insert': apto_insert,
            'panel_internal': panel_internal,
            'panel_absoluto': panel_abs,
            'handle': e.dxf.handle,
            'layer': clean(e.dxf.layer)
        })

print("Apartamentos detectados:", len(apto_data))
for a in apto_data:
    print("  {} @ ({:.2f}, {:.2f}) -> panel interno ({:.2f}, {:.2f}) -> panel ABS ({:.2f}, {:.2f})".format(
        a['name'], a['insert'][0], a['insert'][1], 
        a['panel_internal'][0], a['panel_internal'][1],
        a['panel_absoluto'][0], a['panel_absoluto'][1]))

# 2. Extraer dispositivos de cada apartamento (coordenadas absolutas)
dispositivos = []

for apto in apto_data:
    block_name = apto['name']
    base_x, base_y = apto['insert']
    panel_abs_x, panel_abs_y = apto['panel_absoluto']
    
    try:
        block_def = doc.blocks.get(block_name)
        if not block_def:
            print("[WARN] Bloque '{}' no encontrado".format(block_name))
            continue
        
        for entity in block_def:
            if entity.dxftype() == 'INSERT':
                name = clean(entity.dxf.name)
                if name in DXF_TO_REVIT:
                    fam, typ = DXF_TO_REVIT[name]
                    rot = entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0
                    # ABSOLUTAS = base apartamento + offset interno
                    x_abs = base_x + entity.dxf.insert.x
                    y_abs = base_y + entity.dxf.insert.y
                    z_abs = entity.dxf.insert.z if hasattr(entity.dxf, 'z') else 0
                    
                    # Distancia al panel de su apartamento
                    dist_panel = math.hypot(x_abs - panel_abs_x, y_abs - panel_abs_y)
                    
                    dispositivos.append({
                        'apto_dxf': block_name,
                        'panel_dxf_abs': (panel_abs_x, panel_abs_y),
                        'dist_panel_mm': dist_panel,
                        'nombre_dxf': name,
                        'familia_revit': fam,
                        'tipo_revit': typ,
                        'x_mm': x_abs,
                        'y_mm': y_abs,
                        'z_mm': z_abs,
                        'rotacion_grados': rot,
                        'handle': entity.dxf.handle,
                        'layer': clean(entity.dxf.layer)
                    })
    except Exception as e:
        print("[ERROR] {}: {}".format(block_name, e))

print("\nDispositivos totales extraídos:", len(dispositivos))

# 3. Verificar F01 (debe coincidir: origen->panel = 11599.5mm, 7502.9mm)
print("\n=== VERIFICACIÓN F01 ===")
f01_apto = [a for a in apto_data if a['name'] == 'Apartamento Tipo F 01'][0]
print("F01 panel ABS: ({:.2f}, {:.2f}) mm".format(f01_apto['panel_absoluto'][0], f01_apto['panel_absoluto'][1]))
print("Esperado desde origen: (11599.55, 7502.94) mm")

f01_devices = [d for d in dispositivos if d['apto_dxf'] == 'Apartamento Tipo F 01']
print("F01 dispositivos:", len(f01_devices))
for d in f01_devices[:5]:
    print("  {} @ ({:.2f}, {:.2f}) mm".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))

# 4. Guardar
output = {
    'version': '1.0_COORDS_ABSOLUTAS_MM_PANEL_INTERNO',
    'fecha': '2026-11-20',
    'fuente': 'STM-T5-P5_bloques_electricos.dxf (FUENTE DE VERDAD ABSOLUTA)',
    'unidades': 'mm',
    'apartamentos': [
        {
            'name': a['name'],
            'insert_mm': a['insert'],
            'panel_internal_mm': a['panel_internal'],
            'panel_absoluto_mm': a['panel_absoluto']
        }
        for a in apto_data
    ],
    'dispositivos': dispositivos,
    'total_dispositivos': len(dispositivos)
}

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n[OK] Guardado:", OUT_PATH)

# 5. Generar maestro final para Revit (coordenadas en METROS, absolutas)
# Revit usa Internal Origin en METROS. Origen DXF coincide con origen Revit.
# Solo convertir mm -> m (dividir por 1000)

maestro = {
    'version': 'v07_COORDS_ABSOLUTAS_METROS',
    'fecha': '2026-11-20',
    'proyecto': 'RevitElectrico - T5-SantaMarta',
    'nivel': 'Piso 5',
    'nota': 'Coordenadas ABSOLUTAS en metros (origen DXF = origen Revit Internal Origin). Sin offsets.',
    'apartamentos': {}
}

# Agrupar por apartamento DXF
from collections import defaultdict
dev_by_apto = defaultdict(list)
for d in dispositivos:
    dev_by_apto[d['apto_dxf']].append(d)

# Mapear nombre DXF -> apto_key corta (F01, F17, etc.)
def apto_key_from_dxf(name):
    name_upper = name.upper()
    if 'F 01' in name_upper and 'F 01A' not in name_upper and 'F 01B' not in name_upper:
        return 'F01'
    if 'F 01A' in name_upper: return 'F01A'
    if 'F 01B' in name_upper: return 'F01B'
    if 'F 02' in name_upper and 'F 02A' not in name_upper and 'F 02B' not in name_upper:
        return 'F02'
    if 'F 02A' in name_upper: return 'F02A'
    if 'F 02B' in name_upper: return 'F02B'
    if 'F 17' in name_upper and 'F 17A' not in name_upper: return 'F17'
    if 'F 17A' in name_upper: return 'F17A'
    if 'F 18' in name_upper and 'F 18A' not in name_upper: return 'F18'
    if 'F 18A' in name_upper: return 'F18A'
    if 'E 05' in name_upper and 'E 05A' not in name_upper: return 'E05'
    if 'E 06' in name_upper and 'E 06A' not in name_upper: return 'E06'
    if 'E 07' in name_upper and 'E 07A' not in name_upper: return 'E07'
    if 'E 07A' in name_upper: return 'E07A'
    if 'E 08' in name_upper and 'E 08A' not in name_upper: return 'E08'
    if 'E 08A' in name_upper: return 'E08A'
    if 'B 15' in name_upper: return 'B15'
    if 'B 16' in name_upper: return 'B16'
    if 'C 14' in name_upper or 'C 11' in name_upper: return 'C14'
    if 'D 13' in name_upper or 'D 12' in name_upper: return 'D13'
    return name.replace(' ', '_').replace('TIPO_', '').replace('APARTAMENTO_', '')

for apto_name, devs in dev_by_apto.items():
    key = apto_key_from_dxf(apto_name)
    apto_info = next(a for a in apto_data if a['name'] == apto_name)
    panel_abs = apto_info['panel_absoluto']
    
    maestro['apartamentos'][key] = {
        'apto_dxf': apto_name,
        'panel_absoluto_m': {'x': panel_abs[0] / 1000.0, 'y': panel_abs[1] / 1000.0},
        'dispositivos': [
            {
                'nombre_dxf': d['nombre_dxf'],
                'familia_revit': d['familia_revit'],
                'tipo_revit': d['tipo_revit'],
                'posicion_m': {'x': d['x_mm'] / 1000.0, 'y': d['y_mm'] / 1000.0, 'z': d['z_mm'] / 1000.0},
                'rotacion_grados': d['rotacion_grados'],
                'dist_panel_m': d['dist_panel_mm'] / 1000.0,
                'layer': d['layer']
            }
            for d in devs
        ],
        'total_dispositivos': len(devs)
    }

MAESTRO_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\maestro_colocacion_piso5_ABSOLUTO.json"
with open(MAESTRO_PATH, 'w', encoding='utf-8') as f:
    json.dump(maestro, f, indent=2, ensure_ascii=False)

print("\n[OK] Maestro ABSOLUTO guardado:", MAESTRO_PATH)
print("Apartamentos:", len(maestro['apartamentos']))
total = sum(a['total_dispositivos'] for a in maestro['apartamentos'].values())
print("Total dispositivos:", total)

# Verificación final F17, F18
for k in ['F17', 'F18']:
    if k in maestro['apartamentos']:
        a = maestro['apartamentos'][k]
        px, py = a['panel_absoluto_m']['x'], a['panel_absoluto_m']['y']
        print("\n{}: Panel @ ({:.3f}, {:.3f}) m = ({:.2f}, {:.2f}) ft".format(k, px, py, px/0.3048, py/0.3048))
        if a['dispositivos']:
            d = a['dispositivos'][0]
            print("  1er disp: ({:.3f}, {:.3f}) m".format(d['posicion_m']['x'], d['posicion_m']['y']))