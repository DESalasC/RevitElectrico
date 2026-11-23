# -*- coding: utf-8 -*-
"""
RE7_PLANIFICADOR_RUTEO_v08.py
CALCULA (offline, sin tocar Revit) el plan de conduits F7 para F17/F18.

METODO:
1. Carga topologia del DXF (f7_topologia_dxf_f17_f18_v01.json): polilineas con
   secuencia de aparatos DXF y aristas aparato->aparato.
2. Carga dispositivos reales de Revit (f7_revit_dispositivos_v02.json).
3. Empareja DXF <-> Revit por categoria de familia/tipo + proximidad (greedy
   uno-a-uno, pases de 600 mm y 1800 mm).
4. Deforma cada polilinea del DXF: en cada aparato emparejado el punto se ancla
   a la posicion XY real de Revit; el vector de correccion se interpola a lo
   largo del trazado. Todo el plano horizontal va a Z=15930 mm (plenum techo).
5. Para cada arista (par de aparatos consecutivos emparejados) genera tramos:
   riser vertical en A (z_real -> Z_plano), tramos horizontales en Z_plano
   siguiendo la polilinea deformada, riser vertical en B (Z_plano -> z_real).
6. Comunicaciones (capa ELEC-APPL-NETWORD): 2 tubos paralelos separados 40 mm.
7. Salida: plan JSON (auditable) + reporte por consola. Nada se escribe en Revit.

Entradas:
  data/f7_topologia_dxf_f17_f18_v01.json
  data/f7_revit_dispositivos_v02.json
Salidas:
  data/f7_plan_ruteo_f17_f18_v08.json
"""
import datetime
import json
import math
import os
import sys

FT_A_MM = 304.8
Z_PLANO_MM = 15930.0   # plenum techo: nivel 13220 + 2710 (precedente F01/F02)
NIVEL_PISO5_MM = 13220.0
RADIO1_MM = 600.0      # primer pase de emparejamiento
RADIO2_MM = 1800.0     # segundo pase
LARGO_MIN_MM = 3.0     # conduits mas cortos se saltan
OFFSET_COMMS_MM = 40.0 # separacion entre los 2 tubos de comunicaciones
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

