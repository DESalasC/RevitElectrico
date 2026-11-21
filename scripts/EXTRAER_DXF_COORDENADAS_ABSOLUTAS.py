# -*- coding: utf-8 -*-
"""
EXTRAER_DXF_COORDENADAS_ABSOLUTAS.py
====================================
Extrae TODOS los dispositivos eléctricos con coordenadas ABSOLUTAS (mm)
recorriendo bloques anidados manualmente con ezdxf.
"""

import ezdxf
import json
import math

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_dispositivos_absolutos.json"

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

# Palabras clave para detectar bloques de apartamentos
APTO_KEYWORDS = ['APARTAMENTO', 'TIPO', 'E 0', 'F 0', 'B 1', 'C 1', 'D 1', 'E 1', 'E 2']

# 1. Detectar bloques de apartamentos en modelspace
apto_blocks = []
for e in msp.query('INSERT'):
    name = clean(e.dxf.name)
    if any(kw.upper() in name.upper() for kw in APTO_KEYWORDS):
        apto_blocks.append({
            'name': name,
            'insert': (e.dxf.insert.x, e.dxf.insert.y),
            'handle': e.dxf.handle,
            'layer': clean(e.dxf.layer)
        })

print("Bloques de apartamentos detectados:", len(apto_blocks))
for a in apto_blocks:
    print("  {} @ ({:.2f}, {:.2f}) mm".format(a['name'], a['insert'][0], a['insert'][1]))

# 2. Obtener definición de cada bloque de apartamento y extraer dispositivos internos
# Los dispositivos están DENTRO de la definición del bloque del apartamento
dispositivos = []

for apto in apto_blocks:
    block_name = apto['name']
    base_x, base_y = apto['insert']
    
    try:
        block_def = doc.blocks.get(block_name)
        if not block_def:
            print("[WARN] Bloque '{}' no encontrado en definiciones".format(block_name))
            continue
        
        # Recorrer entidades DENTRO de la definición del bloque
        for entity in block_def:
            if entity.dxftype() == 'INSERT':
                name = clean(entity.dxf.name)
                if name in DXF_TO_REVIT:
                    fam, typ = DXF_TO_REVIT[name]
                    rot = entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0
                    # Coordenadas ABSOLUTAS = base apartamento + offset interno
                    x_abs = base_x + entity.dxf.insert.x
                    y_abs = base_y + entity.dxf.insert.y
                    z_abs = entity.dxf.insert.z if hasattr(entity.dxf, 'z') else 0
                    
                    dispositivos.append({
                        'apto_dxf': block_name,
                        'panel_dxf': 'TB-Panel',  # genérico, se refinará
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
        print("[ERROR] Procesando {}: {}".format(block_name, e))

print("\nDispositivos extraídos:", len(dispositivos))

# 3. Buscar paneles en modelspace para asignar correctamente
panels = {}
for e in msp.query('INSERT'):
    name = clean(e.dxf.name)
    if any(p in name.upper() for p in ['PANEL', 'TF ', 'TE ', 'TB ', 'TC ', 'TD ']):
        panels[name] = (e.dxf.insert.x, e.dxf.insert.y)

print("\nPaneles en modelspace:")
for n, p in panels.items():
    print("  {} @ ({:.2f}, {:.2f}) mm".format(n, p[0], p[1]))

# Asignar panel más cercano a cada dispositivo
for d in dispositivos:
    best_panel = None
    best_dist = float('inf')
    for p_name, (px, py) in panels.items():
        dist = math.hypot(d['x_mm'] - px, d['y_mm'] - py)
        if dist < best_dist:
            best_dist = dist
            best_panel = p_name
    d['panel_dxf'] = best_panel
    d['dist_panel_mm'] = best_dist

# 4. Guardar
output = {
    'version': '1.0_COORDS_ABSOLUTAS_MM',
    'fecha': '2026-11-19',
    'fuente': 'STM-T5-P5_bloques_electricos.dxf (FUENTE DE VERDAD ABSOLUTA)',
    'unidades': 'mm',
    'paneles_dxf': panels,
    'dispositivos': dispositivos,
    'total_dispositivos': len(dispositivos)
}

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n[OK] Guardado:", OUT_PATH)
print("Dispositivos totales:", len(dispositivos))

# Estadísticas
from collections import Counter
panel_counts = Counter(d['panel_dxf'] for d in dispositivos)
print("\nDispositivos por panel DXF:")
for p, c in panel_counts.most_common():
    print("  {}: {}".format(p, c))

# Verificar F01
print("\n--- Verificación F01 (debe coincidir con medición real) ---")
f01_devices = [d for d in dispositivos if 'F 01' in d.get('apto_dxf', '') and 'F 01a' not in d.get('apto_dxf', '') and 'F 01b' not in d.get('apto_dxf', '')]
print("F01 dispositivos:", len(f01_devices))
if f01_devices:
    for d in f01_devices[:5]:
        print("  {} @ ({:.2f}, {:.2f}) mm".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))