# -*- coding: utf-8 -*-
"""
RE7_VALIDAR_MARK_Y_CREAR_VERTICAL_v01.py
Para una lista de ElementIds:
1. Obtiene Location.Point real en Revit
2. Busca el bloque DXF mas cercano para extraer circuito y tablero
3. Genera Mark = apartamento|tablero|circuito
4. Valida que el apartamento del Mark coincida con las coordenadas
5. Asigna Mark en Revit
6. Crea conduit vertical hasta plenum Z=15930

Entrada: data/f7_marks_ajuste_9_ids_v01.json (solo IDs, sin mark)
Entorno: pyRevit IronPython 2.7
"""
import json
import math
import os
import sys
import datetime
import traceback

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

VERSION = "v01_validar_mark_y_vertical"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
JSON_IDS_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_ajuste_9_ids_v01.json"
JSON_DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_dxf_circuitos_f17_f18_v01.json"

Z_PLENUM_MM = 15930.0
OFFSET_COMMS_MM = 40.0
VERIF_TOL_MM = 10.0
LARGO_MIN_MM = 3.0
RADIO_DXF_MM = 400.0

TUBO_E_ID = 112216

ZONAS = {
    "F17": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 1000.0, "y_max": 8500.0},
    "F18": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 9000.0, "y_max": 16500.0},
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