# Mapeo bloque DXF -> categoria de dispositivo Revit (familia, tipo).
# Si familia o tipo es None, ese bloque DXF no tiene contraparte en Revit.
BLOQUE_A_REVIT = {
    "Bala Stil Led 10W":  ("Lighting", "M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 13W":  ("Lighting", "M_Iluminacion", "SONO FLEX 13 trim"),
    "Bala Stil Led 22W":  ("Lighting", "M_Iluminacion", "SONO FLEX 22 trim"),
    "ELEC-T-D-t-15A":     ("Electrical Fixtures", "M_Toma doble", "Normal"),
    "ELEC-T-GFCI-t-15A":  ("Electrical Fixtures", "M_Toma doble", "GFCI"),
    "ELEC-I-S-1-5A":      ("Electrical Fixtures", "M_Interruptores", "Simple"),
    "ELEC-I-S-2-5A":      ("Electrical Fixtures", "M_Interruptores", "Doble"),
    "ELEC-F-CONTROL":     ("Electrical Fixtures", "M_Climatizacion", "Interruptor Ventilador"),
    "ELEC-F-VENT":        ("Electrical Fixtures", "M_ClimatizacionV", "Ventilador"),
    "ELEC-NET-PAU":       ("Data Devices", "Consolidation_Point", "CPB12BL"),
    "S3":                 ("Electrical Fixtures", "M_Interruptores", "Simple"),
    "S3C":                ("Electrical Fixtures", "M_Interruptores", "Doble"),
    # Sin contraparte en Revit (segun volcado v02 de CENTRAL-V01c):
    "ELEC-TEL":           (None, None, None),
    "ELEC-CAMPANA":       (None, None, None),
    "ELEC-TIMBRE":        (None, None, None),
    "ELEC-EXT":           (None, None, None),
}

# Capa DXF -> tipo de conduit (hipotesis: diam. no legible por API)
# TuboE=112216 (electrica, asumido Ø21), TuboC=5508657 (comunicaciones, asumido Ø21),
# Tuberia=112217 (asumido Ø27). VERIFICAR en el modelo.
CAPA_A_TIPO = {
    "ELEC-LIGHT-PIPE":     ("TuboE", 112216, False),
    "ELEC-POWER- PIPE":    ("TuboE", 112216, False),
    "ELEC-Powr-Pipe-Idem Piso": ("TuboE", 112216, False),
    "ELEC-APPL-NETWORD":   ("TuboC", 5508657, True),  # communications: 2 tubos
}


def _raiz():
    r = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if r and os.path.exists(r):
        return r
    return DEFAULT_ROOT


def log(msg):
    print(msg)
    try:
        sys.stdout.flush()
    except Exception:
        pass


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def z_esperada(categoria, familia, tipo):
    """Z real del dispositivo segun el volcado v02 (mm sobre nivel Piso 5)."""
    if familia == "M_Toma doble":
        return 13520.0
    if familia in ("M_Interruptores", "M_Climatizacion"):
        return 14320.0
    if familia in ("M_ClimatizacionV", "M_Iluminacion"):
        return 15820.0
    if familia == "Consolidation_Point":
        return 15920.0
    return Z_PLANO_MM


def emparejar(dxf_devs, revit_devs):
    """Emparejamiento uno-a-uno greedy por categoria y proximidad."""
    matches = []
    usado_revit = set()
    orden = sorted(dxf_devs, key=lambda d: (d["x"], d["y"]))
    for radio in (RADIO1_MM, RADIO2_MM):
        pendientes = [d for d in orden if d["idx"] not in {m["dxf_idx"] for m in matches}]
        for d in pendientes:
            mejor = None
            mejor_dist = None
            for r in revit_devs:
                if r["id"] in usado_revit:
                    continue
                if not categoria_coincide(d, r):
                    continue
                dd = dist2d((d["x"], d["y"]), (r["x_mm"], r["y_mm"]))
                if mejor_dist is None or dd < mejor_dist:
                    mejor_dist = dd
                    mejor = r
            if mejor is not None and mejor_dist <= radio:
                usado_revit.add(mejor["id"])
                matches.append({
                    "dxf_idx": d["idx"],
                    "bloque": d["bloque"],
                    "dxf_x": d["x"],
                    "dxf_y": d["y"],
                    "revit_id": mejor["id"],
                    "revit_familia": mejor.get("familia"),
                    "revit_tipo": mejor.get("tipo"),
                    "revit_x": mejor["x_mm"],
                    "revit_y": mejor["y_mm"],
                    "revit_z": mejor["z_mm"],
                    "dist_mm": round(mejor_dist, 2),
                    "radio_usado": radio,
                })
    return matches


def categoria_coincide(dxf_dev, revit_dev):
    mapa = BLOQUE_A_REVIT.get(dxf_dev["bloque"])
    if not mapa or mapa[0] is None:
        return False
    cat, fam, tip = mapa
    rc = revit_dev.get("categoria")
    rf = revit_dev.get("familia") or ""
    rt = revit_dev.get("tipo") or ""
    if cat and rc and cat.lower() not in rc.lower():
        return False
    if fam and fam.lower() not in rf.lower():
        return False
    if tip and tip.lower() not in rt.lower():
        return False
    return True


def punto_en_polilinea(vertices, s_acum, s):
    """Punto (x,y) de la polilinea a una arclength dada."""
    if s <= 0:
        return vertices[0]
    if s >= s_acum[-1]:
        return vertices[-1]
    # buscar segmento
    for i in range(len(s_acum) - 1):
        if s_acum[i] <= s <= s_acum[i + 1]:
            t = (s - s_acum[i]) / (s_acum[i + 1] - s_acum[i]) if s_acum[i + 1] > s_acum[i] else 0.0
            x = vertices[i][0] + t * (vertices[i + 1][0] - vertices[i][0])
            y = vertices[i][1] + t * (vertices[i + 1][1] - vertices[i][1])
            return (x, y)
    return vertices[-1]


def angulo_valido(deg):
    """Devuelve (es_valido, angulo_cuantizado). Normaliza modulo 180 (linea sin direccion)."""
    a = deg % 180.0
    k = round(a / 22.5)
    sn = k * 22.5
    if abs(a - sn) < 3.0:
        return True, sn
    return False, sn

def angulo_cercano_valido(deg, umbral=8.0):
    """Cuantiza a multiplo de 22.5 si esta dentro de umbral deg. Devuelve el cuantizado o None."""
    a = deg % 180.0
    k = round(a / 22.5)
    sn = k * 22.5
    if abs(a - sn) < umbral:
        return sn
    return None


def mk_tramo(x1, y1, z1, x2, y2, z2, type_id, es_comms, segmentos_raw=0):
    return {
        "a": [round(x1, 3), round(y1, 3), round(z1, 3)],
        "b": [round(x2, 3), round(y2, 3), round(z2, 3)],
        "type_id": type_id,
        "comms": bool(es_comms),
        "largo_mm": round(dist3d([x1, y1, z1], [x2, y2, z2]), 3),
        "segmentos_raw": int(segmentos_raw),
    }


def dist3d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])


