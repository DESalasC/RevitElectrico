# -*- coding: utf-8 -*-
# analizar_dxf_F01_v56.py | v56.0 | Python 3
# Analiza el DXF del Apartamento Tipo F 01 y genera plan de colocación
import json
import math
import re
import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 01.dxf"
OUTPUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\plan_F01_v01.json"

print("=" * 78)
print("ANALISIS DXF F01 v56.0")
print("=" * 78)
print("Archivo: " + DXF_PATH)

# Leer DXF
doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

# Extraer INSERTs y TEXTs
inserts = []
texts = []

for entity in msp:
    if entity.dxftype() == 'INSERT':
        inserts.append({
            "handle": entity.dxf.handle,
            "block_name": entity.dxf.name,
            "x": entity.dxf.insert[0],
            "y": entity.dxf.insert[1],
            "rotation": entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0
        })
    elif entity.dxftype() in ['TEXT', 'MTEXT']:
        x = entity.dxf.insert[0] if hasattr(entity.dxf, 'insert') else 0
        y = entity.dxf.insert[1] if hasattr(entity.dxf, 'insert') else 0
        text = entity.dxf.text if hasattr(entity.dxf, 'text') else ""
        if entity.dxftype() == 'MTEXT':
            text = entity.text
        texts.append({"x": x, "y": y, "text": text})

print("\nINSERTs encontrados: %d" % len(inserts))
print("TEXTs encontrados: %d" % len(texts))

# Estadísticas de bloques
block_counts = {}
for ins in inserts:
    name = ins["block_name"]
    block_counts[name] = block_counts.get(name, 0) + 1

print("\nBloques encontrados:")
for name, count in sorted(block_counts.items(), key=lambda x: -x[1])[:20]:
    print("  %-30s: %d" % (name, count))

# Identificar el origen del bloque del apartamento
print("\n" + "=" * 78)
print("IDENTIFICANDO ORIGEN DEL BLOQUE")
print("=" * 78)

if inserts:
    min_x = min(ins["x"] for ins in inserts)
    min_y = min(ins["y"] for ins in inserts)
    max_x = max(ins["x"] for ins in inserts)
    max_y = max(ins["y"] for ins in inserts)
    
    print("Rango de coordenadas DXF:")
    print("  X: %.3f a %.3f m" % (min_x, max_x))
    print("  Y: %.3f a %.3f m" % (min_y, max_y))
    print("  Ancho: %.3f m" % (max_x - min_x))
    print("  Alto: %.3f m" % (max_y - min_y))
    
    # Buscar el bloque más cercano a la esquina inferior izquierda
    origen_candidates = []
    for ins in inserts:
        dist = math.sqrt((ins["x"] - min_x)**2 + (ins["y"] - min_y)**2)
        origen_candidates.append((dist, ins))
    
    origen_candidates.sort()
    print("\nCandidatos a origen del bloque (esquina inferior izquierda):")
    for i, (dist, ins) in enumerate(origen_candidates[:5]):
        print("  [%d] Handle=%s | Bloque=%s | Pos=(%.3f, %.3f) | Dist=%.3f" % (
            i+1, ins["handle"], ins["block_name"], ins["x"], ins["y"], dist))
    
    # Asumir que el primer candidato es el origen
    origen = None
    if origen_candidates:
        origen = origen_candidates[0][1]
        print("\nOrigen del bloque F01 (estimado):")
        print("  Handle: %s" % origen["handle"])
        print("  Bloque: %s" % origen["block_name"])
        print("  Posición DXF: (%.6f, %.6f)" % (origen["x"], origen["y"]))

# Filtrar dispositivos eléctricos
print("\n" + "=" * 78)
print("FILTRANDO DISPOSITIVOS ELÉCTRICOS")
print("=" * 78)

bloques_electricos = [
    "Bala Stil Led 13W",
    "Bala Stil Led 10W",
    "Bala Stil Led 22W",
    "ELEC-I-S-C1-5A",
    "ELEC-I-S-1-5A",
    "S3",
    "ELEC-F-CONTROL",
    "ELEC-F-VENT",
    "ELEC-TIMBRE",
    "ELEC-T-GFCI-t-15A",
    "ELEC-T-D-t-15A",
    "ELEC-CAMPANA",
    "ELEC-NET-PAU",
    "ELEC-TEL",
    "ELEC-EXT"
]

dispositivos = []
for ins in inserts:
    if ins["block_name"] in bloques_electricos:
        dispositivos.append(ins)

print("Dispositivos eléctricos encontrados: %d" % len(dispositivos))

# Asociar textos cercanos
print("\nAsociando textos a dispositivos...")
RADIO_BUSQUEDA = 0.5

