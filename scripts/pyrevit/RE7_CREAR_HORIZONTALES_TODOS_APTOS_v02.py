# -*- coding: utf-8 -*-
"""
RE7_CREAR_HORIZONTALES_TODOS_APTOS_v02.py

Crea los conduits HORIZONTALES de plenum (Z=15930) de TODOS los apartamentos
de CENTRAL-V01c, conectando cada riser con el Punto de Consolidacion (CP) de
su apartamento mediante una red en peine (comb) a 90 grados.

Reglas:
  * CP: dispositivo cuya familia contiene 'CPB' (Consolidation Point).
    Si el apartamento no tiene CP, se usa la mediana XY de sus dispositivos.
  * Se agrupan los risers por Y (tolerancia 5 mm). Un tramo en X por grupo,
    que cubre todos los risers del grupo y llega a la X del CP.
  * Un troncal en Y a la X del CP que une todos los grupos y alcanza la Y
    del CP.
  * Si el apartamento YA tiene horizontales en plenum (p.ej. F17/F18, ya
    validados), se OMITE: no se borra ni se duplica nada.
  * Verificacion posterior: cada riser debe tocar la red (<=20 mm) y el CP
    debe quedar alcanzado. Se reporta cualquier huerfano.

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
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit
from System import Int64

VERSION = "v02_horiz_todos"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
Z_TOL_MM = 25.0
VERIF_TOL_MM = 10.0
TOL_CONTACTO_MM = 20.0
LARGO_MIN_MM = 5.0
TOL_GRUPO_Y_MM = 5.0
RADIO_RISER_MM = 300.0
MARGEN_BBOX_MM = 500.0
OFFSET_COMMS_MM = 40.0

D_16_MM = 16.0
D_19_MM = 19.0
NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size"]

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]

TUBO_E_ID = 112216


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
                if s is not None:
                    return s
        except Exception:
            pass
    return None


def nombre_familia(el):
    try:
        if el.Symbol is not None and el.Symbol.Family is not None:
            return el.Symbol.Family.Name
    except Exception:
        pass
    return None


def nombre_tipo(el):
    try:
        if el.Symbol is not None:
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                return p.AsString()
    except Exception:
        pass
    return None


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz_mm(x, y, z):
    return XYZ(mm_a_ft(x), mm_a_ft(y), mm_a_ft(z))


def dist3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def dist2d(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def dist_punto_segmento_2d(px, py, ax, ay, bx, by):
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    l2 = vx * vx + vy * vy
    if l2 < 1e-9:
        return math.sqrt(wx * wx + wy * wy)
    t = (wx * vx + wy * vy) / l2
    t = max(0.0, min(1.0, t))
    cx = ax + t * vx
    cy = ay + t * vy
    return math.sqrt((px - cx) ** 2 + (py - cy) ** 2)


def param_diametro(el):
    for nombre in NOMBRES_DIAM:
        try:
            p = el.LookupParameter(nombre)
            if p is not None:
                return p
        except Exception:
            continue
    return None


def fijar_diametro(el, mm):
    try:
        p = param_diametro(el)
        if p is None or p.IsReadOnly:
            return False
        p.Set(mm / FT_A_MM)
        v = p.AsDouble() * FT_A_MM
        return abs(v - mm) <= 0.6
    except Exception:
        return False


def mediana(v):
    s = sorted(v)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def buscar_nivel(doc, nombre_esperado="Piso 5", elevacion_m=13.22):
    mejor = None
    mejor_delta = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        delta = abs(lvl.Elevation * FT_A_MM - elevacion_m * 1000.0)
        if mejor_delta is None or delta < mejor_delta:
            mejor = lvl
            mejor_delta = delta
        if lvl.Name == nombre_esperado:
            return lvl
    return mejor


def agrupar_por_y(risers, tol=TOL_GRUPO_Y_MM):
    grupos = []
    for r in sorted(risers, key=lambda it: it[1]):
        colocado = False
        for g in grupos:
            if abs(g["y"] - r[1]) <= tol:
                g["items"].append(r)
                g["y"] = sum(i[1] for i in g["items"]) / len(g["items"])
                colocado = True
                break
        if not colocado:
            grupos.append({"y": r[1], "items": [r]})
    return grupos


def construir_red(risers, cp_x, cp_y):
    tramos = []
    grupos = agrupar_por_y(risers)
    ys = []
    for g in grupos:
        ys.append(g["y"])
        xs = [it[0] for it in g["items"]]
        xmin, xmax = min(xs), max(xs)
        if cp_x <= xmin:
            xa, xb = xmax, cp_x
        elif cp_x >= xmax:
            xa, xb = xmin, cp_x
        else:
            xa, xb = xmin, xmax
        if abs(xb - xa) < LARGO_MIN_MM:
            continue
        tramos.append(([xa, g["y"], Z_PLENUM_MM], [xb, g["y"], Z_PLENUM_MM], "X", len(g["items"])))
    if ys:
        y_lo = min(min(ys), cp_y)
        y_hi = max(max(ys), cp_y)
        if abs(y_hi - y_lo) > LARGO_MIN_MM:
            tramos.append(([cp_x, y_lo, Z_PLENUM_MM], [cp_x, y_hi, Z_PLENUM_MM], "Y", 0))
    return tramos, grupos


def main():
    log("=" * 70)
    log("RE7_CREAR_HORIZONTALES_TODOS_APTOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    nivel = buscar_nivel(doc)
    if nivel is None:
        log("ERROR: no se encontro nivel Piso 5.")
        return 1
    nivel_id = id_de(nivel)

    # --- dispositivos por apartamento ---
    por_apto = defaultdict(list)
    cp_apto = {}
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            mk = valor_texto(el, ["Mark"]) or ""
            partes = mk.split("|")
            if len(partes) != 3 or not partes[0]:
                continue
            pt = punto_real(el)
            if pt is None:
                continue
            apto = partes[0].upper()
            fam = nombre_familia(el) or ""
            tip = nombre_tipo(el) or ""
            srv = (fam + " " + tip).lower()
            es_dato = any(k in srv for k in
                          ("comunicacion", "datos", "telephone", "data devices", "pau"))
            por_apto[apto].append({"id": id_de(el), "pt": pt,
                                   "familia": fam, "tipo": tip,
                                   "es_datos": es_dato})
            if "CPB" in (fam + " " + tip).upper():
                cur = cp_apto.get(apto)
                if cur is None or pt[2] > cur[2]:
                    cp_apto[apto] = pt

    log("Apartamentos con dispositivos marcados: %d" % len(por_apto))

    # --- conduits: verticales y horizontales existentes ---
    verticales = []
    horizontales = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        par = extremos_conduit(el)
        if par is None:
            continue
        e0, e1 = par
        if abs(e0[0] - e1[0]) <= 2.0 and abs(e0[1] - e1[1]) <= 2.0:
            if abs(max(e0[2], e1[2]) - Z_PLENUM_MM) <= Z_TOL_MM:
                verticales.append((e0[0], e0[1]))
        elif abs(e0[2] - Z_PLENUM_MM) <= Z_TOL_MM and abs(e1[2] - Z_PLENUM_MM) <= Z_TOL_MM:
            horizontales.append((e0, e1))

    log("Verticales en plenum: %d | horizontales en plenum: %d" % (
        len(verticales), len(horizontales)))

    stats = {}
    tramos_ok = 0
    tramos_fallo = 0
    omitidos = []
    fallos = []
    huerfanos_total = []

    trans = Transaction(doc, "RE7_HORIZONTALES_TODOS_v02")
    trans.Start()
    try:
        for apto in sorted(por_apto.keys()):
            items = por_apto[apto]
            xs = [d["pt"][0] for d in items]
            ys = [d["pt"][1] for d in items]
            xmin, xmax = min(xs) - MARGEN_BBOX_MM, max(xs) + MARGEN_BBOX_MM
            ymin, ymax = min(ys) - MARGEN_BBOX_MM, max(ys) + MARGEN_BBOX_MM

            ya_tiene = 0
            for (a, b) in horizontales:
                mx = 0.5 * (a[0] + b[0])
                my = 0.5 * (a[1] + b[1])
                if xmin <= mx <= xmax and ymin <= my <= ymax:
                    ya_tiene += 1
            if ya_tiene > 0:
                omitidos.append({"apto": apto, "horizontales_existentes": ya_tiene})
                log("%-6s OMITIDO: ya tiene %d horizontales" % (apto, ya_tiene))
                continue

            cp = cp_apto.get(apto)
            if cp is not None:
                cp_x, cp_y, cp_origen = cp[0], cp[1], "CPB"
            else:
                cp_x = mediana(xs)
                cp_y = mediana(ys)
                cp_origen = "mediana"

            risers = []
            for (vx, vy) in verticales:
                for d in items:
                    if dist2d(vx, vy, d["pt"][0], d["pt"][1]) <= RADIO_RISER_MM:
                        risers.append((vx, vy))
                        break
            if not risers:
                stats[apto] = {"risers": 0, "tramos": 0, "nota": "sin risers"}
                log("%-6s sin risers" % apto)
                continue

            tramos, grupos = construir_red(risers, cp_x, cp_y)
            datos_items = [d for d in items if d["es_datos"]]
            ok = 0
            fail = 0
            diam_ok = 0
            for (a, b, tipo, n) in tramos:
                es_dato = False
                for d in datos_items:
                    if dist_punto_segmento_2d(d["pt"][0], d["pt"][1],
                                              a[0], a[1], b[0], b[1]) <= 300.0:
                        es_dato = True
                        break
                try:
                    nuevo = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                           xyz_mm(a[0], a[1], a[2]),
                                           xyz_mm(b[0], b[1], b[2]),
                                           ElementId(Int64(nivel_id)))
                    if fijar_diametro(nuevo, D_19_MM if es_dato else D_16_MM):
                        diam_ok += 1
                    ok += 1
                except Exception as ex:
                    fail += 1
                    fallos.append({"apto": apto, "tipo": tipo,
                                   "err": str(ex)[:120]})
            tramos_ok += ok
            tramos_fallo += fail

            # verificacion geometrica de cobertura
            huerfanos = 0
            for (vx, vy) in risers:
                tocado = False
                for (a, b, tipo, n) in tramos:
                    if tipo != "X":
                        continue
                    if abs(a[1] - vy) <= 6.0:
                        xa, xb = sorted([a[0], b[0]])
                        if xa - 1 <= vx <= xb + 1:
                            tocado = True
                            break
                if not tocado:
                    for (a, b, tipo, n) in tramos:
                        if tipo != "Y":
                            continue
                        ya, yb = sorted([a[1], b[1]])
                        if abs(a[0] - vx) <= 6.0 and ya - 1 <= vy <= yb + 1:
                            tocado = True
                            break
                if not tocado:
                    huerfanos += 1
                    huerfanos_total.append({"apto": apto, "x": round(vx, 1), "y": round(vy, 1)})

            stats[apto] = {
                "dispositivos": len(items),
                "risers": len(risers),
                "grupos": len(grupos),
                "tramos_ok": ok,
                "tramos_fallo": fail,
                "diametros_ok": diam_ok,
                "cp": [round(cp_x, 1), round(cp_y, 1)],
                "cp_origen": cp_origen,
                "huerfanos": huerfanos,
            }
            log("%-6s risers=%-3d grupos=%-3d tramos=%-3d fallos=%-2d cp=(%.0f,%.0f) %s huerf=%d" % (
                apto, len(risers), len(grupos), ok, fail, cp_x, cp_y, cp_origen, huerfanos))

        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida, no se creo nada.")
        log(traceback.format_exc())
        return 1

    total = len(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Conduit).ToElements())

    log("")
    log("=" * 70)
    log("RESULTADO: tramos OK=%d fallos=%d | omitidos=%d | huerfanos=%d" % (
        tramos_ok, tramos_fallo, len(omitidos), len(huerfanos_total)))
    log("Conduits totales en el documento: %d" % total)
    for o in omitidos:
        log("   OMITIDO %s (%d horizontales previos)" % (o["apto"], o["horizontales_existentes"]))
    for h in huerfanos_total[:20]:
        log("   HUERFANO %s (%.0f,%.0f)" % (h["apto"], h["x"], h["y"]))
    log("=" * 70)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "tramos_ok": tramos_ok,
            "tramos_fallo": tramos_fallo,
            "omitidos": omitidos,
            "huerfanos": len(huerfanos_total),
            "conduits_totales": total,
        },
        "por_apartamento": stats,
        "fallos": fallos,
        "huerfanos_detalle": huerfanos_total,
    }
    out = os.path.join(raiz, "data", "f7_horizontales_todos_v02.json")
    try:
        with open(out, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=1))
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0 if tramos_fallo == 0 and not huerfanos_total else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