def obtener_parametro(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None and not p.IsReadOnly:
                return p
        except Exception:
            continue
    return None


def obtener_valor_parametro(el, nombres):
    p = obtener_parametro(el, nombres)
    if p is not None:
        try:
            return p.AsString()
        except Exception:
            pass
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


def cargar_json(path):
    with open(path, "r") as f:
        return json.load(f)


def cargar_bloques_dxf(path):
    datos = cargar_json(path)
    return datos.get("bloques", [])


def encontrar_circuito_dxf(x_mm, y_mm, bloques_dxf):
    """Busca el bloque DXF mas cercano y devuelve (apto, circuito, tablero, dist, nombre_bloque)."""
    apto_punto = apto_de(x_mm, y_mm)
    if not apto_punto:
        return None, None, None, None, None

    bloques_apto = [b for b in bloques_dxf if b["apto"] == apto_punto]
    if not bloques_apto:
        return apto_punto, None, None, None, None

    mejor = None
    mejor_dist = None
    for b in bloques_apto:
        d = dist2d([x_mm, y_mm], [b["x"], b["y"]])
        if mejor_dist is None or d < mejor_dist:
            mejor = b
            mejor_dist = d

    if mejor is None or mejor_dist > RADIO_DXF_MM:
        return apto_punto, None, None, None, None

    circuito = mejor.get("circuito") or "SIN CIRCUITO"
    if circuito != "SIN CIRCUITO" and "-" in circuito:
        tablero = circuito.split("-")[0]
    else:
        tablero = apto_punto

    return apto_punto, circuito, tablero, mejor_dist, mejor["nombre"]


def existe_conduit_en_posicion(doc, x_mm, y_mm, z_mm):
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


def main():
    log("=" * 70)
    log("RE7_VALIDAR_MARK_Y_CREAR_VERTICAL_%s" % VERSION)
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

    # 1. Cargar IDs
    raiz = _raiz()
    try:
        ids_lista = cargar_json(JSON_IDS_PATH)
    except Exception as ex:
        log("ERROR cargando JSON de IDs: %s" % ex)
        return 1

    # 2. Cargar bloques DXF
    try:
        bloques_dxf = cargar_bloques_dxf(JSON_DXF_PATH)
    except Exception as ex:
        log("ERROR cargando bloques DXF: %s" % ex)
        log("Ejecuta primero RE7_LEER_DXF_CIRCUITOS_F17_F18_v01.py en Python 3")
        return 1

    log("IDs a procesar: %d, Bloques DXF: %d" % (len(ids_lista), len(bloques_dxf)))

    # 3. Procesar cada ID: validar Mark, asignar, crear vertical
    ok_mark = 0
    fail_mark = 0
    creados = 0
    fallos = 0
    saltados = 0

    t = Transaction(doc, "RE7_VALIDAR_MARK_Y_CREAR_VERTICAL_v01")
    t.Start()
    try:
        for item in ids_lista:
            eid = item["id"]
            mark_forzado = item.get("mark", "")  # puede estar vacio
            comment = item.get("comment")

            el = doc.GetElement(ElementId(Int64(eid)))
            if el is None:
                fail_mark += 1
                log("  FAIL id=%s: elemento no encontrado" % eid)
                continue

            pt = punto_real(el)
            if pt is None:
                fail_mark += 1
                log("  FAIL id=%s: sin Location.Point" % eid)
                continue

            x, y, z = pt
            familia = familia_tipo(el)
            apto_punto = apto_de(x, y)

            # --- PASO 1: Validar/Generar Mark ---
            mark_actual = obtener_valor_parametro(el, ["Mark"])
            log("")
            log("ID %s: apto_por_coordenadas=%s, mark_actual=%r" % (eid, apto_punto, mark_actual))

            # Si ya tiene mark, validar que el apartamento coincida
            if mark_actual and "|" in mark_actual:
                apto_en_mark = mark_actual.split("|")[0]
                if apto_en_mark != apto_punto:
                    log("  ADVERTENCIA: Mark dice %s pero coordenadas indican %s" % (apto_en_mark, apto_punto))
                    # Usar el apartamento de las coordenadas, no el del mark
                    apto_para_mark = apto_punto
                else:
                    apto_para_mark = apto_en_mark
                # Mantener el mark actual si es valido
                mark_final = mark_actual
            else:
                # Generar mark desde DXF
                apto_dxf, circuito, tablero, dist, bloque_nombre = encontrar_circuito_dxf(x, y, bloques_dxf)
                if not circuito:
                    log("  ERROR: no se encontro circuito DXF para id=%s" % eid)
                    fail_mark += 1
                    continue
                mark_final = "%s|%s|%s" % (apto_dxf, tablero, circuito)
                log("  Mark generado desde DXF: %r (bloque=%s, dist=%.1fmm)" % (mark_final, bloque_nombre, dist or 0))

            # Validacion final: el apartamento del mark debe coincidir con coordenadas
            apto_en_mark_final = mark_final.split("|")[0]
            if apto_en_mark_final != apto_punto:
                log("  ERROR: apartamento del mark (%s) no coincide con coordenadas (%s)" % (
                    apto_en_mark_final, apto_punto))
                fail_mark += 1
                continue

            # Asignar Mark en Revit
            p_mark = obtener_parametro(el, ["Mark"])
            if p_mark is None:
                fail_mark += 1
                log("  FAIL id=%s: sin parameter Mark" % eid)
                continue
            p_mark.Set(mark_final)

            if comment is not None:
                p_com = obtener_parametro(el, ["Comments"])
                if p_com is not None:
                    p_com.Set(comment)

            ok_mark += 1
            log("  MARK ASIGNADO: %r" % mark_final)

            # --- PASO 2: Crear vertical ---
            etiqueta = "vertical %s (%.1f,%.1f,%.1f)->plenum" % (mark_final, x, y, z)

            if abs(z - Z_PLENUM_MM) < 5.0:
                saltados += 1
                log("  SKIP %s: ya en plenum" % etiqueta)
                continue

            if existe_conduit_en_posicion(doc, x, y, z):
                saltados += 1
                log("  SKIP %s: conduit ya existe" % etiqueta)
                continue

            b = [x, y, Z_PLENUM_MM]

            es_comms = "Comunicaciones" in familia or "Datos" in familia or "M_Comunicaciones" in mark_final
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
    log("RESULTADO: Marks OK=%d, fallos=%d | Verticales creados=%d, fallos=%d, saltados=%d" % (
        ok_mark, fail_mark, creados, fallos, saltados))
    log("=" * 70)
    return 0 if fail_mark == 0 and fallos == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
