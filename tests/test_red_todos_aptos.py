# -*- coding: utf-8 -*-
"""
Prueba de topologia de la red de plenum para TODOS los apartamentos,
usando las posiciones reales de los dispositivos del DXF (que sirven de
sustitutas de los risers, porque cada riser nace en el dispositivo).

Comprueba, por apartamento:
  * cuantos grupos Y y tramos genera la red
  * que TODOS los risers queden cubiertos por un tramo (<=6 mm)
  * que el CP quede sobre la red

Uso: python tests/test_red_todos_aptos.py
"""
import importlib.util
import io
import json
import math
import os
import re
import sys
from collections import defaultdict

BASE = r"D:\Work\PROJECTS\RevitElectrico"
SRC = os.path.join(BASE, "scripts", "pyrevit", "RE7_CREAR_HORIZONTALES_TODOS_APTOS_v02.py")
DXF = os.path.join(BASE, "data", "dxf_dispositivos_absolutos_v02.json")
INV = os.path.join(BASE, "data", "f7_inventario_revit_v03.json")
Z = 15930.0

src = io.open(SRC, encoding="utf-8").read()


def extraer(nombre):
    m = re.search(r"^def %s\(.*?(?=^def |\Z)" % nombre, src, re.S | re.M)
    return m.group(0)


ns = {"Z_PLENUM_MM": Z, "LARGO_MIN_MM": 5.0, "TOL_GRUPO_Y_MM": 5.0, "math": math}
code = "\n".join(extraer(f) for f in ("agrupar_por_y", "construir_red", "dist_punto_segmento_2d"))
exec(compile(code, "<red>", "exec"), ns)
construir_red = ns["construir_red"]
dps = ns["dist_punto_segmento_2d"]

PAT = re.compile(r"Tipo\s+([A-Z])\s+(\d+)\s*([a-zA-Z]?)", re.I)


def cod(n):
    m = PAT.search(n or "")
    return (m.group(1) + m.group(2).zfill(2) + (m.group(3) or "")).upper() if m else None


d = json.load(io.open(DXF, encoding="utf-8"))
ins = {a["name"]: a["insert_mm"] for a in d["apartamentos"]}
pts = defaultdict(list)
for q in d["dispositivos"]:
    ix, iy = ins[q["apto_dxf"]]
    pts[cod(q["apto_dxf"])].append((ix + (q["x_mm"] - ix) * 1000.0,
                                    iy + (q["y_mm"] - iy) * 1000.0,
                                    q.get("familia_revit") or ""))

# CP: dispositivo con familia CPB; si no, mediana
inv = json.load(io.open(INV, encoding="utf-8"))["dispositivos"]
cp_real = {}
for q in inv:
    mk = q.get("mark") or ""
    if "|" not in mk:
        continue
    a = mk.split("|")[0].upper()
    if "CPB" in (q.get("familia") or "").upper():
        cur = cp_real.get(a)
        if cur is None or q["z"] > cur[2]:
            cp_real[a] = (q["x"], q["y"], q["z"])

total_tramos = 0
fallos = 0
print("%-6s %4s %5s %6s %-22s %s" % ("APTO", "ris", "grup", "tramos", "CP", "cobertura"))
for apto in sorted(pts.keys()):
    risers = [(x, y) for (x, y, f) in pts[apto]]
    # dedup por Y como hace el script real (risers en la misma XY no se repiten)
    uniq = sorted(set(risers))
    if apto in cp_real:
        cx, cy = cp_real[apto][0], cp_real[apto][1]
        origen = "CPB"
    else:
        xs = sorted(p[0] for p in uniq)
        ys = sorted(p[1] for p in uniq)
        cx, cy = xs[len(xs) // 2], ys[len(ys) // 2]
        origen = "mediana"

    tramos, grupos = construir_red(uniq, cx, cy)
    total_tramos += len(tramos)

    huerf = 0
    for (rx, ry) in uniq:
        ok = False
        for (a, b, tipo, n) in tramos:
            if tipo == "X" and abs(a[1] - ry) <= 6.0:
                xa, xb = sorted([a[0], b[0]])
                if xa - 1 <= rx <= xb + 1:
                    ok = True
                    break
            if tipo == "Y" and abs(a[0] - rx) <= 6.0:
                ya, yb = sorted([a[1], b[1]])
                if ya - 1 <= ry <= yb + 1:
                    ok = True
                    break
        if not ok:
            huerf += 1

    cp_ok = any(dps(cx, cy, a[0], a[1], b[0], b[1]) <= 20.0 for (a, b, t, n) in tramos)
    estado = "OK" if (huerf == 0 and cp_ok) else "FALLA(h=%d,cp=%s)" % (huerf, cp_ok)
    if estado != "OK":
        fallos += 1
    print("%-6s %4d %5d %6d %-22s %s" % (
        apto, len(uniq), len(grupos), len(tramos), "%s(%.0f,%.0f)" % (origen, cx, cy), estado))

print("")
print("TOTAL tramos previstos: %d | apartamentos con fallo: %d" % (total_tramos, fallos))
sys.exit(0 if fallos == 0 else 1)
