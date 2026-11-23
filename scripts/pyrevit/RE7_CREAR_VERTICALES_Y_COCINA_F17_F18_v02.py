# -*- coding: utf-8 -*-
"""
RE7_CREAR_VERTICALES_Y_COCINA_F17_F18_v02.py

Crea conduits verticales (risers) para dispositivos electricos de F17 y F18
en CENTRAL-V01c, desde el dispositivo hasta el plenum (Z=15930).

CAMBIOS v02 (corrige fallos de v01):
  - FIX CRITICO: el bucle de creacion va dentro de una Transaction
    (v01 fallaba con "document has no open transaction").
  - FIX: las alturas de cocina son ABSOLUTAS (Z de Revit), no relativas.
    Se calculan como elevacion_nivel + [700, 1050, 1650].
  - FIX: descarte de outliers de posicion (dispositivos a >30 m de la
    mediana del apartamento, p.ej. x=-40140 mm). NO se usa zona
    geografica para asignar apartamento: el apartamento viene del Mark.
  - Datos / Comunicaciones: 2 tubos separados 40 mm.

Flujo:
  1. Borra conduits existentes en zonas F17/F18 (reprocesamiento limpio).
  2. Lee dispositivos con Mark que empieza por 'F17|' o 'F18|'.
  3. Dedup <150 mm entre dispositivos del mismo tipo/familia: solo el mas
     cercano al plenum recibe vertical.
  4. Crea vertical dispositivo->plenum para cada representante.
  5. Cocina (Comment='Cocina'): cadena pasando por las alturas 0.70,
     1.05 y 1.65 m por encima del nivel, y luego hasta plenum.

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

VERSION = "v02_vert_cocina_fix"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
VERIF_TOL_MM = 10.0
LARGO_MIN_MM = 3.0
OFFSET_COMMS_MM = 40.0    # separacion entre los 2 tubos de datos/comunicaciones
DEDUP_MM = 150.0          # dedup mismo tipo/familia
OUTLIER_MM = 30000.0      # descartar dispositivos a mas de 30 m de la mediana

# Alturas de cocina RELATIVAS al nivel (mm). Se convierten a absolutas.
COCINA_ALTURAS_REL_MM = [700.0, 1050.0, 1650.0]

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


def valor_texto(el, nombres):
    p = obtener_parametro(el, nombres)
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


def obtener_dispositivos(doc):
    """Dispositivos cuya Mark empieza por 'F17|' o 'F18|'."""
    resultado = {"F17": [], "F18": []}
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            mark = valor_texto(el, ["Mark"])
            if not mark or "|" not in mark:
                continue
            apto = mark.split("|")[0]
            if apto not in ("F17", "F18"):
                continue
            pt = punto_real(el)
            if pt is None:
                continue
            resultado[apto].append({
                "el": el,
                "id": id_de(el),
                "pt": pt,
                "mark": mark,
                "comment": valor_texto(el, ["Comments"]),
                "familia": familia_tipo(el),
            })
    return resultado


def mediana(valores):
    v = sorted(valores)
    n = len(v)
    if n == 0:
        return None
    if n % 2 == 1:
        return v[n // 2]
    return 0.5 * (v[n // 2 - 1] + v[n // 2])


def filtrar_outliers(items, etiqueta):
    """Quita dispositivos cuya XY esta a mas de OUTLIER_MM de la mediana."""
    if not items:
        return items
    mx = mediana([i["pt"][0] for i in items])
    my = mediana([i["pt"][1] for i in items])
    limpios = []
    descartados = []
    for it in items:
        d = math.sqrt((it["pt"][0] - mx) ** 2 + (it["pt"][1] - my) ** 2)
        if d > OUTLIER_MM:
            descartados.append((it, d))
        else:
            limpios.append(it)
    for it, d in descartados:
        log("  OUTLIER %s id=%s [%s] (%.1f,%.1f): %.0f mm de la mediana" % (
            etiqueta, it["id"], it["familia"], it["pt"][0], it["pt"][1], d))
    if descartados:
        log("  %s: %d outliers descartados de %d dispositivos" % (
            etiqueta, len(descartados), len(items)))
    return limpios


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


def apto_por_coords(x_mm, y_mm):
    """Solo para delimitar la ZONA DE LIMPIEZA de conduits (no para asignar apto)."""
    if 7000.0 <= x_mm <= 10500.0 and 1000.0 <= y_mm <= 8500.0:
        return "F17"
    if 7000.0 <= x_mm <= 10500.0 and 9000.0 <= y_mm <= 16500.0:
        return "F18"
    return None


def borrar_conduits_zonas(doc):
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
        trans = Transaction(doc, "RE7_BORRAR_CONDUITS_F17_F18_v02")
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


def crear_conduit(doc, nivel_id, a, b, etiqueta):
    """Crea un conduit entre a y b (mm). DEBE llamarse dentro de una Transaction."""
    if dist3d(a, b) < LARGO_MIN_MM:
        return False, None, "largo<min"
    try:
        conduit = Conduit.Create(
            doc, ElementId(Int64(TUBO_E_ID)),
            xyz_mm(a[0], a[1], a[2]),
            xyz_mm(b[0], b[1], b[2]),
            ElementId(Int64(nivel_id)))
        cid = id_de(conduit)
        ok = False
        loc = conduit.Location
        da = db = None
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
            return True, cid, "verif_fallo da=%.1f db=%.1f" % (
                da if da is not None else -1.0, db if db is not None else -1.0)
        return True, cid, None
    except Exception as e:
        return False, None, str(e)[:160]


def construir_cadena_cocina(z_dispositivo, z_nivel_mm):
    """Devuelve la lista de Z absolutas para una cocina, de abajo hacia plenum."""
    objetivo = [z_nivel_mm + h for h in COCINA_ALTURAS_REL_MM]
    objetivo.append(Z_PLENUM_MM)
    objetivo = sorted(objetivo)
    z0 = z_dispositivo
    if z0 < z_nivel_mm + 50.0:
        z0 = z_nivel_mm + 50.0
    cadena = [z0]
    for z in objetivo:
        if z > z0 + 1.0 and z < Z_PLENUM_MM - 1.0:
            cadena.append(z)
    cadena.append(Z_PLENUM_MM)
    # quitar duplicados consecutivos
    limpia = []
    for z in cadena:
        if not limpia or abs(z - limpia[-1]) > 1.0:
            limpia.append(z)
    return limpia


def main():
    log("=" * 70)
    log("RE7_CREAR_VERTICALES_Y_COCINA_F17_F18_%s" % VERSION)
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
    nivel_id = id_de(nivel)
    z_nivel_mm = float(nivel.Elevation) * FT_A_MM
    log("nivel: {!r} id={} elevacion_abs={:.0f} mm".format(nivel.Name, nivel_id, z_nivel_mm))
    log("plenum objetivo Z={:.0f} mm | alturas cocina abs={}".format(
        Z_PLENUM_MM,
        [int(z_nivel_mm + h) for h in COCINA_ALTURAS_REL_MM]))

    # --- Paso 1: limpiar conduits previos en las zonas ---
    borrados = borrar_conduits_zonas(doc)

    # --- Paso 2: dispositivos por Mark ---
    dispositivos = obtener_dispositivos(doc)
    for apto in ["F17", "F18"]:
        log("Dispositivos %s: %d (antes de filtrar outliers)" % (apto, len(dispositivos[apto])))
        dispositivos[apto] = filtrar_outliers(dispositivos[apto], apto)
        log("Dispositivos %s utiles: %d" % (apto, len(dispositivos[apto])))

    # --- Paso 3: crear todo dentro de UNA transaccion ---
    total_creados = 0
    total_fallos = 0
    total_saltados = 0
    total_dedup = 0
    total_segmentos = 0
    resultados = []
    fallos_detalle = []

    trans = Transaction(doc, "RE7_CREAR_VERTICALES_Y_COCINA_F17_F18_v02")
    trans.Start()
    try:
        for apto in ["F17", "F18"]:
            por_tipo = defaultdict(list)
            for d in dispositivos[apto]:
                tipo_fam = d["familia"].split(" | ")[-1] if " | " in d["familia"] else d["familia"]
                por_tipo[tipo_fam].append(d)

            for tipo_fam in sorted(por_tipo.keys()):
                items = por_tipo[tipo_fam]
                items.sort(key=lambda it: abs(it["pt"][2] - Z_PLENUM_MM))

                cubierto = set()
                for i, item in enumerate(items):
                    if i in cubierto:
                        continue
                    x, y, z = item["pt"]

                    for j in range(i + 1, len(items)):
                        if j in cubierto:
                            continue
                        xj, yj = items[j]["pt"][0], items[j]["pt"][1]
                        dj = dist2d([x, y], [xj, yj])
                        if dj < DEDUP_MM:
                            cubierto.add(j)
                            total_dedup += 1

                    # Dispositivo ya en plenum: no necesita riser
                    if z >= Z_PLENUM_MM - 5.0:
                        total_saltados += 1
                        continue

                    comentario = item["comment"] or ""
                    es_cocina = "cocina" in comentario.lower()
                    fam_low = item["familia"].lower()
                    es_datos = ("comunicacion" in fam_low or "datos" in fam_low
                                or "telephone" in fam_low or "data devices" in fam_low)

                    creados_item = 0
                    fallos_item = 0
                    segs_item = 0

                    if es_cocina:
                        cadena = construir_cadena_cocina(z, z_nivel_mm)
                        for k in range(len(cadena) - 1):
                            za, zb = cadena[k], cadena[k + 1]
                            ok, cid, err = crear_conduit(
                                doc, nivel_id, [x, y, za], [x, y, zb],
                                "%s cocina seg %.0f->%.0f" % (apto, za, zb))
                            if ok:
                                segs_item += 1
                            else:
                                fallos_item += 1
                                fallos_detalle.append({
                                    "apto": apto, "id": item["id"],
                                    "segmento": "%.0f->%.0f" % (za, zb),
                                    "error": err,
                                })
                        if segs_item > 0:
                            creados_item = 1
                        else:
                            creados_item = 0
                    elif es_datos:
                        for signo, sufijo in ((-1.0, "comms-1"), (1.0, "comms-2")):
                            yy = y + signo * OFFSET_COMMS_MM / 2.0
                            ok, cid, err = crear_conduit(
                                doc, nivel_id, [x, yy, z], [x, yy, Z_PLENUM_MM],
                                "%s datos %s" % (apto, sufijo))
                            if ok:
                                segs_item += 1
                            else:
                                fallos_item += 1
                                fallos_detalle.append({
                                    "apto": apto, "id": item["id"],
                                    "segmento": sufijo, "error": err,
                                })
                        creados_item = 1 if segs_item > 0 else 0
                    else:
                        ok, cid, err = crear_conduit(
                            doc, nivel_id, [x, y, z], [x, y, Z_PLENUM_MM],
                            "%s %s" % (apto, item["familia"]))
                        if ok:
                            segs_item = 1
                            creados_item = 1
                        else:
                            fallos_item = 1
                            fallos_detalle.append({
                                "apto": apto, "id": item["id"],
                                "segmento": "recto", "error": err,
                            })

                    total_segmentos += segs_item
                    if creados_item:
                        total_creados += 1
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
                        "es_datos": es_datos,
                        "segmentos": segs_item,
                        "fallos": fallos_item,
                    })

        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida, no se creo nada.")
        log(traceback.format_exc())
        return 1

    # --- Paso 4: reporte ---
    raiz = _raiz()
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "nivel": {"nombre": nivel.Name, "id": nivel_id, "elevacion_abs_mm": round(z_nivel_mm, 3)},
        "resumen": {
            "borrados": borrados,
            "dispositivos_con_riser": total_creados,
            "segmentos_creados": total_segmentos,
            "fallos": total_fallos,
            "saltados_ya_en_plenum": total_saltados,
            "dedup_150mm": total_dedup,
        },
        "fallos": fallos_detalle,
        "resultados": resultados,
    }
    out_path = os.path.join(raiz, "data", "f7_verticales_resultado_v02.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=2))
        log("JSON guardado: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    log("")
    log("=" * 70)
    log("RESULTADO: %d borrados | %d dispositivos con riser | %d segmentos | "
        "%d fallos | %d saltados | %d dedup" % (
            borrados, total_creados, total_segmentos, total_fallos,
            total_saltados, total_dedup))
    log("=" * 70)
    return 0 if total_fallos == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
