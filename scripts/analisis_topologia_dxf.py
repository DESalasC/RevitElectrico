# -*- coding: utf-8 -*-
"""
Analisis de topologia del DXF XPL: extrae grafo de conectividad aparato-aparato
a partir de las polilineas de conducto y los bloques de aparato.
Salida: data/f7_topologia_dxf_f17_f18_v01.json
"""
import ezdxf
import json
import math
from collections import Counter, defaultdict

DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos-XPL.dxf"
OUT = r"D:\Work\PROJECTS\RevitElectrico\data\f7_topologia_dxf_f17_f18_v01.json"

RANGOS = {
    "F17": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 1000.0, "y_max": 8500.0},
    "F18": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 9000.0, "y_max": 16500.0},
}

TOL_EXTREMO = 300.0   # mm: extremo de polilinea <-> aparato
TOL_SOBRE_LINEA = 200.0  # mm: aparato que cae sobre el trazado (derivacion)

doc = ezdxf.readfile(DXF)
msp = doc.modelspace()

# ---------------------------------------------------------------- inventario
layer_counts = Counter()
for e in msp:
    layer_counts[e.dxf.layer] += 1
print("=== LAYERS (top 40) ===")
for lay, n in layer_counts.most_common(40):
    print("  %-42s %5d" % (lay, n))

block_counts = Counter()
for e in msp.query("INSERT"):
    block_counts[e.dxf.name] += 1
print("")
print("=== BLOQUES (todos, ordenados) ===")
for name, n in sorted(block_counts.items(), key=lambda kv: (-kv[1], kv[0])):
    print("  %-34s %5d" % (name, n))


def en_rango(x, y, r):
    return r["x_min"] <= x <= r["x_max"] and r["y_min"] <= y <= r["y_max"]


def apto_de(x, y):
    for nombre, r in RANGOS.items():
        if en_rango(x, y, r):
            return nombre
    return None


# ---------------------------------------------------------------- aparatos
# Aparatos = familias electricas reales. Los bloques 1FNT/1FTNR/... son
# etiquetas de cantidad de cables SOBRE la linea, no aparatos.
ES_APARATO = lambda n: (n.startswith("ELEC-") or n in ("S3", "S3C") or
                        n.startswith("Bala Stil Led"))

aparatos = []
for e in msp.query("INSERT"):
    name = e.dxf.name or ""
    if not ES_APARATO(name):
        continue
    p = e.dxf.insert
    a = apto_de(p.x, p.y)
    if not a:
        continue
    aparatos.append({
        "idx": len(aparatos),
        "bloque": name,
        "x": round(p.x, 3),
        "y": round(p.y, 3),
        "apto": a,
        "rot": round(e.dxf.rotation, 2) if hasattr(e.dxf, "rotation") else 0.0,
    })

print("")
print("=== APARATOS ===")
por_apto_bloque = defaultdict(Counter)
for d in aparatos:
    por_apto_bloque[d["apto"]][d["bloque"]] += 1
for a in sorted(por_apto_bloque):
    print("  %s: %d aparatos" % (a, sum(por_apto_bloque[a].values())))
    for b, n in sorted(por_apto_bloque[a].items()):
        print("      %-24s %d" % (b, n))

# ---------------------------------------------------------------- conductos
capas_cond = [lay for lay in layer_counts
              if any(k in lay.upper() for k in
                     ("PIPE", "TUBO", "CONDUIT", "COMUNIC", "TEL", "VOZ", "DATOS", "NET"))]
print("")
print("=== CAPAS DE CONDUCTO DETECTADAS ===")
for c in capas_cond:
    print("  %-42s %5d entidades" % (c, layer_counts[c]))