for dev in dispositivos:
    textos_cercanos = []
    for txt in texts:
        dx = txt["x"] - dev["x"]
        dy = txt["y"] - dev["y"]
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < RADIO_BUSQUEDA:
            textos_cercanos.append(txt["text"])
    
    circuito = None
    for txt in textos_cercanos:
        match = re.search(r'\b([A-Z]{2,3}-\d{2,3})\b', txt)
        if match:
            circuito = match.group(1)
            break
    
    altura = None
    for txt in textos_cercanos:
        match = re.search(r'(\d+\.?\d*)\s*m\b', txt)
        if match:
            altura = float(match.group(1))
            break
    
    dev["circuito"] = circuito
    dev["altura_dxf"] = altura
    dev["textos_cercanos"] = textos_cercanos

# Aplicar reglas de rotación del E06
print("\nAplicando reglas de rotación del E06...")
REGLAS_ROTACION = {
    "M_Interruptores": 180.0,
    "M_Comunicaciones": -120.0,
    "M_Pulsador - Interruptor": 90.0,
    "M_Toma doble": -75.0,
    "M_Climatizacion": 0.0,
    "M_ClimatizacionV": 0.0,
    "M_Iluminacion": 0.0,
    "M_Timbre": 0.0,
    "Consolidation_Point": 0.0,
}

DXF_TO_REVIT = {
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    "ELEC-I-S-C1-5A": ("M_Interruptores", "Simple conmutable"),
    "ELEC-I-S-1-5A": ("M_Interruptores", "Simple"),
    "S3": ("M_Interruptores", "Triple"),
    "ELEC-F-CONTROL": ("M_Climatizacion", "Interruptor Ventilador"),
    "ELEC-F-VENT": ("M_ClimatizacionV", "Ventilador"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    "ELEC-CAMPANA": ("M_Timbre", "Campana"),
    "ELEC-NET-PAU": ("Consolidation_Point", "CPB6BL"),
    "ELEC-TEL": ("M_Comunicaciones", "Datos"),
    "ELEC-EXT": ("EA", "M_Extractor"),
}

for dev in dispositivos:
    dxf_name = dev["block_name"]
    if dxf_name in DXF_TO_REVIT:
        fam_name, type_name = DXF_TO_REVIT[dxf_name]
        dev["familia_revit"] = fam_name
        dev["tipo_revit"] = type_name
        
        delta_rot = REGLAS_ROTACION.get(fam_name, 0.0)
        dev["rotacion_dxf"] = dev["rotation"]
        dev["rotacion_final"] = dev["rotation"] + delta_rot
        dev["delta_rotacion"] = delta_rot
    else:
        dev["familia_revit"] = "Desconocido"
        dev["tipo_revit"] = "Desconocido"
        dev["rotacion_dxf"] = dev["rotation"]
        dev["rotacion_final"] = dev["rotation"]
        dev["delta_rotacion"] = 0.0

# Generar plan
print("\n" + "=" * 78)
print("GENERANDO PLAN DE COLOCACIÓN")
print("=" * 78)

plan = []
for dev in dispositivos:
    plan.append({
        "handle": dev["handle"],
        "nombre": dev["block_name"],
        "familia_revit": dev["familia_revit"],
        "tipo_revit": dev["tipo_revit"],
        "x_dxf": dev["x"],
        "y_dxf": dev["y"],
        "rotacion_dxf": dev["rotacion_dxf"],
        "rotacion_final": dev["rotacion_final"],
        "delta_rotacion": dev["delta_rotacion"],
        "circuito": dev.get("circuito"),
        "altura_dxf": dev.get("altura_dxf"),
        "textos_cercanos": dev.get("textos_cercanos", [])
    })

data = {
    "apartamento": "F 01",
    "dxf_path": DXF_PATH,
    "origen_bloque": {
        "handle": origen["handle"],
        "bloque": origen["block_name"],
        "x": origen["x"],
        "y": origen["y"]
    } if origen else None,
    "total_dispositivos": len(plan),
    "plan": plan
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("\nPlan guardado: %s" % OUTPUT_PATH)

# Estadísticas
print("\n" + "=" * 78)
print("ESTADÍSTICAS")
print("=" * 78)

por_familia = {}
for p in plan:
    fam = p["familia_revit"]
    por_familia[fam] = por_familia.get(fam, 0) + 1

print("Por familia Revit:")
for fam, count in sorted(por_familia.items()):
    print("  %-30s: %d" % (fam, count))

con_circuito = sum(1 for p in plan if p["circuito"])
print("\nDispositivos con circuito: %d de %d" % (con_circuito, len(plan)))

con_altura = sum(1 for p in plan if p["altura_dxf"])
print("Dispositivos con altura DXF: %d de %d" % (con_altura, len(plan)))

print("\n" + "=" * 78)
print("FIN")
print("=" * 78)