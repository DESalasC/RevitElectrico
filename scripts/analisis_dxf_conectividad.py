import ezdxf, json
from collections import Counter, defaultdict

dxf_path = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos-XPL.dxf"
doc = ezdxf.readfile(dxf_path)
msp = doc.modelspace()

rango_f17 = {"x_min": 7000, "x_max": 10500, "y_min": 1000, "y_max": 8500}
rango_f18 = {"x_min": 7000, "x_max": 10500, "y_min": 9000, "y_max": 16500}

def en_rango(x, y, rango):
    return rango["x_min"] <= x <= rango["x_max"] and rango["y_min"] <= y <= rango["y_max"]

# ============ 1. TEXTOS DE CIRCUITO ============
print("=" * 70)
print("TEXTOS en rangos F17/F18 - posibles etiquetas de circuito")
print("=" * 70)

textos_circuito = []
for e in msp:
    if e.dxftype() in ("MTEXT", "TEXT"):
        try:
            pt = e.dxf.insert if hasattr(e.dxf, "insert") else e.dxf.location
        except:
            continue
        texto = e.text if e.dxftype() == "MTEXT" else (e.dxf.text if hasattr(e.dxf, "text") else str(e))
        x, y = pt.x, pt.y
        apto = None
        if en_rango(x, y, rango_f17):
            apto = "F17"
        elif en_rango(x, y, rango_f18):
            apto = "F18"
        if apto:
            textos_circuito.append({
                "tipo": e.dxftype(),
                "texto": texto[:80],
                "x": round(x, 2), "y": round(y, 2),
                "apto": apto
            })

print("Total textos en F17/F18: %d" % len(textos_circuito))
print("F17: %d, F18: %d" % (
    sum(1 for t in textos_circuito if t["apto"] == "F17"),
    sum(1 for t in textos_circuito if t["apto"] == "F18")
))

print()
print("=== Textos que parecen etiquetas de circuito (longitud <= 15) ===")
etiquetas = [t for t in textos_circuito if len(t["texto"].strip()) <= 15 and len(t["texto"].strip()) > 0]
for t in sorted(etiquetas, key=lambda x: (x["apto"], x["y"], x["x"]))[:80]:
    print("  [%s] (%8.1f, %8.1f) '%s'" % (t["apto"], t["x"], t["y"], t["texto"]))

# ============ 2. BLOQUES DE CABLE ============
print()
print("=" * 70)
print("BLOQUES de cable (1FNT, 1FTNR, etc.) en rangos F17/F18")
print("=" * 70)

bloques_cable = ["1FNT", "1FTNR", "1TNR", "1FT2R", "1FT2N", "1FTN2R", "1TN2R", "2FT2N",
                 "1TNF4R", "1TNF3R", "1T1N3R", "2F2N1T1R"]

inserts_cable = []
for e in msp.query("INSERT"):
    name = e.dxf.name or ""
    if name in bloques_cable:
        pt = e.dxf.insert
        x, y = pt.x, pt.y
        apto = None
        if en_rango(x, y, rango_f17):
            apto = "F17"
        elif en_rango(x, y, rango_f18):
            apto = "F18"
        if apto:
            inserts_cable.append({
                "bloque": name,
                "x": round(x, 2), "y": round(y, 2),
                "apto": apto
            })

print("Total bloques de cable en F17/F18: %d" % len(inserts_cable))
for b in sorted(inserts_cable, key=lambda x: (x["apto"], x["y"], x["x"])):
    print("  [%s] (%8.1f, %8.1f) %s" % (b["apto"], b["x"], b["y"], b["bloque"]))

# ============ 3. APARATOS ELECTRICOS ============
print()
print("=" * 70)
print("APARATOS ELECTRICOS en rangos F17/F18")
print("=" * 70)

bloques_electricos = [
    "ELEC-T-GFCI-t-15A", "ELEC-T-D-t-15A", "ELEC-I-S-1-5A", "ELEC-I-S-2-5A",
    "ELEC-I-S-C1-5A", "ELEC-TEL", "ELEC-NET-PAU", "ELEC-CAMPANA", "ELEC-TIMBRE",
    "ELEC-F-CONTROL", "ELEC-F-VENT", "S3", "S3C", "ELEC-EXT",
    "Bala Stil Led 10W", "Bala Stil Led 13W", "Bala Stil Led 22W",
    "1FTN", "1FTNR", "1TNR", "1FT2R", "1FT2N", "1FTN2R", "1TN2R", "2FT2N",
    "1TNF4R", "1TNF3R", "1T1N3R", "2F2N1T1R"
]

inserts_elec = []
for e in msp.query("INSERT"):
    name = e.dxf.name or ""
    if name not in bloques_electricos:
        continue
    pt = e.dxf.insert
    x, y = pt.x, pt.y
    apto = None
    if en_rango(x, y, rango_f17):
        apto = "F17"
    elif en_rango(x, y, rango_f18):
        apto = "F18"
    if apto:
        inserts_elec.append({
            "bloque": name,
            "x": round(x, 2), "y": round(y, 2),
            "apto": apto
        })

print("Total aparatos en F17/F18: %d" % len(inserts_elec))
print("F17: %d, F18: %d" % (
    sum(1 for i in inserts_elec if i["apto"] == "F17"),
    sum(1 for i in inserts_elec if i["apto"] == "F18")
))

# ============ 4. INTENTAR AGRUPAR POR CIRCUITO ============
# Buscar textos que contengan patrones de circuito (ej: "C1", "ILUM1", "TOMAS1", etc.)
print()
print("=" * 70)
print("BUSQUEDA DE PATRONES DE CIRCUITO EN TEXTOS")
print("=" * 70)

import re
patron_circuito = re.compile(r'(?:circuito|circ|c\.?\s*|)\s*([A-Z]?\d+[A-Z]?)', re.IGNORECASE)
for t in textos_circuito:
    texto = t["texto"].strip()
    if re.search(r'(circ|circuito|C\d|ILUM|TOMAS|COM|FUERZA|TEL|NET)', texto, re.IGNORECASE):
        print("  [%s] (%8.1f, %8.1f) '%s'" % (t["apto"], t["x"], t["y"], texto))

# Guardar todo
salida = {
    "textos_circuito": textos_circuito,
    "bloques_cable": inserts_cable,
    "inserts_elec": inserts_elec,
    "rango_f17": rango_f17,
    "rango_f18": rango_f18,
}
out_path = r"D:\Work\PROJECTS\RevitElectrico\data\f7_dxf_analisis_conectividad_v01.json"
with open(out_path, "w") as f:
    json.dump(salida, f, indent=2)
print()
print("Guardado en %s" % out_path)
print("Resumen: textos=%d, bloques_cable=%d, aparatos=%d" % (
    len(textos_circuito), len(inserts_cable), len(inserts_elec)))