def vertices_de(e):
    if e.dxftype() == "LWPOLYLINE":
        return [(v[0], v[1]) for v in e.get_points()]
    if e.dxftype() == "POLYLINE":
        return [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
    if e.dxftype() == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    return None


polilineas = []
for e in msp:
    if e.dxf.layer not in capas_cond:
        continue
    vs = vertices_de(e)
    if not vs or len(vs) < 2:
        continue
    cx = sum(v[0] for v in vs) / len(vs)
    cy = sum(v[1] for v in vs) / len(vs)
    a = apto_de(cx, cy) or apto_de(vs[0][0], vs[0][1])
    if not a:
        continue
    largo = 0.0
    for i in range(len(vs) - 1):
        largo += math.hypot(vs[i + 1][0] - vs[i][0], vs[i + 1][1] - vs[i][1])
    polilineas.append({
        "idx": len(polilineas),
        "apto": a,
        "layer": e.dxf.layer,
        "vertices": [(round(v[0], 3), round(v[1], 3)) for v in vs],
        "largo": round(largo, 2),
    })

print("")
print("=== POLILINEAS DE CONDUCTO ===")
for a in sorted(RANGOS):
    ps = [p for p in polilineas if p["apto"] == a]
    print("  %s: %d polilineas, largo total %.0f mm" % (a, len(ps), sum(p["largo"] for p in ps)))

# ------------------------------------------- aparatos que tocan cada polilinea
def proyectar(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-9:
        return 0.0, math.hypot(p[0] - ax, p[1] - ay)
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2
    t = max(0.0, min(1.0, t))
    px, py = ax + t * dx, ay + t * dy
    return t, math.hypot(p[0] - px, p[1] - py)


def analizar_polilinea(poly, aparatos_apto):
    """Devuelve lista ordenada de (s_arco, aparato, dist, tipo_hit)."""
    vs = poly["vertices"]
    # parametro de arco acumulado por vertice
    s_acum = [0.0]
    for i in range(len(vs) - 1):
        s_acum.append(s_acum[-1] + math.hypot(vs[i + 1][0] - vs[i][0],
                                              vs[i + 1][1] - vs[i][1]))
    hits = []
    for d in aparatos_apto:
        pt = (d["x"], d["y"])
        mejor = None
        # sobre segmentos
        for i in range(len(vs) - 1):
            t, dist = proyectar(pt, vs[i], vs[i + 1])
            s = s_acum[i] + t * (s_acum[i + 1] - s_acum[i])
            if mejor is None or dist < mejor[1]:
                mejor = (s, dist)
        if mejor is None:
            continue
        s, dist = mejor
        L = s_acum[-1]
        en_extremo = (s <= TOL_EXTREMO or (L - s) <= TOL_EXTREMO)
        if dist <= TOL_EXTREMO:
            hits.append({"s": s, "idx": d["idx"], "dist": dist,
                         "extremo": bool(en_extremo), "bloque": d["bloque"]})
        elif dist <= TOL_SOBRE_LINEA:
            hits.append({"s": s, "idx": d["idx"], "dist": dist,
                         "extremo": False, "bloque": d["bloque"]})
    hits.sort(key=lambda h: h["s"])
    # dedup por aparato
    vistos = set()
    out = []
    for h in hits:
        if h["idx"] in vistos:
            continue
        vistos.add(h["idx"])
        out.append(h)
    return out


aristas = []
detalle_polys = []
for poly in polilineas:
    ap = [d for d in aparatos if d["apto"] == poly["apto"]]
    hits = analizar_polilinea(poly, ap)
    detalle_polys.append({
        "idx": poly["idx"], "apto": poly["apto"], "layer": poly["layer"],
        "largo": poly["largo"], "n_hits": len(hits),
        "vertices": poly["vertices"],
        "hits": [{"idx": h["idx"], "bloque": h["bloque"],
                  "dist": round(h["dist"], 2), "s": round(h["s"], 1),
                  "extremo": h["extremo"]} for h in hits],
    })
    for i in range(len(hits) - 1):
        a, b = hits[i], hits[i + 1]
        if a["idx"] == b["idx"]:
            continue
        aristas.append({
            "apto": poly["apto"], "a": a["idx"], "b": b["idx"],
            "layer": poly["layer"], "poly": poly["idx"],
            "s_a": round(a["s"], 1), "s_b": round(b["s"], 1),
            "largo_tramo": round(b["s"] - a["s"], 1),
            "dist_a": round(a["dist"], 2), "dist_b": round(b["dist"], 2),
        })

print("")
print("=== COBERTURA: aparatos tocados por alguna polilinea ===")
for a in sorted(RANGOS):
    ap = [d for d in aparatos if d["apto"] == a]
    tocados = set()
    for e in aristas:
        if e["apto"] == a:
            tocados.add(e["a"])
            tocados.add(e["b"])
    # tambien los que aparecen como hit unico
    for p in detalle_polys:
        if p["apto"] == a:
            for h in p["hits"]:
                tocados.add(h["idx"])
    print("  %s: %d/%d aparatos tocados por el trazado (%.0f%%)" % (
        a, len(tocados), len(ap), 100.0 * len(tocados) / max(1, len(ap))))
    huerfanos = [d for d in ap if d["idx"] not in tocados]
    print("     huerfanos: %d" % len(huerfanos))
    for d in huerfanos[:12]:
        print("        %-24s (%.0f, %.0f)" % (d["bloque"], d["x"], d["y"]))

print("")
print("=== ARISTAS ===")
for a in sorted(RANGOS):
    es = [e for e in aristas if e["apto"] == a]
    nodos = set()
    for e in es:
        nodos.add(e["a"])
        nodos.add(e["b"])
    print("  %s: %d aristas, %d nodos" % (a, len(es), len(nodos)))

# componentes conexas por apto
def componentes(apto):
    es = [e for e in aristas if e["apto"] == apto]
    padre = {}
    def find(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            padre[rx] = ry
    for e in es:
        for n in (e["a"], e["b"]):
            if n not in padre:
                padre[n] = n
        union(e["a"], e["b"])
    grupos = defaultdict(list)
    for n in padre:
        grupos[find(n)].append(n)
    return sorted(grupos.values(), key=lambda g: -len(g))

print("")
print("=== COMPONENTES CONEXAS (grupos de aparatos unidos por el trazado) ===")
for a in sorted(RANGOS):
    comps = componentes(a)
    print("  %s: %d componentes" % (a, len(comps)))
    for i, g in enumerate(comps[:10]):
        nombres = Counter()
        for idx in g:
            nombres[aparatos[idx]["bloque"]] += 1
        print("     grupo %d: %d aparatos  %s" % (i + 1, len(g), dict(nombres)))

# ------------------------------------------------------------------- salida
salida = {
    "fuente": DXF,
    "tolerancias": {"extremo_mm": TOL_EXTREMO, "sobre_linea_mm": TOL_SOBRE_LINEA},
    "capas_conducto": capas_cond,
    "aparatos": aparatos,
    "polilineas": detalle_polys,
    "aristas": aristas,
    "stats": {
        "n_aparatos": len(aparatos),
        "n_polilineas": len(polilineas),
        "n_aristas": len(aristas),
        "n_huerfanos": sum(
            1 for a in RANGOS
            for d in [x for x in aparatos if x["apto"] == a]
            if not any(e["a"] == d["idx"] or e["b"] == d["idx"] for e in aristas)
            and not any(h["idx"] == d["idx"] for p in detalle_polys
                        if p["apto"] == a for h in p["hits"])),
    },
}
with open(OUT, "w") as f:
    json.dump(salida, f, indent=2)
print("")
print("Guardado: %s" % OUT)
print("Stats: %d aparatos, %d polilineas, %d aristas, %d huerfanos" % (
    salida["stats"]["n_aparatos"], salida["stats"]["n_polilineas"],
    salida["stats"]["n_aristas"], salida["stats"]["n_huerfanos"]))
