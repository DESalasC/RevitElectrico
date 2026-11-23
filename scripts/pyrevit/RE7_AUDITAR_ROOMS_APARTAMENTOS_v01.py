# -*- coding: utf-8 -*-
"""
RE7_AUDITAR_ROOMS_APARTAMENTOS_v01.py

Auditoria READ-ONLY de los rooms del Piso 5 antes de rutear por recinto.

Comprueba, sin crear ni modificar nada:

  * cuantos rooms hay, en que nivel, con que numero y nombre
  * limite superior de cada room (debe quedar >= 1.70 m sobre el piso)
  * que cada room pertenezca a un solo apartamento (nombre `APTO|TIPO`)
  * cuantos dispositivos caen dentro de un room y cuantos no
  * dispositivos cuyo room pertenece a OTRO apartamento (fuga entre aptos)
  * estimacion de bajantes si se agrupa por room (sin radio)

Salida: data/f7_auditoria_rooms_v01.json

Entorno: pyRevit IronPython 2.7 (o pyrevit agent run --mode=query)
"""
import datetime
import json
import math
import os
import re
import sys
import traceback

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    Level,
    XYZ,
)

VERSION = "v01_auditar_rooms"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_NIVEL_MM = 13220.0
Z_PLENUM_MM = 15930.0
ALTURA_PAU_MM = 2700.0
DEDUP_MM = 150.0
MIN_LIMITE_ROOM_MM = 1700.0
OFFSET_COMMS_MM = 40.0

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
    """'F01|TF 01|C1' -> 'F01'. Sin prefijo valido -> None."""
    if not mark:
        return None
    if "|" not in mark:
        return None
    pref = mark.split("|")[0].strip().upper()
    if not pref:
        return None
    return pref


def apto_de_room(nombre):
    """Nombre de room con convencion `APTO|TIPO` -> 'F01'. Otro formato -> None."""
    if not nombre:
        return None
    n = nombre.strip()
    if "|" not in n:
        return None
    pref = n.split("|")[0].strip().upper()
    if not pref or " " in pref:
        return None
    return pref


def es_dato(familia, tipo):
    txt = ((familia or "") + " " + (tipo or "")).lower()
    for k in CLAVES_DATOS:
        if k in txt:
            return True
    return False


