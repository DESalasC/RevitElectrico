# -*- coding: utf-8 -*-
"""
EXTRAER_ELECTRICOS_XPL.py
=========================
Extrae SOLO los dispositivos eléctricos del DXF explotado (coordenadas absolutas mm).
Estas coordenadas YA están en el sistema de Revit (origen coincidente).
"""

import ezdxf
import json

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos-XPL.dxf"
OUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

print("Leyendo DXF explotado:", DXF_PATH)
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Mapeo DXF -> Revit (solo eléctricos)
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

dispositivos = []

for e in msp.query('INSERT'):
    name = clean(e.dxf.name)
    if name in DXF_TO_REVIT:
        fam, typ = DXF_TO_REVIT[name]
        rot = e.dxf.rotation if hasattr(e.dxf, 'rotation') else 0
        x = e.dxf.insert.x
        y = e.dxf.insert.y
        z = e.dxf.insert.z if hasattr(e.dxf, 'z') else 0
        dispositivos.append({
            'nombre_dxf': name,
            'familia_revit': fam,
            'tipo_revit': typ,
            'x_mm': x,
            'y_mm': y,
            'z_mm': z,
            'rotacion_grados': rot,
            'handle': e.dxf.handle,
            'layer': clean(e.dxf.layer)
        })

print("Dispositivos eléctricos encontrados:", len(dispositivos))

# Verificar F01, F17, F18, E06, E07 (buscar por coordenadas aproximadas)
# F01 panel en Revit: (11597, 7492) mm
# F17 panel en Revit: (8794, 7519) mm
# F18 panel en Revit: (8794, 10159) mm
# E06 panel en Revit: (6507, 10812) mm
# E07 panel en Revit: (-5670, 7302) mm

# Agrupar por zona (aproximación por coordenadas)
from collections import defaultdict

# Usar panel como referencia para agrupar
# Como no tenemos panel en este DXF, agrupar por proximidad a coordenadas conocidas de paneles
PANELES_REF = {
    'F01': (11597, 7492),
    'F17': (8794, 7519),
    'F18': (8794, 10159),
    'E06': (6507, 10812),
    'E07': (-5670, 7302),
    'E05': (6540, 6857),
    'E08': (-5670, 10383),
    'TF 02': (11594, 10149),
    'TF 01a': (-14318, 7493),
    'TF 01b': (-20299, 7493),
    'TF 02a': (-14310, 10149),
    'TF 02b': (-24100, 10149),
    'F17a': (-19575, 7519),
    'F18a': (-19575, 10159),
    'E07a': (-41037, 7302),
    'E08a': (-41037, 10383),
    'B15': (-44300, 8116),
    'B16': (-44350, 9570),
    'C14': (-29395, 6932),
    'D13': (-29375, 10801),
}

# Asignar cada dispositivo al panel más cercano
for d in dispositivos:
    best_key = None
    best_dist = float('inf')
    for key, (px, py) in PANELES_REF.items():
        dist = ((d['x_mm'] - px)**2 + (d['y_mm'] - py)**2)**0.5
        if dist < best_dist:
            best_dist = dist
            best_key = key
    d['apto_asignado'] = best_key
    d['dist_panel_mm'] = best_dist

# Contar por apto
counts = defaultdict(int)
for d in dispositivos:
    counts[d['apto_asignado']] += 1

print("\nDispositivos por apartamento (asignados por proximidad a panel):")
for k, v in sorted(counts.items()):
    print("  {}: {}".format(k, v))

# Guardar JSON
output = {
    'version': '1.0_XPL_ABSOLUTOS_MM',
    'fecha': '2026-11-20',
    'fuente': 'STM-T5-P5_bloques_electricos-XPL.dxf (explotado desde Revit)',
    'nota': 'Coordenadas ABSOLUTAS en mm. Origen DXF = Origen Revit Internal Origin. Solo mm -> m.',
    'unidades': 'mm',
    'dispositivos': dispositivos,
    'total': len(dispositivos)
}

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n[OK] Guardado:", OUT_PATH)

# Verificar algunos
print("\n=== MUESTRA ===")
for apto in ['F01', 'F17', 'F18', 'E06', 'E07']:
    devs = [d for d in dispositivos if d['apto_asignado'] == apto]
    print("\n{}: {} dispositivos".format(apto, len(devs)))
    for d in devs[:3]:
        print("  {} @ ({:.2f}, {:.2f}) mm".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))