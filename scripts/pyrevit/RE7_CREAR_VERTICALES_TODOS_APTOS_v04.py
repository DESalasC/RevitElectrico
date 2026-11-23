# -*- coding: utf-8 -*-
"""
RE7_CREAR_VERTICALES_TODOS_APTOS_v04.py

Crea los conduits verticales (risers) de TODOS los apartamentos en
CENTRAL-V01c, desde cada dispositivo hasta el plenum (Z=15930).

Diferencia con v03 (que era solo F17/F18):
  * Recorre todos los apartamentos segun el Mark (apto|tablero|circuito).
  * NO borra nada: si un dispositivo ya tiene un riser hasta el plenum
    (conduit vertical con extremo superior en Z=15930 a <=50 mm en XY),
    lo omite. Asi F17/F18 (ya validados) quedan intactos.
  * Dedup <150 mm por (apartamento, tipo): solo el mas cercano al plenum.
  * Datos / Comunicaciones: 2 tubos separados 40 mm.
  * Cocina (Comment='Cocina'): cadena por alturas nivel+[700,1050,1650].
  * Descarta posiciones apiladas (>=4 dispositivos en 20 mm) y outliers
    (>30 m de la mediana del apartamento).
  * Toda la creacion en UNA transaccion.

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

VERSION = "v04_vert_todos"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
Z_TOL_MM = 25.0
VERIF_TOL_MM = 10.0
LARGO_MIN_MM = 3.0
OFFSET_COMMS_MM = 40.0
DEDUP_MM = 150.0
OUTLIER_MM = 30000.0
TOL_EXISTENTE_MM = 50.0
APILADO_MM = 20.0

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
        return [
            0.5 * (p0.X + p1.X) * FT_A_MM,
            0.5 * (p0.Y + p1.Y) * FT_A_MM,
            0.5 * (p0.Z + p1.Z) * FT_A_MM,
        ]
    return None


def extremos_conduit(el):
    try:
        loc = el.Location
        if not isinstance(loc, LocationCurve):
            return None
        c = loc.Curve
        e0 = c.GetEndPoint(0)
        e1 = c.GetEndPoint(1)
        return (
            [e0.X * FT_A_MM, e0.Y * FT_A_MM, e0.Z * FT_A_MM],
            [e1.X * FT_A_MM, e1.Y * FT_A_MM, e1.Z * FT_A_MM],
        )
    except Exception:
        return None


def valor_texto(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None:
                s = p.AsString()
                if s is not None:
                    return s
        except Exception:
            pass
    return None


def nombre_familia(el):
    try:
        if el.Symbol is not None and el.Symbol.Family is not None:
            return el.Symbol.Family.Name
    except Exception:
        pass
    return None


def familia_tipo(el):
    try:
        if el.Symbol is not None:
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            nom = p.AsString() if p is not None else str(el.Symbol.Id)
            fam = nombre_familia(el) or "?"
            return "%s | %s" % (fam, nom)
    except Exception:
        pass
    return nombre_familia(el) or "?"


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz_mm(x, y, z):
    return XYZ(mm_a_ft(x), mm_a_ft(y), mm_a_ft(z))


def dist3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def dist2d(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def mediana(v):
    s = sorted(v)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


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
    log("=" * 70)
    log("RE7_CREAR_VERTICALES_TODOS_APTOS_%s" % VERSION)
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
    z_nivel = float(nivel.Elevation) * FT_A_MM
    log("nivel=%r id=%s elevacion=%.0f mm | plenum=%.0f mm" % (
        nivel.Name, nivel_id, z_nivel, Z_PLENUM_MM))
    log("alturas cocina abs=%s" % [int(z_nivel + h) for h in COCINA_ALTURAS_REL_MM])

    # --- dispositivos con Mark completo ---
    disp = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            mk = valor_texto(el, ["Mark"]) or ""
            partes = mk.split("|")
            if len(partes) != 3 or not partes[0]:
                continue
            pt = punto_real(el)
            if pt is None:
                continue
            disp.append({
                "el": el, "id": id_de(el), "pt": pt, "mark": mk,
                "apto": partes[0],
                "comment": valor_texto(el, ["Comments"]),
                "familia": familia_tipo(el),
                "tipo": partes[2],
            })

    aptos = sorted(set(d["apto"].upper() for d in disp))
    log("Dispositivos con Mark: %d en %d apartamentos" % (len(disp), len(aptos)))

    # --- risers existentes (para no duplicar ni tocar F17/F18) ---
    existentes = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        par = extremos_conduit(el)
        if par is None:
            continue
        e0, e1 = par
        if abs(e0[0] - e1[0]) > 2.0 or abs(e0[1] - e1[1]) > 2.0:
            continue
        if abs(max(e0[2], e1[2]) - Z_PLENUM_MM) > Z_TOL_MM:
            continue
        existentes.append((e0[0], e0[1]))
    log("Risers existentes hasta plenum: %d" % len(existentes))

    # --- apilados por apartamento ---
    apilados = set()
    por_apto_xy = defaultdict(list)
    for d in disp:
        por_apto_xy[d["apto"].upper()].append(d)
    for apto, items in por_apto_xy.items():
        grupos = defaultdict(list)
        for d in items:
            grupos[(int(round(d["pt"][0] / APILADO_MM)),
                    int(round(d["pt"][1] / APILADO_MM)))].append(d["id"])
        for k, ids in grupos.items():
            if len(ids) >= 4:
                for i in ids:
                    apilados.add(i)

    def tiene_riser(x, y):
        for (ex, ey) in existentes:
            if dist2d(x, y, ex, ey) <= TOL_EXISTENTE_MM:
                return True
        return False

    # --- creacion ---
    creados = 0
    segmentos = 0
    fallos = 0
    saltados_existente = 0
    saltados_apilado = 0
    dedup = 0
    fallos_detalle = []
    por_apto = defaultdict(lambda: {"disp": 0, "risers": 0, "seg": 0, "dedup": 0,
                                    "saltados": 0, "fallos": 0})

    trans = Transaction(doc, "RE7_VERTICALES_TODOS_v04")
    trans.Start()
    try:
        for apto in aptos:
            items = por_apto_xy[apto]
            mx = mediana([d["pt"][0] for d in items])
            my = mediana([d["pt"][1] for d in items])
            limpios = []
            for d in items:
                if d["id"] in apilados:
                    saltados_apilado += 1
                    por_apto[apto]["saltados"] += 1
                    continue
                if dist2d(d["pt"][0], d["pt"][1], mx, my) > OUTLIER_MM:
                    continue
                limpios.append(d)
            por_apto[apto]["disp"] = len(limpios)

            grupos = defaultdict(list)
            for d in limpios:
                grupos[d["familia"].split(" | ")[-1]].append(d)

            for tipo_fam in sorted(grupos.keys()):
                g = grupos[tipo_fam]
                g.sort(key=lambda d: abs(d["pt"][2] - Z_PLENUM_MM))
                cubierto = set()
                for i, d in enumerate(g):
                    if i in cubierto:
                        continue
                    x, y, z = d["pt"]
                    for j in range(i + 1, len(g)):
                        if j in cubierto:
                            continue
                        if dist2d(x, y, g[j]["pt"][0], g[j]["pt"][1]) < DEDUP_MM:
                            cubierto.add(j)
                            dedup += 1
                            por_apto[apto]["dedup"] += 1

                    if z >= Z_PLENUM_MM - 5.0:
                        saltados_existente += 1
                        por_apto[apto]["saltados"] += 1
                        continue
                    if tiene_riser(x, y):
                        saltados_existente += 1
                        por_apto[apto]["saltados"] += 1
                        continue

                    com = (d["comment"] or "").lower()
                    es_cocina = "cocina" in com
                    fl = d["familia"].lower() + " " + (d["tipo"] or "").lower()
                    es_datos = any(k in fl for k in
                                   ("comunicacion", "datos", "telephone", "data devices", "pau"))

                    segs = 0
                    fails = 0

                    if es_cocina:
                        objetivo = [z_nivel + h for h in COCINA_ALTURAS_REL_MM]
                        objetivo.append(Z_PLENUM_MM)
                        z0 = max(z, z_nivel + 50.0)
                        cadena = [z0]
                        for zz in sorted(objetivo):
                            if zz > z0 + 1.0 and zz < Z_PLENUM_MM - 1.0:
                                cadena.append(zz)
                        cadena.append(Z_PLENUM_MM)
                        tramos = [(cadena[k], cadena[k + 1]) for k in range(len(cadena) - 1)
                                  if abs(cadena[k + 1] - cadena[k]) > 1.0]
                    elif es_datos:
                        tramos = []
                        for signo in (-1.0, 1.0):
                            yy = y + signo * OFFSET_COMMS_MM / 2.0
                            tramos.append((yy, yy))
                    else:
                        tramos = [(y, y)]

                    if es_datos:
                        for signo in (-1.0, 1.0):
                            yy = y + signo * OFFSET_COMMS_MM / 2.0
                            try:
                                Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                               xyz_mm(x, yy, z), xyz_mm(x, yy, Z_PLENUM_MM),
                                               ElementId(Int64(nivel_id)))
                                segs += 1
                            except Exception as ex:
                                fails += 1
                                fallos_detalle.append({"apto": apto, "id": d["id"],
                                                       "err": str(ex)[:120]})
                    elif es_cocina:
                        for (za, zb) in tramos:
                            try:
                                Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                               xyz_mm(x, y, za), xyz_mm(x, y, zb),
                                               ElementId(Int64(nivel_id)))
                                segs += 1
                            except Exception as ex:
                                fails += 1
                                fallos_detalle.append({"apto": apto, "id": d["id"],
                                                       "tramo": "%.0f->%.0f" % (za, zb),
                                                       "err": str(ex)[:120]})
                    else:
                        try:
                            Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                           xyz_mm(x, y, z), xyz_mm(x, y, Z_PLENUM_MM),
                                           ElementId(Int64(nivel_id)))
                            segs += 1
                        except Exception as ex:
                            fails += 1
                            fallos_detalle.append({"apto": apto, "id": d["id"],
                                                   "err": str(ex)[:120]})

                    segmentos += segs
                    if segs > 0:
                        creados += 1
                        por_apto[apto]["risers"] += 1
                        por_apto[apto]["seg"] += segs
                    else:
                        fallos += 1
                        por_apto[apto]["fallos"] += 1

        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida, no se creo nada.")
        log(traceback.format_exc())
        return 1

    total_conduits = len(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Conduit).ToElements())

    log("")
    log("=" * 70)
    log("RESULTADO: %d dispositivos con riser | %d segmentos | %d fallos" % (
        creados, segmentos, fallos))
    log("Saltados: %d ya tenian riser/en plenum | %d apilados | dedup %d" % (
        saltados_existente, saltados_apilado, dedup))
    log("Conduits totales en el documento: %d" % total_conduits)
    log("")
    log("%-8s %5s %5s %5s %5s %5s %5s" % ("APTO", "disp", "riser", "seg", "dedup", "salt", "fall"))
    for a in sorted(por_apto.keys()):
        v = por_apto[a]
        log("%-8s %5d %5d %5d %5d %5d %5d" % (
            a, v["disp"], v["risers"], v["seg"], v["dedup"], v["saltados"], v["fallos"]))
    log("=" * 70)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "dispositivos": len(disp),
            "apartamentos": len(aptos),
            "creados": creados,
            "segmentos": segmentos,
            "fallos": fallos,
            "saltados_existente": saltados_existente,
            "saltados_apilados": saltados_apilado,
            "dedup": dedup,
            "conduits_totales": total_conduits,
        },
        "por_apartamento": dict((k, dict(v)) for k, v in por_apto.items()),
        "fallos_detalle": fallos_detalle,
    }
    out = os.path.join(raiz, "data", "f7_verticales_todos_v04.json")
    try:
        with open(out, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=1))
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0 if fallos == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
