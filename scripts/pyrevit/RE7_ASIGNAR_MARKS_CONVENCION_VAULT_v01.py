# -*- coding: utf-8 -*-
"""
RE7_ASIGNAR_MARKS_CONVENCION_VAULT_v01.py
Asigna Marks a dispositivos electricos siguiendo la convencion del vault:
    apartamento|tablero|circuito

Fuentes de datos:
- Apartamento: del Mark existente (antes del primer "|") o de JSON de IDs especificos
- Tablero: del circuito (antes del "-") o "TF" para datos/comunicaciones
- Circuito: del bloque DXF mas cercano (misma zona de apartamento) o "Datos" para ELEC-TEL/M_Comunicaciones
- Comment: "Cocina" si el dispositivo ya tiene ese comment en Revit

Entrada:
  data/f7_dxf_circuitos_f17_f18_v01.json  (bloques DXF con circuitos)
  data/f7_ids_a_asignar_v01.json          (opcional: lista de IDs con apartamento forzado)

Entorno: pyRevit IronPython 2.7 (dentro de Revit)
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

VERSION = "v01_conv_vault"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
JSON_DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_dxf_circuitos_f17_f18_v01.json"
JSON_IDS_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f7_ids_a_asignar_v01.json"
OUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\f7_marks_asignados_conven_v01.json"

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


def dist2d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def punto_real(el):
    """Devuelve [x, y, z] en mm de la ubicacion real del elemento."""
    loc = el.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        return [p.X * 304.8, p.Y * 304.8, p.Z * 304.8]
    if isinstance(loc, LocationCurve):
        c = loc.Curve
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


def apartamento_de_mark(mark):
    """Extrae el apartamento de un Mark (antes del primer '|')."""
    if mark and "|" in mark:
        return mark.split("|")[0]
    return None


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
    bloques_apto = [b for b in bloques_dxf if b.get("apto") == apto]
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


def generar_mark(apto, familia, nombre_bloque_dxf, x_mm, y_mm, bloques_dxf):
    """Genera el Mark completo: apartamento|tablero|circuito."""
    es_datos = es_datos_o_comunicaciones(familia, nombre_bloque_dxf)

    if es_datos:
        return "%s|TF|Datos" % apto, "Datos"

    circuito, tablero, bloque_nombre = encontrar_circuito_dxf(x_mm, y_mm, apto, bloques_dxf)
    if not circuito:
        return None, None

    mark = "%s|%s|%s" % (apto, tablero, circuito)
    return mark, circuito


def main():
    log("=" * 70)
    log("RE7_ASIGNAR_MARKS_CONVENCION_VAULT_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    log("=" * 70)

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    raiz = _raiz()

    # 1. Cargar bloques DXF
    try:
        bloques_dxf = cargar_bloques_dxf(JSON_DXF_PATH)
    except Exception as ex:
        log("ERROR cargando bloques DXF: %s" % ex)
        log("Ejecuta primero RE7_LEER_DXF_CIRCUITOS_F17_F18_v01.py en Python 3")
        return 1
    log("Bloques DXF cargados: %d" % len(bloques_dxf))

    # 2. Cargar IDs con apartamento forzado (opcional)
    ids_forzados = {}
    try:
        ids_lista = cargar_json(JSON_IDS_PATH)
        for item in ids_lista:
            eid = item.get("id")
            apto = item.get("apto", "")
            if eid and apto:
                ids_forzados[int(eid)] = apto
        log("IDs forzados desde JSON: %d" % len(ids_forzados))
    except Exception:
        log("No hay JSON de IDs forzados (opcional).")
        ids_forzados = {}

    # 3. Obtener todos los dispositivos de Revit
    dispositivos = []
    for cat in CATEGORIAS_REVIT:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto_real(el)
            if pt is None:
                continue
            mark_actual = obtener_valor_parametro(el, ["Mark"])
            apto_mark = apartamento_de_mark(mark_actual)
            # Apartamento forzado tiene prioridad
            apto_fuente = ids_forzados.get(id_de(el), apto_mark)
            dispositivos.append({
                "id": id_de(el),
                "x": pt[0],
                "y": pt[1],
                "z": pt[2],
                "apto_fuente": apto_fuente,
                "familia": familia_tipo(el),
                "elemento": el,
                "mark_actual": mark_actual,
                "comment_actual": obtener_valor_parametro(el, ["Comments"]),
                "nombre_bloque_dxf": None,  # se llena si se usa DXF
            })

    log("Dispositivos en Revit: %d" % len(dispositivos))
    log("Dispositivos con apartamento fuente: %d" % sum(1 for d in dispositivos if d["apto_fuente"]))
    log("Dispositivos SIN apartamento fuente: %d" % sum(1 for d in dispositivos if not d["apto_fuente"]))

    # 4. Generar Marks y asignar en Revit
    ok = 0
    fail = 0
    sin_apto = 0
    sin_circuito = 0

    resultados = []

    t = Transaction(doc, "RE7 Asignar Marks Convencion Vault")
    t.Start()
    try:
        for disp in dispositivos:
            eid = disp["id"]
            el = disp["elemento"]
            apto = disp["apto_fuente"]
            familia = disp["familia"]

            if not apto:
                sin_apto += 1
                log("  SIN APTO id=%s [%s]" % (eid, familia))
                continue

            # Determinar nombre del bloque DXF para detectar datos
            nombre_bloque = None
            if disp["nombre_bloque_dxf"]:
                nombre_bloque = disp["nombre_bloque_dxf"]

            mark, circuito = generar_mark(
                apto, familia, nombre_bloque, disp["x"], disp["y"], bloques_dxf)

            if not mark:
                sin_circuito += 1
                log("  SIN CIRCUITO id=%s [%s] apto=%s" % (eid, familia, apto))
                continue

            comment = "Cocina" if (disp["comment_actual"] and "cocina" in disp["comment_actual"].lower()) else None

            # Asignar Mark
            p_mark = obtener_parametro(el, ["Mark"])
            if p_mark is None:
                fail += 1
                log("  FAIL id=%s: sin parameter Mark" % eid)
                continue
            p_mark.Set(mark)

            if comment is not None:
                p_com = obtener_parametro(el, ["Comments"])
                if p_com is not None:
                    p_com.Set(comment)

            ok += 1
            resultados.append({
                "id": eid,
                "mark": mark,
                "circuito": circuito,
                "comment": comment,
                "apto": apto,
                "familia": familia,
                "mark_anterior": disp["mark_actual"],
            })
            log("  OK id=%s -> Mark=%r Comment=%r" % (eid, mark, comment))

        t.Commit()
    except Exception:
        t.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    # 5. Guardar reporte JSON
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "total_dispositivos": len(dispositivos),
            "asignados_ok": ok,
            "fallos": fail,
            "sin_apartamento": sin_apto,
            "sin_circuito": sin_circuito,
        },
        "resultados": resultados,
    }

    out_path = os.path.join(raiz, "data", "f7_marks_asignados_conven_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=2))
        log("JSON guardado: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    log("")
    log("=" * 70)
    log("RESULTADO: %d OK, %d fallos, %d sin apartamento, %d sin circuito" % (
        ok, fail, sin_apto, sin_circuito))
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
