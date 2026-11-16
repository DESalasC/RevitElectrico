# -*- coding: utf-8 -*-
"""Sondeo fino: asociacion marcador -> polilinea y delimitacion del apartamento F 02."""
import json
import math
from collections import Counter, defaultdict

import ezdxf
from ezdxf.math import Vec2

DXF = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T4-P4_todos_bloques_electricos.dxf"

MARCADORES = {
    "1FTNR": 4, "1FTN": 3, "1FTR": 3, "2F2N1T1R": 6, "1TNR": 3, "2FT2N": 5,
}
CAPAS_PIPE = ["ELEC-LIGHT-PIPE", "ELEC-POWER- PIPE", "ELEC-Powr-service", "ELEC-Data-Service"]

doc = ezdxf.readfile(DXF)
msp = doc.modelspace()


def dist_punto_segmento(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# --- 1. Polilineas pipe ---
polilineas = []
for e in msp.query("LWPOLYLINE"):
    capa = e.dxf.layer
    if capa not in CAPAS_PIPE:
        continue
    pts = [(p[0], p[1]) for p in e.get_points()]
    if len(pts) < 2:
        continue
    L = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(len(pts) - 1))
    polilineas.append({
        "idx": len(polilineas),
        "handle": e.dxf.handle,
        "capa": capa,
        "pts": pts,
        "largo": L,
    })

print("Polilineas pipe: %d" % len(polilineas))

# --- 2. Marcadores ---
marcadores = []
for e in msp.query("INSERT"):
    nombre = e.dxf.name
    if nombre not in MARCADORES:
        continue
    p = (e.dxf.insert.x, e.dxf.insert.y)
    marcadores.append({
        "nombre": nombre,
        "cables": MARCADORES[nombre],
        "capa": e.dxf.layer,
        "p": p,
        "handle": e.dxf.handle,
    })
print("Marcadores de conductores: %d" % len(marcadores))

# --- 3. Asociar cada marcador a la polilinea mas cercana ---
print()
print("=" * 100)
print("ASOCIACION MARCADOR -> POLILINEA MAS CERCANA")
print("=" * 100)
asociados = []
for m in marcadores:
    mejor = None
    mejor_d = 1e9
    for pl in polilineas:
        if pl["capa"] == "ELEC-LIGHT-PIPE" and m["capa"] not in ("Elec-Lite-Wire",):
            pass
        d = min(dist_punto_segmento(m["p"], pl["pts"][i], pl["pts"][i + 1])
                for i in range(len(pl["pts"]) - 1))
        if d < mejor_d:
            mejor_d = d
            mejor = pl
    m["poly_idx"] = mejor["idx"] if mejor else None
    m["poly_capa"] = mejor["capa"] if mejor else None
    m["dist"] = mejor_d
    asociados.append(m)

distancias = sorted(m["dist"] for m in asociados)
print("distancia marcador->polilinea (m): min=%.3f  p50=%.3f  p90=%.3f  max=%.3f"
      % (distancias[0], distancias[len(distancias) // 2],
         distancias[int(len(distancias) * 0.9)], distancias[-1]))
print()
print("Fuera de 0.30 m (posible ambiguedad):")
for m in asociados:
    if m["dist"] > 0.30:
        print("   %-10s capa=%-26s d=%.3f m  -> poly#%s (%s)"
              % (m["nombre"], m["capa"], m["dist"], m["poly_idx"], m["poly_capa"]))

# --- 4. Polilineas con marcador y sin marcador ---
por_poly = defaultdict(list)
for m in asociados:
    por_poly[m["poly_idx"]].append(m)

print()
print("=" * 100)
print("COBERTURA: polilineas con/sin marcador asociado (<= 0.30 m)")
print("=" * 100)
con = [pl for pl in polilineas if any(m["dist"] <= 0.30 for m in por_poly.get(pl["idx"], []))]
sin = [pl for pl in polilineas if not any(m["dist"] <= 0.30 for m in por_poly.get(pl["idx"], []))]
print("Con marcador: %d (%.1f m)" % (len(con), sum(p["largo"] for p in con)))
print("Sin marcador: %d (%.1f m)" % (len(sin), sum(p["largo"] for p in sin)))

# --- 5. Distribucion de cables por polilinea ---
print()
print("Cables asignados por polilinea (si hay varios marcadores, lista):")
for pl in polilineas:
    ms = [m for m in por_poly.get(pl["idx"], []) if m["dist"] <= 0.30]
    if ms:
        print("   poly#%-3d %-20s L=%6.2f m  cables=%s  d=%s"
              % (pl["idx"], pl["capa"], pl["largo"],
                 [m["cables"] for m in ms], ["%.2f" % m["dist"] for m in ms]))

# --- 6. Delimitar apartamento F 02 ---
print()
print("=" * 100)
print("DELIMITACION APARTAMENTO F 02")
print("=" * 100)
for e in msp.query("INSERT"):
    if "F 02" in e.dxf.name or "F-02" in e.dxf.name:
        print("  bloque='%s' capa='%s' insert=(%.3f, %.3f)"
              % (e.dxf.name, e.dxf.layer, e.dxf.insert.x, e.dxf.insert.y))

# --- 7. Dispositivos: atributos de servicio ---
print()
print("=" * 100)
print("DISPOSITIVOS: capas electricas y atributos RED / ALTURA_INST (muestra)")
print("=" * 100)
capas_disp = Counter()
for e in msp.query("INSERT"):
    if e.dxf.layer.startswith(("ELEC-", "Elec-", "E-Lite")):
        capas_disp[e.dxf.layer] += 1
for c, n in capas_disp.most_common():
    print("  %-32s %d" % (c, n))

salida = {
    "polilineas": [{"idx": p["idx"], "handle": p["handle"], "capa": p["capa"],
                    "largo": round(p["largo"], 3), "pts": p["pts"]} for p in polilineas],
    "marcadores": [{"nombre": m["nombre"], "cables": m["cables"], "capa": m["capa"],
                    "p": m["p"], "poly_idx": m["poly_idx"], "dist": round(m["dist"], 4)}
                   for m in asociados],
}
with open(r"D:\Work\PROJECTS\RevitElectrico\data\_sonda_asociacion.json", "w", encoding="utf-8") as f:
    json.dump(salida, f, indent=1, ensure_ascii=False)
print("\nJSON -> data\\_sonda_asociacion.json")
