# -*- coding: utf-8 -*-
"""Sondeo del DXF para disenar el pipeline de ruteo de conduit.

Responde:
  - Que capas existen y cuantas entidades tiene cada una (por tipo).
  - Que capas parecen tuberia/cableado.
  - Como se agrupan las polilineas (cantidad, vertices, longitud).
  - Donde caen los marcadores de conductores respecto a las polilineas.
"""
import json
import math
from collections import Counter, defaultdict

import ezdxf

DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T4-P4_todos_bloques_electricos.dxf"

doc = ezdxf.readfile(DXF)
msp = doc.modelspace()

tipos_por_capa = defaultdict(Counter)
for e in msp:
    tipos_por_capa[e.dxf.layer][e.dxftype()] += 1

print("=" * 100)
print("CAPAS (entidades por tipo)")
print("=" * 100)
for capa in sorted(tipos_por_capa, key=lambda c: -sum(tipos_por_capa[c].values())):
    cnt = tipos_por_capa[capa]
    total = sum(cnt.values())
    detalle = ", ".join("%s=%d" % (t, n) for t, n in cnt.most_common(6))
    print("%-42s %6d  %s" % (capa, total, detalle))

print()
print("=" * 100)
print("CAPAS CANDIDATAS A TUBERIA / CABLEADO")
print("=" * 100)
claves = ("pipe", "wire", "conduit", "tub", "canal", "bandeja", "tray", "acomet", "netword", "network")
for capa in sorted(tipos_por_capa):
    if any(k in capa.lower() for k in claves):
        print("  %-42s %s" % (capa, dict(tipos_por_capa[capa])))

print()
print("=" * 100)
print("POLILINEAS EN CAPAS DE TUBERIA")
print("=" * 100)
for capa in sorted(tipos_por_capa):
    if not any(k in capa.lower() for k in claves):
        continue
    plines = [e for e in msp.query('LWPOLYLINE') if e.dxf.layer == capa]
    if not plines:
        continue
    largos = []
    nverts = Counter()
    for pl in plines:
        pts = [(p[0], p[1]) for p in pl.get_points()]
        nverts[len(pts)] += 1
        L = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                for i in range(len(pts) - 1))
        largos.append(L)
    print("\nCAPA: %s  (%d polilineas)" % (capa, len(plines)))
    print("   vertices: %s" % dict(nverts))
    if largos:
        print("   longitud m: min=%.3f  max=%.3f  media=%.3f  total=%.1f"
              % (min(largos), max(largos), sum(largos) / len(largos), sum(largos)))

print()
print("=" * 100)
print("BLOQUES INSERT: marcadores de conductores y su capa")
print("=" * 100)
marcadores = ("1FTNR", "1FTN", "1FTR", "2F2N1T1R", "1TNR", "2FT2N")
ins = Counter()
for e in msp.query("INSERT"):
    if e.dxf.name in marcadores:
        ins[(e.dxf.name, e.dxf.layer)] += 1
for (nombre, capa), n in sorted(ins.items()):
    print("  %-10s capa=%-28s n=%d" % (nombre, capa, n))

# Volcar un resumen util para el diseno
salida = {
    "dxf": DXF,
    "capas": {c: dict(t) for c, t in tipos_por_capa.items()},
}
with open(r"D:\Work\PROJECTS\RevitElectrico\data\_sonda_dxf_ruteo.json", "w", encoding="utf-8") as f:
    json.dump(salida, f, indent=1, ensure_ascii=False)
print("\nResumen JSON -> data\\_sonda_dxf_ruteo.json")
