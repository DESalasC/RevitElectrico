# -*- coding: utf-8 -*-
"""extraer_F01_F02_DXF_a_JSON.py - Python 3.12 + ezdxf (DXF eléctricos reales)"""

import ezdxf
import json
import os

BASE = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase"
OUT_DIR = r"D:\Work\PROJECTS\RevitElectrico\data"

F01_DXF = os.path.join(BASE, "Apartamento Tipo F 01.dxf")
F02_DXF = os.path.join(BASE, "Apartamento Tipo F 02.dxf")
OUT_PATH = os.path.join(OUT_DIR, "dxf_F01_F02_extraido.json")

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

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

def extract_dxf(dxf_path, apto_name):
    print(f"\nLeyendo {apto_name}: {dxf_path}")
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    
    devices = []
    panels = {}
    walls = []
    
    for e in msp.query('INSERT'):
        name = clean(e.dxf.name)
        layer = clean(e.dxf.layer)
        rot = e.dxf.rotation if hasattr(e.dxf, 'rotation') else 0
        
        # Detectar paneles
        if 'PANEL' in name.upper() or 'TF' in name.upper() or 'T0' in name.upper():
            panels[name] = {'x': e.dxf.insert.x, 'y': e.dxf.insert.y, 'layer': layer}
        
        # Dispositivos eléctricos
        if any(kw in name.upper() for kw in ['ELEC', 'TOMA', 'INTERRUPT', 'ILUM', 'TIMBRE', 'CAMPANA', 'EXT', 'VENT', 'BALA', 'SENSOR', 'ZUMBADOR']):
            d = {
                'apto': apto_name,
                'handle': e.dxf.handle,
                'name': name,
                'layer': layer,
                'x': e.dxf.insert.x,
                'y': e.dxf.insert.y,
                'rotation': rot
            }
            if name in DXF_TO_REVIT:
                fam, typ = DXF_TO_REVIT[name]
                d['familia_revit'] = fam
                d['tipo_revit'] = typ
            devices.append(d)
    
    # Muros (polilíneas en layers ELEC-*)
    wall_layers = [l.dxf.name for l in doc.layers if l.dxf.name.startswith('ELEC-')]
    for e in msp.query('LWPOLYLINE'):
        if e.dxf.layer in wall_layers:
            walls.append({'layer': e.dxf.layer, 'points': [(v[0], v[1]) for v in e.get_points()], 'closed': e.closed})
    
    print(f"  Paneles: {len(panels)} | Dispositivos: {len(devices)} | Muros: {len(walls)}")
    for n, p in panels.items():
        print(f"    Panel: {n} @ ({p['x']:.2f}, {p['y']:.2f})")
    
    return {'apto': apto_name, 'panels': panels, 'devices': devices, 'walls': walls, 'wall_layers': wall_layers}

# Extraer ambos
f01_data = extract_dxf(F01_DXF, "F01")
f02_data = extract_dxf(F02_DXF, "F02")

# Guardar JSON combinado
output = {
    'version': '1.0',
    'F01': f01_data,
    'F02': f02_data
}

OUT_FILE = os.path.join(OUT_DIR, "dxf_F01_F02_extraido.json")
with open(OUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\nJSON guardado: {OUT_FILE}")
print(f"F01 dispositivos mapeables: {sum(1 for d in f01_data['devices'] if 'familia_revit' in d)}")
print(f"F02 dispositivos mapeables: {sum(1 for d in f02_data['devices'] if 'familia_revit' in d)}")