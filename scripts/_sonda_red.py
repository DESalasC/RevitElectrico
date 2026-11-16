# -*- coding: utf-8 -*-
"""Sondeo 3: conectividad de la red, dispositivos en extremos, alturas y servicio."""
import json
import math
from collections import Counter, defaultdict

import ezdxf

DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T4-P4_todos_bloques_electricos.dxf"
MARCADORES = {"1FTNR": 4, "1FTN": 3, "1FTR": 3, "2F2N1T1R": 6, "1TNR": 3, "2FT2N": 5}
CAPAS_PIPE = ["ELEC-LIGHT-PIPE", "ELEC-POWER- PIPE", "ELEC-Powr-service", "ELEC-Data-Service"]

doc = ezdxf.readfile(DXF)
msp = doc.modelspace()

# --- polilineas
plines = []
for e in msp.query("LWPOLYLINE"):
    if e.dxf.layer not in CAPAS_PIPE:
        continue
    pts = [(p[0], p[1]) for p in e.get_points()]
    if len(pts) < 2:
        continue
    plines.append({"idx": len(plines), "capa": e.dxf.layer, "pts": pts})

# --- dispositivos electricos (INSERT) con atributos
DISPOSITIVOS_CAPAS = ("ELEC-APPL-TOMAS", "ELEC-APPL-ILUM", "ELEC-BALA LED 13 W",
                      "E-Lite-Swch", "Elec-Lite-Lite-Emer", "ELEC-STA_ Hermetica 40W",
                      "SS-Sensor", "ELEC-Powr-Appl", "ELEC-APPL-NETWORD")
dispositivos = []
for e in msp.query("INSERT"):
    if e.dxf.name in MARCADORES:
        continue
    capa = e.dxf.layer
    if not capa.startswith(("ELEC-", "Elec-", "E-Lite")):
        continue
    attrs = {}
    try:
        if e.has_attrib:
            for a in e.attribs:
                attrs[a.dxf.tag] = a.dxf.text.strip()
    except Exception:
        pass
    dispositivos.append({
        "nombre": e.dxf.name, "capa": capa,
        "p": (e.dxf.insert.x, e.dxf.insert.y),
        "attrs": attrs,
    })

print("Dispositivos electricos (INSERT no marcador): %d" % len(dispositivos))

# --- 1. extremos de polilinea vs dispositivos
print()
print("=" * 100)
print("EXTREMOS DE POLILINEA -> DISPOSITIVO MAS CERCANO")
print("=" * 100)
resumen = Counter()
detalle_lejano = []
for pl in plines:
    for extremo in (pl["pts"][0], pl["pts"][-1]):
        mejor = min(dispositivos, key=lambda d: math.hypot(d["p"][0] - extremo[0], d["p"][1] - extremo[1]))
        d = math.hypot(mejor["p"][0] - extremo[0], mejor["p"][1] - extremo[1])
        if d <= 0.15:
            resumen["<=0.15"] += 1
        elif d <= 0.50:
            resumen["0.15-0.50"] += 1
            detalle_lejano.append((pl["idx"], extremo, d, mejor["nombre"], mejor["capa"]))
        elif d <= 1.50:
            resumen["0.50-1.50"] += 1
            detalle_lejano.append((pl["idx"], extremo, d, mejor["nombre"], mejor["capa"]))
        else:
            resumen[">1.50"] += 1
            detalle_lejano.append((pl["idx"], extremo, d, mejor["nombre"], mejor["capa"]))
print("  extremos dentro de 0.15 m de un dispositivo: %d" % resumen["<=0.15"])
print("  0.15-0.50 m: %d | 0.50-1.50 m: %d | >1.50 m: %d"
      % (resumen["0.15-0.50"], resumen["0.50-1.50"], resumen[">1.50"]))

print()
print("  Detalle de extremos con dispositivo a mas de 0.50 m (primeros 15):")
n = 0
for idx, ext, d, nombre, capa in detalle_lejano:
    if d > 0.50 and n < 15:
        print("    poly#%-3d extremo=(%.2f, %.2f)  d=%.2f m  disp=%s (%s)" % (idx, ext[0], ext[1], d, nombre, capa))
        n += 1

# --- 2. conectividad entre polilineas (extremos compartidos)
print()
print("=" * 100)
print("CONECTIVIDAD DE LA RED (extremos que coinciden)")
print("=" * 100)
TOL = 0.05
nodos = defaultdict(list)
for pl in plines:
    for i, extremo in enumerate((pl["pts"][0], pl["pts"][-1])):
        clave = (round(extremo[0] / TOL), round(extremo[1] / TOL))
        nodos[clave].append((pl["idx"], i))
grados = Counter(len(v) for v in nodos.values())
print("  nodos unicos (tol %.2f m): %d" % (TOL, len(nodos)))
print("  grado de nodo: %s" % dict(sorted(grados.items())))
sueltos = [v for v in nodos.values() if len(v) == 1]
print("  extremos sueltos (grado 1): %d de %d extremos" % (len(sueltos), 2 * len(plines)))

# --- 3. atributos de dispositivos: RED / ALTURA_INST / CIRCUITO
print()
print("=" * 100)
print("ATRIBUTOS DE DISPOSITIVOS (muestra por capa)")
print("=" * 100)
por_capa = defaultdict(list)
for d in dispositivos:
    por_capa[d["capa"]].append(d)
for capa in sorted(por_capa):
    ds = por_capa[capa]
    print("\n  CAPA: %s  (%d)" % (capa, len(ds)))
    for d in ds[:3]:
        print("     %-24s RED=%-14s CIRCUITO=%-10s ALTURA_INST=%-18s ACOMETIDA=%s"
              % (d["nombre"], d["attrs"].get("RED", "")[:14], d["attrs"].get("CIRCUITO", "")[:10],
                 d["attrs"].get("ALTURA_INST", "")[:18], d["attrs"].get("ACOMETIDA", "")[:12]))

# --- 4. alturas: valores distintos de ALTURA_INST
print()
print("=" * 100)
print("VALORES DISTINTOS DE ALTURA_INST")
print("=" * 100)
alturas = Counter(d["attrs"].get("ALTURA_INST", "") for d in dispositivos)
for a, n in alturas.most_common(25):
    print("  %-40s %d" % (a, n))

# --- 5. capas pipe: rangos de coordenadas para validar offset
print()
print("=" * 100)
print("RANGO DE COORDENADAS")
print("=" * 100)
xs = [p[0] for pl in plines for p in pl["pts"]]
ys = [p[1] for pl in plines for p in pl["pts"]]
print("  polilineas: X %.2f..%.2f   Y %.2f..%.2f" % (min(xs), max(xs), min(ys), max(ys)))
xdd = [d["p"][0] for d in dispositivos]
ydd = [d["p"][1] for d in dispositivos]
print("  dispositivos: X %.2f..%.2f   Y %.2f..%.2f" % (min(xdd), max(xdd), min(ydd), max(ydd)))
