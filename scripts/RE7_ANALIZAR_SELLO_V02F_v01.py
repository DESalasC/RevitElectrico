# -*- coding: utf-8 -*-
"""
RE7_ANALIZAR_SELLO_V02F_v01.py

Analiza el sello de E-STM-...-CENTRA_V02-f.rvt (data/f7_v02f_sello_v01.json)
contra la red creada por el router v09 (data/f7_conduits_desde_revit_v01.json)
y el inventario de dispositivos activo (data/f7_inventario_revit_v03.json).

Responde cuatro preguntas:

  1. MARCO: los aparatos de V02-f caen sobre los aparatos del modelo activo
     (distancia al vecino mas cercano)?
  2. RED REAL: cuantos tramos/longitud/verticales tiene V02-f dentro del area
     de F01/F02, y a que alturas corre?
  3. COBERTURA: que porcentaje de la red real de V02-f cubre nuestra red
     (muestreo cada 100 mm, distancia al tramo propio mas cercano)?
  4. FIDELIDAD: el export derivado data/analisis_ruteo_F01_F02.json
     reproduce la red real de V02-f?

Uso: python scripts/RE7_ANALIZAR_SELLO_V02F_v01.py
Entorno: Python 3
"""
from __future__ import annotations

import datetime
import io
import json
import math
import os
import sys
from collections import Counter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELLO = os.path.join(RAIZ, "data", "f7_v02f_sello_v01.json")
NUESTRA = os.path.join(RAIZ, "data", "f7_conduits_desde_revit_v01.json")
INVENTARIO = os.path.join(RAIZ, "data", "f7_inventario_revit_v03.json")
DERIVADO = os.path.join(RAIZ, "data", "analisis_ruteo_F01_F02.json")
OUT = os.path.join(RAIZ, "data", "f7_analisis_sello_v02f_v01.json")

PASO_M = 0.10
INFLAR_AREA_MM = 1500.0
Z_MIN_MM = 12000.0
Z_MAX_MM = 17500.0


def cargar(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def largo_seg(a, b):
    return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))


def es_vertical(a, b, tol=2.0):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def es_horizontal(a, b, tol=2.0):
    return abs(a[2] - b[2]) <= tol


def centro(a, b):
    return tuple(0.5 * (a[i] + b[i]) for i in range(3))


def bbox(segs):
    xs, ys, zs = [], [], []
    for a, b in segs:
        for q in (a, b):
            xs.append(q[0])
            ys.append(q[1])
            zs.append(q[2])
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def dentro_de(seg, caja, margen=0.0):
    c = centro(seg[0], seg[1])
    return (caja[0] - margen <= c[0] <= caja[1] + margen
            and caja[2] - margen <= c[1] <= caja[3] + margen
            and caja[4] - margen <= c[2] <= caja[5] + margen)


def muestrear(a, b, paso_mm=PASO_M * 1000.0):
    L = largo_seg(a, b)
    n = max(1, int(L / paso_mm))
    return [tuple(a[i] + (b[i] - a[i]) * k / float(n) for i in range(3))
            for k in range(n + 1)]


def dist_punto_seg(p, a, b):
    vx, vy, vz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    wx, wy, wz = p[0] - a[0], p[1] - a[1], p[2] - a[2]
    l2 = vx * vx + vy * vy + vz * vz
    if l2 < 1e-12:
        return math.sqrt(wx * wx + wy * wy + wz * wz)
    t = (wx * vx + wy * vy + wz * vz) / l2
    t = max(0.0, min(1.0, t))
    return math.sqrt((p[0] - (a[0] + t * vx)) ** 2
                     + (p[1] - (a[1] + t * vy)) ** 2
                     + (p[2] - (a[2] + t * vz)) ** 2)


