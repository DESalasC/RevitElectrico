# -*- coding: utf-8 -*-
"""
RE7_REGISTRO_COMPONENTES_POR_APTO_v01.py
Lee el DXF XPL y genera un registro de componentes electricos por apartamento,
para validar/asignar el Mark de cada dispositivo en Revit sin volver al DXF.

SOLO LECTURA del DXF. Escribe un JSON en data/ que el operador revisa y firma.

Entrada:
  D:\\Work\\PROJECTS\\RevitElectrico\\ArchivosBase\\STM-T5-P5_bloques_electricos-XPL.dxf
Salida:
  data/f7_registro_componentes_por_apto_v01.json

Entorno: Python 3 (offline, no toca Revit)
"""
import ezdxf
import json
import math
import os
import sys
from collections import defaultdict, Counter

DXF_PATH = "D:\\Work\\PROJECTS\\RevitElectrico\\ArchivosBase\\STM-T5-P5_bloques_electricos-XPL.dxf"
OUT_JSON = "D:\\Work\\PROJECTS\\RevitElectrico\\data\\f7_registro_componentes_por_apto_v01.json"

# Zonas de apartamento (mm). Ajustar si los DXF parciales desplazan coordenadas.
ZONAS = {
    "F17": {"x_min": 6500.0, "x_max": 11000.0, "y_min": 500.0, "y_max": 8800.0},
    "F18": {"x_min": 6500.0, "x_max": 11000.0, "y_min": 8800.0, "y_max": 17000.0},
}

# Bloques que consideramos componentes electricos (no etiquetas de cable 1FNT/1FTNR...)
BLOQUES_ELECTRICOS = [
    "ELEC-T-GFCI-t-15A", "ELEC-T-D-t-15A", "ELEC-I-S-1-5A", "ELEC-I-S-2-5A",
    "ELEC-I-S-C1-5A", "ELEC-TEL", "ELEC-NET-PAU", "ELEC-CAMPANA", "ELEC-TIMBRE",
    "ELEC-F-CONTROL", "ELEC-F-VENT", "S3", "S3C", "ELEC-EXT",
    "Bala Stil Led 10W", "Bala Stil Led 13W", "Bala Stil Led 22W",
    "1FNT", "1FTNR", "1TNR", "1FT2R", "1FT2N", "1FTN2R", "1TN2R", "2FT2N",
    "1TNF4R", "1TNF3R", "1T1N3R", "2F2N1T1R",
]

# Bloques de panel/tablero que identifican el apartamento en el DXF
BLOQUES_PANEL = ["TB-Panel", "TB-Parcial"]


def apto_de(x_mm, y_mm):
    for nombre in ZONAS:
        z = ZONAS[nombre]
        if z["x_min"] <= x_mm <= z["x_max"] and z["y_min"] <= y_mm <= z["y_max"]:
            return nombre
    return "SIN_ZONA"


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main():
    print("=" * 80)
    print("RE7_REGISTRO_COMPONENTES_POR_APTO_v01")
    print("DXF:", DXF_PATH)
    print("=" * 80)

    doc = ezdxf.readfile(DXF_PATH)
    msp = doc.modelspace()

    # --- Extraer bloques de panel (referencia de apartamento en el DXF)
    paneles = []
    for e in msp.query("INSERT"):
        name = e.dxf.name or ""
        if name in BLOQUES_PANEL:
            p = e.dxf.insert
            paneles.append({
                "nombre": name,
                "x": round(p.x, 3),
                "y": round(p.y, 3),
                "apto": apto_de(p.x, p.y),
            })
    print("Paneles encontrados en DXF:", len(paneles))
    for p in paneles:
        print("  %-12s (%-8.1f, %-8.1f) apto=%s" % (p["nombre"], p["x"], p["y"], p["apto"]))

    # --- Extraer componentes electricos
    componentes = []
    for e in msp.query("INSERT"):
        name = e.dxf.name or ""
        if name not in BLOQUES_ELECTRICOS:
            continue
        p = e.dxf.insert
        apto = apto_de(p.x, p.y)
        componentes.append({
            "bloque": name,
            "x": round(p.x, 3),
            "y": round(p.y, 3),
            "apto": apto,
            "rot": round(e.dxf.rotation, 2) if hasattr(e.dxf, "rotation") else 0.0,
        })

    print("")
    print("Componentes electricos en DXF:", len(componentes))
    por_apto_bloque = defaultdict(Counter)
    for c in componentes:
        por_apto_bloque[c["apto"]][c["bloque"]] += 1
    for apto in sorted(por_apto_bloque):
        print("  %s: %d componentes" % (apto, sum(por_apto_bloque[apto].values())))
        for b, n in sorted(por_apto_bloque[apto].items()):
            print("      %-28s %d" % (b, n))

    # --- Construir registro por apartamento
    registro = {
        "fuente_dxf": DXF_PATH,
        "generado_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "zonas": ZONAS,
        "paneles": paneles,
        "apartamentos": {},
    }

    for apto in sorted(ZONAS.keys()):
        comps_apto = [c for c in componentes if c["apto"] == apto]
        registro["apartamentos"][apto] = {
            "total_componentes": len(comps_apto),
            "componentes": comps_apto,
            "pendicion_revision": True,  # el operador debe revisar y poner en False
            "marque_en_revit": False,    # se pone True cuando se escribio el Mark en Revit
        }

    with open(OUT_JSON, "w") as f:
        f.write(json.dumps(registro, ensure_ascii=True, indent=2))
    print("")
    print("JSON guardado en:", OUT_JSON)
    print("")
    print("SIGUIENTE PASO (operador):")
    print("  1. Revisar cada apartamento en el JSON y confirmar los componentes.")
    print("  2. Si hay desplazamiento entre DXF y modelo, ajustar zonas en este script.")
    print("  3. Marcar pendicion_revision=False cuando este confirmado.")
    print("  4. Ejecutar RE7_ASIGNA_MARK_POR_APTO_v01.py en Revit para escribir los Marks.")
    print("=" * 80)


if __name__ == "__main__":
    main()
