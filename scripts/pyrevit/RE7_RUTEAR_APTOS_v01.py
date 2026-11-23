# -*- coding: utf-8 -*-
"""
RE7_RUTEAR_APTOS_v01.py

Ruteo por apartamento con logica de red (no "un tubo por aparato"):

  1. Raiz: TABLERO del apartamento. Se coloca un CP (familia/tipo CPB*) en la
     vertical del tablero, a Z de plenum. Si no se puede colocar, se usa el
     punto del tablero como raiz conceptual y se reporta.
  2. Por cada aparato: bajante (riser) desde su Z hasta plenum, en su XY.
     * Datos/comunicaciones: 2 tubos separados 40 mm, uno por agrupacion.
     * Cocina: una vertical que pasa por nivel+700, +1050, +1650 y plenum,
       con un ramal en L hasta cada aparato a la altura del aparato.
  3. Horizontales en plenum: peine hacia la X del tablero/CP + troncal en Y.
  4. Diametros: 16 mm general, 19 mm en datos/comunicaciones.

Apartamentos por variable de entorno APTOS_RUTEO (coma separada). Default F01,F02.

Exporta lo creado a data/f7_ruteo_creado_<aptos>_v01.json para comparar.

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

VERSION = "v01_rutear_aptos"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
Z_TOL_MM = 25.0
LARGO_MIN_MM = 5.0
DEDUP_MM = 150.0
TOL_GRUPO_Y_MM = 5.0
OFFSET_COMMS_MM = 40.0
ALTURAS_COCINA_REL_MM = [700.0, 1050.0, 1650.0]

D_16_MM = 16.0
D_19_MM = 19.0
NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size"]

TUBO_E_ID = 112216

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]

# panel del DXF por apartamento (respaldo si no se encuentra en el modelo)
PANEL_DXF_MM = {
    "F01": (11602.7, 7497.0),
    "F02": (14041.0, 9649.0),
    "F17": (8814.1, 7512.3),
    "F18": (8784.4, 10158.3),
    "E05": (6512.9, 6863.2),
    "E06": (6515.6, 10803.7),
    "E07": (-5650.6, 7305.0),
    "E08": (-5650.6, 10385.3),
    "E07A": (-43087.7, 6851.0),
    "E08A": (-43108.3, 10783.8),
    "B15": (-46280.5, 8131.6),
    "B16": (-46342.4, 9566.7),
    "F01A": (-14369.4, 7513.8),
    "F01B": (-22119.6, 7513.8),
    "F17A": (-17125.9, 7522.4),
    "F18A": (-17108.0, 10168.0),
    "F02A": (-11849.0, 9650.0),
    "F02B": (-19649.0, 9674.0),
    "C14": (-29296.0, 5708.0),
    "D13": (-32161.0, 9675.0),
}


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


def punto(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            p = loc.Point
            return [p.X * FT_A_MM, p.Y * FT_A_MM, p.Z * FT_A_MM]
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            a = c.GetEndPoint(0)
            b = c.GetEndPoint(1)
            return [0.5 * (a.X + b.X) * FT_A_MM,
                    0.5 * (a.Y + b.Y) * FT_A_MM,
                    0.5 * (a.Z + b.Z) * FT_A_MM]
    except Exception:
        pass
    return None


def texto(el, nombres):
    for n in nombres:
        try:
            p = el.LookupParameter(n)
            if p is not None:
                s = p.AsString()
                if s is not None:
                    return s
        except Exception:
            pass
    return None


def fam_tipo(el):
    fam = tip = None
    try:
        if el.Symbol is not None:
            if el.Symbol.Family is not None:
                fam = el.Symbol.Family.Name
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                tip = p.AsString()
    except Exception:
        pass
    return fam, tip


def param_diam(el):
    for n in NOMBRES_DIAM:
        try:
            p = el.LookupParameter(n)
            if p is not None:
                return p
        except Exception:
            pass
    return None


def fijar_diam(el, mm):
    try:
        p = param_diam(el)
        if p is None or p.IsReadOnly:
            return False
        p.Set(mm / FT_A_MM)
        return abs(p.AsDouble() * FT_A_MM - mm) <= 0.6
    except Exception:
        return False


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz(x, y, z):
    return XYZ(mm_a_ft(x), mm_a_ft(y), mm_a_ft(z))


def d2(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def nivel_piso5(doc):
    mejor = None
    mejor_d = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        dd = abs(lvl.Elevation * FT_A_MM - 13220.0)
        if mejor_d is None or dd < mejor_d:
            mejor = lvl
            mejor_d = dd
    return mejor


def normaliza(s):
    return (s or "").upper().replace(" ", "").replace("-", "").replace("_", "")


def main():
    log("=" * 74)
    log("RE7_RUTEAR_APTOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    aptos_env = os.environ.get("APTOS_RUTEO", "").strip()
    aptos = [a.strip().upper() for a in aptos_env.split(",")] if aptos_env else ["F01", "F02"]
    log("documento=%r | apartamentos=%s" % (doc.Title, aptos))

    nivel = nivel_piso5(doc)
    if nivel is None:
        log("ERROR: no se encontro el nivel Piso 5.")
        return 1
    nivel_id = id_de(nivel)
    z_nivel = float(nivel.Elevation) * FT_A_MM
    log("nivel=%r id=%s elevacion=%.0f | plenum=%.0f" % (
        nivel.Name, nivel_id, z_nivel, Z_PLENUM_MM))

    # ---- tableros ----
    equipos = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_ElectricalEquipment).ToElements():
        pt = punto(el)
        fam, tip = fam_tipo(el)
        equipos.append({
            "id": id_de(el), "el": el, "pt": pt,
            "nombre": texto(el, ["Panel Name", "Name", "Panel"]),
            "mark": texto(el, ["Mark"]),
            "familia": fam, "tipo": tip,
        })
    log("equipos electricos en el modelo: %d" % len(equipos))
    for e in equipos:
        log("   id=%-9s mark=%-8r nombre=%-16r %s/%s pos=%s" % (
            e["id"], e["mark"], e["nombre"], e["familia"], e["tipo"],
            [round(v) for v in e["pt"]] if e["pt"] else None))

    # ---- dispositivos ----
    disp = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto(el)
            if pt is None:
                continue
            fam, tip = fam_tipo(el)
            mk = texto(el, ["Mark"]) or ""
            disp.append({"el": el, "id": id_de(el), "pt": pt, "mark": mk,
                         "familia": fam or "", "tipo": tip or "",
                         "comment": texto(el, ["Comments"]) or ""})
    log("dispositivos: %d" % len(disp))

    coc_ids = set()
    try:
        p = os.path.join(DEFAULT_ROOT, "data", "f7_cocinas_ids_v01.json")
        with open(p) as f:
            coc_ids = set(int(x) for x in json.load(f)["ids"])
    except Exception:
        pass
    log("ids de cocina cargados: %d" % len(coc_ids))

    creados = []
    tramos = 0
    fallos = []
    resumen = {}

    trans = Transaction(doc, "RE7_RUTEAR_APTOS_v01")
    trans.Start()
    try:
        for apto in aptos:
            items = [d for d in disp if d["mark"].startswith(apto + "|")]
            if not items:
                log("%s: SIN dispositivos marcados" % apto)
                resumen[apto] = {"error": "sin dispositivos"}
                continue

            # tablero: codigo esperado del panel (F01 -> TF01, E07A -> TE07A, B15 -> TB15)
            prefijo = {"F": "TF", "E": "TE", "B": "TB", "C": "TC", "D": "TD"}
            esperado = prefijo.get(apto[0], "TF") + apto[1:]
            cand = None
            for e in equipos:
                for campo in (e["mark"], e["nombre"], e["tipo"]):
                    n = normaliza(campo)
                    if n and (n == esperado or n.startswith(esperado)):
                        cand = e
                        break
                if cand is not None:
                    break

            if cand is not None and cand["pt"] is not None:
                cp_x, cp_y = cand["pt"][0], cand["pt"][1]
                origen_panel = "equipo %s (%s)" % (cand["nombre"], cand["mark"])
            elif apto in PANEL_DXF_MM:
                cp_x, cp_y = PANEL_DXF_MM[apto]
                origen_panel = "DXF TB-Panel"
            else:
                log("%s: no se pudo determinar el tablero" % apto)
                resumen[apto] = {"error": "sin tablero"}
                continue
            log("")
            log("%s: %d dispositivos | tablero=(%.0f,%.0f) via %s" % (
                apto, len(items), cp_x, cp_y, origen_panel))

            # dedup por tipo a 150 mm
            por_tipo = defaultdict(list)
            for d in items:
                por_tipo[d["tipo"]].append(d)
            reps = []
            for tipo in por_tipo:
                grupo = sorted(por_tipo[tipo], key=lambda z: -z["pt"][2])
                usados = set()
                for i in range(len(grupo)):
                    if i in usados:
                        continue
                    reps.append(grupo[i])
                    for j in range(i + 1, len(grupo)):
                        if j in usados:
                            continue
                        if d2(grupo[i]["pt"][0], grupo[i]["pt"][1],
                              grupo[j]["pt"][0], grupo[j]["pt"][1]) <= DEDUP_MM:
                            usados.add(j)

            # cocina: agrupar
            coc = [d for d in reps if d["id"] in coc_ids]
            no_coc = [d for d in reps if d["id"] not in coc_ids]
            risers_xy = []

            # --- no cocina: bajante recto ---
            for d in no_coc:
                x, y, z = d["pt"]
                es_dato = any(k in (d["familia"] + " " + d["tipo"]).lower()
                              for k in ("comunicacion", "datos", "telephone", "data devices", "pau"))
                if es_dato:
                    for signo in (-1.0, 1.0):
                        yy = y + signo * OFFSET_COMMS_MM / 2.0
                        try:
                            c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                               xyz(x, yy, z), xyz(x, yy, Z_PLENUM_MM),
                                               ElementId(Int64(nivel_id)))
                            fijar_diam(c, D_19_MM)
                            tramos += 1
                            creados.append({"apto": apto, "tipo": "riser_datos",
                                            "a": [round(x, 1), round(yy, 1), round(z, 1)],
                                            "b": [round(x, 1), round(yy, 1), Z_PLENUM_MM],
                                            "disp_id": d["id"]})
                        except Exception as ex:
                            fallos.append({"apto": apto, "id": d["id"], "err": str(ex)[:110]})
                    risers_xy.append((x, y - OFFSET_COMMS_MM / 2.0))
                    risers_xy.append((x, y + OFFSET_COMMS_MM / 2.0))
                else:
                    try:
                        c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                           xyz(x, y, z), xyz(x, y, Z_PLENUM_MM),
                                           ElementId(Int64(nivel_id)))
                        fijar_diam(c, D_16_MM)
                        tramos += 1
                        creados.append({"apto": apto, "tipo": "riser",
                                        "a": [round(x, 1), round(y, 1), round(z, 1)],
                                        "b": [round(x, 1), round(y, 1), Z_PLENUM_MM],
                                        "disp_id": d["id"]})
                    except Exception as ex:
                        fallos.append({"apto": apto, "id": d["id"], "err": str(ex)[:110]})
                    risers_xy.append((x, y))

            # --- cocina: vertical por alturas + ramal por aparato ---
            coc_usados = set()
            for i in range(len(coc)):
                if i in coc_usados:
                    continue
                grupo = [coc[i]]
                coc_usados.add(i)
                for j in range(i + 1, len(coc)):
                    if j in coc_usados:
                        continue
                    if d2(coc[i]["pt"][0], coc[i]["pt"][1],
                          coc[j]["pt"][0], coc[j]["pt"][1]) <= 200.0:
                        grupo.append(coc[j])
                        coc_usados.add(j)
                cx = grupo[0]["pt"][0]
                cy = grupo[0]["pt"][1]
                z_min = min(g["pt"][2] for g in grupo)
                objetivo_z = [z_nivel + h for h in ALTURAS_COCINA_REL_MM]
                objetivo_z.append(Z_PLENUM_MM)
                cadena = [z_min]
                for z in sorted(objetivo_z):
                    if z > z_min + 1.0:
                        cadena.append(z)
                limpia = []
                for z in cadena:
                    if not limpia or abs(z - limpia[-1]) > 1.0:
                        limpia.append(z)
                for k in range(len(limpia) - 1):
                    za, zb = limpia[k], limpia[k + 1]
                    if abs(zb - za) < LARGO_MIN_MM:
                        continue
                    try:
                        c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                           xyz(cx, cy, za), xyz(cx, cy, zb),
                                           ElementId(Int64(nivel_id)))
                        fijar_diam(c, D_16_MM)
                        tramos += 1
                        creados.append({"apto": apto, "tipo": "riser_cocina",
                                        "a": [round(cx, 1), round(cy, 1), round(za, 1)],
                                        "b": [round(cx, 1), round(cy, 1), round(zb, 1)]})
                    except Exception as ex:
                        fallos.append({"apto": apto, "id": grupo[0]["id"], "err": str(ex)[:110]})
                risers_xy.append((cx, cy))

                # ramal en L por aparato hasta la vertical
                for g in grupo:
                    gx, gy, gz = g["pt"]
                    if d2(gx, gy, cx, cy) <= 1.0:
                        continue
                    try:
                        c1 = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                            xyz(gx, gy, gz), xyz(cx, gy, gz),
                                            ElementId(Int64(nivel_id)))
                        fijar_diam(c1, D_16_MM)
                        c2 = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                            xyz(cx, gy, gz), xyz(cx, cy, gz),
                                            ElementId(Int64(nivel_id)))
                        fijar_diam(c2, D_16_MM)
                        tramos += 2
                        creados.append({"apto": apto, "tipo": "ramal_cocina",
                                        "disp_id": g["id"],
                                        "a": [round(gx, 1), round(gy, 1), round(gz, 1)],
                                        "b": [round(cx, 1), round(cy, 1), round(gz, 1)]})
                    except Exception as ex:
                        fallos.append({"apto": apto, "id": g["id"], "err": str(ex)[:110]})

            # --- horizontales en peine hasta el tablero ---
            tramos_red, grupos_y = [], []
            for r in sorted(set(risers_xy), key=lambda t: t[1]):
                colocado = False
                for gy in grupos_y:
                    if abs(gy["y"] - r[1]) <= TOL_GRUPO_Y_MM:
                        gy["items"].append(r)
                        gy["y"] = sum(i[1] for i in gy["items"]) / len(gy["items"])
                        colocado = True
                        break
                if not colocado:
                    grupos_y.append({"y": r[1], "items": [r]})
            ys = []
            for gy in grupos_y:
                ys.append(gy["y"])
                xs = [i[0] for i in gy["items"]]
                xmin, xmax = min(xs), max(xs)
                if cp_x <= xmin:
                    xa, xb = xmax, cp_x
                elif cp_x >= xmax:
                    xa, xb = xmin, cp_x
                else:
                    xa, xb = xmin, xmax
                if abs(xb - xa) >= LARGO_MIN_MM:
                    tramos_red.append((xa, gy["y"], xb, gy["y"]))
            if ys:
                y_lo = min(min(ys), cp_y)
                y_hi = max(max(ys), cp_y)
                if abs(y_hi - y_lo) >= LARGO_MIN_MM:
                    tramos_red.append((cp_x, y_lo, cp_x, y_hi))

            datos_items = [d for d in items
                           if any(k in (d["familia"] + " " + d["tipo"]).lower()
                                  for k in ("comunicacion", "datos", "telephone", "data devices", "pau"))]
            for (ax, ay, bx, by) in tramos_red:
                es_dato = False
                for d in datos_items:
                    if dist_punto_seg(d["pt"][0], d["pt"][1], ax, ay, bx, by) <= 300.0:
                        es_dato = True
                        break
                try:
                    c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                       xyz(ax, ay, Z_PLENUM_MM), xyz(bx, by, Z_PLENUM_MM),
                                       ElementId(Int64(nivel_id)))
                    fijar_diam(c, D_19_MM if es_dato else D_16_MM)
                    tramos += 1
                    creados.append({"apto": apto, "tipo": "horizontal",
                                    "a": [round(ax, 1), round(ay, 1), Z_PLENUM_MM],
                                    "b": [round(bx, 1), round(by, 1), Z_PLENUM_MM],
                                    "datos": es_dato})
                except Exception as ex:
                    fallos.append({"apto": apto, "err": str(ex)[:110]})

            resumen[apto] = {
                "dispositivos": len(items), "representantes": len(reps),
                "cocina": len(coc), "no_cocina": len(no_coc),
                "grupos_y": len(grupos_y), "tramos_horiz": len(tramos_red),
                "tablero": [round(cp_x, 1), round(cp_y, 1)], "origen_panel": origen_panel,
            }

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
    log("=" * 74)
    log("RESULTADO: tramos creados=%d | fallos=%d | conduits totales=%d" % (
        tramos, len(fallos), total))
    for a in aptos:
        r = resumen.get(a, {})
        log("   %-4s %s" % (a, r))
    for f in fallos[:10]:
        log("      FALLO %s" % f)
    log("=" * 74)

    out = os.path.join(DEFAULT_ROOT, "data",
                       "f7_ruteo_creado_%s_v01.json" % "_".join(aptos))
    try:
        with open(out, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "nivel": {"nombre": nivel.Name, "elevacion_abs_mm": round(z_nivel, 1)},
                "plenum_mm": Z_PLENUM_MM,
                "resumen": resumen,
                "tramos": creados,
                "fallos": fallos,
            }, ensure_ascii=True, indent=1))
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0


def dist_punto_seg(px, py, ax, ay, bx, by):
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


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
