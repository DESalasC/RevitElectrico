# -*- coding: utf-8 -*-
"""
RE7_COMPARAR_RUTEO_F01_F02_v01.py

Compara el ruteo programado (data/f7_ruteo_creado_F01_F02_v02.json) contra la
referencia manual validada de CENTRA_V02-f (data/analisis_ruteo_F01_F02.json,
147 conduits + 88 accesorios).

Metricas:
  * conteo por tipo y orientacion, longitud total
  * distancia de cada tramo de la referencia al tramo programado mas cercano
    (muestreo cada 100 mm; mediana, p90, max, % dentro de 300 mm)
  * cobertura de aparatos: verticales de la referencia vs verticales nuestras
  * alturas de cocina: rango Z de las verticales de cada red

Entorno: Python 3
"""
import io
import json
import math
import os
import sys
BASE = r"D:\Work\PROJECTS\RevitElectrico"
REF = os.path.join(BASE, "data", "analisis_ruteo_F01_F02.json")
CMP = os.path.join(BASE, "data", "f7_ruteo_creado_F01_F02_v03.json")
if len(sys.argv) > 1:
    CMP = sys.argv[1]
OUT = os.path.join(BASE, "data", "f7_comparacion_ruteo_f01_f02_v01.json")

PASO_M = 0.10


