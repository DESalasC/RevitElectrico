# -*- coding: utf-8 -*-
"""
RE7_PROPONER_MARKS_TODOS_v02.py

Entorno: Python 3 (fuera de Revit).

Propone el Mark (apartamento|tablero|circuito) de TODOS los dispositivos
electricos, sin usar zonas geograficas.

FUENTE DE VERDAD (validada):
  data/dxf_dispositivos_absolutos_v02.json
    version 1.0_COORDS_ABSOLUTAS_MM_PANEL_INTERNO, 899 dispositivos, 20 aptos.
    Sus x_mm/y_mm estan en METROS LOCALES dentro del bloque de apartamento y
    el bloque se inserta con escala 1000. Transformacion verificada contra los
    901 INSERT del DXF: distancia 0.0 mm en los 899 dispositivos.

    global_x_mm = insert_x_mm + (x_mm - insert_x_mm) * 1000
    global_y_mm = insert_y_mm + (y_mm - insert_y_mm) * 1000

  data/f7_dxf_bloques_completo_v01.json
    Bloque DXF con circuito asignado (texto XX-NN mas cercano, <=1000 mm).

  data/f7_inventario_revit_v03.json
    Dispositivos reales del modelo (id + XYZ mm + Mark/Comment actuales).

Reglas:
  * Apartamento: el del dispositivo DXF mas cercano (dato de origen).
  * Circuito: el del bloque DXF emparejado; Datos/Comunicaciones -> "Datos".
  * Tablero: letra del apartamento (B->TB, C->TC, D->TD, E->TE, F->TF).
  * Sin circuito conocido -> "SIN CIRCUITO" (se reporta, no se inventa).
  * Solo se proponen cambios para dispositivos SIN Mark completo; los que ya
    tienen apto|tablero|circuito no se tocan.

Salidas:
  data/f7_marks_propuestos_todos_v02.json
  data/f7_marks_propuestos_todos_v02_resumen.txt
"""
import datetime
import io
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

BASE = r"D:\Work\PROJECTS\RevitElectrico"
DXF_DISPOSITIVOS = os.path.join(BASE, "data", "dxf_dispositivos_absolutos_v02.json")
DXF_BLOQUES = os.path.join(BASE, "data", "f7_dxf_bloques_completo_v01.json")
INVENTARIO = os.path.join(BASE, "data", "f7_inventario_revit_v03.json")
OUT_JSON = os.path.join(BASE, "data", "f7_marks_propuestos_todos_v02.json")
OUT_TXT = os.path.join(BASE, "data", "f7_marks_propuestos_todos_v02_resumen.txt")

RADIO_MATCH_MM = 350.0
RADIO_MATCH_AMPLIO_MM = 800.0
RADIO_BLOQUE_MM = 3.0

PATRON_APTO = re.compile(r"Tipo\s+([A-Z])\s+(\d+)\s*([a-zA-Z]?)", re.I)
FAMILIAS_DATOS = ("comunicacion", "comunicaciones", "datos", "telephone", "data devices", "pau")
LETRA_TABLERO = {"B": "TB", "C": "TC", "D": "TD", "E": "TE", "F": "TF"}

lineas = []


def p(msg):
    print(msg)
    lineas.append(msg)


def cargar_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def apto_codigo(nombre):
    """'Apartamentos Tipo F 18' -> 'F18' ; 'Apartamento Tipo E 07a' -> 'E07A'."""
    if not nombre:
        return None
    m = PATRON_APTO.search(nombre)
    if not m:
        return None
    letra = m.group(1).upper()
    numero = m.group(2).zfill(2)
    sufijo = (m.group(3) or "").upper()
    return letra + numero + sufijo


def construir_indice(puntos, celda_mm):
    idx = defaultdict(list)
    for it in puntos:
        k = (int(math.floor(it["x"] / celda_mm)), int(math.floor(it["y"] / celda_mm)))
        idx[k].append(it)
    return idx


def vecinos(idx, celda_mm, x, y, radio):
    cx = int(math.floor(x / celda_mm))
    cy = int(math.floor(y / celda_mm))
    n = int(math.ceil(radio / celda_mm)) + 1
    out = []
    for i in range(cx - n, cx + n + 1):
        for j in range(cy - n, cy + n + 1):
            out.extend(idx.get((i, j), []))
    return out