def main():
    raiz = _raiz()
    topo_path = os.path.join(raiz, "data", "f7_topologia_dxf_f17_f18_v01.json")
    revit_path = os.path.join(raiz, "data", "f7_revit_dispositivos_v02.json")

    with open(topo_path) as f:
        topo = json.load(f)
    with open(revit_path) as f:
        revit_dump = json.load(f)

    aristas = topo.get("aristas", [])
    polilines = topo.get("polilineas", [])
    aparatos = topo.get("aparatos", [])
    revit_devs = revit_dump.get("dispositivos", [])

    log("=" * 66)
    log("RE7_PLANIFICADOR_RUTEO_v08  (offline - nada se escribe en Revit)")
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    log("=" * 66)
    log("Aparatos DXF: %d  |  Dispositivos Revit: %d" % (len(aparatos), len(revit_devs)))
    log("Aristas DXF: %d  |  Polilineas: %d" % (len(aristas), len(polilines)))
    log("Z plano ruteo: %.0f mm  |  Nivel Piso 5: %.0f mm" % (Z_PLANO_MM, NIVEL_PISO5_MM))
    log("Radio emparejamiento: %d mm luego %d mm" % (RADIO1_MM, RADIO2_MM))
    log("")

    # indice polilinea -> datos
    poly_por_idx = {p["idx"]: p for p in polilines}
    # aristas por polilinea
    aristas_por_poly = {}
    for e in aristas:
        aristas_por_poly.setdefault(e["poly"], []).append(e)

    # hits por polilinea (reconstruir desde detalle)
    hits_por_poly = {}
    for p in polilines:
        hits = []
        for h in p.get("hits", []):
            hits.append({
                "idx": h["idx"],
                "dxf_x": h.get("x"),   # no existe en hits; usar aparatos
                "s": h["s"],
            })
        hits_por_poly[p["idx"]] = hits

    # mapear aparatos idx -> datos completos
    apto_por_idx = {a["idx"]: a for a in aparatos}

    plan = {
        "version": "v08",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "parametros": {
            "z_plano_mm": Z_PLANO_MM,
            "nivel_piso5_mm": NIVEL_PISO5_MM,
            "radio1_mm": RADIO1_MM,
            "radio2_mm": RADIO2_MM,
            "largo_min_mm": LARGO_MIN_MM,
            "offset_comms_mm": OFFSET_COMMS_MM,
        },
        "apartamentos": {},
        "resumen_global": {},
    }

    total_match = 0
    total_conduits = 0
    total_gaps = 0

    for apto in sorted(["F17", "F18"]):
        dxf_ap = [a for a in aparatos if a["apto"] == apto]
        revit_ap = [d for d in revit_devs if d["apto"] == apto]

        # anotar dxf_devs con x,y del aparato
        dxf_devs = []
        for a in dxf_ap:
            mapa = BLOQUE_A_REVIT.get(a["bloque"])
            dxf_devs.append({
                "idx": a["idx"], "bloque": a["bloque"], "x": a["x"], "y": a["y"],
                "mapa": mapa,
            })

        matches = emparejar(dxf_devs, revit_ap)
        total_match += len(matches)
        matches_por_idx = {m["dxf_idx"]: m for m in matches}

        matched_ids = {m["dxf_idx"] for m in matches}
        revit_matched_ids = {m["revit_id"] for m in matches}
        unmatched_dxf = [d for d in dxf_devs if d["idx"] not in matched_ids]
        unmatched_revit = [r for r in revit_ap if r["id"] not in revit_matched_ids]

        # rutas por polilinea de este apto
        rutas = []
        conduits_plan = []
        edges_ok = 0
        edges_parcial = 0
        for p in polilines:
            if p["apto"] != apto:
                continue
            hits = []
            for h in p.get("hits", []):
                a = apto_por_idx.get(h["idx"])
                if not a:
                    continue
                m = matches_por_idx.get(h["idx"])
                hits.append({
                    "idx": h["idx"],
                    "s": h["s"],
                    "dxf_x": a["x"],
                    "dxf_y": a["y"],
                    "revit": m,
                })
            hits.sort(key=lambda h: h["s"])
            matched_hits = [h for h in hits if h["revit"] is not None]
            if len(matched_hits) >= 2:
                edges_ok += len(matched_hits) - 1
            elif len(hits) >= 1:
                edges_parcial += 1

            # construir tramos: unir hits consecutivos emparejados siguiendo la polilinea
            tramos = generar_ruta_desde_hits(p, matched_hits, CAPA_A_TIPO)
            for t in tramos:
                if t["largo_mm"] < LARGO_MIN_MM:
                    continue
                conduits_plan.append({
                    "apto": apto,
                    "poly": p["idx"],
                    "layer": p["layer"],
                    "type_id": t["type_id"],
                    "comms": t["comms"],
                    "a": t["a"],
                    "b": t["b"],
                    "largo_mm": t["largo_mm"],
                })
            rutas.append({
                "poly": p["idx"],
                "layer": p["layer"],
                "n_hits": len(hits),
                "n_matched": len(matched_hits),
                "n_tramos": len([t for t in tramos if dist3d(t["a"], t["b"]) >= LARGO_MIN_MM]),
            })

        total_conduits += len(conduits_plan)
        total_gaps += edges_parcial

        log("-" * 66)
        log("APARTAMENTO %s" % apto)
        log("  DXF aparatos: %d  |  Revit dispositivos: %d  |  Emparejados: %d" % (
            len(dxf_ap), len(revit_ap), len(matches)))
        log("  Aristas con ambos extremos emparejados: %d" % edges_ok)
        log("  Aristas parciales (sin conexion): %d" % edges_parcial)
        log("  Conduits a crear (plan): %d" % len(conduits_plan))
        log("  DXF sin match en Revit: %d" % len(unmatched_dxf))
        for d in unmatched_dxf[:8]:
            log("     %-30s (%.0f, %.0f) %s" % (d["bloque"], d["x"], d["y"],
                                                d["mapa"]))
        log("  Revit sin match en DXF: %d" % len(unmatched_revit))
        for r in unmatched_revit[:8]:
            log("     %-30s %-20s (%.0f, %.0f) Z=%.0f" % (
                r.get("familia"), r.get("tipo"), r["x_mm"], r["y_mm"], r["z_mm"]))

        plan["apartamentos"][apto] = {
            "dxf_aparatos": len(dxf_ap),
            "revit_dispositivos": len(revit_ap),
            "emparejados": len(matches),
            "aristas_completas": edges_ok,
            "aristas_parciales": edges_parcial,
            "conduits_plan": len(conduits_plan),
            "unmatched_dxf": [{"bloque": d["bloque"], "x": d["x"], "y": d["y"]} for d in unmatched_dxf],
            "unmatched_revit": [{"familia": r.get("familia"), "tipo": r.get("tipo"),
                                 "x": r["x_mm"], "y": r["y_mm"], "z": r["z_mm"], "id": r["id"]}
                                for r in unmatched_revit],
            "matches": matches,
            "conduits": conduits_plan,
            "rutas": rutas,
        }

    log("=" * 66)
    log("RESUMEN GLOBAL: emparejados=%d  conduits_plan=%d  gaps=%d" % (
        total_match, total_conduits, total_gaps))
    log("=" * 66)

    ruta_out = os.path.join(raiz, "data", "f7_plan_ruteo_f17_f18_v08.json")
    try:
        with open(ruta_out, "w") as f:
            f.write(json.dumps(plan, ensure_ascii=True, indent=2))
        log("PLAN guardado: %s" % ruta_out)
    except Exception as e:
        log("ERROR escribiendo plan: %s" % str(e))

    log("FIN (plan solo en disco, Revit sin modificar)")
    log("=" * 66)