def d2(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def dedup_por_tipo(items, tolerancia_mm=DEDUP_MM):
    """Misma regla que el router: por tipo, el mas alto representa."""
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
    """Agrupacion secuencial por distancia (solo para cocina y datos)."""
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


def clave_recinto(d):
    """room si el dispositivo cae en un room; si no, muro host; si no, None."""
    if d.get("room_id") is not None:
        return ("room", d["room_id"])
    if d.get("host_id") is not None:
        return ("host", d["host_id"])
    return None


def estimar_bajantes(dispositivos, ids_cocina):
    """Estimacion de puntos de bajante por apartamento (regla del proyecto)."""
    reps, dedup = dedup_por_tipo(dispositivos)
    coc = [d for d in reps if d["id"] in ids_cocina]
    no_coc = [d for d in reps if d["id"] not in ids_cocina]
    datos = [d for d in no_coc if es_dato(d.get("familia"), d.get("tipo"))]
    normales = [d for d in no_coc if not es_dato(d.get("familia"), d.get("tipo"))]

    grupos_datos = agrupar_por_proximidad(datos, 200.0)
    grupos_cocina = agrupar_por_proximidad(coc, 200.0)

    claves = {}
    sin_recinto = []
    for d in normales:
        k = clave_recinto(d)
        if k is None:
            sin_recinto.append(d)
        else:
            claves.setdefault(k, []).append(d)

    return {
        "representantes": len(reps),
        "dedup": dedup,
        "cocina_dispositivos": len(coc),
        "datos_dispositivos": len(datos),
        "normales_dispositivos": len(normales),
        "grupos_datos": len(grupos_datos),
        "grupos_cocina": len(grupos_cocina),
        "claves_normales": len(claves),
        "normales_sin_recinto": len(sin_recinto),
        "bajantes_estimadas": len(grupos_datos) + len(grupos_cocina) + len(claves) + len(sin_recinto),
        "claves_detalle": sorted(
            ["%s:%s" % (k[0], k[1]) for k in claves]
        ),
    }


def auditar_rooms(rooms, dispositivos, ids_cocina):
    """rooms y dispositivos como dicts planos -> reporte."""
    por_room = {}
    for r in rooms:
        por_room[r["id"]] = {
            "id": r["id"],
            "numero": r.get("numero") or "",
            "nombre": r.get("nombre") or "",
            "nivel": r.get("nivel") or "",
            "area_m2": r.get("area_m2"),
            "limite_mm": r.get("limite_mm"),
            "apto_nombre": apto_de_room(r.get("nombre")),
            "dispositivos": 0,
            "aptos": {},
        }

    sin_room = []
    for d in dispositivos:
        rid = d.get("room_id")
        if rid is None or rid not in por_room:
            sin_room.append(d)
            continue
        info = por_room[rid]
        info["dispositivos"] += 1
        a = apto_de_mark(d.get("mark"))
        clave = a or "(sin mark)"
        info["aptos"][clave] = info["aptos"].get(clave, 0) + 1

    rooms_mezclan = []
    rooms_apto_distinto = []
    rooms_sin_prefijo = []
    for rid in por_room:
        info = por_room[rid]
        aptos = [k for k in info["aptos"] if k != "(sin mark)"]
        if len(aptos) > 1:
            rooms_mezclan.append(info)
        if info["apto_nombre"] is None:
            rooms_sin_prefijo.append(info)
        elif aptos and any(a != info["apto_nombre"] for a in aptos):
            rooms_apto_distinto.append(info)

    por_apto = {}
    for d in dispositivos:
        a = apto_de_mark(d.get("mark"))
        if a is None:
            continue
        por_apto.setdefault(a, []).append(d)

    resumen_aptos = {}
    for a in sorted(por_apto):
        items = por_apto[a]
        est = estimar_bajantes(items, ids_cocina)
        con_room = [d for d in items if d.get("room_id") is not None]
        rooms_usados = sorted(set(d["room_id"] for d in con_room))
        resumen_aptos[a] = {
            "dispositivos": len(items),
            "con_room": len(con_room),
            "sin_room": len(items) - len(con_room),
            "rooms_usados": len(rooms_usados),
            "estimacion": est,
        }

    problemas = []
    for r in rooms_sin_prefijo:
        problemas.append({"tipo": "room_sin_prefijo_apto", "room": r["id"],
                          "nombre": r["nombre"]})
    for r in rooms_mezclan:
        problemas.append({"tipo": "room_mezcla_aptos", "room": r["id"],
                          "nombre": r["nombre"], "aptos": r["aptos"]})
    for r in rooms_apto_distinto:
        problemas.append({"tipo": "room_apto_no_coincide", "room": r["id"],
                          "nombre": r["nombre"],
                          "apto_nombre": r["apto_nombre"], "aptos": r["aptos"]})
    for r in rooms:
        lim = r.get("limite_mm")
        if lim is None or lim < MIN_LIMITE_ROOM_MM:
            problemas.append({"tipo": "room_limite_bajo", "room": r["id"],
                              "nombre": r.get("nombre"), "limite_mm": lim})
    for d in sin_room:
        problemas.append({"tipo": "dispositivo_sin_room", "id": d["id"],
                          "mark": d.get("mark"), "pt": d.get("pt")})

    return {
        "rooms": por_room,
        "resumen_aptos": resumen_aptos,
        "rooms_sin_prefijo": len(rooms_sin_prefijo),
        "rooms_mezclan_aptos": len(rooms_mezclan),
        "rooms_apto_no_coincide": len(rooms_apto_distinto),
        "dispositivos_sin_room": len(sin_room),
        "total_dispositivos_marcados": sum(len(v) for v in por_apto.values()),
        "problemas": problemas,
    }


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


def cargar_ids_cocina():
    out = set()
    try:
        p = os.path.join(DEFAULT_ROOT, "data", "f7_cocinas_ids_v01.json")
        with open(p) as f:
            out = set(int(x) for x in json.load(f)["ids"])
    except Exception:
        pass
    return out


def nivel_piso5(doc):
    mejor = None
    mejor_d = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        dd = abs(lvl.Elevation * FT_A_MM - Z_NIVEL_MM)
        if mejor_d is None or dd < mejor_d:
            mejor = lvl
            mejor_d = dd
    return mejor


def recolectar_rooms(doc):
    rooms = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements():
        try:
            numero = texto(el, ["Number"])
            nombre = texto(el, ["Name"])
            nivel = ""
            try:
                if el.Level is not None:
                    nivel = el.Level.Name
            except Exception:
                pass
            area = None
            try:
                a = el.Area
                if a is not None and a > 0:
                    area = round(float(a) * 0.09290304, 2)
            except Exception:
                pass
            base = 0.0
            pb = el.get_Parameter(BuiltInParameter.ROOM_LOWER_OFFSET)
            if pb is not None:
                base = pb.AsDouble() * FT_A_MM
            lim_off = 0.0
            po = el.get_Parameter(BuiltInParameter.ROOM_UPPER_OFFSET)
            if po is not None:
                lim_off = po.AsDouble() * FT_A_MM
            lim_niv = 0.0
            try:
                pu = el.get_Parameter(BuiltInParameter.ROOM_UPPER_LEVEL)
                if pu is not None:
                    lv = doc.GetElement(pu.AsElementId())
                    if lv is not None:
                        lim_niv = float(lv.Elevation) * FT_A_MM
            except Exception:
                pass
            rooms.append({
                "id": id_de(el),
                "numero": numero or "",
                "nombre": nombre or "",
                "nivel": nivel,
                "area_m2": area,
                "base_mm": round(base, 0),
                "limite_mm": round(lim_niv + lim_off, 0),
            })
        except Exception:
            pass
    return rooms


def recolectar_dispositivos(doc, nivel_piso5_id):
    out = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto(el)
            if pt is None:
                continue
            fam, tip = fam_tipo(el)
            mark = texto(el, ["Mark"]) or ""
            room_id = None
            room_num = None
            room_nom = None
            try:
                rm = doc.GetRoomAtPoint(XYZ(pt[0] / FT_A_MM, pt[1] / FT_A_MM,
                                            pt[2] / FT_A_MM))
                if rm is not None:
                    room_id = id_de(rm)
                    room_num = texto(rm, ["Number"])
                    room_nom = texto(rm, ["Name"])
            except Exception:
                pass
            host_id = None
            try:
                h = el.Host
                if h is not None:
                    host_id = id_de(h)
            except Exception:
                pass
            out.append({
                "id": id_de(el),
                "pt": [round(pt[0], 1), round(pt[1], 1), round(pt[2], 1)],
                "mark": mark,
                "familia": fam or "",
                "tipo": tip or "",
                "room_id": room_id,
                "room_numero": room_num,
                "room_nombre": room_nom,
                "host_id": host_id,
            })
    return out


def main():
    log("=" * 74)
    log("RE7_AUDITAR_ROOMS_APARTAMENTOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)
    hubo_cambios = False
    try:
        hubo_cambios = bool(doc.IsModified)
    except Exception:
        pass
    log("modificado_sin_guardar=%s" % hubo_cambios)

    nivel = nivel_piso5(doc)
    if nivel is None:
        log("ERROR: no se encontro Piso 5.")
        return 1
    z_nivel = float(nivel.Elevation) * FT_A_MM
    log("nivel=%r elevacion=%.0f mm" % (nivel.Name, z_nivel))

    rooms = recolectar_rooms(doc)
    log("rooms en el documento: %d" % len(rooms))
    disp = recolectar_dispositivos(doc, id_de(nivel))
    log("dispositivos con punto: %d" % len(disp))

    ids_cocina = cargar_ids_cocina()
    log("ids cocina cargados: %d" % len(ids_cocina))

    rep = auditar_rooms(rooms, disp, ids_cocina)

    log("")
    log("ROOMS (id | numero | nombre | nivel | area | limite sobre piso)")
    for r in sorted(rooms, key=lambda x: (x["nombre"] or "", x["id"])):
        log("  %-9s | %-8s | %-22s | %-8s | %6s m2 | %6s mm" % (
            r["id"], r["numero"], r["nombre"], r["nivel"],
            r["area_m2"], r["limite_mm"]))
    log("")
    log("RESUMEN")
    log("  rooms totales ................ %d" % len(rooms))
    log("  rooms sin prefijo de apto .... %d" % rep["rooms_sin_prefijo"])
    log("  rooms que mezclan aptos ...... %d" % rep["rooms_mezclan_aptos"])
    log("  rooms con apto que no cuadra . %d" % rep["rooms_apto_no_coincide"])
    log("  dispositivos sin room ........ %d" % rep["dispositivos_sin_room"])
    log("")
    log("POR APARTAMENTO (disp | con room | sin room | rooms | bajantes estimadas)")
    total_est = 0
    for a in sorted(rep["resumen_aptos"]):
        s = rep["resumen_aptos"][a]
        total_est += s["estimacion"]["bajantes_estimadas"]
        log("  %-5s %4d | %4d | %3d | %3d rooms | %3d bajantes (datos %d, cocina %d, recintos %d, sin recinto %d)" % (
            a, s["dispositivos"], s["con_room"], s["sin_room"], s["rooms_usados"],
            s["estimacion"]["bajantes_estimadas"], s["estimacion"]["grupos_datos"],
            s["estimacion"]["grupos_cocina"], s["estimacion"]["claves_normales"],
            s["estimacion"]["normales_sin_recinto"]))
    log("  TOTAL bajantes estimadas: %d" % total_est)

    problemas = rep["problemas"]
    log("")
    log("PROBLEMAS: %d" % len(problemas))
    por_tipo = {}
    for p in problemas:
        por_tipo[p["tipo"]] = por_tipo.get(p["tipo"], 0) + 1
    for t in sorted(por_tipo):
        log("  %-26s %d" % (t, por_tipo[t]))
    for p in problemas[:15]:
        log("    %s" % p)

    out = os.path.join(DEFAULT_ROOT, "data", "f7_auditoria_rooms_v01.json")
    try:
        with open(out, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "modificado_sin_guardar": hubo_cambios,
                "nivel": {"nombre": nivel.Name, "elevacion_mm": round(z_nivel, 1)},
                "rooms": rooms,
                "resumen_global": {
                    "rooms": len(rooms),
                    "rooms_sin_prefijo": rep["rooms_sin_prefijo"],
                    "rooms_mezclan_aptos": rep["rooms_mezclan_aptos"],
                    "rooms_apto_no_coincide": rep["rooms_apto_no_coincide"],
                    "dispositivos_sin_room": rep["dispositivos_sin_room"],
                    "dispositivos_marcados": rep["total_dispositivos_marcados"],
                    "bajantes_estimadas_total": total_est,
                },
                "resumen_aptos": rep["resumen_aptos"],
                "problemas": problemas,
            }, ensure_ascii=True, indent=1))
        log("")
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)
        log(traceback.format_exc())
    log("=" * 74)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
