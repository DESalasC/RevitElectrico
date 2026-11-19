# -*- coding: utf-8 -*-
"""extraer_STM_T5_P5_DXF_a_JSON.py - Python 3.12 + ezdxf"""

import ezdxf
import json
import os

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_stm_t5_p5_extraido.json"

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

print("Leyendo DXF:", DXF_PATH)
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# 1. Paneles
panels = {}
for e in msp.query('INSERT'):
    name = clean(e.dxf.name)
    if 'PANEL' in name.upper() or 'TF' in name.upper() or 'T0' in name.upper():
        panels[name] = {
            'x': e.dxf.insert.x,
            'y': e.dxf.insert.y,
            'layer': clean(e.dxf.layer)
        }

# 2. Muros (polilíneas en layers relevantes)
wall_layers = [l.dxf.name for l in doc.layers if any(kw in l.dxf.name.upper() for kw in ['MURO', 'WALL', 'ELEC-', 'PARED'])]
walls = []
for e in msp.query('LWPOLYLINE'):
    if e.dxf.layer in wall_layers:
        walls.append({
            'layer': e.dxf.layer,
            'points': [(v[0], v[1]) for v in e.get_points()],
            'closed': e.closed
        })

# 3. Dispositivos eléctricos
devices = []
elec_keywords = ['ELEC', 'TOMA', 'INTERRUPT', 'ILUM', 'TIMBRE', 'CAMPANA', 'EXT', 'VENT', 'BALA', 'SENSOR', 'PANEL', 'ZUMBADOR', 'CONTACTOR', 'CONMUTADOR']
for e in msp.query('INSERT'):
    name = clean(e.dxf.name)
    layer = clean(e.dxf.layer)
    if any(kw in name.upper() for kw in elec_keywords):
        rot = e.dxf.rotation if hasattr(e.dxf, 'rotation') else 0
        devices.append({
            'handle': e.dxf.handle,
            'name': name,
            'layer': layer,
            'x': e.dxf.insert.x,
            'y': e.dxf.insert.y,
            'rotation': rot
        })

# 4. Mapeo DXF -> RVT (equivalencias v07)
DXF_TO_REVIT = {
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    "ELEC-T-220": ("M_Toma - 220V", "220V"),
    "ELEC-EXT": ("EA", "EA 1010"),
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
    "EA": ("EA", "EA 1010"),
    "S3": ("M_Interruptores", "Simple"),
}

# Filtrar solo dispositivos mapeables
mapped_devices = []
for d in devices:
    if d['name'] in DXF_TO_REVIT:
        fam, typ = DXF_TO_REVIT[d['name']]
        d['familia_revit'] = fam
        d['tipo_revit'] = typ
        mapped_devices.append(d)

# Guardar JSON
output = {
    'version': '1.0',
    'dxf_file': os.path.basename(DXF_PATH),
    'panels': panels,
    'walls': walls,
    'wall_layers': wall_layers,
    'devices_all': devices,
    'devices_mapped': mapped_devices,
    'mapping': DXF_TO_REVIT
}

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("=" * 60)
print("PANELES DXF:", len(panels))
for n, p in panels.items():
    print(f"  {n}: ({p['x']:.2f}, {p['y']:.2f}) layer={p['layer']}")
print("MUROS:", len(walls))
print("DISPOSITIVOS TOTALES:", len(devices))
print("DISPOSITIVOS MAPEABLES:", len(mapped_devices))
print("JSON guardado:", OUT_PATH)
print("=" * 60)