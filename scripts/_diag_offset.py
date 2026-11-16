# -*- coding: utf-8 -*-
"""Diagnostico del offset entre las coordenadas del mapa Revit y el DXF."""
import json
import math
import sys

sys.path.insert(0, r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\ruteo")

import ezdxf

DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T4-P4_todos_bloques_electricos.dxf"
MAPA = r"D:\Work\PROJECTS\RevitElectrico\data\apto_F_02_aplicar_mapa_v3.json"

doc = ezdxf.readfile(DXF)
msp = doc.modelspace()

# todos los INSERT electricos del DXF
dxf_pts = []
for e in msp.query("INSERT"):
    capa = e.dxf.layer
    if capa.startswith(("ELEC-", "Elec-", "E-Lite")):
        dxf_pts.append((e.dxf.insert.x, e.dxf.insert.y, e.dxf.name, capa))

mapa = json.load(open(MAPA, encoding="utf-8-sig"))
alvo = [(a["x_revit"], a["y_revit"], a["nombre_bloque"]) for a in mapa["acciones_modelar"]]

def bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), max(xs), min(ys), max(ys))

print("DXF  bbox: X %.2f..%.2f  Y %.2f..%.2f  (n=%d)" % (*bbox(dxf_pts), len(dxf_pts)))
print("MAPA bbox: X %.2f..%.2f  Y %.2f..%.2f  (n=%d)" % (*bbox(alvo), len(alvo)))
print()

# 1. offset ingenuo por centroides
cx_dxf = sum(p[0] for p in dxf_pts) / len(dxf_pts)
cy_dxf = sum(p[1] for p in dxf_pts) / len(dxf_pts)
cx_map = sum(p[0] for p in alvo) / len(alvo)
cy_map = sum(p[1] for p in alvo) / len(alvo)
print("centroide DXF : (%.3f, %.3f)" % (cx_dxf, cy_dxf))
print("centroide MAPA: (%.3f, %.3f)" % (cx_map, cy_map))
print("delta centroides: (%.3f, %.3f)" % (cx_map - cx_dxf, cy_map - cy_dxf))
print()

# 2. para cada punto del mapa, el punto DXF mas cercano y el vector resultante
print("Vectores mapa->DXF mas cercano (primeros 12):")
for x, y, nombre in alvo[:12]:
    best = min(dxf_pts, key=lambda p: math.hypot(p[0] - x, p[1] - y))
    d = math.hypot(best[0] - x, best[1] - y)
    print("  mapa(%.2f, %.2f) -> dxf(%.2f, %.2f) d=%.2f  vec=(%+.2f, %+.2f)  %s"
          % (x, y, best[0], best[1], d, best[0] - x, best[1] - y, nombre))

# 3. probar traslaciones candidatas y contar coincidencias
print()
print("Prueba de traslaciones (tol 0.20 m):")
candidatos = []
for px, py, _, _ in dxf_pts:
    for ax, ay, _ in alvo[:6]:
        candidatos.append((px - ax, py - ay))
# refinar por la moda aproximada
from collections import Counter
redondeados = Counter((round(dx, 1), round(dy, 1)) for dx, dy in candidatos)
for (dx0, dy0), frecuencia in redondeados.most_common(6):
    # buscar el mejor ajuste fino alrededor del redondeo
    mejor = (0, (dx0, dy0))
    for ex in range(-3, 4):
        for ey in range(-3, 4):
            dx = dx0 + ex * 0.05
            dy = dy0 + ey * 0.05
            hits = 0
            for ax, ay, _ in alvo:
                objetivo = (ax + dx, ay + dy)
                if min(math.hypot(p[0] - objetivo[0], p[1] - objetivo[1]) for p in dxf_pts) <= 0.20:
                    hits += 1
            if hits > mejor[0]:
                mejor = (hits, (round(dx, 3), round(dy, 3)))
    print("  offset~(%6.1f,%6.1f) freq=%-3d -> mejor %d/%d con offset (%.3f, %.3f)"
          % (dx0, dy0, frecuencia, mejor[0], len(alvo), mejor[1][0], mejor[1][1]))
