# -*- coding: utf-8 -*-
# extraer_circuitos_dxf.py | v1.0 | 2026-11-14
# Ejecutar con Python 3 desde terminal (NO desde Revit)
# Extrae circuitos del DXF y genera JSON
import json
import math
import re
import ezdxf

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo E 06.dxf"
OUTPUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\circuitos_E06.json"
RADIO_BUSQUEDA = 0.5  # metros

# ============================================================================
# LEER DXF
# ============================================================================
print("=" * 78)
print("EXTRAYENDO CIRCUITOS DEL DXF")
print("=" * 78)
print("Archivo: " + DXF_PATH)

dxf_doc = ezdxf.readfile(DXF_PATH)
msp = dxf_doc.modelspace()

# Extraer INSERTs y TEXTs
inserts = {}
texts = []

for entity in msp:
    if entity.dxftype() == 'INSERT':
        handle = entity.dxf.handle
        x = entity.dxf.insert[0]
        y = entity.dxf.insert[1]
        name = entity.dxf.name
        inserts[handle] = {"x": x, "y": y, "name": name}
    elif entity.dxftype() in ['TEXT', 'MTEXT']:
        x = entity.dxf.insert[0] if hasattr(entity.dxf, 'insert') else 0
        y = entity.dxf.insert[1] if hasattr(entity.dxf, 'insert') else 0
        if entity.dxftype() == 'MTEXT':
            text = entity.text
        else:
            text = entity.dxf.text
        texts.append({"x": x, "y": y, "text": text})

print("INSERTs encontrados: %d" % len(inserts))
print("TEXTs encontrados: %d" % len(texts))

# ============================================================================
# ASOCIAR TEXTOS CERCANOS A CADA INSERT
# ============================================================================
print("\nAsociando textos a bloques (radio %.2f m)..." % RADIO_BUSQUEDA)

circuitos = {}

for handle, ins in inserts.items():
    x_ins = ins["x"]
    y_ins = ins["y"]
    name = ins["name"]
    
    textos_cercanos = []
    for txt in texts:
        dx = txt["x"] - x_ins
        dy = txt["y"] - y_ins
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < RADIO_BUSQUEDA:
            textos_cercanos.append(txt["text"])
    
    # Buscar circuito (patrón: letras-números, ej: TE-03, IL-01, AL-02, AC-01)
    circuito = None
    for txt in textos_cercanos:
        match = re.search(r'\b([A-Z]{2,3}-\d{2,3})\b', txt)
        if match:
            circuito = match.group(1)
            break
    
    # Buscar altura (patrón: número seguido de 'm', ej: 0.7m, 1.2m)
    altura = None
    for txt in textos_cercanos:
        match = re.search(r'(\d+\.?\d*)\s*m\b', txt)
        if match:
            altura = float(match.group(1))
            break
    
    if circuito or altura:
        circuitos[handle] = {
            "nombre_bloque": name,
            "circuito": circuito,
            "altura_dxf": altura,
            "textos_cercanos": textos_cercanos
        }

print("\nCircuitos encontrados: %d" % len(circuitos))

# ============================================================================
# GUARDAR JSON
# ============================================================================
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(circuitos, f, indent=2, ensure_ascii=False)

print("\nJSON guardado en: " + OUTPUT_PATH)

# ============================================================================
# REPORTE DETALLADO
# ============================================================================
print("\n" + "=" * 78)
print("DETALLE DE CIRCUITOS")
print("=" * 78)

for handle, info in sorted(circuitos.items()):
    print("\nHandle: %s" % handle)
    print("  Bloque: %s" % info["nombre_bloque"])
    print("  Circuito: %s" % (info["circuito"] if info["circuito"] else "NO ENCONTRADO"))
    print("  Altura DXF: %s" % (info["altura_dxf"] if info["altura_dxf"] else "NO ENCONTRADA"))
    print("  Textos cercanos: %s" % info["textos_cercanos"])

print("\n" + "=" * 78)
print("FIN")
print("=" * 78)