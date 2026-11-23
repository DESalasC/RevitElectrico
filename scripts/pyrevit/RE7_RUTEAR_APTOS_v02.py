# -*- coding: utf-8 -*-
"""
RE7_RUTEAR_APTOS_v02.py

Ruteo por apartamento con la logica acordada:

  CP: punto del dispositivo ELEC-NET-PAU del apartamento, a Z = nivel + 2700 mm.
      El troncal de plenum llega a la vertical del PAU y baja hasta 2.70 m.

  Aparatos normales: bajante vertical desde el aparato hasta plenum, en su XY.
  Datos/comunicaciones: 2 tubos separados 40 mm (uno por agrupacion).

  COCINA (regla del operador):
    * La alimentacion llega horizontal a 1.05 m (toma de entrada).
    * La vertical se ancla en la GFCI de 1.05 m y sube/baja en la MISMA linea
      hasta las otras alturas presentes (0.70 y/o 1.65).
    * Cada otra toma se conecta con un ramal corto en L a esa vertical.
    * Desde la altura superior de la vertical sube el riser hasta plenum.

  Horizontales: peine en plenum hacia la X del PAU + troncal en Y.

  Diametros: 16 mm general, 19 mm datos/comunicaciones.

Apartamentos: variable de entorno APTOS_RUTEO (default F01,F02).

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

VERSION = "v02_rutear_aptos"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
ALTURA_PAU_MM = 2700.0
LARGO_MIN_MM = 5.0
DEDUP_MM = 150.0
TOL_GRUPO_Y_MM = 5.0
OFFSET_COMMS_MM = 40.0
COCINA_BAJA_MM = 700.0
COCINA_MEDIA_MM = 1050.0
COCINA_ALTA_MM = 1650.0

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

CLAVES_DATOS = ("comunicacion", "datos", "telephone", "data devices", "pau")


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


def fijar_diam(el, mm):
    for n in NOMBRES_DIAM:
        try:
            p = el.LookupParameter(n)
            if p is not None and not p.IsReadOnly:
                p.Set(mm / FT_A_MM)
                return abs(p.AsDouble() * FT_A_MM - mm) <= 0.6
        except Exception:
            pass
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


def cargar_pau():
    out = {}
    try:
        p = os.path.join(DEFAULT_ROOT, "data", "f7_pau_por_apto_v01.json")
        with open(p) as f:
            for q in json.load(f)["pau"]:
                out[q["apto"]] = (q["x"], q["y"])
    except Exception:
        pass
    return out


def main():
    log("=" * 76)
    log("RE7_RUTEAR_APTOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    env = os.environ.get("APTOS_RUTEO", "").strip()
    aptos = [a.strip().upper() for a in env.split(",")] if env else ["F01", "F02"]
    log("documento=%r | apartamentos=%s" % (doc.Title, aptos))

    nivel = nivel_piso5(doc)
    if nivel is None:
        log("ERROR: no se encontro Piso 5.")
        return 1
    nivel_id = id_de(nivel)
    z_nivel = float(nivel.Elevation) * FT_A_MM
    log("nivel=%r elevacion=%.0f | plenum=%.0f | PAU=%.0f" % (
        nivel.Name, z_nivel, Z_PLENUM_MM, z_nivel + ALTURA_PAU_MM))

    pau_por_apto = cargar_pau()
    log("PAU cargados: %d" % len(pau_por_apto))

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
        with open(os.path.join(DEFAULT_ROOT, "data", "f7_cocinas_ids_v01.json")) as f:
            coc_ids = set(int(x) for x in json.load(f)["ids"])
    except Exception:
        pass
    log("ids cocina: %d" % len(coc_ids))

    creados = []
    fallos = []
    resumen = {}
    total_tramos = 0

    trans = Transaction(doc, "RE7_RUTEAR_APTOS_v02")
    trans.Start()
    try:
        for apto in aptos:
            if apto not in pau_por_apto:
                log("%s: sin PAU en los datos" % apto)
                resumen[apto] = {"error": "sin PAU"}
                continue
            cp_x, cp_y = pau_por_apto[apto]
            cp_z = z_nivel + ALTURA_PAU_MM

            items = [d for d in disp if d["mark"].startswith(apto + "|")]
            if not items:
                log("%s: sin dispositivos marcados" % apto)
                resumen[apto] = {"error": "sin dispositivos"}
                continue
            log("")
            log("%s: %d dispositivos | PAU=(%.0f,%.0f) a %.0f mm" % (
                apto, len(items), cp_x, cp_y, cp_z))

            # dedup por tipo a 150 mm (el mas alto representa)
            por_tipo = defaultdict(list)
            for d in items:
                por_tipo[d["tipo"]].append(d)
            reps = []
            dedup = 0
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
                            dedup += 1

            coc = [d for d in reps if d["id"] in coc_ids]
            no_coc = [d for d in reps if d["id"] not in coc_ids]
            risers = []

            # ---------- no cocina ----------
            for d in no_coc:
                x, y, z = d["pt"]
                es_dato = any(k in (d["familia"] + " " + d["tipo"]).lower()
                              for k in CLAVES_DATOS)
                if es_dato:
                    for signo in (-1.0, 1.0):
                        yy = y + signo * OFFSET_COMMS_MM / 2.0
                        try:
                            c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                               xyz(x, yy, z), xyz(x, yy, Z_PLENUM_MM),
                                               ElementId(Int64(nivel_id)))
                            fijar_diam(c, D_19_MM)
                            total_tramos += 1
                            creados.append({"apto": apto, "tipo": "riser_datos",
                                            "a": [round(x, 1), round(yy, 1), round(z, 1)],
                                            "b": [round(x, 1), round(yy, 1), Z_PLENUM_MM],
                                            "disp": d["id"]})
                        except Exception as ex:
                            fallos.append({"apto": apto, "id": d["id"], "err": str(ex)[:110]})
                    risers.append((x, y - OFFSET_COMMS_MM / 2.0))
                    risers.append((x, y + OFFSET_COMMS_MM / 2.0))
                else:
                    try:
                        c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                           xyz(x, y, z), xyz(x, y, Z_PLENUM_MM),
                                           ElementId(Int64(nivel_id)))
                        fijar_diam(c, D_16_MM)
                        total_tramos += 1
                        creados.append({"apto": apto, "tipo": "riser",
                                        "a": [round(x, 1), round(y, 1), round(z, 1)],
                                        "b": [round(x, 1), round(y, 1), Z_PLENUM_MM],
                                        "disp": d["id"]})
                    except Exception as ex:
                        fallos.append({"apto": apto, "id": d["id"], "err": str(ex)[:110]})
                    risers.append((x, y))

            # ---------- cocina ----------
            usados_c = set()
            for i in range(len(coc)):
                if i in usados_c:
                    continue
                grupo = [coc[i]]
                usados_c.add(i)
                for j in range(i + 1, len(coc)):
                    if j in usados_c:
                        continue
                    if d2(coc[i]["pt"][0], coc[i]["pt"][1],
                          coc[j]["pt"][0], coc[j]["pt"][1]) <= 200.0:
                        grupo.append(coc[j])
                        usados_c.add(j)

                # ancla: la toma a 1.05 (preferir GFCI)
                cerca_1050 = [g for g in grupo
                              if abs(g["pt"][2] - (z_nivel + COCINA_MEDIA_MM)) <= 120.0]
                if cerca_1050:
                    gfci = [g for g in cerca_1050 if "gfci" in g["tipo"].lower()]
                    ancla = gfci[0] if gfci else cerca_1050[0]
                else:
                    ancla = min(grupo, key=lambda g: abs(g["pt"][2] - (z_nivel + COCINA_MEDIA_MM)))
                vx, vy = ancla["pt"][0], ancla["pt"][1]
                vz = ancla["pt"][2]

                # alturas presentes en la agrupacion
                alturas = set()
                for g in grupo:
                    rel = g["pt"][2] - z_nivel
                    if COCINA_BAJA_MM - 60 <= rel <= COCINA_ALTA_MM + 60:
                        alturas.add(round(rel / 10.0) * 10.0)
                alturas.add(round((vz - z_nivel) / 10.0) * 10.0)
                alturas = sorted(alturas)
                z_lo = min(alturas) + z_nivel
                z_hi = max(alturas) + z_nivel

                # vertical unica entre z_lo y z_hi (sube y baja desde 1.05)
                tramos_v = []
                for k in range(len(alturas) - 1):
                    za = alturas[k] + z_nivel
                    zb = alturas[k + 1] + z_nivel
                    if abs(zb - za) >= LARGO_MIN_MM:
                        tramos_v.append((za, zb))
                for (za, zb) in tramos_v:
                    try:
                        c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                           xyz(vx, vy, za), xyz(vx, vy, zb),
                                           ElementId(Int64(nivel_id)))
                        fijar_diam(c, D_16_MM)
                        total_tramos += 1
                        creados.append({"apto": apto, "tipo": "cocina_vertical",
                                        "a": [round(vx, 1), round(vy, 1), round(za, 1)],
                                        "b": [round(vx, 1), round(vy, 1), round(zb, 1)]})
                    except Exception as ex:
                        fallos.append({"apto": apto, "err": str(ex)[:110]})

                # riser desde la altura superior hasta plenum
                try:
                    c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                       xyz(vx, vy, z_hi), xyz(vx, vy, Z_PLENUM_MM),
                                       ElementId(Int64(nivel_id)))
                    fijar_diam(c, D_16_MM)
                    total_tramos += 1
                    creados.append({"apto": apto, "tipo": "cocina_riser",
                                    "a": [round(vx, 1), round(vy, 1), round(z_hi, 1)],
                                    "b": [round(vx, 1), round(vy, 1), Z_PLENUM_MM]})
                except Exception as ex:
                    fallos.append({"apto": apto, "err": str(ex)[:110]})
                risers.append((vx, vy))

                # ramales en L de cada toma a la vertical
                for g in grupo:
                    gx, gy, gz = g["pt"]
                    if d2(gx, gy, vx, vy) <= 1.0:
                        continue
                    try:
                        c1 = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                            xyz(gx, gy, gz), xyz(vx, gy, gz),
                                            ElementId(Int64(nivel_id)))
                        fijar_diam(c1, D_16_MM)
                        c2 = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                            xyz(vx, gy, gz), xyz(vx, vy, gz),
                                            ElementId(Int64(nivel_id)))
                        fijar_diam(c2, D_16_MM)
                        total_tramos += 2
                        creados.append({"apto": apto, "tipo": "cocina_ramal",
                                        "disp": g["id"],
                                        "a": [round(gx, 1), round(gy, 1), round(gz, 1)],
                                        "b": [round(vx, 1), round(vy, 1), round(gz, 1)]})
                    except Exception as ex:
                        fallos.append({"apto": apto, "id": g["id"], "err": str(ex)[:110]})

            # ---------- horizontales en peine hasta la vertical del PAU ----------
            grupos_y = []
            for r in sorted(set(risers), key=lambda t: t[1]):
                puesto = False
                for gy in grupos_y:
                    if abs(gy["y"] - r[1]) <= TOL_GRUPO_Y_MM:
                        gy["items"].append(r)
                        gy["y"] = sum(i[1] for i in gy["items"]) / len(gy["items"])
                        puesto = True
                        break
                if not puesto:
                    grupos_y.append({"y": r[1], "items": [r]})
            tramos_h = []
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
                    tramos_h.append((xa, gy["y"], xb, gy["y"]))
            if ys:
                y_lo = min(min(ys), cp_y)
                y_hi = max(max(ys), cp_y)
                if abs(y_hi - y_lo) >= LARGO_MIN_MM:
                    tramos_h.append((cp_x, y_lo, cp_x, y_hi))

            datos_items = [d for d in items
                           if any(k in (d["familia"] + " " + d["tipo"]).lower()
                                  for k in CLAVES_DATOS)]
            for (ax, ay, bx, by) in tramos_h:
                es_dato = False
                for d in datos_items:
                    if dist_seg(d["pt"][0], d["pt"][1], ax, ay, bx, by) <= 300.0:
                        es_dato = True
                        break
                try:
                    c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                       xyz(ax, ay, Z_PLENUM_MM), xyz(bx, by, Z_PLENUM_MM),
                                       ElementId(Int64(nivel_id)))
                    fijar_diam(c, D_19_MM if es_dato else D_16_MM)
                    total_tramos += 1
                    creados.append({"apto": apto, "tipo": "horizontal",
                                    "a": [round(ax, 1), round(ay, 1), Z_PLENUM_MM],
                                    "b": [round(bx, 1), round(by, 1), Z_PLENUM_MM],
                                    "datos": es_dato})
                except Exception as ex:
                    fallos.append({"apto": apto, "err": str(ex)[:110]})

            # ---------- bajada del troncal al PAU (plenum -> 2.70) ----------
            try:
                c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                   xyz(cp_x, cp_y, Z_PLENUM_MM), xyz(cp_x, cp_y, cp_z),
                                   ElementId(Int64(nivel_id)))
                fijar_diam(c, D_19_MM)
                total_tramos += 1
                creados.append({"apto": apto, "tipo": "bajada_pau",
                                "a": [round(cp_x, 1), round(cp_y, 1), Z_PLENUM_MM],
                                "b": [round(cp_x, 1), round(cp_y, 1), round(cp_z, 1)]})
            except Exception as ex:
                fallos.append({"apto": apto, "err": str(ex)[:110]})

            resumen[apto] = {
                "dispositivos": len(items), "representantes": len(reps),
                "dedup": dedup, "cocina": len(coc), "no_cocina": len(no_coc),
                "grupos_y": len(grupos_y), "tramos_horizontales": len(tramos_h),
                "pau": [round(cp_x, 1), round(cp_y, 1), round(cp_z, 1)],
            }
            log("   reps=%d (dedup %d) | cocina=%d | no_cocina=%d | grupos_y=%d | horiz=%d" % (
                len(reps), dedup, len(coc), len(no_coc), len(grupos_y), len(tramos_h)))

        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida.")
        log(traceback.format_exc())
        return 1

    total = len(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Conduit).ToElements())
    log("")
    log("=" * 76)
    log("RESULTADO: tramos=%d | fallos=%d | conduits totales=%d" % (
        total_tramos, len(fallos), total))
    for a in aptos:
        log("   %-4s %s" % (a, resumen.get(a)))
    for f in fallos[:8]:
        log("      %s" % f)
    log("=" * 76)

    out = os.path.join(DEFAULT_ROOT, "data",
                       "f7_ruteo_creado_%s_v02.json" % "_".join(aptos))
    try:
        with open(out, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "nivel": {"nombre": nivel.Name, "elevacion_abs_mm": round(z_nivel, 1)},
                "plenum_mm": Z_PLENUM_MM,
                "altura_pau_mm": ALTURA_PAU_MM,
                "resumen": resumen,
                "tramos": creados,
                "fallos": fallos,
            }, ensure_ascii=True, indent=1))
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0


def dist_seg(px, py, ax, ay, bx, by):
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    l2 = vx * vx + vy * vy
    if l2 < 1e-9:
        return math.sqrt(wx * wx + wy * wy)
    t = (wx * vx + wy * vy) / l2
    t = max(0.0, min(1.0, t))
    return math.sqrt((px - (ax + t * vx)) ** 2 + (py - (ay + t * vy)) ** 2)


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
