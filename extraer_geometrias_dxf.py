"""
Script Fase 1 — Extracción de geometrías eléctricas del DXF para modelado 3D.
Lee LWPOLYLINE, LINE, ARC, CIRCLE con sus capas y puntos.
Genera JSON para modelado 3D en Revit (conductos/cableado).
"""

import ezdxf
import json
import math
from collections import Counter

DXF_ORIGEN = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\3.-Proceso\STM-T4-P4_todos_bloques_electricos.dxf"
JSON_SALIDA = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\3.-Proceso\STM-T4-P4_geometrias_3d.json"

CAPAS_ELECTRICAS = ["ELEC-", "Elec-", "E-Lite-", "Elec-Lite-", "TDT", "Apartamento"]

def pertenece_a_capa_electrica(capa):
    for pref in CAPAS_ELECTRICAS:
        if capa.startswith(pref):
            return True
    return False

def extraer_geometrias():
    doc = ezdxf.readfile(DXF_ORIGEN)
    msp = doc.modelspace()

    polilineas = []
    lineas = []
    arcos = []
    circulos = []

    for entity in msp:
        capa = entity.dxf.layer
        es_electrica = pertenece_a_capa_electrica(capa)

        if entity.dxftype() == "LWPOLYLINE":
            puntos = [(round(p[0], 3), round(p[1], 3), round(p[2] if len(p) > 2 else 0, 3))
                      for p in entity.get_points()]
            if len(puntos) >= 2:
                polilineas.append({
                    "capa": capa,
                    "es_electrica": es_electrica,
                    "puntos": puntos,
                    "cerrada": entity.closed
                })

        elif entity.dxftype() == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            lineas.append({
                "capa": capa,
                "es_electrica": es_electrica,
                "inicio": [round(start.x, 3), round(start.y, 3), round(start.z, 3)],
                "fin": [round(end.x, 3), round(end.y, 3), round(end.z, 3)]
            })

        elif entity.dxftype() == "ARC":
            center = entity.dxf.center
            arcos.append({
                "capa": capa,
                "es_electrica": es_electrica,
                "centro": [round(center.x, 3), round(center.y, 3), round(center.z, 3)],
                "radio": round(entity.dxf.radius, 3),
                "angulo_inicio": round(math.degrees(entity.dxf.start_angle), 2),
                "angulo_fin": round(math.degrees(entity.dxf.end_angle), 2)
            })

        elif entity.dxftype() == "CIRCLE":
            center = entity.dxf.center
            circulos.append({
                "capa": capa,
                "es_electrica": es_electrica,
                "centro": [round(center.x, 3), round(center.y, 3), round(center.z, 3)],
                "radio": round(entity.dxf.radius, 3)
            })

    salida = {
        "origen_dxf": DXF_ORIGEN,
        "resumen": {
            "polilineas": len(polilineas),
            "lineas": len(lineas),
            "arcos": len(arcos),
            "circulos": len(circulos),
            "polilineas_electricas": sum(1 for p in polilineas if p["es_electrica"]),
            "lineas_electricas": sum(1 for l in lineas if l["es_electrica"]),
        },
        "polilineas": polilineas,
        "lineas": lineas,
        "arcos": arcos,
        "circulos": circulos
    }

    with open(JSON_SALIDA, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    print("=== Estadisticas de geometrias ===")
    print(f"Polilineas: {len(polilineas)} (electricas: {salida['resumen']['polilineas_electricas']})")
    print(f"Lineas: {len(lineas)} (electricas: {salida['resumen']['lineas_electricas']})")
    print(f"Arcos: {len(arcos)}")
    print(f"Circulos: {len(circulos)}")
    print(f"\nJSON guardado en: {JSON_SALIDA}")
    return salida

if __name__ == "__main__":
    extraer_geometrias()
