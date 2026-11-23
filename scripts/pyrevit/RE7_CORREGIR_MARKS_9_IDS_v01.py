# -*- coding: utf-8 -*-
"""
RE7_CORREGIR_MARKS_9_IDS_v01.py
Corrige los Mark de 9 ElementIds especificos y de cualquier ELEC-TEL/Datos
que tenga 'SIN CIRCUITO' en el mark.

Reglas:
- ELEC-TEL / M_Comunicaciones / Datos: circuito = 'Datos' (no hay circuito en DXF)
- Tomas/Interruptores/Iluminacion: buscar circuito real del DXF mas cercano
- Mark: apartamento|tablero|circuito
- Validar que apartamento del mark coincida con coordenadas

Entrada: data/f7_marks_ajuste_9_ids_v01.json + data/f7_dxf_circuitos_f17_f18_v01.json
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
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    Transaction,
)
from System import Int64

VERSION = "v01_corregir_9_ids"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
JSON_IDS_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_ajuste_9_ids_v01.json"
JSON_DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_dxf_circuitos_f17_f18_v01.json"

ZONAS = {
    "F17": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 1000.0, "y_max": 8500.0},
    "F18": {"x_min": 7000.0, "x_max": 10500.0, "y_min": 9000.0, "y_max": 16500.0},
}

RADIO_DXF_MM = 400.0

CATEGORIAS_REVIT = [
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


def apto_de(x_mm, y_mm):
    for nombre in ZONAS:
        z = ZONAS[nombre]
        if z["x_min"] <= x_mm <= z["x_max"] and z["y_min"] <= y_mm <= z["y_max"]:
            return nombre
    return None


def dist2d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def punto_real(el):
    loc = el.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        return [p.X * 304.8, p.Y * 304.8, p.Z * 304.8]
    if isinstance(loc, LocationCurve):
        c = loc.Curve
        # Para elementos face-based (tomas en pared), tomar el punto medio de la curva
        p0 = c.GetEndPoint(0)
        p1 = c.GetEndPoint(1)
        xm = 0.5 * (p0.X + p1.X) * 304.8
        ym = 0.5 * (p0.Y + p1.Y) * 304.8
        zm = 0.5 * (p0.Z + p1.Z) * 304.8
        return [xm, ym, zm]
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


def es_datos_o_comunicaciones(familia, nombre_bloque_dxf):
    """Detecta si es un dispositivo de datos/comunicaciones (sin circuito en DXF)."""
    f = (familia or "").lower()
    b = (nombre_bloque_dxf or "").lower()
    if "comunic" in f or "datos" in f or "tel" in f:
        return True
    if "elec-tel" in b or "elec-net" in b:
        return True
    return False


def encontrar_circuito_dxf(x_mm, y_mm, apto, bloques_dxf):
    """Busca el bloque DXF mas cercano del mismo apartamento y devuelve circuito."""
    bloques_apto = [b for b in bloques_dxf if b["apto"] == apto]
    if not bloques_apto:
        return None, None, None

    mejor = None
    mejor_dist = None
    for b in bloques_apto:
        d = dist2d([x_mm, y_mm], [b["x"], b["y"]])
        if mejor_dist is None or d < mejor_dist:
            mejor = b
            mejor_dist = d

    if mejor is None or mejor_dist > RADIO_DXF_MM:
        return None, None, None

    circuito = mejor.get("circuito") or "SIN CIRCUITO"
    tablero = circuito.split("-")[0] if circuito != "SIN CIRCUITO" and "-" in circuito else apto
    return circuito, tablero, mejor["nombre"]


def main():
    log("=" * 70)
    log("RE7_CORREGIR_MARKS_9_IDS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    log("=" * 70)

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    raiz = _raiz()

    # 1. Cargar IDs a corregir
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
        return 1

    # 3. Obtener TODOS los dispositivos de Revit en F17/F18 para corregir ELEC-TEL con SIN CIRCUITO
    dispositivos_revit = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_TelephoneDevices).ToElements():
        pt = punto_real(el)
        if pt and apto_de(pt[0], pt[1]):
            dispositivos_revit.append({
                "id": id_de(el),
                "x": pt[0],
                "y": pt[1],
                "z": pt[2],
                "apto": apto_de(pt[0], pt[1]),
                "familia": familia_tipo(el),
                "elemento": el,
                "mark_actual": obtener_valor_parametro(el, ["Mark"]),
            })
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_CommunicationDevices).ToElements():
        pt = punto_real(el)
        if pt and apto_de(pt[0], pt[1]):
            dispositivos_revit.append({
                "id": id_de(el),
                "x": pt[0],
                "y": pt[1],
                "z": pt[2],
                "apto": apto_de(pt[0], pt[1]),
                "familia": familia_tipo(el),
                "elemento": el,
                "mark_actual": obtener_valor_parametro(el, ["Mark"]),
            })
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_DataDevices).ToElements():
        pt = punto_real(el)
        if pt and apto_de(pt[0], pt[1]):
            dispositivos_revit.append({
                "id": id_de(el),
                "x": pt[0],
                "y": pt[1],
                "z": pt[2],
                "apto": apto_de(pt[0], pt[1]),
                "familia": familia_tipo(el),
                "elemento": el,
                "mark_actual": obtener_valor_parametro(el, ["Mark"]),
            })

    log("Dispositivos Datos/Comunicaciones en F17/F18: %d" % len(dispositivos_revit))

    # 4. Procesar: corregir 9 IDs + ELEC-TEL con SIN CIRCUITO
    ok = 0
    fail = 0

    ids_a_corregir = {item["id"]: item for item in ids_lista}

    t = Transaction(doc, "RE7_CORREGIR_MARKS_9_IDS_v01")
    t.Start()
    try:
        # A. Corregir los 9 IDs especificos
        for eid, item in ids_a_corregir.items():
            el = doc.GetElement(ElementId(Int64(eid)))
            if el is None:
                fail += 1
                log("  FAIL id=%s: elemento no encontrado" % eid)
                continue

            pt = punto_real(el)
            if pt is None:
                fail += 1
                log("  FAIL id=%s: sin Location.Point" % eid)
                continue

            x, y, z = pt
            apto = apto_de(x, y)
            familia = familia_tipo(el)
            bloque_nombre = item.get("bloque_dxf", "")

            es_datos = es_datos_o_comunicaciones(familia, bloque_nombre)

            if es_datos:
                # Para datos: circuito = "Datos", tablero = TF
                circuito = "Datos"
                tablero = "TF"
                mark_final = "%s|%s|%s" % (apto, tablero, circuito)
                log("  ID %s [%s]: Datos -> Mark=%r" % (eid, familia, mark_final))
            else:
                # Para tomas/otros: buscar circuito del DXF
                circuito, tablero, bloque_nombre_dxf = encontrar_circuito_dxf(x, y, apto, bloques_dxf)
                if not circuito:
                    fail += 1
                    log("  FAIL id=%s: no se encontro circuito DXF" % eid)
                    continue
                mark_final = "%s|%s|%s" % (apto, tablero, circuito)
                log("  ID %s [%s]: DXF circuito=%s -> Mark=%r" % (
                    eid, familia, circuito, mark_final))

            # Validar apartamento del mark
            apto_en_mark = mark_final.split("|")[0]
            if apto_en_mark != apto:
                fail += 1
                log("  ERROR id=%s: apartamento mark=%s != coordenadas=%s" % (
                    eid, apto_en_mark, apto))
                continue

            # Asignar Mark
            p_mark = obtener_parametro(el, ["Mark"])
            if p_mark is None:
                fail += 1
                log("  FAIL id=%s: sin parameter Mark" % eid)
                continue
            p_mark.Set(mark_final)
            ok += 1

        # B. Corregir ELEC-TEL/Datos que tengan 'SIN CIRCUITO' en el mark
        for disp in dispositivos_revit:
            mark_actual = disp["mark_actual"] or ""
            if "SIN CIRCUITO" in mark_actual:
                eid = disp["id"]
                apto = disp["apto"]
                familia = disp["familia"]

                # Verificar que sea realmente datos/comunicaciones
                if not es_datos_o_comunicaciones(familia, ""):
                    continue

                mark_final = "%s|TF|Datos" % apto
                log("  ID %s [%s]: SIN CIRCUITO -> Mark=%r" % (eid, familia, mark_final))

                el = disp["elemento"]
                p_mark = obtener_parametro(el, ["Mark"])
                if p_mark is None:
                    fail += 1
                    log("  FAIL id=%s: sin parameter Mark" % eid)
                    continue
                p_mark.Set(mark_final)
                ok += 1

        t.Commit()
    except Exception:
        t.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    log("")
    log("=" * 70)
    log("RESULTADO: %d corregidos OK, %d fallos" % (ok, fail))
    log("=" * 70)
    return 0 if fail == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
