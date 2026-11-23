# -*- coding: utf-8 -*-
"""
RE7_PROPONER_MARKS_TODOS_v01.py

Entorno: Python 3 (fuera de Revit).

Cruza tres fuentes para proponer el Mark de TODOS los dispositivos electricos,
sin usar zonas geograficas:

  1. data/f7_inventario_revit_v03.json      -> dispositivos reales (id + XYZ mm)
  2. data/maestro_colocacion_piso5_ABSOLUTO.json -> apto de origen por posicion
  3. ArchivosBase/STM-T5-P5_bloques_electricos-XPL.dxf -> circuito por bloque
     y nombre de tablero por INSERT TB-Panel (atributo TABLERO)

Reglas:
  * El apartamento sale del maestro de colocacion (dato de origen), no de cajas
    de zona. Cada dispositivo de Revit se empareja con el dispositivo del
    maestro mas cercano en XY.
  * El circuito sale del texto de circuito (patron XX-NN) mas cercano al bloque
    DXF emparejado, a <= 1000 mm.
  * El tablero sale del INSERT TB-Panel mas cercano; su atributo TABLERO
    ("TF 17", "TE 07a", "TB 15") se convierte al codigo de apartamento
    (F17, E07A, B15).
  * Datos / comunicaciones: circuito "Datos", tablero del apartamento.
  * Si no hay circuito: "SIN CIRCUITO" (se reporta, no se inventa).
  * Se calcula el desfase por apartamento usando los dispositivos que ya
    tienen Mark (F17/F18) como testigos, para verificar alineacion.

Salidas:
  data/f7_dxf_bloques_completo_v01.json
  data/f7_marks_propuestos_todos_v01.json
  data/f7_marks_propuestos_todos_v01_resumen.txt
"""
import datetime
import io
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos-XPL.dxf"
INVENTARIO = r"D:\Work\PROJECTS\RevitElectrico\data\f7_inventario_revit_v03.json"
MAESTRO = r"D:\Work\PROJECTS\RevitElectrico\data\maestro_colocacion_piso5_ABSOLUTO.json"
OUT_BLOQUES = r"D:\Work\PROJECTS\RevitElectrico\data\f7_dxf_bloques_completo_v01.json"
OUT_PROPUESTA = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_propuestos_todos_v01.json"
OUT_TXT = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_propuestos_todos_v01_resumen.txt"

BLOQUES_ELEC = [
    "ELEC-T-D-t-15A", "ELEC-T-GFCI-t-15A", "ELEC-I-S-1-5A", "ELEC-I-S-2-5A",
    "ELEC-I-S-C1-5A", "ELEC-TEL", "ELEC-NET-PAU", "ELEC-CAMPANA", "ELEC-TIMBRE",
    "ELEC-F-CONTROL", "ELEC-F-VENT", "S3", "S3C", "ELEC-EXT",
    "Bala Stil Led 10W", "Bala Stil Led 13W", "Bala Stil Led 22W",
]

RADIO_TEXTO_MM = 1000.0
PATRON_CIRCUITO = re.compile(r"\b([A-Z]{2}-\d{2})\b")

RADIO_MATCH_MM = 300.0       # radio de emparejamiento Revit <-> maestro
RADIO_MATCH_ESTRICTO_MM = 150.0
RADIO_BLOQUE_MM = 400.0      # radio para tomar circuito del bloque DXF

FAMILIAS_DATOS = ("M_Comunicaciones", "Comunicaciones", "M_Toma datos")

lineas = []


def p(msg):
    print(msg)
    lineas.append(msg)


def cargar_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def panel_a_apto(nombre):
    """'TF 17' -> 'F17' ; 'TE 07a' -> 'E07A' ; 'TB 15' -> 'B15'."""
    if not nombre:
        return None
    partes = nombre.strip().split()
    if len(partes) < 2:
        return None
    codigo = partes[0].upper()
    numero = partes[1].replace(" ", "").upper()
    if len(codigo) < 2:
        return None
    letra = codigo[1]
    return (letra + numero).upper()


