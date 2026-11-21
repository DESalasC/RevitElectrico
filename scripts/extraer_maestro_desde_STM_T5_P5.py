# -*- coding: utf-8 -*-
"""
extraer_maestro_desde_STM_T5_P5.py
===================================
Extrae TODOS los apartamentos desde el archivo maestro absoluto:
D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf

FUENTE DE VERDAD ABSOLUTA - Regla fija registrada.
Los dispositivos están en el primer nivel de la definición del bloque apartamento.
"""

import ezdxf
import json
import os
import re

MASTER_DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

# Mapeo DXF -> Revit (v07 confirmado)
DXF_TO_REVIT = {
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    "ELEC-T-220": ("M_Toma - 220V", "220V"),
    "ELEC-EXT": ("EA", "Extintor"),
    "ELEC-TEL": ("M_Comunicaciones", "Datos"),
    "ELEC-NET-PAU": ("M_Comunicaciones", "Datos"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
    "ELEC-ZUMBADOR": ("M_Timbre", "Campana"),
    "ELEC-CAMPANA": ("M_Timbre", "Campana"),
    "ELEC-I-S-1-5A": ("M_Interruptores", "Simple"),
    "ELEC-I-S-2-5A": ("M_Interruptores", "Doble"),
    "ELEC-I-S-C1-5A": ("M_Interruptores", "Control"),
    "ELEC-F-CONTROL": ("M_Interruptores", "Control"),
    "ELEC-F-VENT": ("M_ClimatizacionV", "Ventilador"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "EA": ("EA", "Extintor"),
    "S3": ("M_Interruptores", "Simple"),
    "S3C": ("M_Interruptores", "Simple"),
}

# Patrones para identificar bloques de apartamento
APTO_BLOCK_PATTERNS = [
    r'^Apartamento\s+Tipo\s+[A-Z]\s+\d+[a-z]?$',
    r'^Apartamentos\s+Tipo\s+[A-Z]\s+\d+[a-z]?$',
    r'^ELEC-Apartamento\s+Tipo\s+[A-Z]\s+\d+$',
    r'^ApaRtamento\s+Tipo\s+[A-Z]\s+\d+$',
]

def is_apto_block(name):
    name = clean(name)
    for pat in APTO_BLOCK_PATTERNS:
        if re.match(pat, name, re.IGNORECASE):
            return True
    return False

def normalize_apto_name(name):
    """Normaliza: 'Apartamento Tipo F 01' -> 'F01', 'Apartamentos Tipo F 18' -> 'F18', etc."""
    name = clean(name)
    for pref in ["Apartamento ", "Apartamentos ", "ELEC-", "Tipo "]:
        name = name.replace(pref, "")
    name = name.replace(" ", "")
    name = name.replace("ApaRtamento", "")
    return name.upper()

print("=" * 70)
print("EXTRACCIÓN DESDE FUENTE DE VERDAD ABSOLUTA")
print(f"Archivo: {MASTER_DXF}")
print("=" * 70)

doc = ezdxf.readfile(MASTER_DXF)
msp = doc.modelspace()

# 1. Encontrar todos los INSERT de apartamentos en modelspace
apto_inserts = []
for e in msp.query('INSERT'):
    name = clean(e.dxf.name)
    if is_apto_block(name):
        apto_inserts.append(e)

print(f"\n[INFO] Bloques de apartamento encontrados en modelspace: {len(apto_inserts)}")

# 2. Procesar cada apartamento
apartamentos = {}
for apto_ins in apto_inserts:
    apto_name = clean(apto_ins.dxf.name)
    apto_key = normalize_apto_name(apto_name)
    apto_x = apto_ins.dxf.insert.x
    apto_y = apto_ins.dxf.insert.y
    apto_rot = apto_ins.dxf.rotation if hasattr(apto_ins.dxf, 'rotation') else 0
    
    # Obtener definición del bloque
    try:
        block_def = doc.blocks.get(apto_name)
        if not block_def:
            print(f"  [WARN] '{apto_name}': sin definición")
            continue
    except:
        print(f"  [WARN] '{apto_name}': error accediendo a bloque")
        continue
    
    # Buscar panel y dispositivos EN EL PRIMER NIVEL de la definición
    panel_name = None
    panel_x = None
    panel_y = None
    devices = []
    
    for e in block_def:
        if e.dxftype() != 'INSERT':
            continue
        
        name = clean(e.dxf.name)
        layer = clean(e.dxf.layer) if hasattr(e.dxf, 'layer') else ''
        x = e.dxf.insert.x
        y = e.dxf.insert.y
        rot = e.dxf.rotation if hasattr(e.dxf, 'rotation') else 0
        handle = e.dxf.handle
        
        # ¿Es un panel? (buscar TB-Panel, TF, TE, TB, TC, TD, PANEL)
        if panel_name is None:
            upper = name.upper()
            if ('PANEL' in upper or upper.startswith('TF') or upper.startswith('TE') 
                or upper.startswith('TB') or upper.startswith('TC') or upper.startswith('TD')):
                panel_name = name
                panel_x = x
                panel_y = y
        
        # Mapear dispositivo
        if name in DXF_TO_REVIT:
            fam, typ = DXF_TO_REVIT[name]
            devices.append({
                'handle': handle,
                'name': name,
                'layer': layer,
                'x': x,      # relativo al origen del bloque apartamento
                'y': y,
                'rotation': rot,
                'familia_revit': fam,
                'tipo_revit': typ,
            })
    
    if apto_key in apartamentos:
        print(f"  [WARN] Duplicado: {apto_key}")
        continue
    
    apartamentos[apto_key] = {
        'apto_name': apto_name,
        'apto_insert': {'x': apto_x, 'y': apto_y, 'rotation': apto_rot},
        'panel_name': panel_name,
        'panel_pos': {'x': panel_x, 'y': panel_y} if panel_name else None,
        'devices': devices,
        'total_entities': len(list(block_def)),
    }
    
    print(f"\n[INFO] {apto_key} ('{apto_name}'):")
    print(f"  Insert modelspace: ({apto_x:.2f}, {apto_y:.2f})")
    if panel_name:
        print(f"  Panel: {panel_name} @ ({panel_x:.2f}, {panel_y:.2f}) [relativo a bloque]")
    else:
        print(f"  Panel: NO ENCONTRADO")
    print(f"  Dispositivos mapeados: {len(devices)} / {apartamentos[apto_key]['total_entities']} entidades")

# 3. Calcular base para cada apartamento (usar panel_pos o apto_insert)
# La base en coordenadas GLOBALES (modelspace) = apto_insert + panel_pos (si panel está en coords relativas al bloque)
# OJO: panel_pos está en coords relativas al origen del bloque apartamento
# Coordenadas globales del panel = apto_insert + panel_pos
for apto_key, data in apartamentos.items():
    if data['panel_pos'] and data['panel_pos']['x'] is not None:
        # Panel está en coords relativas al bloque
        base_x_global = data['apto_insert']['x'] + data['panel_pos']['x']
        base_y_global = data['apto_insert']['y'] + data['panel_pos']['y']
        base_x_block = data['panel_pos']['x']  # relativo al bloque
        base_y_block = data['panel_pos']['y']
    else:
        # Fallback: origen del bloque
        base_x_global = data['apto_insert']['x']
        base_y_global = data['apto_insert']['y']
        base_x_block = 0
        base_y_block = 0
    
    # Dispositivos ya están en coords relativas al bloque (x, y)
    # Para el JSON maestro guardamos base en pies (coordenadas globales del panel)
    data['base_x_ft'] = base_x_global
    data['base_y_ft'] = base_y_global
    data['base_x_block_ft'] = base_x_block
    data['base_y_block_ft'] = base_y_block
    
    # Coordenadas relativas a la base del apartamento (para colocación)
    for dev in data['devices']:
        dev['x_rel'] = dev['x'] - base_x_block
        dev['y_rel'] = dev['y'] - base_y_block

# 4. Construir salida en formato dxf_master_global_all.json
output = {
    'version': 'v02_FROM_MASTER_DXF',
    'fecha_generacion': '2026-11-19',
    'fuente': 'STM-T5-P5_bloques_electricos.dxf (FUENTE DE VERDAD ABSOLUTA - regla fija)',
    'apartamentos': {}
}

for apto_key, data in sorted(apartamentos.items()):
    devices_out = []
    for dev in data['devices']:
        devices_out.append({
            'handle': dev['handle'],
            'name': dev['name'],
            'x': dev['x_rel'],  # relativo a base del apartamento (panel)
            'y': dev['y_rel'],
            'rotation': dev['rotation'],
            'familia_revit': dev['familia_revit'],
            'tipo_revit': dev['tipo_revit'],
        })
    
    output['apartamentos'][apto_key] = {
        'devices': devices_out,
        'walls': [],
        'panels': [],
        'panel_name': data['panel_name'] or '',
        'apto_type': apto_key[0] if apto_key else '',
        'apto_num': apto_key[1:] if len(apto_key) > 1 else '',
        'base_x_ft': data['base_x_ft'],
        'base_y_ft': data['base_y_ft'],
    }

# 5. Guardar
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 70)
print("RESUMEN FINAL")
print("=" * 70)
total_devs = 0
for k, v in sorted(output['apartamentos'].items()):
    n = len(v['devices'])
    total_devs += n
    print(f"  {k}: {n} dispositivos, base_global=({v['base_x_ft']:.2f},{v['base_y_ft']:.2f})ft, panel={v['panel_name'] or 'N/A'}")

print(f"\nTOTAL APARTAMENTOS: {len(output['apartamentos'])}")
print(f"TOTAL DISPOSITIVOS: {total_devs}")
print(f"\nJSON guardado: {OUT_PATH}")

# Verificar 20 esperados
esperados = ['F01','F01A','F01B','F02','F02A','F02B','F17','F17A','F18','F18A',
             'E05','E06','E07','E07A','E08','E08A',
             'B15','B16','C14','D13']
print(f"\nVerificación 20 apartamentos esperados:")
for e in esperados:
    status = "OK" if e in output['apartamentos'] else "FALTA"
    print(f"  {e}: {status}")