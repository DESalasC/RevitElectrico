# -*- coding: utf-8 -*-
"""
RE7_CREAR_VERTICALES_DESDE_MARKS_v01.py
Lee f7_marks_asignados_v01.json (dispositivos con Mark = apartamento|tablero|circuito),
borra conduits verticales existentes en zonas F17/F18 y crea verticales nuevos
desde cada dispositivo hasta plenum Z=15930.

Reglas:
- Dedup por proximidad <150mm entre dispositivos del mismo tipo (familia)
- Comunicaciones (M_Comunicaciones): 2 tubos separados 40mm en Y
- No tocar conduits horizontales existentes

Entorno: pyRevit IronPython 2.7
"""
import json
import math
import os
import sys
import datetime
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

VERSION = "v01_vert_desde_marks"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
JSON_MARKS_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_asignados_v01.json"

Z_PLENUM_MM = 15930.0
RADIO_DEDUP_MM = 150.0
OFFSET_COMMS_MM = 40.0
VERIF_TOL_MM = 10.0
LARGO_MIN_MM = 3.0

ZONAS = {
    "F17": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 1000.0, "y_max": 8500.0},
    "F18": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 9000.0, "y_max": 16500.0},
}

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


def apto_de(x_mm, y_mm):
    for nombre in ZONAS:
        z = ZONAS[nombre]
        if z["x_min"] <= x_mm <= z["x_max"] and z["y_min"] <= y_mm <= z["y_max"]:
            return nombre
    return None


def dist2d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def dist3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def mm_a_ft(mm):
    return mm / 304.8


def xyz_mm(x_mm, y_mm, z_mm):
    return XYZ(mm_a_ft(x_mm), mm_a_ft(y_mm), mm_a_ft(z_mm))


def punto_real(el):
    loc = el.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        return [p.X * 304.8, p.Y * 304.8, p.Z * 304.8]
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
            return "%s" % nom
    except Exception:
        pass
    return el.Category.Name


def cargar_json_marks(path):
    with open(path, "r") as f:
        return json.load(f)


def obtener_dispositivos_desde_json(doc, datos_json):
    """Crea lista de dispositivos a partir del JSON y sus objetos Revit."""
    dispositivos = []
    for r in datos_json.get("resultados", []):
        eid = r["id"]
        el = doc.GetElement(ElementId(Int64(eid)))
        if el is None:
            log("  SKIP id=%s: elemento no encontrado en Revit" % eid)
            continue
        pt = punto_real(el)
        if pt is None:
            log("  SKIP id=%s: sin Location.Point" % eid)
            continue
        dispositivos.append({
            "id": eid,
            "el": el,
            "x": pt[0],
            "y": pt[1],
            "z": pt[2],
            "mark": r["mark"],
            "comment": r["comment"],
            "apto": r["apto"],
            "familia": familia_tipo(el),
        })
    log("Dispositivos desde JSON: %d" % len(dispositivos))
    return dispositivos


def existe_conduit_en_posicion(doc, x_mm, y_mm, z_mm):
    """Verifica si ya hay un conduit cuyo extremo este cerca de (x,y,z)."""
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        try:
            loc = el.Location
            if not isinstance(loc, LocationCurve):
                continue
            c = loc.Curve
            for i in (0, 1):
                p = c.GetEndPoint(i)
                px = p.X * 304.8
                py = p.Y * 304.8
                pz = p.Z * 304.8
                if abs(px - x_mm) < 5.0 and abs(py - y_mm) < 5.0 and abs(pz - z_mm) < 5.0:
                    return True
        except Exception:
            continue
    return False


def crear_conduit(doc, nivel_id, a, b, etiqueta):
    """Crea un conduit entre a y b. Devuelve (ok, cid)."""
    if dist3d(a, b) < LARGO_MIN_MM:
        log("  SKIP %s: largo muy corto (%.1f mm)" % (etiqueta, dist3d(a, b)))
        return False, None
    try:
        conduit = Conduit.Create(
            doc, ElementId(Int64(TUBO_E_ID)),
            xyz_mm(a[0], a[1], a[2]),
            xyz_mm(b[0], b[1], b[2]),
            ElementId(Int64(nivel_id)))
        cid = id_de(conduit)
        # verificar
        loc = conduit.Location
        ok = False
        if isinstance(loc, LocationCurve):
            curva = loc.Curve
            ep0 = curva.GetEndPoint(0)
            ep1 = curva.GetEndPoint(1)
            ra = [ep0.X * 304.8, ep0.Y * 304.8, ep0.Z * 304.8]
            rb = [ep1.X * 304.8, ep1.Y * 304.8, ep1.Z * 304.8]
            da = dist3d(ra, a)
            db = dist3d(rb, b)
            ok = da < VERIF_TOL_MM and db < VERIF_TOL_MM
            if not ok:
                log("  VERIF FALLO %s: dist_a=%.1f dist_b=%.1f" % (etiqueta, da, db))
        return True, cid
    except Exception as e:
        log("  ERROR creando %s: %s" % (etiqueta, str(e)[:150]))
        return False, None


