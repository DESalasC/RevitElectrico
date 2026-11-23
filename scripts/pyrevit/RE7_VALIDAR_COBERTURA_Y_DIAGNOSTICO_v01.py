# -*- coding: utf-8 -*-
"""
RE7_VALIDAR_COBERTURA_Y_DIAGNOSTICO_v01.py

SOLO LECTURA (no abre transacciones, no modifica el modelo).

Parte A - Cobertura de la red de plenum de F17/F18:
  * localiza los risers (conduits verticales con extremo superior en Z=15930)
  * verifica que cada riser toque un tramo horizontal de plenum (<=20 mm)
  * verifica que el Punto de Consolidacion (CPB*BL) quede alcanzado
  * lista risers huerfanos y tramos sueltos

Parte B - Diagnostico de la fuente de apartamento para el resto:
  * de los dispositivos sin Mark, cuantos tienen circuito electrico asignado
    (panel + numero de circuito) y por tanto pueden heredar el apartamento
    del tablero, sin usar zonas geograficas
  * resumen por categoria y por panel

Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import math
import os
import sys
import traceback
from collections import defaultdict

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    XYZ,
)

VERSION = "v01_validacion"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
Z_TOL_MM = 25.0
TOL_CONTACTO_MM = 20.0
RADIO_RISER_MM = 300.0

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]


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


def obtener_doc():
    try:
        app = __revit__
        if app is not None and hasattr(app, "ActiveUIDocument"):
            return app.ActiveUIDocument.Document
    except Exception:
        pass
    try:
        from pyrevit import revit as _revit
        if getattr(_revit, "doc", None) is not None:
            return _revit.doc
    except Exception:
        pass
    return None


def id_de(el):
    v = el.Id
    if hasattr(v, "IntegerValue"):
        return int(v.IntegerValue)
    return int(v.Value)


def punto_real(el):
    loc = el.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        return [p.X * FT_A_MM, p.Y * FT_A_MM, p.Z * FT_A_MM]
    if isinstance(loc, LocationCurve):
        c = loc.Curve
        p0 = c.GetEndPoint(0)
        p1 = c.GetEndPoint(1)
        return [
            0.5 * (p0.X + p1.X) * FT_A_MM,
            0.5 * (p0.Y + p1.Y) * FT_A_MM,
            0.5 * (p0.Z + p1.Z) * FT_A_MM,
        ]
    return None


def extremos_conduit(el):
    try:
        loc = el.Location
        if not isinstance(loc, LocationCurve):
            return None
        c = loc.Curve
        e0 = c.GetEndPoint(0)
        e1 = c.GetEndPoint(1)
        return (
            [e0.X * FT_A_MM, e0.Y * FT_A_MM, e0.Z * FT_A_MM],
            [e1.X * FT_A_MM, e1.Y * FT_A_MM, e1.Z * FT_A_MM],
        )
    except Exception:
        return None


def valor_texto(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None:
                s = p.AsString()
                if s:
                    return s
        except Exception:
            pass
    return None


def valor_param_bip(el, bip):
    try:
        p = el.get_Parameter(bip)
        if p is not None:
            return p.AsString()
    except Exception:
        pass
    return None


def familia_tipo(el):
    try:
        sym = el.Symbol
        if sym is not None:
            pname = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if pname is not None:
                return "%s | %s" % (el.Category.Name, pname.AsString())
    except Exception:
        pass
    try:
        return el.Category.Name
    except Exception:
        return "?"


def dist2d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def dist_punto_segmento_2d(px, py, ax, ay, bx, by):
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    l2 = vx * vx + vy * vy
    if l2 < 1e-9:
        return math.sqrt(wx * wx + wy * wy)
    t = (wx * vx + wy * vy) / l2
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    cx = ax + t * vx
    cy = ay + t * vy
    return math.sqrt((px - cx) ** 2 + (py - cy) ** 2)


def circuitos_de(el):
    """Devuelve lista de (panel, numero) de los circuitos asignados."""
    out = []
    panel = valor_param_bip(el, BuiltInParameter.RBS_ELEC_CIRCUIT_PANEL_PARAM)
    numero = valor_param_bip(el, BuiltInParameter.RBS_ELEC_CIRCUIT_NUMBER)
    if panel or numero:
        out.append((panel or "", numero or ""))
    try:
        mep = el.MEPModel
        if mep is not None and hasattr(mep, "GetAssignedElectricalSystems"):
            sistemas = mep.GetAssignedElectricalSystems()
            if sistemas is not None:
                for s in sistemas:
                    try:
                        pn = s.PanelName
                    except Exception:
                        pn = None
                    try:
                        cn = s.CircuitNumber
                    except Exception:
                        cn = None
                    par = (pn or "", cn or "")
                    if par not in out:
                        out.append(par)
    except Exception:
        pass
    return out


def main():
    log("=" * 70)
    log("RE7_VALIDAR_COBERTURA_Y_DIAGNOSTICO_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    # ---------- Recolectar conduits ----------
    verticales = []
    horizontales = []
    otros = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        par = extremos_conduit(el)
        if par is None:
            continue
        e0, e1 = par
        cid = id_de(el)
        dx = abs(e0[0] - e1[0])
        dy = abs(e0[1] - e1[1])
        if dx <= 2.0 and dy <= 2.0:
            verticales.append({"cid": cid, "x": e0[0], "y": e0[1],
                               "z0": min(e0[2], e1[2]), "z1": max(e0[2], e1[2])})
        elif abs(e0[2] - Z_PLENUM_MM) <= Z_TOL_MM and abs(e1[2] - Z_PLENUM_MM) <= Z_TOL_MM:
            horizontales.append({"cid": cid, "a": e0, "b": e1})
        else:
            otros.append({"cid": cid, "a": e0, "b": e1})

    log("Conduits: %d verticales | %d horizontales en plenum | %d otros" % (
        len(verticales), len(horizontales), len(otros)))

    # ---------- Dispositivos ----------
    dispositivos = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto_real(el)
            if pt is None:
                continue
            dispositivos.append({
                "el": el,
                "id": id_de(el),
                "pt": pt,
                "mark": valor_texto(el, ["Mark"]),
                "familia": familia_tipo(el),
            })

    def apto_de_mark(mk):
        if mk and "|" in mk:
            return mk.split("|")[0]
        return None

    por_apto = defaultdict(list)
    sin_mark = []
    for d in dispositivos:
        a = apto_de_mark(d["mark"])
        if a:
            por_apto[a].append(d)
        else:
            sin_mark.append(d)

    # ---------- PARTE A: cobertura F17/F18 ----------
    log("")
    log("-" * 70)
    log("PARTE A - COBERTURA DE RED EN PLENUM")
    cobertura = {}
    for apto in ["F17", "F18"]:
        disp = por_apto.get(apto, [])
        if not disp:
            log("%s: sin dispositivos con Mark" % apto)
            continue
        cp = None
        for d in disp:
            if "CPB" in d["familia"].upper():
                if cp is None or d["pt"][2] > cp[2]:
                    cp = d["pt"]
        # risers del apartamento
        risers = []
        for v in verticales:
            if abs(v["z1"] - Z_PLENUM_MM) > Z_TOL_MM:
                continue
            mejor = None
            mejor_d = None
            for d in disp:
                dd = dist2d([v["x"], v["y"]], [d["pt"][0], d["pt"][1]])
                if mejor_d is None or dd < mejor_d:
                    mejor_d = dd
                    mejor = d
            if mejor is not None and mejor_d <= RADIO_RISER_MM:
                risers.append({"v": v, "dist": mejor_d, "disp": mejor["id"]})

        huerfanos = []
        conectados = 0
        for r in risers:
            v = r["v"]
            tocado = False
            for h in horizontales:
                d = dist_punto_segmento_2d(
                    v["x"], v["y"], h["a"][0], h["a"][1], h["b"][0], h["b"][1])
                if d <= TOL_CONTACTO_MM:
                    tocado = True
                    break
            if tocado:
                conectados += 1
            else:
                huerfanos.append({"cid": v["cid"], "x": round(v["x"], 1),
                                  "y": round(v["y"], 1),
                                  "disp": r["disp"],
                                  "dist_disp": round(r["dist"], 1)})

        cp_ok = None
        cp_dist = None
        if cp is not None:
            mejor = None
            for h in horizontales:
                d = dist_punto_segmento_2d(
                    cp[0], cp[1], h["a"][0], h["a"][1], h["b"][0], h["b"][1])
                if mejor is None or d < mejor:
                    mejor = d
            cp_dist = mejor
            cp_ok = (mejor is not None and mejor <= TOL_CONTACTO_MM)

        cobertura[apto] = {
            "dispositivos": len(disp),
            "risers": len(risers),
            "risers_conectados": conectados,
            "risers_huerfanos": len(huerfanos),
            "cp": [round(cp[0], 1), round(cp[1], 1)] if cp else None,
            "cp_alcanzado": cp_ok,
            "cp_dist_mm": round(cp_dist, 1) if cp_dist is not None else None,
            "huerfanos": huerfanos,
        }
        log("%s: %d disp | %d risers | conectados=%d | huerfanos=%d | CP=%s alcanzado=%s (d=%s mm)" % (
            apto, len(disp), len(risers), conectados, len(huerfanos),
            cobertura[apto]["cp"], cp_ok, cobertura[apto]["cp_dist_mm"]))
        for hu in huerfanos[:15]:
            log("   HUERFANO riser %s (%.1f,%.1f) disp=%s d=%.1f" % (
                hu["cid"], hu["x"], hu["y"], hu["disp"], hu["dist_disp"]))
        if len(huerfanos) > 15:
            log("   ... y %d mas" % (len(huerfanos) - 15))

    # ---------- PARTE B: diagnostico de apartamento ----------
    log("")
    log("-" * 70)
    log("PARTE B - FUENTE DE APARTAMENTO PARA LOS DISPOSITIVOS SIN MARK")
    log("Dispositivos totales: %d | con Mark: %d | sin Mark: %d" % (
        len(dispositivos), len(dispositivos) - len(sin_mark), len(sin_mark)))

    con_circuito = 0
    sin_circuito = 0
    por_panel = defaultdict(int)
    sin_circuito_ejemplos = []
    for d in sin_mark:
        cs = circuitos_de(d["el"])
        cs_validos = [c for c in cs if c[0] or c[1]]
        if cs_validos:
            con_circuito += 1
            for (pn, cn) in cs_validos:
                por_panel[pn or "(sin panel)"] += 1
        else:
            sin_circuito += 1
            if len(sin_circuito_ejemplos) < 20:
                sin_circuito_ejemplos.append({
                    "id": d["id"], "familia": d["familia"],
                    "pt": [round(v, 1) for v in d["pt"]],
                })

    log("Sin Mark con circuito asignado: %d" % con_circuito)
    log("Sin Mark SIN circuito: %d" % sin_circuito)
    log("")
    if por_panel:
        log("Paneles detectados en dispositivos sin Mark (top 25):")
        for pn in sorted(por_panel.keys(), key=lambda k: -por_panel[k])[:25]:
            log("   %-22s %d" % (pn, por_panel[pn]))
    log("")
    if sin_circuito_ejemplos:
        log("Ejemplos sin circuito (20):")
        for e in sin_circuito_ejemplos:
            log("   id=%s [%s] %s" % (e["id"], e["familia"], e["pt"]))

    # conteo por categoria de los sin mark
    cat_sin = defaultdict(int)
    for d in sin_mark:
        cat_sin[d["familia"].split(" | ")[0]] += 1
    log("")
    log("Sin Mark por categoria:")
    for c in sorted(cat_sin.keys(), key=lambda kk: -cat_sin[kk]):
        log("   %-30s %d" % (c, cat_sin[c]))

    # ---------- Reporte ----------
    raiz = _raiz()
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "conduits": {
            "verticales": len(verticales),
            "horizontales_plenum": len(horizontales),
            "otros": len(otros),
        },
        "cobertura": cobertura,
        "diagnostico_apartamento": {
            "dispositivos_totales": len(dispositivos),
            "con_mark": len(dispositivos) - len(sin_mark),
            "sin_mark": len(sin_mark),
            "sin_mark_con_circuito": con_circuito,
            "sin_mark_sin_circuito": sin_circuito,
            "por_panel": dict(por_panel),
            "sin_mark_por_categoria": dict(cat_sin),
            "ejemplos_sin_circuito": sin_circuito_ejemplos,
        },
    }
    out_path = os.path.join(raiz, "data", "f7_validacion_cobertura_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=2))
        log("")
        log("JSON guardado: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    log("=" * 70)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