def leer_dxf():
    import ezdxf
    doc = ezdxf.readfile(DXF_PATH)
    msp = doc.modelspace()

    bloques = []
    for e in msp.query("INSERT"):
        nombre = e.dxf.name or ""
        if nombre not in BLOQUES_ELEC:
            continue
        pt = e.dxf.insert
        bloques.append({
            "nombre": nombre,
            "x": round(pt.x, 3),
            "y": round(pt.y, 3),
            "handle": str(e.dxf.handle),
            "layer": e.dxf.layer,
        })

    textos = []
    for e in msp.query("TEXT"):
        pt = e.dxf.insert
        textos.append({"x": pt.x, "y": pt.y, "text": e.dxf.text or ""})
    for e in msp.query("MTEXT"):
        pt = e.dxf.insert
        textos.append({"x": pt.x, "y": pt.y, "text": e.text or ""})

    paneles = []
    for e in msp.query("INSERT"):
        if e.dxf.name != "TB-Panel":
            continue
        pt = e.dxf.insert
        nombre_tablero = None
        for a in e.attribs:
            if a.dxf.tag.upper() == "TABLERO":
                nombre_tablero = a.dxf.text
        if not nombre_tablero:
            continue
        paneles.append({
            "tablero": nombre_tablero,
            "apto": panel_a_apto(nombre_tablero),
            "x": round(pt.x, 3),
            "y": round(pt.y, 3),
        })

    # circuito mas cercano por bloque
    for b in bloques:
        mejor_d = None
        mejor_c = None
        for t in textos:
            d = math.sqrt((t["x"] - b["x"]) ** 2 + (t["y"] - b["y"]) ** 2)
            if d > RADIO_TEXTO_MM:
                continue
            m = PATRON_CIRCUITO.search(t["text"])
            if not m:
                continue
            if mejor_d is None or d < mejor_d:
                mejor_d = d
                mejor_c = m.group(1)
        b["circuito"] = mejor_c
        b["circuito_dist_mm"] = round(mejor_d, 1) if mejor_d is not None else None

    # panel mas cercano por bloque
    for b in bloques:
        mejor = None
        mejor_d = None
        for pn in paneles:
            d = math.sqrt((pn["x"] - b["x"]) ** 2 + (pn["y"] - b["y"]) ** 2)
            if mejor_d is None or d < mejor_d:
                mejor_d = d
                mejor = pn
        b["panel_cercano"] = mejor["tablero"] if mejor else None
        b["panel_apto"] = mejor["apto"] if mejor else None
        b["panel_dist_mm"] = round(mejor_d, 1) if mejor_d is not None else None

    p("DXF: %d bloques electricos, %d textos, %d paneles TB-Panel" % (
        len(bloques), len(textos), len(paneles)))
    for pn in sorted(paneles, key=lambda q: q["apto"] or ""):
        p("   panel %-8s -> %s" % (pn["tablero"], pn["apto"]))
    return bloques, textos, paneles


