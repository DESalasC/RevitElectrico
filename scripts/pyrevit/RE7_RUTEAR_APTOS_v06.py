# -*- coding: utf-8 -*-
"""
RE7_RUTEAR_APTOS_v06.py

Ruteo por apartamento agrupando por RECINTO (room). Sin radio.

Cambios respecto de v05:
  * El grupo de aparatos normales es el ROOM; si el dispositivo no cae en un
    room se usa el MURO HOST. Se elimina la agrupacion por radio: los
    dispositivos sin room y sin host generan su propia bajante y se reportan.
  * El room se resuelve tambien cuando el punto del aparato cae justo sobre la
    cara del muro (Revit devuelve None en el borde): se prueban corrimientos
    cortos y se vota el room mas repetido.
  * Un room solo se usa si su apartamento dominante coincide con el del
    aparato; si no, el aparato vuelve al muro host y queda reportado.
  * Modo `dry_run` (inputs={"dry_run": true}): calcula y escribe el plan sin
    crear geometria. Modo por defecto: crea los conduits.

Reglas que se conservan de v05 (validadas con el operador):
  * CP: punto del ELEC-NET-PAU del apartamento a nivel + 2700 mm.
  * Datos: dos tubos separados 40 mm por agrupacion (19 mm).
  * Cocina: vertical unica anclada en la GFCI de 1.05 m, sube y baja a 0.70 y
    1.65, ramal corto por toma, riser desde la altura superior a plenum.
  * Horizontales: peine en plenum hacia la X del PAU + troncal en Y.
  * Diametros: 16 mm general, 19 mm datos/comunicaciones.

Entorno: pyRevit IronPython 2.7.
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

VERSION = "v06_rooms_sin_radio"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
ALTURA_PAU_MM = 2700.0
LARGO_MIN_MM = 5.0
DEDUP_MM = 150.0
MIN_RAMAL_MM = 25.0
TOL_GRUPO_Y_MM = 5.0
OFFSET_COMMS_MM = 40.0
COCINA_BAJA_MM = 700.0
COCINA_MEDIA_MM = 1050.0
COCINA_ALTA_MM = 1650.0
TOL_ALTURA_COCINA_MM = 60.0

D_16_MM = 16.0
D_19_MM = 19.0
NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size"]
TUBO_E_ID = 112216

# corrimientos para resolver el room cuando el punto cae en el borde del muro
OFFSETS_ROOM_MM = [
    (0.0, 0.0),
    (120.0, 0.0), (-120.0, 0.0), (0.0, 120.0), (0.0, -120.0),
    (120.0, 120.0), (120.0, -120.0), (-120.0, 120.0), (-120.0, -120.0),
    (250.0, 0.0), (-250.0, 0.0), (0.0, 250.0), (0.0, -250.0),
]

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


# --------------------------------------------------------------------------
# funciones puras (las levanta el test con exec, sin Revit)
# --------------------------------------------------------------------------
def apto_de_mark(mark):
    if not mark or "|" not in mark:
        return None
    pref = mark.split("|")[0].strip().upper()
    return pref or None


def es_dato(familia, tipo):
    txt = ((familia or "") + " " + (tipo or "")).lower()
    for k in CLAVES_DATOS:
        if k in txt:
            return True
    return False


def d2(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def dist_3d(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def votar_room(ids):
    """Room mas repetido entre los corrimientos; empate -> el primero."""
    if not ids:
        return None
    cuenta = {}
    orden = []
    for i in ids:
        if i is None:
            continue
        if i not in cuenta:
            cuenta[i] = 0
            orden.append(i)
        cuenta[i] += 1
    if not cuenta:
        return None
    mejor = None
    for i in orden:
        if mejor is None or cuenta[i] > cuenta[mejor]:
            mejor = i
    return mejor


def dominante_por_room(dispositivos):
    """room_id -> apto con mas aparatos dentro (None si no hay marks)."""
    cuenta = defaultdict(dict)
    for d in dispositivos:
        rid = d.get("room_id")
        a = apto_de_mark(d.get("mark"))
        if rid is None or a is None:
            continue
        m = cuenta[rid]
        m[a] = m.get(a, 0) + 1
    out = {}
    for rid in cuenta:
        m = cuenta[rid]
        mejor = None
        for a in m:
            if mejor is None or m[a] > m[mejor]:
                mejor = a
        out[rid] = mejor
    return out


def clave_recinto(d, dominante):
    """(room|host, id) valido para el apartamento del aparato, o None."""
    a = apto_de_mark(d.get("mark"))
    rid = d.get("room_id")
    if rid is not None and dominante.get(rid) == a:
        return ("room", rid)
    hid = d.get("host_id")
    if hid is not None:
        return ("host", hid)
    return None


def agrupar_normales(dispositivos, dominante):
    """{clave: [dispositivos]} + lista de los que no tienen recinto."""
    grupos = {}
    sin = []
    for d in dispositivos:
        k = clave_recinto(d, dominante)
        if k is None:
            sin.append(d)
        else:
            grupos.setdefault(k, []).append(d)
    return grupos, sin


def dedup_por_tipo(items, tolerancia_mm=DEDUP_MM):
    grupos = {}
    for d in items:
        grupos.setdefault(d.get("tipo") or "", []).append(d)
    reps = []
    dedup = 0
    for tipo in grupos:
        grupo = sorted(grupos[tipo], key=lambda z: -z["pt"][2])
        usados = set()
        for i in range(len(grupo)):
            if i in usados:
                continue
            reps.append(grupo[i])
            for j in range(i + 1, len(grupo)):
                if j in usados:
                    continue
                if d2(grupo[i]["pt"][0], grupo[i]["pt"][1],
                      grupo[j]["pt"][0], grupo[j]["pt"][1]) <= tolerancia_mm:
                    usados.add(j)
                    dedup += 1
    return reps, dedup


def agrupar_por_proximidad(items, tolerancia_mm):
    usados = set()
    grupos = []
    for i in range(len(items)):
        if i in usados:
            continue
        grupo = [items[i]]
        usados.add(i)
        for j in range(i + 1, len(items)):
            if j in usados:
                continue
            if d2(items[i]["pt"][0], items[i]["pt"][1],
                  items[j]["pt"][0], items[j]["pt"][1]) <= tolerancia_mm:
                grupo.append(items[j])
                usados.add(j)
        grupos.append(grupo)
    return grupos


# --------------------------------------------------------------------------
# acceso a Revit
# --------------------------------------------------------------------------
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


def nivel_piso5(doc):
    mejor = None
    mejor_d = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        dd = abs(lvl.Elevation * FT_A_MM - 13220.0)
        if mejor_d is None or dd < mejor_d:
            mejor = lvl
            mejor_d = dd
    return mejor


def area_room(room):
    try:
        a = room.Area
        if a is not None and a > 0:
            return float(a) * 0.09290304
    except Exception:
        pass
    return None


def room_en_punto(doc, pt, offsets):
    """Devuelve (room_id, numero, nombre, metodo) resolviendo el borde del muro."""
    for idx, (dx, dy) in enumerate(offsets):
        try:
            rm = doc.GetRoomAtPoint(xyz(pt[0] + dx, pt[1] + dy, pt[2]))
        except Exception:
            rm = None
        if rm is None:
            continue
        if area_room(rm) is None:
            continue
        return (id_de(rm), texto(rm, ["Number"]), texto(rm, ["Name"]),
                "punto" if idx == 0 else "corrimiento")
    return (None, None, None, None)


def resolver_rooms(doc, disp):
    """Completa room_id/number/name/metodo en cada dispositivo."""
    for d in disp:
        rid, num, nom, met = room_en_punto(doc, d["pt"], OFFSETS_ROOM_MM)
        d["room_id"] = rid
        d["room_numero"] = num
        d["room_nombre"] = nom
        d["room_metodo"] = met


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


def cargar_ids_cocina():
    try:
        p = os.path.join(DEFAULT_ROOT, "data", "f7_cocinas_ids_v01.json")
        with open(p) as f:
            return set(int(x) for x in json.load(f)["ids"])
    except Exception:
        return set()


def leer_inputs():
    entrada = {}
    try:
        g = globals().get("inputs")
        if isinstance(g, dict):
            entrada = g
    except Exception:
        pass
    return entrada


def contar_conduits(doc):
    try:
        return int(FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().GetElementCount())
    except Exception:
        return -1


def main():
    log("=" * 78)
    log("RE7_RUTEAR_APTOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1

    inp = leer_inputs()
    dry_run = bool(inp.get("dry_run", False))
    modo = "dry_run" if dry_run else "crear"
    env = os.environ.get("APTOS_RUTEO", "").strip()
    aptos = inp.get("aptos")
    if not aptos:
        aptos = [a.strip().upper() for a in env.split(",")] if env else ["F01", "F02"]
    aptos = [str(a).strip().upper() for a in aptos]
    log("documento=%r | modo=%s | apartamentos=%s" % (doc.Title, modo, aptos))

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
    coc_ids = cargar_ids_cocina()
    log("ids cocina: %d" % len(coc_ids))
    conduits_previos = contar_conduits(doc)
    log("conduits en el documento antes de rutear: %d" % conduits_previos)

    disp = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto(el)
            if pt is None:
                continue
            fam, tip = fam_tipo(el)
            host_id = None
            try:
                h = el.Host
                if h is not None:
                    host_id = id_de(h)
            except Exception:
                pass
            disp.append({"el": el, "id": id_de(el), "pt": pt,
                         "mark": texto(el, ["Mark"]) or "",
                         "familia": fam or "", "tipo": tip or "",
                         "host_id": host_id,
                         "room_id": None, "room_numero": None,
                         "room_nombre": None, "room_metodo": None})
    log("dispositivos con punto: %d" % len(disp))

    resolver_rooms(doc, disp)
    con_room = [d for d in disp if d["room_id"] is not None]
    por_corrimiento = [d for d in con_room if d["room_metodo"] == "corrimiento"]
    log("con room: %d (resueltos por corrimiento: %d) | sin room: %d" % (
        len(con_room), len(por_corrimiento), len(disp) - len(con_room)))

    dominante = dominante_por_room(disp)
    log("rooms con apartamento dominante: %d" % len(dominante))

    tramos = []
    fallos = []
    resumen = {}
    contador = {"tramo": 0}

    def crear_tramo(apto, tipo, a, b, diam, extra=None):
        largo = dist_3d(a, b)
        if largo < LARGO_MIN_MM:
            return False
        reg = {"apto": apto, "tipo": tipo,
               "a": [round(a[0], 1), round(a[1], 1), round(a[2], 1)],
               "b": [round(b[0], 1), round(b[1], 1), round(b[2], 1)],
               "diam_mm": diam, "largo_mm": round(largo, 1)}
        if extra:
            reg.update(extra)
        if not dry_run:
            try:
                c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                   xyz(a[0], a[1], a[2]), xyz(b[0], b[1], b[2]),
                                   ElementId(Int64(nivel_id)))
                fijar_diam(c, diam)
                try:
                    reg["conduit_id"] = id_de(c)
                except Exception:
                    pass
            except Exception as ex:
                fallos.append({"apto": apto, "tipo": tipo,
                               "err": str(ex)[:110]})
                return False
        tramos.append(reg)
        contador["tramo"] += 1
        return True

    trans = None
    if not dry_run:
        trans = Transaction(doc, "RE7_RUTEAR_APTOS_v06")
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

            reps, dedup = dedup_por_tipo(items)
            coc = [d for d in reps if d["id"] in coc_ids]
            no_coc = [d for d in reps if d["id"] not in coc_ids]
            datos = [d for d in no_coc if es_dato(d["familia"], d["tipo"])]
            normales = [d for d in no_coc if not es_dato(d["familia"], d["tipo"])]

            log("")
            log("%s: %d disp | reps=%d (dedup %d) | PAU=(%.0f,%.0f) a %.0f mm" % (
                apto, len(items), len(reps), dedup, cp_x, cp_y, cp_z))

            risers = []

            # ---------- datos: pareja de tubos por agrupacion ----------
            grupos_datos = agrupar_por_proximidad(datos, 200.0)
            rechazados = 0
            for grupo_d in grupos_datos:
                rep = max(grupo_d, key=lambda g: g["pt"][2])
                x, y = rep["pt"][0], rep["pt"][1]
                z_bajo = min(g["pt"][2] for g in grupo_d)
                for signo in (-1.0, 1.0):
                    yy = y + signo * OFFSET_COMMS_MM / 2.0
                    crear_tramo(apto, "riser_datos",
                                (x, yy, z_bajo), (x, yy, Z_PLENUM_MM), D_19_MM,
                                {"disp": rep["id"], "n_grupo": len(grupo_d)})
                risers.append((x, y - OFFSET_COMMS_MM / 2.0))
                risers.append((x, y + OFFSET_COMMS_MM / 2.0))
                for g in grupo_d:
                    gx, gy, gz = g["pt"]
                    if d2(gx, gy, x, y) <= MIN_RAMAL_MM:
                        continue
                    crear_tramo(apto, "ramal_datos", (gx, gy, gz), (x, gy, gz),
                                D_19_MM, {"disp": g["id"]})
                    crear_tramo(apto, "ramal_datos", (x, gy, gz), (x, y, gz),
                                D_19_MM, {"disp": g["id"]})

            # ---------- normales: una bajante por ROOM (o muro host) ----------
            grupos_n, sin_recinto = agrupar_normales(normales, dominante)
            for d in normales:
                if d["room_id"] is not None and dominante.get(d["room_id"]) != apto:
                    rechazados += 1

            for clave in grupos_n:
                grupo_n = grupos_n[clave]
                rep = max(grupo_n, key=lambda g: g["pt"][2])
                rx, ry = rep["pt"][0], rep["pt"][1]
                z_bajo = min(g["pt"][2] for g in grupo_n)
                crear_tramo(apto, "riser", (rx, ry, z_bajo), (rx, ry, Z_PLENUM_MM),
                            D_16_MM, {"disp": rep["id"], "n_grupo": len(grupo_n),
                                      "recinto": clave[0], "recinto_id": clave[1],
                                      "recinto_num": rep.get("room_numero")})
                risers.append((rx, ry))
                for g in grupo_n:
                    gx, gy, gz = g["pt"]
                    if d2(gx, gy, rx, ry) <= MIN_RAMAL_MM:
                        continue
                    crear_tramo(apto, "ramal", (gx, gy, gz), (rx, gy, gz),
                                D_16_MM, {"disp": g["id"]})
                    crear_tramo(apto, "ramal", (rx, gy, gz), (rx, ry, gz),
                                D_16_MM, {"disp": g["id"]})

            for d in sin_recinto:
                gx, gy, gz = d["pt"]
                crear_tramo(apto, "riser", (gx, gy, gz), (gx, gy, Z_PLENUM_MM),
                            D_16_MM, {"disp": d["id"], "n_grupo": 1,
                                      "recinto": "ninguno",
                                      "recinto_id": None})
                risers.append((gx, gy))

            # ---------- cocina ----------
            grupos_cocina = agrupar_por_proximidad(coc, 200.0)
            for grupo in grupos_cocina:
                cerca = [g for g in grupo
                         if abs(g["pt"][2] - (z_nivel + COCINA_MEDIA_MM)) <= 120.0]
                if cerca:
                    gfci = [g for g in cerca if "gfci" in (g["tipo"] or "").lower()]
                    ancla = gfci[0] if gfci else cerca[0]
                else:
                    ancla = min(grupo, key=lambda g: abs(
                        g["pt"][2] - (z_nivel + COCINA_MEDIA_MM)))
                vx, vy = ancla["pt"][0], ancla["pt"][1]
                vz = ancla["pt"][2]

                alturas = set()
                for g in grupo:
                    rel = g["pt"][2] - z_nivel
                    if (COCINA_BAJA_MM - TOL_ALTURA_COCINA_MM <= rel <=
                            COCINA_ALTA_MM + TOL_ALTURA_COCINA_MM):
                        alturas.add(round(rel / 10.0) * 10.0)
                alturas.add(round((vz - z_nivel) / 10.0) * 10.0)
                alturas = sorted(alturas)
                z_hi = max(alturas) + z_nivel

                for k in range(len(alturas) - 1):
                    crear_tramo(apto, "cocina_vertical",
                                (vx, vy, alturas[k] + z_nivel),
                                (vx, vy, alturas[k + 1] + z_nivel), D_16_MM)
                crear_tramo(apto, "cocina_riser", (vx, vy, z_hi),
                            (vx, vy, Z_PLENUM_MM), D_16_MM)
                risers.append((vx, vy))
                for g in grupo:
                    gx, gy, gz = g["pt"]
                    if d2(gx, gy, vx, vy) <= MIN_RAMAL_MM:
                        continue
                    crear_tramo(apto, "cocina_ramal", (gx, gy, gz), (vx, gy, gz),
                                D_16_MM, {"disp": g["id"]})
                    crear_tramo(apto, "cocina_ramal", (vx, gy, gz), (vx, vy, gz),
                                D_16_MM, {"disp": g["id"]})

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
                           if es_dato(d["familia"], d["tipo"])]
            for (ax, ay, bx, by) in tramos_h:
                es_de_datos = False
                for d in datos_items:
                    if dist_seg(d["pt"][0], d["pt"][1], ax, ay, bx, by) <= 300.0:
                        es_de_datos = True
                        break
                crear_tramo(apto, "horizontal", (ax, ay, Z_PLENUM_MM),
                            (bx, by, Z_PLENUM_MM),
                            D_19_MM if es_de_datos else D_16_MM,
                            {"datos": es_de_datos})

            # ---------- bajada del troncal al PAU ----------
            crear_tramo(apto, "bajada_pau", (cp_x, cp_y, Z_PLENUM_MM),
                        (cp_x, cp_y, cp_z), D_19_MM)

            resumen[apto] = {
                "dispositivos": len(items),
                "representantes": len(reps),
                "dedup": dedup,
                "con_room": len([d for d in items if d["room_id"] is not None]),
                "sin_room": len([d for d in items if d["room_id"] is None]),
                "rooms_rechazados": rechazados,
                "cocina": len(coc),
                "datos": len(datos),
                "normales": len(normales),
                "grupos_datos": len(grupos_datos),
                "grupos_normales": len(grupos_n),
                "normales_sin_recinto": len(sin_recinto),
                "grupos_cocina": len(grupos_cocina),
                "grupos_y": len(grupos_y),
                "tramos_horizontales": len(tramos_h),
                "pau": [round(cp_x, 1), round(cp_y, 1), round(cp_z, 1)],
            }
            log("   reps=%d (dedup %d) | cocina %d | datos %d | normales %d" % (
                len(reps), dedup, len(coc), len(datos), len(normales)))
            log("   recintos: %d (sin recinto %d, room rechazado %d) | cocina grupos %d" % (
                len(grupos_n), len(sin_recinto), rechazados, len(grupos_cocina)))
            log("   horizontales: %d grupos Y, %d tramos" % (
                len(grupos_y), len(tramos_h)))

        if trans is not None:
            trans.Commit()
            log("Transaccion COMMIT.")

    except Exception:
        if trans is not None:
            try:
                trans.RollBack()
                log("ERROR: transaccion revertida.")
            except Exception:
                log("ERROR: no se pudo revertir la transaccion.")
        log(traceback.format_exc())
        return 1

    total_tramos = len(tramos)
    longitud = 0.0
    por_tipo = {}
    for t in tramos:
        longitud += dist_3d(t["a"], t["b"])
        por_tipo[t["tipo"]] = por_tipo.get(t["tipo"], 0) + 1
    verticales = 0
    for t in tramos:
        if abs(t["a"][0] - t["b"][0]) < 2.0 and abs(t["a"][1] - t["b"][1]) < 2.0:
            verticales += 1

    log("")
    log("=" * 78)
    log("RESULTADO (%s): tramos=%d | fallos=%d | longitud=%.1f m | verticales=%d" % (
        modo, total_tramos, len(fallos), longitud / 1000.0, verticales))
    for tipo in sorted(por_tipo):
        log("   %-16s %d" % (tipo, por_tipo[tipo]))
    for a in aptos:
        log("   %-5s %s" % (a, resumen.get(a)))
    for f in fallos[:8]:
        log("      %s" % f)
    if dry_run:
        log("MODO dry_run: no se creo geometria.")
    else:
        log("conduits en el documento despues: %d" % contar_conduits(doc))
    log("=" * 78)

    out = os.path.join(DEFAULT_ROOT, "data",
                       "f7_%s_ruteo_%s_v06.json" % (
                           "plan" if dry_run else "creado", "_".join(aptos)))
    try:
        with open(out, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "modo": modo,
                "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "nivel": {"nombre": nivel.Name,
                          "elevacion_abs_mm": round(z_nivel, 1)},
                "plenum_mm": Z_PLENUM_MM,
                "altura_pau_mm": ALTURA_PAU_MM,
                "conduits_previos": conduits_previos,
                "resumen": resumen,
                "totales": {"tramos": total_tramos,
                            "longitud_m": round(longitud / 1000.0, 2),
                            "verticales": verticales,
                            "por_tipo": por_tipo,
                            "fallos": len(fallos)},
                "tramos": tramos,
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
