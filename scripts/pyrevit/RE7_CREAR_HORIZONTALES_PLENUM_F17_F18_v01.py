# -*- coding: utf-8 -*-
"""
RE7_CREAR_HORIZONTALES_PLENUM_F17_F18_v01.py

Crea los conduits HORIZONTALES de plenum (Z=15930) de F17 y F18 en
CENTRAL-V01c, conectando los risers verticales ya creados con el Punto
de Consolidacion (CP) de cada apartamento.

Topologia "peine" (comb), toda a 90 grados:
  1. Se agrupan los risers por su coordenada Y (tolerancia 5 mm).
  2. Por cada grupo Y se crea un tramo en X, a esa Y y en el plenum,
     desde el riser mas alejado del CP hasta la X del CP.
  3. Se crea un troncal en Y, a la X del CP, que une todos los grupos
     y alcanza la Y del CP.
  Resultado: red ortogonal sin diagonales, con tramos compartidos en vez
  de un L por dispositivo (menos solape y menos metros de tubo).

El CP se localiza por familia de datos tipo CPB*BL (Consolidation Point).
Si no se encuentra, se usa la mediana XY de los dispositivos del apto.

Limpieza previa: borra solo horizontales de plenum (ambos extremos a
Z ~ 15930, no verticales) cuyo punto medio cae en el bbox del apartamento.

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

VERSION = "v01_horiz_plenum"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
Z_TOL_MM = 25.0            # tolerancia para considerar un tramo "en plenum"
VERIF_TOL_MM = 10.0
LARGO_MIN_MM = 5.0
TOL_GRUPO_Y_MM = 5.0       # agrupar risers con Y casi igual
RADIO_RISER_MM = 300.0     # un riser pertenece al dispositivo si esta a <300 mm XY
MARGEN_BBOX_MM = 1500.0    # margen para la limpieza de horizontales previos

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]

TUBO_E_ID = 112216


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


def obtener_parametro(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None:
                return p
        except Exception:
            continue
    return None


def valor_texto(el, nombres):
    p = obtener_parametro(el, nombres)
    if p is not None:
        try:
            return p.AsString()
        except Exception:
            return None
    return None


def familia_tipo(el):
    try:
        sym = el.Symbol
        if sym is not None:
            from Autodesk.Revit.DB import BuiltInParameter
            pname = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if pname is not None:
                nom = pname.AsString()
            else:
                nom = str(sym.Id)
            return "%s | %s" % (el.Category.Name, nom)
    except Exception:
        pass
    return el.Category.Name


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz_mm(x_mm, y_mm, z_mm):
    return XYZ(mm_a_ft(x_mm), mm_a_ft(y_mm), mm_a_ft(z_mm))


def dist3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def dist2d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


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


def mediana(valores):
    v = sorted(valores)
    n = len(v)
    if n == 0:
        return None
    if n % 2 == 1:
        return v[n // 2]
    return 0.5 * (v[n // 2 - 1] + v[n // 2])


def leer_dispositivos(doc, apto):
    """Dispositivos del apartamento segun Mark (apto|tablero|circuito)."""
    out = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            mark = valor_texto(el, ["Mark"])
            if not mark or "|" not in mark:
                continue
            if mark.split("|")[0] != apto:
                continue
            pt = punto_real(el)
            if pt is None:
                continue
            out.append({
                "id": id_de(el),
                "pt": pt,
                "mark": mark,
                "familia": familia_tipo(el),
            })
    return out


def localizar_cp(dispositivos, apto):
    """CP = dispositivo cuya familia contiene 'CPB'. Si no, mediana XY."""
    candidatos = [d for d in dispositivos if "CPB" in d["familia"].upper()]
    if candidatos:
        # el de mayor Z (plenum) y, en empate, el mas centrico
        candidatos.sort(key=lambda d: d["pt"][2], reverse=True)
        cp = candidatos[0]
        return cp["pt"][0], cp["pt"][1], "familia CPB (%s)" % cp["familia"]
    mx = mediana([d["pt"][0] for d in dispositivos])
    my = mediana([d["pt"][1] for d in dispositivos])
    return mx, my, "mediana (sin CPB)"


def leer_risers(doc, dispositivos):
    """Conduits verticales con extremo superior en plenum, cerca de un dispositivo."""
    risers = []
    sin_match = 0
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        par = extremos_conduit(el)
        if par is None:
            continue
        e0, e1 = par
        if abs(e0[0] - e1[0]) > 2.0 or abs(e0[1] - e1[1]) > 2.0:
            continue  # no vertical
        z_top = max(e0[2], e1[2])
        if abs(z_top - Z_PLENUM_MM) > Z_TOL_MM:
            continue
        x, y = e0[0], e0[1]
        mejor = None
        mejor_d = None
        for d in dispositivos:
            dd = dist2d([x, y], [d["pt"][0], d["pt"][1]])
            if mejor_d is None or dd < mejor_d:
                mejor_d = dd
                mejor = d
        if mejor is None or mejor_d > RADIO_RISER_MM:
            sin_match += 1
            continue
        risers.append({
            "cid": id_de(el),
            "x": x,
            "y": y,
            "dispositivo_id": mejor["id"],
            "familia": mejor["familia"],
            "dist_mm": round(mejor_d, 1),
        })
    return risers, sin_match


def crear_conduit(doc, nivel_id, a, b, etiqueta):
    if dist3d(a, b) < LARGO_MIN_MM:
        return False, None, "largo<min"
    try:
        conduit = Conduit.Create(
            doc, ElementId(Int64(TUBO_E_ID)),
            xyz_mm(a[0], a[1], a[2]),
            xyz_mm(b[0], b[1], b[2]),
            ElementId(Int64(nivel_id)))
        cid = id_de(conduit)
        loc = conduit.Location
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            e0 = c.GetEndPoint(0)
            e1 = c.GetEndPoint(1)
            ra = [e0.X * FT_A_MM, e0.Y * FT_A_MM, e0.Z * FT_A_MM]
            rb = [e1.X * FT_A_MM, e1.Y * FT_A_MM, e1.Z * FT_A_MM]
            da = dist3d(ra, a)
            db = dist3d(rb, b)
            if da > VERIF_TOL_MM or db > VERIF_TOL_MM:
                return True, cid, "verif da=%.1f db=%.1f" % (da, db)
        return True, cid, None
    except Exception as e:
        return False, None, str(e)[:160]


def agrupar_por_y(risers):
    """Agrupa risers por Y (tolerancia TOL_GRUPO_Y_MM). Devuelve lista de grupos."""
    grupos = []
    for r in sorted(risers, key=lambda it: it["y"]):
        colocado = False
        for g in grupos:
            if abs(g["y"] - r["y"]) <= TOL_GRUPO_Y_MM:
                g["items"].append(r)
                g["y"] = sum(i["y"] for i in g["items"]) / len(g["items"])
                colocado = True
                break
        if not colocado:
            grupos.append({"y": r["y"], "items": [r]})
    return grupos


def construir_red(risers, cp_x, cp_y):
    """Devuelve lista de tramos (a, b, etiqueta) en peine hacia el CP."""
    tramos = []
    grupos = agrupar_por_y(risers)
    ys_grupos = []

    for g in grupos:
        y = g["y"]
        ys_grupos.append(y)
        xs = [it["x"] for it in g["items"]]
        x_min = min(xs)
        x_max = max(xs)

        # El tramo en X debe cubrir TODOS los risers del grupo y alcanzar la X
        # del CP. Si el CP cae entre las X, basta con unir x_min..x_max (ese
        # tramo pasa sobre el CP).
        if cp_x <= x_min:
            xa, xb = x_max, cp_x
        elif cp_x >= x_max:
            xa, xb = x_min, cp_x
        else:
            xa, xb = x_min, x_max

        if abs(xb - xa) < LARGO_MIN_MM:
            continue

        tramos.append({
            "a": [xa, y, Z_PLENUM_MM],
            "b": [xb, y, Z_PLENUM_MM],
            "tipo": "X",
            "y": round(y, 1),
            "n_risers": len(g["items"]),
        })

    # Troncal en Y a la X del CP, cubriendo todos los grupos y la Y del CP
    if ys_grupos:
        y_lo = min(min(ys_grupos), cp_y)
        y_hi = max(max(ys_grupos), cp_y)
        if abs(y_hi - y_lo) > LARGO_MIN_MM:
            tramos.append({
                "a": [cp_x, y_lo, Z_PLENUM_MM],
                "b": [cp_x, y_hi, Z_PLENUM_MM],
                "tipo": "Y_troncal",
                "n_risers": 0,
            })
    return tramos, grupos


def main():
    log("=" * 70)
    log("RE7_CREAR_HORIZONTALES_PLENUM_F17_F18_%s" % VERSION)
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
    log("nivel: {!r} id={}".format(nivel.Name, nivel_id))

    plan = {}
    resumen = {}
    fallos_detalle = []
    total_tramos = 0
    total_ok = 0
    total_fallos = 0
    total_borrados = 0

    # --- Recolectar por apartamento ---
    por_apto = {}
    for apto in ["F17", "F18"]:
        disp = leer_dispositivos(doc, apto)
        if not disp:
            log("ERROR %s: sin dispositivos con Mark %s|..." % (apto, apto))
            return 1
        cp_x, cp_y, cp_origen = localizar_cp(disp, apto)
        log("%s: %d dispositivos | CP=(%.1f,%.1f) via %s" % (
            apto, len(disp), cp_x, cp_y, cp_origen))
        por_apto[apto] = {"disp": disp, "cp": (cp_x, cp_y), "cp_origen": cp_origen}

    # --- Limpieza de horizontales previos (por bbox de cada apto) ---
    trans_borrado = Transaction(doc, "RE7_LIMPIAR_HORIZONTALES_F17_F18_v01")
    trans_borrado.Start()
    borrados_total = 0
    for apto in ["F17", "F18"]:
        disp = por_apto[apto]["disp"]
        xs = [d["pt"][0] for d in disp]
        ys = [d["pt"][1] for d in disp]
        bbox = (min(xs) - MARGEN_BBOX_MM, max(xs) + MARGEN_BBOX_MM,
                min(ys) - MARGEN_BBOX_MM, max(ys) + MARGEN_BBOX_MM)
        # se borra dentro de la misma transaccion
        xmin, xmax, ymin, ymax = bbox
        for el in FilteredElementCollector(doc).OfCategory(
                BuiltInCategory.OST_Conduit).ToElements():
            par = extremos_conduit(el)
            if par is None:
                continue
            e0, e1 = par
            if abs(e0[2] - Z_PLENUM_MM) > Z_TOL_MM or abs(e1[2] - Z_PLENUM_MM) > Z_TOL_MM:
                continue
            if abs(e0[0] - e1[0]) <= 2.0 and abs(e0[1] - e1[1]) <= 2.0:
                continue
            mx = 0.5 * (e0[0] + e1[0])
            my = 0.5 * (e0[1] + e1[1])
            if xmin <= mx <= xmax and ymin <= my <= ymax:
                try:
                    doc.Delete(el.Id)
                    borrados_total += 1
                except Exception:
                    pass
    trans_borrado.Commit()
    log("Horizontales previos borrados: %d" % borrados_total)

    # --- Construccion de la red ---
    trans = Transaction(doc, "RE7_CREAR_HORIZONTALES_PLENUM_F17_F18_v01")
    trans.Start()
    try:
        for apto in ["F17", "F18"]:
            info = por_apto[apto]
            risers, sin_match = leer_risers(doc, info["disp"])
            log("%s: %d risers en plenum (%d verticales ajenos ignorados)" % (
                apto, len(risers), sin_match))
            if not risers:
                resumen[apto] = {"risers": 0, "tramos": 0, "error": "sin risers"}
                continue

            cp_x, cp_y = info["cp"]
            tramos, grupos = construir_red(risers, cp_x, cp_y)
            log("%s: %d grupos Y -> %d tramos a crear" % (apto, len(grupos), len(tramos)))

            ok_cnt = 0
            fail_cnt = 0
            for t in tramos:
                etiqueta = "%s horiz %s y=%.0f" % (apto, t["tipo"], t.get("y", cp_y))
                ok, cid, err = crear_conduit(doc, nivel_id, t["a"], t["b"], etiqueta)
                total_tramos += 1
                if ok and err is None:
                    ok_cnt += 1
                    total_ok += 1
                else:
                    fail_cnt += 1
                    total_fallos += 1
                    fallos_detalle.append({
                        "apto": apto, "tipo": t["tipo"],
                        "a": [round(v, 1) for v in t["a"]],
                        "b": [round(v, 1) for v in t["b"]],
                        "err": err, "cid": cid,
                    })
                    log("  FALLO %s: %s" % (etiqueta, err))

            resumen[apto] = {
                "dispositivos": len(info["disp"]),
                "risers": len(risers),
                "risers_sin_match": sin_match,
                "grupos_y": len(grupos),
                "tramos_ok": ok_cnt,
                "tramos_fallo": fail_cnt,
                "cp": [round(cp_x, 1), round(cp_y, 1)],
                "cp_origen": info["cp_origen"],
            }
            plan[apto] = {
                "cp": [round(cp_x, 1), round(cp_y, 1)],
                "grupos": [{"y": round(g["y"], 1),
                            "n": len(g["items"]),
                            "xs": [round(i["x"], 1) for i in g["items"]]}
                           for g in grupos],
                "tramos": [{"a": [round(v, 1) for v in t["a"]],
                            "b": [round(v, 1) for v in t["b"]],
                            "tipo": t["tipo"]} for t in tramos],
            }

        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida, no se creo nada.")
        log(traceback.format_exc())
        return 1

    # --- Conteo final ---
    total_conduits = len(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Conduit).ToElements())

    raiz = _raiz()
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "horizontales_previos_borrados": borrados_total,
            "tramos_intentados": total_tramos,
            "tramos_ok": total_ok,
            "tramos_fallo": total_fallos,
            "conduits_totales_documento": total_conduits,
            "por_apartamento": resumen,
        },
        "fallos": fallos_detalle,
        "plan": plan,
    }
    out_path = os.path.join(raiz, "data", "f7_horizontales_resultado_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=2))
        log("JSON guardado: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    log("")
    log("=" * 70)
    log("RESULTADO")
    log("  horizontales previos borrados: %d" % borrados_total)
    log("  tramos: %d intentados | %d OK | %d fallos" % (
        total_tramos, total_ok, total_fallos))
    log("  conduits totales en el documento: %d" % total_conduits)
    for apto in ["F17", "F18"]:
        r = resumen.get(apto, {})
        log("  %s: risers=%s grupos=%s tramos_ok=%s cp=%s" % (
            apto, r.get("risers"), r.get("grupos_y"),
            r.get("tramos_ok"), r.get("cp")))
    log("=" * 70)
    return 0 if total_fallos == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