def construir_indice(puntos, celda_mm):
    idx = defaultdict(list)
    for it in puntos:
        k = (int(math.floor(it["x"] / celda_mm)), int(math.floor(it["y"] / celda_mm)))
        idx[k].append(it)
    return idx, celda_mm


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
    p("RE7_PROPONER_MARKS_TODOS_v01")
    p("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    p("=" * 78)

    if not os.path.exists(INVENTARIO):
        p("FALTA el inventario de Revit: %s" % INVENTARIO)
        p("Ejecuta primero RE7_EXPORTAR_INVENTARIO_DISPOSITIVOS_v03.py en pyRevit.")
        return 1

    inv = cargar_json(INVENTARIO)
    disp_revit = inv["dispositivos"]
    p("Inventario Revit: %d dispositivos (doc=%r)" % (
        len(disp_revit), inv.get("documento", {}).get("titulo")))

    maes = cargar_json(MAESTRO)
    puntos_maestro = []
    for apto, info in maes["apartamentos"].items():
        for d in info["dispositivos"]:
            pm = d["posicion_m"]
            puntos_maestro.append({
                "apto": apto,
                "x": pm["x"] * 1000.0,
                "y": pm["y"] * 1000.0,
                "nombre_dxf": d.get("nombre_dxf"),
                "familia_revit": d.get("familia_revit"),
                "tipo_revit": d.get("tipo_revit"),
                "layer": d.get("layer"),
            })
    p("Maestro: %d dispositivos en %d apartamentos" % (
        len(puntos_maestro), len(maes["apartamentos"])))

    bloques, textos, paneles = leer_dxf()

    with io.open(OUT_BLOQUES, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "version": "v01",
            "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "dxf": DXF_PATH,
            "paneles": paneles,
            "bloques": bloques,
        }, ensure_ascii=True, indent=1))
    p("Bloques DXF guardados: %s" % OUT_BLOQUES)

    idx_maestro, celda = construir_indice(puntos_maestro, 500.0)
    idx_bloques, celda_b = construir_indice(bloques, 500.0)

    # ---- Verificacion de alineacion con dispositivos ya marcados ----
    p("")
    p("-" * 78)
    p("VERIFICACION DE ALINEACION (dispositivos que ya tienen Mark)")
    offsets = defaultdict(list)
    for d in disp_revit:
        mk = d.get("mark") or ""
        if "|" not in mk:
            continue
        apto = mk.split("|")[0]
        cands = vecinos(idx_maestro, celda, d["x"], d["y"], 1500.0)
        cands = [c for c in cands if c["apto"] == apto]
        if not cands:
            continue
        mejor = min(cands, key=lambda c: (c["x"] - d["x"]) ** 2 + (c["y"] - d["y"]) ** 2)
        dx = d["x"] - mejor["x"]
        dy = d["y"] - mejor["y"]
        offsets[apto].append((dx, dy, math.hypot(dx, dy)))

    for apto in sorted(offsets.keys()):
        vals = offsets[apto]
        ds = sorted(v[2] for v in vals)
        med = ds[len(ds) // 2]
        dx = sorted(v[0] for v in vals)[len(vals) // 2]
        dy = sorted(v[1] for v in vals)[len(vals) // 2]
        p("   %-6s n=%-3d mediana_dist=%.1f mm  offset_mediano=(%+.1f, %+.1f) mm" % (
            apto, len(vals), med, dx, dy))

    # ---- Propuesta de Mark por dispositivo ----
    propuestas = []
    sin_match = []
    stats = Counter()
    por_apto = defaultdict(int)
    circuitos_por_apto_tipo = defaultdict(Counter)

    for d in disp_revit:
        mk = d.get("mark") or ""
        if "|" in mk and len(mk.split("|")) == 3 and mk.split("|")[2]:
            stats["ya_tenia_mark"] += 1
            continue

        cands = vecinos(idx_maestro, celda, d["x"], d["y"], RADIO_MATCH_MM)
        mejor = None
        if cands:
            def coste(c):
                dd = math.hypot(c["x"] - d["x"], c["y"] - d["y"])
                mismo_tipo = 0.0
                if c.get("tipo_revit") and d.get("tipo") and c["tipo_revit"].lower() == (d["tipo"] or "").lower():
                    mismo_tipo = -80.0
                return dd + mismo_tipo
            mejor = min(cands, key=coste)

        if mejor is None:
            sin_match.append({
                "id": d["id"], "familia": d["familia"], "tipo": d["tipo"],
                "x": d["x"], "y": d["y"], "z": d["z"],
            })
            stats["sin_match_maestro"] += 1
            continue

        dist = math.hypot(mejor["x"] - d["x"], mejor["y"] - d["y"])
        apto = mejor["apto"]
        por_apto[apto] += 1

        # circuito desde el bloque DXF mas cercano
        circuito = None
        bloque_cercano = None
        bd = None
        cands_b = vecinos(idx_bloques, celda_b, d["x"], d["y"], RADIO_BLOQUE_MM)
        if cands_b:
            bloque_cercano = min(
                cands_b, key=lambda c: (c["x"] - d["x"]) ** 2 + (c["y"] - d["y"]) ** 2)
            bd = math.hypot(bloque_cercano["x"] - d["x"], bloque_cercano["y"] - d["y"])
            circuito = bloque_cercano.get("circuito")

        familia_txt = (d.get("familia") or "") + " " + (d.get("categoria") or "")
        es_datos = any(k.lower() in familia_txt.lower() for k in FAMILIAS_DATOS) \
            or (d.get("tipo") or "").lower() in ("datos", "pau")

        letra_tablero = "TF"
        if paneles:
            cands_p = min(
                paneles,
                key=lambda q: (q["x"] - d["x"]) ** 2 + (q["y"] - d["y"]) ** 2)
            if cands_p.get("apto") == apto:
                letra_tablero = cands_p["tablero"].split()[0]

        if es_datos:
            circuito = "Datos"
        elif not circuito:
            circuito = "SIN CIRCUITO"
            stats["sin_circuito"] += 1

        mark = "%s|%s|%s" % (apto, letra_tablero, circuito)
        circuitos_por_apto_tipo[(apto, d.get("tipo"))][circuito] += 1

        propuestas.append({
            "id": d["id"],
            "familia": d.get("familia"),
            "tipo": d.get("tipo"),
            "categoria": d.get("categoria"),
            "x": d["x"], "y": d["y"], "z": d["z"],
            "mark_anterior": mk or None,
            "apto": apto,
            "tablero": letra_tablero,
            "circuito": circuito,
            "mark": mark,
            "match_apto_dist_mm": round(dist, 1),
            "match_maestro": {
                "nombre_dxf": mejor.get("nombre_dxf"),
                "familia_revit": mejor.get("familia_revit"),
                "tipo_revit": mejor.get("tipo_revit"),
            },
            "bloque_dxf": bloque_cercano["nombre"] if bloque_cercano else None,
            "bloque_dist_mm": round(bd, 1) if bd is not None else None,
            "es_datos": es_datos,
        })
        if dist <= RADIO_MATCH_ESTRICTO_MM:
            stats["match_estricto"] += 1
        else:
            stats["match_amplio"] += 1

    p("")
    p("-" * 78)
    p("PROPUESTA")
    p("Dispositivos en inventario: %d" % len(disp_revit))
    p("Ya tenian Mark completo (no se tocan): %d" % stats["ya_tenia_mark"])
    p("Propuestas generadas: %d" % len(propuestas))
    p("   emparejados <=%.0f mm: %d" % (RADIO_MATCH_ESTRICTO_MM, stats["match_estricto"]))
    p("   emparejados %.0f-%.0f mm: %d" % (
        RADIO_MATCH_ESTRICTO_MM, RADIO_MATCH_MM, stats["match_amplio"]))
    p("Sin match en maestro: %d" % stats["sin_match_maestro"])
    p("Propuestas sin circuito (SIN CIRCUITO): %d" % stats["sin_circuito"])
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

    with io.open(OUT_PROPUESTA, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "version": "v01",
            "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "documento": inv.get("documento"),
            "resumen": {
                "inventario": len(disp_revit),
                "ya_tenian_mark": stats["ya_tenia_mark"],
                "propuestas": len(propuestas),
                "match_estricto": stats["match_estricto"],
                "match_amplio": stats["match_amplio"],
                "sin_match": len(sin_match),
                "sin_circuito": stats["sin_circuito"],
                "por_apartamento": dict(por_apto),
            },
            "propuestas": propuestas,
            "sin_match": sin_match,
        }, ensure_ascii=True, indent=1))
    p("")
    p("JSON propuesta: %s" % OUT_PROPUESTA)

    with io.open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    p("Resumen texto: %s" % OUT_TXT)
    p("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
