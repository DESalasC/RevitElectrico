# -*- coding: utf-8 -*-
"""
RE7_CONSULTAR_SERVICIOS_V02F_v01.py

Consulta read-only del vocabulario de servicios de V02-f:

  * nombres de parametros de un conduit (para ubicar Servicio_Conduit)
  * distribucion de valores de ese parametro y geometria por servicio
    (tramos, longitud, verticales, alturas)
  * aparatos por familia con su altura sobre el nivel (para mapear
    interruptores / tomas / datos / ventilacion)

Entorno: pyRevit IronPython 2.7 (pyrevit agent run --mode=query)
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

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
)

VERSION = "v01_servicios_v02f"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
RUTA_V02F = os.path.join(
    DEFAULT_ROOT, "ArchivosBase",
    "E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt")
OUT = os.path.join(DEFAULT_ROOT, "data", "f7_servicios_v02f_v01.json")

Z_NIVEL_MM = 13220.0
CANDIDATOS_SERVICIO = ["Servicio_Conduit", "Servicio Conduit",
                       "ServicioConduit", "Servicio", "Service"]
NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size", "Diametro"]

CATEGORIAS_APARATOS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]


def log(msg):
    print(msg)
    try:
        sys.stdout.flush()
    except Exception:
        pass


def ascii_seguro(s):
    if s is None:
        return None
    try:
        u = None
        if isinstance(s, unicode):
            u = s
        else:
            for enc in ("utf-8", "latin-1", "cp1252"):
                try:
                    u = s.decode(enc)
                    break
                except Exception:
                    continue
        if u is None:
            return None
        return u.encode("ascii", "replace").decode("ascii")
    except Exception:
        try:
            return str(s).encode("ascii", "replace").decode("ascii")
        except Exception:
            return None


def app_de():
    try:
        app = __revit__
        if app is not None and hasattr(app, "Application"):
            return app.Application
    except Exception:
        pass
    try:
        from pyrevit import revit as _revit
        if _revit.app is not None:
            return _revit.app
    except Exception:
        pass
    return None


def id_de(el):
    v = el.Id
    if hasattr(v, "IntegerValue"):
        return int(v.IntegerValue)
    return int(v.Value)


def param_cadena(el, nombre):
    try:
        p = el.LookupParameter(nombre)
        if p is not None:
            if p.StorageType.ToString() == "String":
                return ascii_seguro(p.AsString())
            try:
                return ascii_seguro(p.AsValueString())
            except Exception:
                return None
    except Exception:
        pass
    return None


def diametro(el, doc):
    for fuente in ("instancia", "tipo"):
        objetivo = el
        if fuente == "tipo":
            try:
                objetivo = doc.GetElement(el.GetTypeId())
            except Exception:
                objetivo = None
        if objetivo is None:
            continue
        for n in NOMBRES_DIAM:
            try:
                p = objetivo.LookupParameter(n)
                if p is not None and p.StorageType.ToString() == "Double":
                    v = p.AsDouble() * FT_A_MM
                    if v > 0.1:
                        return round(v, 1)
            except Exception:
                pass
    return None


def extremos(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            a = c.GetEndPoint(0)
            b = c.GetEndPoint(1)
            return ([round(a.X * FT_A_MM, 1), round(a.Y * FT_A_MM, 1),
                     round(a.Z * FT_A_MM, 1)],
                    [round(b.X * FT_A_MM, 1), round(b.Y * FT_A_MM, 1),
                     round(b.Z * FT_A_MM, 1)])
    except Exception:
        pass
    return (None, None)


def punto(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            p = loc.Point
            return (round(p.X * FT_A_MM, 1), round(p.Y * FT_A_MM, 1),
                    round(p.Z * FT_A_MM, 1))
    except Exception:
        pass
    return None


def fam_tipo(el):
    fam = tip = None
    try:
        if el.Symbol is not None:
            if el.Symbol.Family is not None:
                fam = ascii_seguro(el.Symbol.Family.Name)
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                tip = ascii_seguro(p.AsString())
    except Exception:
        pass
    return fam, tip


def main():
    log("=" * 76)
    log("RE7_CONSULTAR_SERVICIOS_V02F_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    app = app_de()
    if app is None:
        log("ERROR: sin Application.")
        return 1

    doc = None
    ya = False
    try:
        for d in app.Documents:
            try:
                if d.PathName == RUTA_V02F:
                    doc = d
                    ya = True
                    break
            except Exception:
                continue
    except Exception:
        pass
    if doc is None:
        try:
            doc = app.OpenDocumentFile(RUTA_V02F)
        except Exception:
            log("ERROR abriendo V02-f:")
            log(traceback.format_exc())
            return 1
    log("documento: %r (%s)" % (doc.Title, "reutilizado" if ya else "abierto"))

    conduits = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().ToElements()
    log("conduits: %d" % len(conduits))

    # nombres de parametros del primer conduit
    ejemplo = None
    for el in conduits:
        ejemplo = el
        break
    if ejemplo is not None:
        nombres = []
        try:
            for p in ejemplo.Parameters:
                try:
                    nombres.append(ascii_seguro(p.Definition.Name) or "?")
                except Exception:
                    pass
        except Exception:
            pass
        log("parametros de un conduit (%d): %s" % (len(nombres), nombres))

    # que candidato existe y con que valores
    servicio_param = None
    for n in CANDIDATOS_SERVICIO:
        valores = defaultdict(int)
        for el in conduits:
            v = param_cadena(el, n)
            if v is not None:
                valores[v] += 1
        if valores:
            servicio_param = n
            log("parametro de servicio: %r -> %s" % (
                n, dict(sorted(valores.items(), key=lambda kv: -kv[1]))))
            break
    if servicio_param is None:
        log("NINGUN candidato de servicio encontro valores.")

    # geometria por servicio
    por_servicio = defaultdict(list)
    for el in conduits:
        a, b = extremos(el)
        if a is None:
            continue
        s = param_cadena(el, servicio_param) if servicio_param else "(sin parametro)"
        c = 0.5 * (a[2] + b[2])
        en_area = (12000 <= 0.5 * (a[0] + b[0]) <= 16000
                   and 12000 <= c <= 17500)
        if not en_area:
            continue
        vertical = abs(a[0] - b[0]) <= 2 and abs(a[1] - b[1]) <= 2
        por_servicio[s or "(vacio)"].append({
            "id": id_de(el), "a": a, "b": b,
            "largo": round(math.sqrt(sum((b[i] - a[i]) ** 2
                                         for i in range(3))), 1),
            "vertical": vertical, "diam": diametro(el, doc)})

    log("")
    log("GEOMETRIA POR SERVICIO (area F01/F02)")
    resumen = {}
    for s in sorted(por_servicio):
        qs = por_servicio[s]
        vert = [q for q in qs if q["vertical"]]
        hor = [q for q in qs if not q["vertical"]]
        hor_plenum = [q for q in hor if 0.5 * (q["a"][2] + q["b"][2]) > 15000]
        hor_aparato = [q for q in hor if 0.5 * (q["a"][2] + q["b"][2]) <= 15000]
        dz = [round(q["a"][2] - Z_NIVEL_MM, 0) for q in vert]
        dzt = [round(q["b"][2] - Z_NIVEL_MM, 0) for q in vert]
        resumen[s] = {
            "tramos": len(qs),
            "longitud_m": round(sum(q["largo"] for q in qs) / 1000.0, 2),
            "verticales": len(vert),
            "vertical_z_ini_sobre_nivel": sorted(set(dz + dzt)),
            "horizontales_plenum": len(hor_plenum),
            "horizontales_plenum_m": round(
                sum(q["largo"] for q in hor_plenum) / 1000.0, 2),
            "horizontales_aparato": len(hor_aparato),
            "horizontales_aparato_m": round(
                sum(q["largo"] for q in hor_aparato) / 1000.0, 2),
            "diametros": sorted(set(q["diam"] for q in qs if q["diam"])),
        }
        log("  %-14s tramos=%3d | %6.2f m | vert %2d (z ini %s) | "
            "plenum %2d (%5.2f m) | aparato %2d (%4.2f m) | diam %s" % (
                s, len(qs), resumen[s]["longitud_m"], len(vert),
                sorted(set(dz + dzt))[:6], len(hor_plenum),
                resumen[s]["horizontales_plenum_m"], len(hor_aparato),
                resumen[s]["horizontales_aparato_m"], resumen[s]["diametros"]))

    # aparatos por familia y altura
    log("")
    log("APARATOS POR FAMILIA (altura sobre el nivel, conteo)")
    aparatos = []
    por_familia = defaultdict(list)
    for cat in CATEGORIAS_APARATOS:
        for el in FilteredElementCollector(doc).OfCategory(cat) \
                .WhereElementIsNotElementType().ToElements():
            p = punto(el)
            if p is None:
                continue
            fam, tip = fam_tipo(el)
            mark = None
            try:
                pm = el.LookupParameter("Mark")
                if pm is not None and pm.StorageType.ToString() == "String":
                    mark = ascii_seguro(pm.AsString())
            except Exception:
                pass
            d = {"familia": fam or "", "tipo": tip or "",
                 "mark": mark or "", "x": p[0], "y": p[1],
                 "z_sobre_nivel": round(p[2] - Z_NIVEL_MM, 0)}
            aparatos.append(d)
            por_familia[(fam or "?")].append(d)
    for fam in sorted(por_familia):
        qs = por_familia[fam]
        alturas = sorted(set(q["z_sobre_nivel"] for q in qs))
        log("  %-22s %3d | alturas %s" % (fam, len(qs), alturas[:8]))

    try:
        with open(OUT, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"),
                "parametro_servicio": servicio_param,
                "resumen_por_servicio": resumen,
                "por_servicio": dict((k, v) for k, v in por_servicio.items()),
                "aparatos": aparatos,
            }, ensure_ascii=True, indent=1))
        log("JSON: %s" % OUT)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)
        log(traceback.format_exc())
    log("=" * 76)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