def borrar_verticales_existentes(doc):
    """Borra conduits verticales existentes en zonas F17/F18."""
    ids = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        try:
            loc = el.Location
            if not isinstance(loc, LocationCurve):
                continue
            c = loc.Curve
            p0 = c.GetEndPoint(0)
            p1 = c.GetEndPoint(1)
            xm = 0.5 * (p0.X + p1.X) * 304.8
            ym = 0.5 * (p0.Y + p1.Y) * 304.8
            zm0 = p0.Z * 304.8
            zm1 = p1.Z * 304.8
            es_vertical = abs(p0.X - p1.X) * 304.8 < 1.0 and abs(p0.Y - p1.Y) * 304.8 < 1.0
            toca_plenum = abs(zm0 - Z_PLENUM_MM) < 100.0 or abs(zm1 - Z_PLENUM_MM) < 100.0
            if es_vertical and toca_plenum and apto_de(xm, ym) is not None:
                ids.append(id_de(el))
        except Exception:
            continue
    borrados = 0
    if ids:
        trans = Transaction(doc, "RE7_BORRAR_VERTICALES_PREVIOS_v01")
        trans.Start()
        try:
            for cid in ids:
                try:
                    el = doc.GetElement(ElementId(Int64(cid)))
                    if el is not None:
                        doc.Delete(el.Id)
                        borrados += 1
                except Exception:
                    pass
            trans.Commit()
        except Exception:
            trans.RollBack()
            raise
    log("Conduits verticales borrados en zonas F17/F18: %d" % borrados)
    return borrados


def main():
    log("=" * 70)
    log("RE7_CREAR_VERTICALES_DESDE_MARKS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    log("=" * 70)

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    nivel = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if lvl.Name == "Piso 5":
            nivel = lvl
            break
    if nivel is None:
        log("ERROR: no se encontro nivel Piso 5.")
        return 1
    log("nivel: {!r} id={}".format(nivel.Name, id_de(nivel)))

    # 1. Borrar verticales existentes
    borrados = borrar_verticales_existentes(doc)

    # 2. Cargar JSON de marks
    raiz = _raiz()
    try:
        datos_json = cargar_json_marks(JSON_MARKS_PATH)
    except Exception as ex:
        log("ERROR cargando JSON: %s" % ex)
        return 1

    dispositivos = obtener_dispositivos_desde_json(doc, datos_json)

    # 3. Dedup por proximidad <150mm entre dispositivos del mismo tipo/familia
    # Agrupar por (apto, familia)
    grupos = defaultdict(list)
    for d in dispositivos:
        clave = (d["apto"], d["familia"])
        grupos[clave].append(d)

    # Ordenar cada grupo por distancia al plenum (menor z diferencia = mas cercano al techo)
    for clave in grupos:
        grupos[clave].sort(key=lambda d: abs(d["z"] - Z_PLENUM_MM))

    # Marcar dispositivos cubiertos por dedup
    cubierto = set()
    dedup_count = 0

    dispositivos_a_ruteo = []

    for clave in sorted(grupos.keys()):
        grupo = grupos[clave]
        for i, d_i in enumerate(grupo):
            if i in cubierto:
                continue
            x_i, y_i = d_i["x"], d_i["y"]
            # Buscar dispositivos del mismo grupo a menos de 150mm
            for j in range(i + 1, len(grupo)):
                if j in cubierto:
                    continue
                d_j = grupo[j]
                if dist2d([x_i, y_i], [d_j["x"], d_j["y"]]) < RADIO_DEDUP_MM:
                    cubierto.add(j)
                    dedup_count += 1
                    log("  DEDUP %s (%.1f,%.1f) cubre a %s (%.1f,%.1f): dist=%.1fmm <150mm" % (
                        d_i["familia"], x_i, y_i, d_j["familia"], d_j["x"], d_j["y"],
                        dist2d([x_i, y_i], [d_j["x"], d_j["y"]])))
            dispositivos_a_ruteo.append(d_i)

    log("Dispositivos para ruteo despues dedup: %d (dedup=%d)" % (len(dispositivos_a_ruteo), dedup_count))

    # 4. Crear verticales
    creados = 0
    fallos = 0
    saltados = 0

    t = Transaction(doc, "RE7_CREAR_VERTICALES_DESDE_MARKS_v01")
    t.Start()
    try:
        for d in dispositivos_a_ruteo:
            x, y, z = d["x"], d["y"], d["z"]
            familia = d["familia"]

            # Si ya en plenum, saltar
            if abs(z - Z_PLENUM_MM) < 5.0:
                saltados += 1
                log("  SKIP %s (%.1f,%.1f): ya en plenum" % (d["mark"], x, y))
                continue

            # Si ya existe conduit en esta posicion, no duplicar
            if existe_conduit_en_posicion(doc, x, y, z):
                saltados += 1
                log("  SKIP %s (%.1f,%.1f): conduit ya existe" % (d["mark"], x, y))
                continue

            etiqueta = "%s (%.1f,%.1f,%.1f)->plenum" % (d["mark"], x, y, z)
            b = [x, y, Z_PLENUM_MM]

            es_comms = "Comunicaciones" in familia or "Datos" in familia or "M_Comunicaciones" in d["mark"]
            if es_comms:
                ok1, cid1 = crear_conduit(doc, id_de(nivel),
                                          [x, y - OFFSET_COMMS_MM / 2.0, z],
                                          [x, y - OFFSET_COMMS_MM / 2.0, Z_PLENUM_MM],
                                          etiqueta + " comms-1")
                ok2, cid2 = crear_conduit(doc, id_de(nivel),
                                          [x, y + OFFSET_COMMS_MM / 2.0, z],
                                          [x, y + OFFSET_COMMS_MM / 2.0, Z_PLENUM_MM],
                                          etiqueta + " comms-2")
                if ok1 or ok2:
                    creados += 1
                else:
                    fallos += 1
            else:
                ok, cid = crear_conduit(doc, id_de(nivel), [x, y, z], b, etiqueta)
                if ok:
                    creados += 1
                else:
                    fallos += 1
        t.Commit()
    except Exception:
        t.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    log("")
    log("=" * 70)
    log("RESULTADO: %d borrados, %d creados, %d fallos, %d saltados, %d dedup" % (
        borrados, creados, fallos, saltados, dedup_count))
    log("=" * 70)
    return 0 if fallos == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