def cobertura(puntos, red, umbral_mm=300.0):
    """Distancia de cada punto a la red mas cercana. Red = [(a, b), ...]."""
    dists = []
    for p in puntos:
        mejor = None
        for a, b in red:
            d = dist_punto_seg(p, a, b)
            if mejor is None or d < mejor:
                mejor = d
                if mejor < 20.0:
                    break
        dists.append(mejor)
    dists.sort()
    n = len(dists) or 1
    return {
        "puntos": len(dists),
        "mediana_mm": round(dists[len(dists) // 2], 1),
        "p90_mm": round(dists[int(0.9 * (len(dists) - 1))], 1),
        "max_mm": round(dists[-1], 1),
        "pct_dentro_300": round(100.0 * sum(1 for d in dists if d <= umbral_mm) / n, 1),
        "pct_dentro_150": round(100.0 * sum(1 for d in dists if d <= 150.0) / n, 1),
    }


def vecino_mas_cercano(puntos, candidatos):
    ds = []
    for p in puntos:
        mejor = None
        for q in candidatos:
            d = math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                          + (p[2] - q[2]) ** 2)
            if mejor is None or d < mejor:
                mejor = d
        if mejor is not None:
            ds.append(mejor)
    ds.sort()
    if not ds:
        return None
    n = len(ds)
    return {
        "puntos": n,
        "mediana_mm": round(ds[n // 2], 1),
        "p90_mm": round(ds[int(0.9 * (n - 1))], 1),
        "max_mm": round(ds[-1], 1),
        "pct_dentro_150": round(100.0 * sum(1 for d in ds if d <= 150.0) / n, 1),
    }


def emparejar_extremos(segs_a, segs_b, tol_mm=50.0):
    """Cuantos tramos de A tienen uno en B con ambos extremos cerca."""
    usados = set()
    n = 0
    for i, (a, b) in enumerate(segs_a):
        for j, (c, d) in enumerate(segs_b):
            if j in usados:
                continue
            ok = ((largo_seg(a, c) <= tol_mm and largo_seg(b, d) <= tol_mm)
                  or (largo_seg(a, d) <= tol_mm and largo_seg(b, c) <= tol_mm))
            if ok:
                usados.add(j)
                n += 1
                break
    return n, len(segs_a) - n


def main():
    print("=" * 76)
    print("RE7_ANALIZAR_SELLO_V02F_v01")
    print("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    sello = cargar(SELLO)
    nuestra = cargar(NUESTRA)
    inv = cargar(INVENTARIO)

    # ---- nuestra red (mm) ----
    segs_nuestros = [(q["a_mm"], q["b_mm"]) for q in nuestra["conduits"]
                     if q.get("a_mm") and q.get("b_mm")]
    print("nuestra red: %d tramos | %.2f m" % (
        len(segs_nuestros),
        sum(largo_seg(a, b) for a, b in segs_nuestros) / 1000.0))
    caja = bbox(segs_nuestros)
    print("  bbox: X %.0f..%.0f | Y %.0f..%.0f | Z %.0f..%.0f mm" % caja)

    # ---- 1. MARCO: aparatos V02-f vs inventario activo ----
    apar_v02f = [(q["x"], q["y"], q["z"]) for q in sello["aparatos"]]
    apar_nuestros = [(q["x"], q["y"], q["z"]) for q in inv["dispositivos"]]
    alineacion = vecino_mas_cercano(apar_v02f, apar_nuestros)
    print("")
    print("1) MARCO — aparatos V02-f (%d) vs activo (%d): %s" % (
        len(apar_v02f), len(apar_nuestros), alineacion))

    # ---- 2. RED REAL de V02-f en el area de F01/F02 ----
    segs_v02f_todos = [(q["a_mm"], q["b_mm"]) for q in sello["conduits"]
                       if q.get("a_mm") and q.get("b_mm")]
    en_z = [s for s in segs_v02f_todos
            if Z_MIN_MM <= centro(*s)[2] <= Z_MAX_MM]
    en_area = [s for s in en_z if dentro_de(s, caja, INFLAR_AREA_MM)]
    fuera = len(segs_v02f_todos) - len(en_area)
    print("")
    print("2) RED REAL V02-f: %d conduits totales | %d fuera de area/zona "
          "(descartados)" % (len(segs_v02f_todos), fuera))
    lv = sum(largo_seg(a, b) for a, b in en_area)
    vert = [s for s in en_area if es_vertical(*s)]
    hor = [s for s in en_area if es_horizontal(*s)]
    pts_vert = set((round(s[0][0], 0), round(s[0][1], 0)) for s in vert)
    print("   en area F01/F02: %d tramos | %.2f m | verticales %d en %d puntos"
          % (len(en_area), lv / 1000.0, len(vert), len(pts_vert)))
    print("   horizontales: %d | %.2f m" % (
        len(hor), sum(largo_seg(a, b) for a, b in hor) / 1000.0))
    zh = Counter(round(0.5 * (a[2] + b[2]) / 100.0) * 100 for a, b in hor)
    print("   Z de horizontales (mm, top 8): %s" % dict(
        sorted(zh.items(), key=lambda kv: -kv[1])[:8]))
    diams = Counter(str(q.get("diam_mm")) for q in sello["conduits"]
                    if q.get("a_mm") and dentro_de((q["a_mm"], q["b_mm"]),
                                                   caja, INFLAR_AREA_MM)
                    and Z_MIN_MM <= centro(q["a_mm"], q["b_mm"])[2] <= Z_MAX_MM)
    print("   diametros en area: %s" % dict(diams))

    # ---- 3. COBERTURA de la red real por la nuestra ----
    puntos = []
    for a, b in en_area:
        puntos.extend(muestrear(a, b))
    cov = cobertura(puntos, segs_nuestros)
    print("")
    print("3) COBERTURA de V02-f real por nuestra red: %s" % cov)

    # cobertura de referencia: la derivada
    segs_deriv = None
    if os.path.exists(DERIVADO):
        der = cargar(DERIVADO)
        segs_deriv = [((q["x_start_m"] * 1000.0, q["y_start_m"] * 1000.0,
                        q["z_start_m"] * 1000.0),
                       (q["x_end_m"] * 1000.0, q["y_end_m"] * 1000.0,
                        q["z_end_m"] * 1000.0))
                      for q in der["conduits"]]
        cov_der = cobertura(puntos, segs_deriv)
        print("   cobertura por el export derivado (control): %s" % cov_der)

    # ---- 4. FIDELIDAD del export derivado ----
    print("")
    if segs_deriv:
        en_z_der = [s for s in segs_deriv
                    if Z_MIN_MM <= centro(*s)[2] <= Z_MAX_MM]
        en_area_der = [s for s in en_z_der
                       if dentro_de(s, caja, INFLAR_AREA_MM)]
        n_iguales, n_sin = emparejar_extremos(en_area_der, en_area, 50.0)
        print("4) FIDELIDAD: derivado en area %d tramos vs real %d | "
              "emparejados a 50 mm: %d | del derivado sin par: %d" % (
                  len(en_area_der), len(en_area), n_iguales, n_sin))
    else:
        print("4) FIDELIDAD: no existe el export derivado")

    rep = {
        "version": "v01",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "marco_aparatos": alineacion,
        "red_real": {
            "conduits_totales": len(segs_v02f_todos),
            "descartados_fuera": fuera,
            "tramos_en_area": len(en_area),
            "longitud_m": round(lv / 1000.0, 2),
            "verticales": len(vert),
            "puntos_verticales": len(pts_vert),
            "horizontales": len(hor),
            "z_horizontales": dict(zh),
            "diametros": dict(diams),
        },
        "cobertura_real_por_nuestra": cov,
        "nuestra_red": {
            "tramos": len(segs_nuestros),
            "longitud_m": round(
                sum(largo_seg(a, b) for a, b in segs_nuestros) / 1000.0, 2),
        },
    }
    if segs_deriv:
        rep["cobertura_real_por_derivado"] = cov_der
        rep["fidelidad_derivado"] = {
            "tramos_derivado_en_area": len(en_area_der),
            "emparejados_50mm": n_iguales,
            "sin_par": n_sin,
        }
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(rep, ensure_ascii=True, indent=1))
    print("")
    print("JSON: %s" % OUT)
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