def cargar(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def seg_de_ref(q):
    return ((q["x_start_m"], q["y_start_m"], q["z_start_m"]),
            (q["x_end_m"], q["y_end_m"], q["z_end_m"]))


def seg_de_cmp(q):
    a, b = q["a"], q["b"]
    return ((a[0] / 1000.0, a[1] / 1000.0, a[2] / 1000.0),
            (b[0] / 1000.0, b[1] / 1000.0, b[2] / 1000.0))


def puntos_segmento(a, b, paso):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    dz = b[2] - a[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    n = max(1, int(L / paso))
    out = []
    for i in range(n + 1):
        t = float(i) / n
        out.append((a[0] + dx * t, a[1] + dy * t, a[2] + dz * t))
    return out


def dist_punto_seg(p, a, b):
    vx = b[0] - a[0]
    vy = b[1] - a[1]
    vz = b[2] - a[2]
    wx = p[0] - a[0]
    wy = p[1] - a[1]
    wz = p[2] - a[2]
    l2 = vx * vx + vy * vy + vz * vz
    if l2 < 1e-12:
        return math.sqrt(wx * wx + wy * wy + wz * wz)
    t = (wx * vx + wy * vy + wz * vz) / l2
    t = max(0.0, min(1.0, t))
    return math.sqrt((p[0] - (a[0] + t * vx)) ** 2 +
                     (p[1] - (a[1] + t * vy)) ** 2 +
                     (p[2] - (a[2] + t * vz)) ** 2)


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    i = int(round((len(s) - 1) * p))
    return s[i]


def main():
    if not os.path.exists(CMP):
        print("FALTA %s" % CMP)
        print("Ejecuta primero RE7_RUTEAR_APTOS_v02.py en pyRevit (APTOS=F01,F02).")
        return 1
    ref = cargar(REF)
    cmp_ = cargar(CMP)

    rs_all = [seg_de_ref(q) for q in ref["conduits"]]
    cs = [seg_de_cmp(q) for q in cmp_["tramos"]]

    # filtro de outliers de la referencia: dentro del piso y del area F01/F02
    def dentro(s):
        a, b = s
        cx = 0.5 * (a[0] + b[0])
        cy = 0.5 * (a[1] + b[1])
        cz = 0.5 * (a[2] + b[2])
        if not (10.0 <= cx <= 15.5):
            return False
        if not ((4.0 <= cy <= 9.0) or (11.0 <= cy <= 17.5)):
            return False
        return 12.8 <= cz <= 16.6

    rs = [s for s in rs_all if dentro(s)]
    fuera = len(rs_all) - len(rs)
    if fuera:
        print("Referencia: %d tramos fuera del area/piso (descartados)" % fuera)

    print("=" * 76)
    print("REFERENCIA V02-f: %d conduits | %d accesorios" % (
        len(rs), ref.get("total_accesorios") or 0))
    print("PROGRAMADO      : %d tramos" % len(cs))
    print("=" * 76)

    # longitudes
    def largo(s):
        a, b = s
        return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))

    lr = sum(largo(s) for s in rs)
    lc = sum(largo(s) for s in cs)
    print("Longitud total: referencia %.2f m | programado %.2f m" % (lr, lc))

    # orientacion
    def orient(s):
        a, b = s
        if abs(a[0] - b[0]) < 0.002 and abs(a[1] - b[1]) < 0.002:
            return "vertical"
        if abs(a[2] - b[2]) < 0.002:
            return "horizontal"
        return "otro"

    from collections import Counter
    print("Orientacion ref : %s" % dict(Counter(orient(s) for s in rs)))
    print("Orientacion prog: %s" % dict(Counter(orient(s) for s in cs)))

    # cobertura: cada punto de la referencia a la red programada
    print("")
    print("-" * 76)
    print("DISTANCIA DE LA REFERENCIA A LA RED PROGRAMADA")
    dists = []
    sin = 0
    for s in rs:
        a, b = s
        for p in puntos_segmento(a, b, PASO_M):
            best = None
            for t in cs:
                dd = dist_punto_seg(p, t[0], t[1])
                if best is None or dd < best:
                    best = dd
                    if best < 0.02:
                        break
            dists.append(best)
            if best > 0.30:
                sin += 1
    print("  puntos muestreados: %d" % len(dists))
    print("  mediana=%.3f m | p90=%.3f m | p99=%.3f m | max=%.3f m" % (
        pct(dists, 0.50), pct(dists, 0.90), pct(dists, 0.99), max(dists)))
    print("  puntos a mas de 0.30 m: %d (%.1f%%)" % (
        sin, 100.0 * sin / max(1, len(dists))))
    dentro = sum(1 for d in dists if d <= 0.30)
    print("  cobertura <=0.30 m: %.1f%%" % (100.0 * dentro / max(1, len(dists))))

    # verticales: comparar alturas
    print("")
    print("-" * 76)
    print("VERTICALES")
    rv = [s for s in rs if orient(s) == "vertical"]
    cv = [s for s in cs if orient(s) == "vertical"]
    print("  referencia: %d | programado: %d" % (len(rv), len(cv)))
    if rv:
        zr = [min(s[0][2], s[1][2]) for s in rv]
        zr2 = [max(s[0][2], s[1][2]) for s in rv]
        print("  ref  Z: min=%.2f max=%.2f m" % (min(zr), max(zr2)))
    if cv:
        zc = [min(s[0][2], s[1][2]) for s in cv]
        zc2 = [max(s[0][2], s[1][2]) for s in cv]
        print("  prog Z: min=%.2f max=%.2f m" % (min(zc), max(zc2)))

    # tramos por tipo en lo programado
    print("")
    print("-" * 76)
    print("TRAMOS PROGRAMADOS POR TIPO")
    for k, v in Counter(q["tipo"] for q in cmp_["tramos"]).most_common():
        print("  %-18s %d" % (k, v))

    rep = {
        "version": "v01",
        "referencia": {"archivo": REF, "conduits": len(rs_all),
                       "conduits_en_area": len(rs),
                       "accesorios": ref.get("total_accesorios"),
                       "longitud_m": round(lr, 3)},
        "programado": {"archivo": CMP, "tramos": len(cs),
                       "longitud_m": round(lc, 3),
                       "por_tipo": dict(Counter(q["tipo"] for q in cmp_["tramos"]))},
        "distancia": {
            "puntos": len(dists),
            "mediana_m": round(pct(dists, 0.50), 4),
            "p90_m": round(pct(dists, 0.90), 4),
            "p99_m": round(pct(dists, 0.99), 4),
            "max_m": round(max(dists), 4),
            "pct_dentro_030": round(100.0 * dentro / max(1, len(dists)), 2),
        },
        "verticales": {"referencia": len(rv), "programado": len(cv)},
    }
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(rep, ensure_ascii=True, indent=1))
    print("")
    print("JSON: %s" % OUT)
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