def main():
    p("=" * 78)
    p("RE7_PROPONER_MARKS_TODOS_v02")
    p("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    p("=" * 78)

    for f in (DXF_DISPOSITIVOS, DXF_BLOQUES, INVENTARIO):
        if not os.path.exists(f):
            p("FALTA: %s" % f)
            return 1

    # ---- 1. Dispositivos DXF en coordenadas globales ----
    dxf_dis = cargar_json(DXF_DISPOSITIVOS)
    inserts = {}
    for a in dxf_dis["apartamentos"]:
        inserts[a["name"]] = a["insert_mm"]

    puntos = []
    sin_apto_codigo = 0
    for q in dxf_dis["dispositivos"]:
        ins = inserts.get(q["apto_dxf"])
        if ins is None:
            sin_apto_codigo += 1
            continue
        ix, iy = ins
        gx = ix + (q["x_mm"] - ix) * 1000.0
        gy = iy + (q["y_mm"] - iy) * 1000.0
        cod = apto_codigo(q["apto_dxf"])
        if cod is None:
            sin_apto_codigo += 1
            continue
        puntos.append({
            "x": gx,
            "y": gy,
            "apto": cod,
            "apto_dxf": q["apto_dxf"],
            "nombre_dxf": q.get("nombre_dxf"),
            "familia_revit": q.get("familia_revit"),
            "tipo_revit": q.get("tipo_revit"),
            "layer": q.get("layer"),
            "circuito": None,
        })
    p("Dispositivos DXF globales: %d (sin codigo de apto: %d)" % (
        len(puntos), sin_apto_codigo))

    # ---- 2. Circuito por dispositivo DXF (desde los INSERT del DXF) ----
    bloques = cargar_json(DXF_BLOQUES)["bloques"]
    idx_b = construir_indice(bloques, 500.0)
    con_circuito = 0
    for q in puntos:
        mejores = vecinos(idx_b, 500.0, q["x"], q["y"], RADIO_BLOQUE_MM)
        if mejores:
            b = min(mejores, key=lambda z: (z["x"] - q["x"]) ** 2 + (z["y"] - q["y"]) ** 2)
            q["circuito"] = b.get("circuito")
            q["bloque"] = b.get("nombre")
        if q["circuito"]:
            con_circuito += 1
    p("Con circuito desde bloque DXF: %d / %d" % (con_circuito, len(puntos)))

    faltan = [q for q in puntos if not q["circuito"]]
    if faltan:
        p("Sin circuito (se resolvera por tipo en la propuesta): %d" % len(faltan))

    # ---- 3. Inventario Revit ----
    inv = cargar_json(INVENTARIO)
    disp = inv["dispositivos"]
    p("Inventario Revit: %d dispositivos" % len(disp))

    idx_p = construir_indice(puntos, 500.0)

    # ---- 4. Verificacion de alineacion con los que ya tienen Mark ----
    p("")
    p("-" * 78)
    p("ALINEACION (dispositivos con Mark completo, testigos)")
    por_apto_d = defaultdict(list)
    for d in disp:
        mk = d.get("mark") or ""
        partes = mk.split("|")
        if len(partes) != 3:
            continue
        apto = partes[0]
        cands = vecinos(idx_p, 500.0, d["x"], d["y"], 1500.0)
        if not cands:
            continue
        b = min(cands, key=lambda z: (z["x"] - d["x"]) ** 2 + (z["y"] - d["y"]) ** 2)
        dd = math.hypot(b["x"] - d["x"], b["y"] - d["y"])
        por_apto_d[apto].append((dd, b["apto"]))
    for apto in sorted(por_apto_d.keys()):
        vals = por_apto_d[apto]
        ds = sorted(v[0] for v in vals)
        coinc = sum(1 for v in vals if v[1] == apto)
        p("   %-6s n=%-3d mediana=%6.1f mm  mismo_apto=%d/%d" % (
            apto, len(vals), ds[len(ds) // 2], coinc, len(vals)))

    # ---- 4b. Deteccion de posiciones apiladas (posicion invalida) ----
    apilados = set()
    grupos_xy = defaultdict(list)
    for d in disp:
        grupos_xy[(int(round(d["x"] / 20.0)), int(round(d["y"] / 20.0)))].append(d["id"])
    for k, ids in grupos_xy.items():
        if len(ids) >= 4:
            for i in ids:
                apilados.add(i)
    p("Dispositivos en posicion apilada (>=4 en 20 mm): %d" % len(apilados))

    # ---- 5. Propuesta ----
    propuestas = []
    sin_match = []
    stats = Counter()
    por_apto = defaultdict(int)
    distancias = []

    for d in disp:
        mk = d.get("mark") or ""
        partes = mk.split("|")
        circuito_actual = partes[2].strip() if len(partes) == 3 else ""
        tiene_mark_completo = (len(partes) == 3 and partes[0] and circuito_actual
                               and circuito_actual.upper() != "SIN CIRCUITO")

        cands_prev = vecinos(idx_p, 500.0, d["x"], d["y"], RADIO_MATCH_AMPLIO_MM)
        corregir = False
        motivo = None
        if tiene_mark_completo:
            if not cands_prev:
                stats["ya_tenia_mark"] += 1
                continue
            b0 = min(cands_prev, key=lambda z: (z["x"] - d["x"]) ** 2 + (z["y"] - d["y"]) ** 2)
            d0 = math.hypot(b0["x"] - d["x"], b0["y"] - d["y"])
            mismo_apto = partes[0].upper() == (b0["apto"] or "").upper()
            if mismo_apto:
                stats["ya_tenia_mark"] += 1
                continue
            tipo_ok = (b0.get("tipo_revit") and d.get("tipo") and
                       b0["tipo_revit"].lower() == (d["tipo"] or "").lower())
            # Evidencia fuerte: <=150 mm, o <=80 mm si el tipo no coincide
            if d0 <= 150.0 or (d0 <= 80.0 and tipo_ok):
                corregir = True
                motivo = "mark %s contradice DXF %s a %.0f mm" % (partes[0], b0["apto"], d0)
                stats["correcciones"] += 1
            else:
                stats["ya_tenia_mark_conflicto_debil"] += 1
                continue

        if corregir:
            cands = cands_prev
        else:
            cands = cands_prev

        if not cands:
            sin_match.append({
                "id": d["id"], "familia": d["familia"], "tipo": d["tipo"],
                "x": d["x"], "y": d["y"], "z": d["z"], "mark": mk or None,
            })
            stats["sin_match"] += 1
            continue

        def coste(z):
            dd = math.hypot(z["x"] - d["x"], z["y"] - d["y"])
            if z.get("tipo_revit") and d.get("tipo") and \
                    z["tipo_revit"].lower() == (d["tipo"] or "").lower():
                dd -= 60.0
            return dd

        mejor = min(cands, key=coste)
        dist = math.hypot(mejor["x"] - d["x"], mejor["y"] - d["y"])
        distancias.append(dist)

        if dist <= RADIO_MATCH_MM:
            stats["match_ok"] += 1
        else:
            stats["match_amplio"] += 1

        apto = mejor["apto"]
        letra = LETRA_TABLERO.get(apto[0], "TF")

        fam_txt = ((d.get("familia") or "") + " " + (d.get("categoria") or "") + " " +
                   (d.get("tipo") or "")).lower()
        es_datos = any(k in fam_txt for k in FAMILIAS_DATOS)

        if es_datos:
            circuito = "Datos"
        else:
            circuito = mejor.get("circuito")
            if not circuito:
                circuito = "SIN CIRCUITO"
                stats["sin_circuito"] += 1

        mark = "%s|%s|%s" % (apto, letra, circuito)
        por_apto[apto] += 1

        tipo_ok = bool(mejor.get("tipo_revit")) and bool(d.get("tipo")) and \
            mejor["tipo_revit"].lower() == (d["tipo"] or "").lower()
        aplicable = True
        motivo_no = None
        if d["id"] in apilados:
            aplicable = False
            motivo_no = "posicion apilada en el modelo (>=4 dispositivos en 20 mm)"
        elif dist <= 250.0:
            aplicable = True
        elif dist <= 400.0 and tipo_ok:
            aplicable = True
        else:
            aplicable = False
            motivo_no = "match debil: %.0f mm, tipo DXF %r vs %r" % (
                dist, mejor.get("tipo_revit"), d.get("tipo"))
        if aplicable:
            stats["aplicables"] += 1
        else:
            stats["no_aplicables"] += 1

        propuestas.append({
            "id": d["id"],
            "familia": d.get("familia"),
            "tipo": d.get("tipo"),
            "categoria": d.get("categoria"),
            "x": d["x"], "y": d["y"], "z": d["z"],
            "mark_anterior": mk or None,
            "correccion": corregir,
            "motivo_correccion": motivo,
            "aplicable": aplicable,
            "motivo_no_aplicable": motivo_no,
            "apto": apto,
            "tablero": letra,
            "circuito": circuito,
            "mark": mark,
            "match_dist_mm": round(dist, 1),
            "match_tipo_dxf": mejor.get("tipo_revit"),
            "match_familia_dxf": mejor.get("familia_revit"),
            "match_nombre_dxf": mejor.get("nombre_dxf"),
            "es_datos": es_datos,
        })

    p("")
    p("-" * 78)
    p("PROPUESTA")
    p("Dispositivos en inventario: %d" % len(disp))
    p("Ya tenian Mark completo: %d" % stats["ya_tenia_mark"])
    p("Correcciones de Mark contradictorio: %d" % stats["correcciones"])
    p("Conflictos no corregidos (evidencia debil): %d" % stats["ya_tenia_mark_conflicto_debil"])
    p("Propuestas: %d" % len(propuestas))
    p("   match <= %.0f mm: %d" % (RADIO_MATCH_MM, stats["match_ok"]))
    p("   match %.0f-%.0f mm: %d" % (RADIO_MATCH_MM, RADIO_MATCH_AMPLIO_MM, stats["match_amplio"]))
    p("Sin match: %d" % stats["sin_match"])
    p("Propuestas SIN CIRCUITO: %d" % stats["sin_circuito"])
    p("Aplicables automaticamente: %d | NO aplicables (revisar): %d" % (
        stats["aplicables"], stats["no_aplicables"]))
    if distancias:
        ds = sorted(distancias)
        p("Distancia de match: mediana=%.1f p90=%.1f max=%.1f mm" % (
            ds[len(ds) // 2], ds[int(len(ds) * 0.9)], ds[-1]))
    p("")
    p("Propuestas por apartamento:")
    for a in sorted(por_apto.keys()):
        p("   %-6s %d" % (a, por_apto[a]))
    if sin_match:
        p("")
        p("Sin match (primeros 25 de %d):" % len(sin_match))
        for s in sin_match[:25]:
            p("   id=%s [%s | %s] (%.0f,%.0f,%.0f)" % (
                s["id"], s["familia"], s["tipo"], s["x"], s["y"], s["z"]))

    with io.open(OUT_JSON, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "version": "v02",
            "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "documento": inv.get("documento"),
            "fuente_posiciones": DXF_DISPOSITIVOS,
            "resumen": {
                "inventario": len(disp),
                "ya_tenian_mark": stats["ya_tenia_mark"],
                "correcciones": stats["correcciones"],
                "conflictos_debiles_no_corregidos": stats["ya_tenia_mark_conflicto_debil"],
                "propuestas": len(propuestas),
                "match_ok": stats["match_ok"],
                "match_amplio": stats["match_amplio"],
                "sin_match": len(sin_match),
                "sin_circuito": stats["sin_circuito"],
                "aplicables": stats["aplicables"],
                "no_aplicables": stats["no_aplicables"],
                "apilados": len(apilados),
                "por_apartamento": dict(por_apto),
            },
            "propuestas": propuestas,
            "sin_match": sin_match,
        }, ensure_ascii=True, indent=1))
    p("")
    p("JSON: %s" % OUT_JSON)

    with io.open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    p("Resumen: %s" % OUT_TXT)
    p("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
