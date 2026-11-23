# -*- coding: utf-8 -*-
"""
RE7_CREAR_VERTICALES_Y_COCINA_F17_F18_v01.py

Crea conduits verticales (risers) para dispositivos electricos de F17 y F18
en CENTRAL-V01c, desde el dispositivo hasta el plenum (Z=15930).

Flujo:
  1. Borra conduits existentes en zonas F17/F18 (reprocesamiento limpio).
  2. Lee dispositivos de Revit con Mark que empieza por 'F17|' o 'F18|'
     (convencion del vault: apartamento|tablero|circuito).
  3. Dedup <150mm entre dispositivos del mismo tipo/familia: solo el mas
     cercano al plenum recibe vertical.
  4. Crea vertical recto dispositivo->plenum para cada dispositivo.
  5. Para comunicaciones: 2 tubos separados 40mm.
  6. Para cocina (Comment='Cocina'): vertical con escalones en
     alturas 1.05m, 0.70m, 1.65m y luego plenum.
     Secuencia: dispositivo(z) -> 1050 -> 700 -> 1650 -> plenum(15930).

Conduits nunca rectos: solo angulos 90°, 22.5°, 45°. Los verticales son
rectos en Z (angulo 90° respecto al plano horizontal).

Entrada: datos directamente de Revit (Mark, Comment, posicion).
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

VERSION = "v01_vert_cocina"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
VERIF_TOL_MM = 10.0
LARGO_MIN_MM = 3.0
OFFSET_COMMS_MM = 40.0   # separacion entre los 2 tubos de comunicaciones
DEDUP_MM = 150.0         # dedup mismo tipo/familia

# Alturas de cocina en mm (de dispositivo hacia plenum)
COCINA_ESCALONES_MM = [1050.0, 700.0, 1650.0]

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
        xm = 0.5 * (p0.X + p1.X) * FT_A_MM
        ym = 0.5 * (p0.Y + p1.Y) * FT_A_MM
        zm = 0.5 * (p0.Z + p1.Z) * FT_A_MM
        return [xm, ym, zm]
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


def obtener_mark(el):
    p = obtener_parametro(el, ["Mark"])
    if p is not None:
        try:
            return p.AsString()
        except Exception:
            return None
    return None


def obtener_comment(el):
    p = obtener_parametro(el, ["Comments"])
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


def obtener_dispositivos_f17_f18(doc):
    """Dispositivos con Mark que empieza por 'F17|' o 'F18|'."""
    resultado = {"F17": [], "F18": []}
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            mark = obtener_mark(el)
            if not mark:
                continue
            for apto in ("F17", "F18"):
                if mark.startswith(apto + "|"):
                    pt = punto_real(el)
                    if pt is None:
                        continue
                    resultado[apto].append({
                        "el": el,
                        "id": id_de(el),
                        "pt": pt,
                        "mark": mark,
                        "comment": obtener_comment(el),
                        "familia": familia_tipo(el),
                    })
                    break
    return resultado


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


def borrar_conduits_zonas(doc):
    """Borra todos los conduits cuyo punto medio cae en zonas F17/F18."""
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
            xm = 0.5 * (p0.X + p1.X) * FT_A_MM
            ym = 0.5 * (p0.Y + p1.Y) * FT_A_MM
            if apto_por_coords(xm, ym) is not None:
                ids.append(id_de(el))
        except Exception:
            continue

    borrados = 0
    if ids:
        trans = Transaction(doc, "RE7_BORRAR_CONDUITS_F17_F18_v01")
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
    log("Conduits borrados en zonas F17/F18: %d (de %d candidatos)" % (borrados, len(ids)))
    return borrados


def apto_por_coords(x_mm, y_mm):
    """Devuelve 'F17' o 'F18' segun coordenadas (ZONAS hardcoded como referencia)."""
    if 7000.0 <= x_mm <= 10500.0 and 1000.0 <= y_mm <= 8500.0:
        return "F17"
    if 7000.0 <= x_mm <= 10500.0 and 9000.0 <= y_mm <= 16500.0:
        return "F18"
    return None


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
    """Crea un conduit entre a y b (mm). Devuelve (ok, cid)."""
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
        ok = False
        loc = conduit.Location
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


def crear_vertical_cocina(doc, nivel_id, x, y, z_inicial, etiqueta):
    """Crea vertical de cocina con escalones: z_inicial -> 1050 -> 700 -> 1650 -> plenum."""
    puntos = [z_inicial] + COCINA_ESCALONES_MM + [Z_PLENUM_MM]
    # Eliminar duplicados consecutivos y ordenar ascendente hacia plenum
    puntos_filtrados = []
    for zp in puntos:
        if not puntos_filtrados or abs(zp - puntos_filtrados[-1]) > 1.0:
            puntos_filtrados.append(zp)
    # Asegurar que el ultimo es plenum
    if abs(puntos_filtrados[-1] - Z_PLENUM_MM) > 1.0:
        puntos_filtrados.append(Z_PLENUM_MM)

    creados_local = 0
    fallos_local = 0
    for i in range(len(puntos_filtrados) - 1):
        z_a = puntos_filtrados[i]
        z_b = puntos_filtrados[i + 1]
        if abs(z_b - z_a) < 1.0:
            continue
        etiqueta_seg = "%s escalon %.0f->%.0f" % (etiqueta, z_a, z_b)
        ok, cid = crear_conduit(doc, nivel_id, [x, y, z_a], [x, y, z_b], etiqueta_seg)
        if ok:
            creados_local += 1
        else:
            fallos_local += 1
    return creados_local, fallos_local


def main():
    log("=" * 66)
    log("RE7_CREAR_VERTICALES_Y_COCINA_F17_F18_%s  (EJECUCION EN REVIT)" % VERSION)
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

    # Paso 1: borrar conduits existentes en zonas F17/F18
    borrados = borrar_conduits_zonas(doc)

    # Paso 2: obtener dispositivos F17 y F18
    dispositivos = obtener_dispositivos_f17_f18(doc)
    log("Dispositivos F17: %d" % len(dispositivos["F17"]))
    log("Dispositivos F18: %d" % len(dispositivos["F18"]))

    # Paso 3: dedup <150mm mismo tipo/familia, crear verticales
    total_creados = 0
    total_fallos = 0
    total_saltados = 0
    total_dedup = 0
    resultados = []

    for apto in ["F17", "F18"]:
        grupo = dispositivos[apto]
        # Indexar por tipo de familia para dedup
        por_tipo = defaultdict(list)
        for d in grupo:
            tipo_fam = d["familia"].split(" | ")[-1] if " | " in d["familia"] else d["familia"]
            por_tipo[tipo_fam].append(d)

        for tipo_fam in sorted(por_tipo.keys()):
            items = por_tipo[tipo_fam]
            # Ordenar por distancia al plenum (menor Z diferencia = mas cercano al techo)
            items.sort(key=lambda item: abs(item["pt"][2] - Z_PLENUM_MM))

            cubierto = set()
            for i, item_i in enumerate(items):
                if i in cubierto:
                    continue
                x_i, y_i, z_i = item_i["pt"]

                # Dedup: buscar dispositivos del mismo tipo a menos de DEDUP_MM
                for j in range(i + 1, len(items)):
                    if j in cubierto:
                        continue
                    item_j = items[j]
                    x_j, y_j, z_j = item_j["pt"]
                    if dist2d([x_i, y_i], [x_j, y_j]) < DEDUP_MM:
                        cubierto.add(j)
                        total_dedup += 1
                        log("  DEDUP %s (%.1f,%.1f) cubre a %s (%.1f,%.1f): dist=%.1fmm <150mm" % (
                            item_i["familia"], x_i, y_i,
                            item_j["familia"], x_j, y_j,
                            dist2d([x_i, y_i], [x_j, y_j])))

                # Procesar representante (mas cercano al plenum)
                x, y, z = x_i, y_i, z_i
                item = item_i
                etiqueta = "%s %s (%.1f,%.1f,%.1f)" % (apto, item["familia"], x, y, z)

                # Si ya en plenum, saltar
                if abs(z - Z_PLENUM_MM) < 5.0:
                    total_saltados += 1
                    log("  SKIP %s: ya en plenum" % etiqueta)
                    continue

                # Si ya existe conduit en esta posicion, no duplicar
                if existe_conduit_en_posicion(doc, x, y, z):
                    total_saltados += 1
                    log("  SKIP %s: conduit ya existe" % etiqueta)
                    continue

                es_cocina = item["comment"] and "cocina" in item["comment"].lower()
                es_comms = "Comunicaciones" in item["familia"] or "M_Comunicaciones" in item["familia"]

                if es_cocina:
                    # Vertical de cocina con escalones
                    ok1, ok2 = crear_vertical_cocina(doc, id_de(nivel), x, y, z, etiqueta)
                    if ok1 > 0:
                        total_creados += 1
                        log("  OK cocina %s: %d segmentos creados" % (etiqueta, ok1))
                    else:
                        total_fallos += 1
                        log("  FAIL cocina %s: 0 segmentos" % etiqueta)
                    if ok2 > 0:
                        total_fallos += ok2
                elif es_comms:
                    # 2 tubos separados 40mm en Y
                    ok1, cid1 = crear_conduit(doc, id_de(nivel),
                                              [x, y - OFFSET_COMMS_MM / 2.0, z],
                                              [x, y - OFFSET_COMMS_MM / 2.0, Z_PLENUM_MM],
                                              etiqueta + " comms-1")
                    ok2, cid2 = crear_conduit(doc, id_de(nivel),
                                              [x, y + OFFSET_COMMS_MM / 2.0, z],
                                              [x, y + OFFSET_COMMS_MM / 2.0, Z_PLENUM_MM],
                                              etiqueta + " comms-2")
                    if ok1 or ok2:
                        total_creados += 1
                        log("  OK comms %s: tubos=%d" % (etiqueta, (1 if ok1 else 0) + (1 if ok2 else 0)))
                    else:
                        total_fallos += 1
                else:
                    # Vertical recto dispositivo->plenum
                    ok, cid = crear_conduit(doc, id_de(nivel), [x, y, z],
                                            [x, y, Z_PLENUM_MM], etiqueta)
                    if ok:
                        total_creados += 1
                        log("  OK %s: conduit %s" % (etiqueta, cid))
                    else:
                        total_fallos += 1

                resultados.append({
                    "apto": apto,
                    "id": item["id"],
                    "mark": item["mark"],
                    "comment": item["comment"],
                    "familia": item["familia"],
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "z": round(z, 3),
                    "es_cocina": es_cocina,
                    "es_comms": es_comms,
                })

    # Guardar reporte
    raiz = _raiz()
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "borrados": borrados,
            "creados": total_creados,
            "fallos": total_fallos,
            "saltados": total_saltados,
            "dedup": total_dedup,
        },
        "resultados": resultados,
    }
    out_path = os.path.join(raiz, "data", "f7_verticales_resultado_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=2))
        log("JSON guardado: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    log("")
    log("=" * 66)
    log("RESULTADO: %d borrados, %d creados, %d fallos, %d saltados, %d dedup" % (
        borrados, total_creados, total_fallos, total_saltados, total_dedup))
    log("=" * 66)
    return 0 if total_fallos == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