def generar_ruta_desde_hits(poly, matched_hits, capa_a_tipo):
    """Wrapper que reusa la logica de generar_ruta con hits ya mapeados."""
    vertices = [(v[0], v[1]) for v in poly["vertices"]]
    s_acum = [0.0]
    for i in range(len(vertices) - 1):
        s_acum.append(s_acum[-1] + dist2d(vertices[i], vertices[i + 1]))

    if len(matched_hits) < 2:
        return []

    tramos = []
    tipo_info = CAPA_A_TIPO.get(poly["layer"])
    if not tipo_info:
        return []
    type_id = tipo_info[1]
    es_comms = tipo_info[2]

    for i in range(len(matched_hits) - 1):
        ha = matched_hits[i]
        hb = matched_hits[i + 1]
        si, sj = ha["s"], hb["s"]
        if sj <= si:
            continue
        m_a, m_b = ha["revit"], hb["revit"]
        off_a = (m_a["revit_x"] - ha["dxf_x"], m_a["revit_y"] - ha["dxf_y"])
        off_b = (m_b["revit_x"] - hb["dxf_x"], m_b["revit_y"] - hb["dxf_y"])
        z_a = m_a["revit_z"]
        z_b = m_b["revit_z"]

        pts = [punto_en_polilinea(vertices, s_acum, si)]
        for k in range(len(vertices)):
            if si < s_acum[k] < sj:
                pts.append(vertices[k])
        pts.append(punto_en_polilinea(vertices, s_acum, sj))

        s_pts = [si]
        for k in range(len(vertices)):
            if si < s_acum[k] < sj:
                s_pts.append(s_acum[k])
        s_pts.append(sj)

        defos = []
        for pt, s in zip(pts, s_pts):
            if sj <= si:
                t = 0.0
            else:
                t = (s - si) / (sj - si)
            ox = off_a[0] + (off_b[0] - off_a[0]) * t
            oy = off_a[1] + (off_b[1] - off_a[1]) * t
            defos.append((pt[0] + ox, pt[1] + oy))

        tramos.append(mk_tramo(m_a["revit_x"], m_a["revit_y"], z_a,
                               m_a["revit_x"], m_a["revit_y"], Z_PLANO_MM,
                               type_id, es_comms))
        # tramos horizontales en plano, cuantizando a angulos validos (22.5 deg)
        # y forzando el cierre exacto en el dispositivo B (ultimo tramo absorbe
        # el residuo). Cada tramo reporta si tuvo que usar un angulo raw.
        cursor = (defos[0][0], defos[0][1])
        segmentos_raw = 0
        for j in range(len(defos) - 1):
            p2_raw = (defos[j + 1][0], defos[j + 1][1])
            es_ultimo_h = (j == len(defos) - 2)
            L = dist2d(cursor, p2_raw)
            if L < 0.01:
                cursor = p2_raw
                continue
            a = math.degrees(math.atan2(p2_raw[1] - cursor[1], p2_raw[0] - cursor[0]))
            if es_ultimo_h:
                p2 = p2_raw  # cierre exacto en el dispositivo B
            else:
                sn = angulo_cercano_valido(a, umbral=8.0)
                if sn is not None:
                    rad = math.radians(sn)
                    p2 = (cursor[0] + L * math.cos(rad),
                          cursor[1] + L * math.sin(rad))
                else:
                    p2 = p2_raw  # angulo raw: se reporta para revision manual
                    segmentos_raw = segmentos_raw + 1
            if es_ultimo_h:
                # cierre exacto en B; si el tramo final no es angulo valido, se
                # divide en un codo en L (dos segmentos validos) para no dejar
                # diagonales de fabricacion.
                if dist2d(cursor, p2_raw) > 0.01:
                    af, _ = angulo_valido(math.degrees(math.atan2(p2_raw[1]-cursor[1], p2_raw[0]-cursor[0])))
                    if not af:
                        intermedio = (p2_raw[0], cursor[1])
                        tramos.append(mk_tramo(cursor[0], cursor[1], Z_PLANO_MM,
                                               intermedio[0], intermedio[1], Z_PLANO_MM,
                                               type_id, es_comms, 0))
                        cursor = intermedio
                p2 = p2_raw
            tramos.append(mk_tramo(cursor[0], cursor[1], Z_PLANO_MM,
                                   p2[0], p2[1], Z_PLANO_MM,
                                   type_id, es_comms, segmentos_raw))
            cursor = p2
        tramos.append(mk_tramo(m_b["revit_x"], m_b["revit_y"], Z_PLANO_MM,
                               m_b["revit_x"], m_b["revit_y"], z_b,
                               type_id, es_comms, segmentos_raw))
    return tramos


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
