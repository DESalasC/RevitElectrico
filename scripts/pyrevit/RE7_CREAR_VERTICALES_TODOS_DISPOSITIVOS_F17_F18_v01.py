# -*- coding: utf-8 -*-
"""
RE7_CREAR_VERTICALES_TODOS_DISPOSITIVOS_F17_F18_v01.py
Crea conduits verticales (risers) para TODOS los dispositivos electricos
con Mark == 'F17' o Mark == 'F18' en CENTRAL-V01c.

Lee los dispositivos directamente de Revit (no del DXF), asi no depende
del emparejamiento DXF-Revit.

Para M_Comunicaciones crea 2 tubos separados 40mm (convención comunicaciones).
Verifica que no exista ya un conduit en la misma posicion para no duplicar.

Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import math
import os
import sys
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
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit
from System import Int64

VERSION = "v01_vert_todos"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
VERIF_TOL_MM = 10.0
LARGO_MIN_MM = 3.0
OFFSET_COMMS_MM = 40.0  # separacion entre los 2 tubos de comunicaciones

# Categorias que consideramos dispositivos electricos
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
    """Devuelve (x, y, z) en mm de la ubicacion real del elemento."""
    loc = el.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        return [p.X * FT_A_MM, p.Y * FT_A_MM, p.Z * FT_A_MM]
    if isinstance(loc, LocationCurve):
        c = loc.Curve
        # Tomar el punto medio de la curva como referencia
        p0 = c.GetEndPoint(0)
        p1 = c.GetEndPoint(1)
        xm = 0.5 * (p0.X + p1.X) * FT_A_MM
        ym = 0.5 * (p0.Y + p1.Y) * FT_A_MM
        zm = 0.5 * (p0.Z + p1.Z) * FT_A_MM
        return [xm, ym, zm]
    return None


def obtener_mark(el):
    param = el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if param is None:
        param = el.get_Parameter(BuiltInParameter.ALL_INSTANCE_MARK)
    if param is not None and not param.IsReadOnly:
        try:
            return param.AsString()
        except Exception:
            return None
    return None


def familia_tipo(el):
    try:
        sym = el.Symbol
        if sym is not None:
            # Usar SYMBOL_NAME_PARAM porque s.Name no existe en IronPython 2.7
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


def obtener_dispositivos_con_mark(doc, marca):
    """Devuelve lista de (elemento, [x,y,z]) para dispositivos con Mark==marca."""
    resultado = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            mark = obtener_mark(el)
            if mark == marca:
                pt = punto_real(el)
                if pt is not None:
                    resultado.append((el, pt, familia_tipo(el)))
    return resultado


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
                px = p.X * FT_A_MM
                py = p.Y * FT_A_MM
                pz = p.Z * FT_A_MM
                if abs(px - x_mm) < 5.0 and abs(py - y_mm) < 5.0 and abs(pz - z_mm) < 5.0:
                    return True
        except Exception:
            continue
    return False


def crear_conduit(doc, nivel_id, a, b, etiqueta):
    """Crea un conduit entre a y b (coordenadas mm). Devuelve (ok, cid_o_None)."""
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
            ra = [ep0.X * FT_A_MM, ep0.Y * FT_A_MM, ep0.Z * FT_A_MM]
            rb = [ep1.X * FT_A_MM, ep1.Y * FT_A_MM, ep1.Z * FT_A_MM]
            da = dist3d(ra, a)
            db = dist3d(rb, b)
            ok = da < VERIF_TOL_MM and db < VERIF_TOL_MM
            if not ok:
                log("  VERIF FALLO %s: dist_a=%.1f dist_b=%.1f" % (etiqueta, da, db))
        return True, cid
    except Exception as e:
        log("  ERROR creando %s: %s" % (etiqueta, str(e)[:150]))
        return False, None


def dist3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def dist2d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def xyz_mm(x_mm, y_mm, z_mm):
    return XYZ(mm_a_ft(x_mm), mm_a_ft(y_mm), mm_a_ft(z_mm))


def mm_a_ft(mm):
    return mm / FT_A_MM


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


def main():
    log("=" * 66)
    log("RE7_CREAR_VERTICALES_TODOS_DISPOSITIVOS_F17_F18_%s" % VERSION)
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
    log("nivel: {!r} id={}".format(nivel.Name, id_de(nivel)))

    # --- paso 1: borrar conduits verticales existentes en zonas F17/F18 ---
    # (solo verticales: mismo x,y en ambos extremos)
    ids_borrar = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        try:
            loc = el.Location
            if not isinstance(loc, LocationCurve):
                continue
            c = loc.Curve
            p0 = c.GetEndPoint(0)
            p1 = c.GetEndPoint(1)
            xm = 0.5 * (p0.X + p1.X) * FT_A_MM
            ym = 0.5 * (p0.Y + p1.Y) * FT_A_MM
            zm0 = p0.Z * FT_A_MM
            zm1 = p1.Z * FT_A_MM
            es_vertical = abs(xm - (p0.X * FT_A_MM)) < 1.0 and abs(ym - (p0.Y * FT_A_MM)) < 1.0
            if es_vertical and (abs(zm0 - Z_PLENUM_MM) < 100.0 or abs(zm1 - Z_PLENUM_MM) < 100.0):
                if apto_de(xm, ym) is not None:
                    ids_borrar.append(id_de(el))
        except Exception:
            continue

    borrados = 0
    if ids_borrar:
        trans = Transaction(doc, "RE7_BORRAR_VERTICALES_v01")
        trans.Start()
        try:
            for cid in ids_borrar:
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

    # --- paso 2: obtener dispositivos con Mark F17 y F18 ---
    dispositivos = {}
    for marca in ["F17", "F18"]:
        disp = obtener_dispositivos_con_mark(doc, marca)
        dispositivos[marca] = disp
        log("Dispositivos con Mark=%s: %d" % (marca, len(disp)))

    # --- paso 3: crear verticales para cada dispositivo ---
    creados = 0
    fallos = 0
    saltados = 0
    dedup_proximidad = 0

    # Indexar dispositivos por tipo y marca para dedup por proximidad
    # Clave: (marca, tipo_familia) -> lista de (el, pt, desc)
    from collections import defaultdict
    dispositivos_por_tipo = defaultdict(list)
    for marca in ["F17", "F18"]:
        for el, pt, desc in dispositivos[marca]:
            # Extraer tipo de familia del desc (despues del ' | ')
            tipo_fam = desc.split(" | ")[-1] if " | " in desc else desc
            dispositivos_por_tipo[(marca, tipo_fam)].append((el, pt, desc))

    trans = Transaction(doc, "RE7_CREAR_VERTICALES_TODOS_v01")
    trans.Start()
    try:
        for clave in sorted(dispositivos_por_tipo.keys()):
            grupo = dispositivos_por_tipo[clave]
            marca, tipo_fam = clave
            # Ordenar por distancia al plenum (menor Z primero = mas cercano al techo)
            grupo.sort(key=lambda item: abs(item[1][2] - Z_PLENUM_MM))

            # Marcar dispositivos ya cubiertos por dedup de proximidad
            cubierto = set()
            for i, (el_i, pt_i, desc_i) in enumerate(grupo):
                if i in cubierto:
                    continue
                x_i, y_i, z_i = pt_i
                # Buscar dispositivos del mismo tipo a menos de 150mm
                para_eliminar = []
                for j in range(i + 1, len(grupo)):
                    if j in cubierto:
                        continue
                    el_j, pt_j, desc_j = grupo[j]
                    x_j, y_j, z_j = pt_j
                    if dist2d([x_i, y_i], [x_j, y_j]) < 150.0:
                        para_eliminar.append(j)
                        cubierto.add(j)
                        dedup_proximidad += 1
                        log("  DEDUP %s (%.1f,%.1f) cubre a %s (%.1f,%.1f): dist=%.1fmm <150mm" % (
                            desc_i, x_i, y_i, desc_j, x_j, y_j, dist2d([x_i, y_i], [x_j, y_j])))

                # Procesar el dispositivo representante (el mas cercano al plenum)
                x, y, z = pt_i
                desc = desc_i
                el = el_i

                # Si el dispositivo ya esta en plenum, no crear vertical
                if abs(z - Z_PLENUM_MM) < 5.0:
                    saltados += 1
                    log("  SKIP %s (%.1f,%.1f,%.1f): ya en plenum" % (desc, x, y, z))
                    continue

                # Si ya existe conduit en esta posicion, no duplicar
                if existe_conduit_en_posicion(doc, x, y, z):
                    saltados += 1
                    log("  SKIP %s (%.1f,%.1f,%.1f): conduit ya existe" % (desc, x, y, z))
                    continue

                etiqueta = "%s (%.1f,%.1f,%.1f)->plenum" % (desc, x, y, z)
                b = [x, y, Z_PLENUM_MM]

                # Para comunicaciones: crear 2 tubos separados 40mm en Y
                es_comms = "Comunicaciones" in desc or "M_Comunicaciones" in desc
                if es_comms:
                    # Tubo 1: desplazado -20mm en Y
                    ok1, cid1 = crear_conduit(doc, id_de(nivel), [x, y - OFFSET_COMMS_MM / 2.0, z],
                                              [x, y - OFFSET_COMMS_MM / 2.0, Z_PLENUM_MM],
                                              etiqueta + " comms-1")
                    # Tubo 2: desplazado +20mm en Y
                    ok2, cid2 = crear_conduit(doc, id_de(nivel), [x, y + OFFSET_COMMS_MM / 2.0, z],
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
        trans.Commit()
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    log("RESULTADO: %d creados, %d fallos, %d saltados (ya existen/ya en plenum), %d dedup por proximidad <150mm" % (
        creados, fallos, saltados, dedup_proximidad))
    log("NOTA: Elementos de esquina ('coina') con conexion horizontal: revisar manualmente si necesitan vertical.")
    log("FIN")
    log("=" * 66)
    return 0 if fallos == 0 else 1


def apto_de(x_mm, y_mm):
    for nombre in ZONAS:
        z = ZONAS[nombre]
        if z["x_min"] <= x_mm <= z["x_max"] and z["y_min"] <= y_mm <= z["y_max"]:
            return nombre
    return None


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
