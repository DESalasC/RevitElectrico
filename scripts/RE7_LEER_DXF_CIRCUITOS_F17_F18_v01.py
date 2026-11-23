# -*- coding: utf-8 -*-
"""
RE7_LEER_DXF_CIRCUITOS_F17_F18_v01.py
Lee el DXF XPL y extrae bloques electricos de F17/F18 con sus circuitos cercanos.
Genera JSON para usar en Revit y asignar Marks.

Entorno: Python 3 (fuera de Revit)
"""
import ezdxf
import json
import math
import re
import os
import sys
import datetime

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos-XPL.dxf"
OUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_dxf_circuitos_f17_f18_v01.json"

ZONAS = {
    "F17": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 1000.0, "y_max": 8500.0},
    "F18": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 9000.0, "y_max": 16500.0},
}

BLOQUES_ELEC = [
    "ELEC-T-D-t-15A", "ELEC-T-GFCI-t-15A", "ELEC-I-S-1-5A", "ELEC-I-S-2-5A",
    "ELEC-I-S-C1-5A", "ELEC-TEL", "ELEC-NET-PAU", "ELEC-CAMPANA", "ELEC-TIMBRE",
    "ELEC-F-CONTROL", "ELEC-F-VENT", "S3", "S3C", "ELEC-EXT",
    "Bala Stil Led 10W", "Bala Stil Led 13W", "Bala Stil Led 22W",
]

RADIO_TEXTO_MM = 1000.0
PATRON_CIRCUITO = re.compile(r"\b([A-Z]{2}-\d{2})\b")


def apto_de(x_mm, y_mm):
    for nombre in ZONAS:
        z = ZONAS[nombre]
        if z["x_min"] <= x_mm <= z["x_max"] and z["y_min"] <= y_mm <= z["y_max"]:
            return nombre
    return None


def main():
    print("=" * 70)
    print("RE7_LEER_DXF_CIRCUITOS_F17_F18_v01")
    print("DXF:", DXF_PATH)
    print("=" * 70)

    doc = ezdxf.readfile(DXF_PATH)
    msp = doc.modelspace()

    bloques = []
    textos = []

    # Extraer INSERTs (bloques)
    for e in msp.query("INSERT"):
        name = e.dxf.name or ""
        if name not in BLOQUES_ELEC:
            continue
        p = e.dxf.insert
        apto = apto_de(p.x, p.y)
        if not apto:
            continue
        bloques.append({
            "nombre": name,
            "x": p.x,
            "y": p.y,
            "apto": apto,
            "handle": str(e.dxf.handle),
        })

    # Extraer TEXT y MTEXT
    for e in msp.query("TEXT"):
        p = e.dxf.insert
        textos.append({"x": p.x, "y": p.y, "text": e.dxf.text})
    for e in msp.query("MTEXT"):
        p = e.dxf.insert
        textos.append({"x": p.x, "y": p.y, "text": e.text})

    print("DXF leído: %d bloques electricos F17/F18, %d textos" % (len(bloques), len(textos)))

    # Para cada bloque, buscar circuito mas cercano
    for b in bloques:
        mejor_dist = None
        mejor_circuito = None
        mejor_texto = None
        for t in textos:
            d = math.sqrt((t["x"] - b["x"]) ** 2 + (t["y"] - b["y"]) ** 2)
            if d > RADIO_TEXTO_MM:
                continue
            m = PATRON_CIRCUITO.search(t["text"])
            if m:
                circuito = m.group(1)
                if mejor_dist is None or d < mejor_dist:
                    mejor_dist = d
                    mejor_circuito = circuito
                    mejor_texto = t["text"]
        b["circuito"] = mejor_circuito
        b["circuito_dist"] = mejor_dist
        b["circuito_texto"] = mejor_texto

    # Resumen por apartamento
    for apto in ["F17", "F18"]:
        bs = [b for b in bloques if b["apto"] == apto]
        con_circuito = [b for b in bs if b["circuito"]]
        print("\n%s: %d bloques, %d con circuito asignado" % (apto, len(bs), len(con_circuito)))
        # Mostrar algunos ejemplos
        for b in bs[:5]:
            print("  %s (%.1f,%.1f) -> circuito=%s (dist=%.1fmm, texto=%r)" % (
                b["nombre"], b["x"], b["y"], b["circuito"],
                b["circuito_dist"] or 0, b["circuito_texto"]))

    reporte = {
        "version": "v01",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "dxf": DXF_PATH,
        "resumen": {
            "total_bloques": len(bloques),
            "f17": len([b for b in bloques if b["apto"] == "F17"]),
            "f18": len([b for b in bloques if b["apto"] == "F18"]),
            "con_circuito": len([b for b in bloques if b["circuito"]]),
            "sin_circuito": len([b for b in bloques if not b["circuito"]]),
        },
        "bloques": bloques,
    }

    with open(OUT_JSON, "w") as f:
        f.write(json.dumps(reporte, ensure_ascii=True, indent=2))

    print("\nJSON guardado: %s" % OUT_JSON)
    print("=" * 70)


if __name__ == "__main__":
    main()
