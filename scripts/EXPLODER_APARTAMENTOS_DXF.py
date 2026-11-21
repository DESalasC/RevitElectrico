# -*- coding: utf-8 -*-
"""
EXPLODER_APARTAMENTOS_DXF.py
=============================
Explota SOLO los bloques de apartamentos (no los dispositivos internos)
para obtener coordenadas absolutas directas de cada dispositivo en modelspace.
"""

import ezdxf
import json

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf"
OUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_explotado_apartamentos.dxf"

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

print("Leyendo DXF:", DXF_PATH)
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Identificar bloques de apartamentos
APTO_KEYWORDS = ['APARTAMENTO', 'TIPO', 'E 0', 'F 0', 'B 1', 'C 1', 'D 1']

apto_inserts = []
for e in msp.query('INSERT'):
    name = clean(e.dxf.name)
    if any(kw.upper() in name.upper() for kw in APTO_KEYWORDS):
        apto_inserts.append((name, e.dxf.insert.x, e.dxf.insert.y, e.dxf.handle))

print("Bloques de apartamentos a explotar:", len(apto_inserts))

# EXPLOTAR: mover entidades internas a modelspace con transformación
# ezdxf no tiene explode automático que preserve coords absolutas fácil
# Vamos a crear un NUEVO DXF con los dispositivos en coordenadas absolutas

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

# Extraer dispositivos con coords absolutas (base apto + offset interno)
dispositivos_absolutos = []

for name, base_x, base_y, handle in apto_inserts:
    block_def = doc.blocks.get(name)
    if not block_def:
        continue
    
    for entity in block_def:
        if entity.dxftype() == 'INSERT':
            ent_name = clean(entity.dxf.name)
            if ent_name in DXF_TO_REVIT:
                fam, typ = DXF_TO_REVIT[ent_name]
                rot = entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0
                x_abs = base_x + entity.dxf.insert.x
                y_abs = base_y + entity.dxf.insert.y
                z_abs = entity.dxf.insert.z if hasattr(entity.dxf, 'z') else 0
                
                dispositivos_absolutos.append({
                    'apto_dxf': name,
                    'nombre_dxf': ent_name,
                    'familia_revit': fam,
                    'tipo_revit': typ,
                    'x_mm': x_abs,
                    'y_mm': y_abs,
                    'z_mm': z_abs,
                    'rotacion_grados': rot,
                    'handle': entity.dxf.handle,
                    'layer': clean(entity.dxf.layer)
                })

print("Dispositivos con coords ABSOLUTAS:", len(dispositivos_absolutos))

# Crear NUEVO DXF con dispositivos en modelspace en coords absolutas
new_doc = ezdxf.new('R2010')
new_doc.header['$INSUNITS'] = 4  # mm
new_msp = new_doc.modelspace()

# Agregar dispositivos como INSERT en modelspace (coords absolutas)
# Usar bloques simples (puntos) o directamente POINT entities
for d in dispositivos_absolutos:
    new_msp.add_point((d['x_mm'], d['y_mm'], d['z_mm']), dxfattribs={
        'layer': d['layer'],
        'color': 1
    })

# Guardar DXF explotado
new_doc.saveas(OUT_PATH)
print("\n[OK] DXF explotado guardado:", OUT_PATH)

# También JSON para usar directo
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_dispositivos_ABSOLUTOS_EXPLOTADO.json"
output = {
    'version': '1.0_EXPLOTADO_COORDS_ABSOLUTAS_MM',
    'fecha': '2026-11-20',
    'fuente': 'STM-T5-P5_bloques_electricos.dxf (apartamentos explotados)',
    'unidades': 'mm',
    'dispositivos': dispositivos_absolutos,
    'total': len(dispositivos_absolutos)
}

with open(JSON_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("[OK] JSON guardado:", JSON_PATH)

# Verificar F01, F17, F18
print("\n=== VERIFICACIÓN ===")
for key_name in ['F01', 'F17', 'F18', 'E06', 'E07']:
    devs = [d for d in dispositivos_absolutos if key_name in d['apto_dxf'].upper() and 'A' not in d['apto_dxf'].upper().split(key_name)[-1][:1]]
    if not devs:
        devs = [d for d in dispositivos_absolutos if d['apto_dxf'].upper().startswith(key_name.replace('0', ' 0').replace('17', ' 17').replace('18', ' 18').replace('01', ' 01').replace('06', ' 06').replace('07', ' 07'))]
    # Buscar más simple
    devs = [d for d in dispositivos_absolutos if key_name.replace('0', ' 0') in d['apto_dxf'].upper() or 'F 01' in d['apto_dxf'].upper() or 'F 17' in d['apto_dxf'].upper() or 'F 18' in d['apto_dxf'].upper() or 'E 06' in d['apto_dxf'].upper() or 'E 07' in d['apto_dxf'].upper()]
    if devs:
        print("\n{} - {} dispositivos:".format(key_name, len(devs)))
        for d in devs[:3]:
            print("  {} @ ({:.2f}, {:.2f}) mm".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
        # Panel del apto (primer TB-Panel en el bloque)
        apto_name = devs[0]['apto_dxf']
        # Calcular panel absoluto para este apto
        apto_insert = next((a for a in apto_inserts if a[0] == apto_name), None)
        if apto_insert:
            block_def = doc.blocks.get(apto_name)
            if block_def:
                for ent in block_def:
                    if ent.dxftype() == 'INSERT':
                        en = clean(ent.dxf.name)
                        if 'PANEL' in en.upper() or 'TB-PANEL' in en.upper() or 'TB-PARCIAL' in en.upper():
                            px = apto_insert[1] + ent.dxf.insert.x
                            py = apto_insert[2] + ent.dxf.insert.y
                            print("  PANEL {} @ ({:.2f}, {:.2f}) mm".format(en, px, py))
                            break