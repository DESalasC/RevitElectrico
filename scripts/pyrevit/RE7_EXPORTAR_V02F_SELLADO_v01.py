# -*- coding: utf-8 -*-
"""
RE7_EXPORTAR_V02F_SELLADO_v01.py

Verificacion sellada del ruteo manual de referencia: abre
E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt con
Application.OpenDocumentFile (sin UI, sin guardar) y exporta su contenido
real: conduits, accesorios de conduit y aparatos electricos.

Si el documento quedo abierto de una corrida anterior (el API a veces
rechaza Close), lo reutiliza en lugar de abrirlo dos veces.

Escribe: data/f7_v02f_sello_v01.json

Entorno: pyRevit IronPython 2.7 (pyrevit agent run --mode=query)
"""
import datetime
import json
import os
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
)

VERSION = "v01b_sello_v02f"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
RUTA_V02F = os.path.join(
    DEFAULT_ROOT, "ArchivosBase",
    "E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt")
OUT = os.path.join(DEFAULT_ROOT, "data", "f7_v02f_sello_v01.json")

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
    """Convierte cualquier string .NET/IronPython a ASCII sin romper el JSON."""
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


def texto(el, nombres):
    for n in nombres:
        try:
            p = el.LookupParameter(n)
            if p is not None:
                s = p.AsString()
                if s is not None:
                    return ascii_seguro(s)
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


def recolectar(doc):
    conduits = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().ToElements():
        a, b = extremos(el)
        if a is None:
            conduits.append({"id": id_de(el), "a_mm": None, "b_mm": None,
                             "diam_mm": diametro(el, doc),
                             "nivel": texto(el, ["Reference Level", "Level"])})
            continue
        conduits.append({"id": id_de(el), "a_mm": a, "b_mm": b,
                         "diam_mm": diametro(el, doc),
                         "nivel": texto(el, ["Reference Level", "Level"])})

    fittings = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_ConduitFitting
    ).WhereElementIsNotElementType().ToElements():
        p = punto(el)
        fam, tip = fam_tipo(el)
        fittings.append({"id": id_de(el), "pt_mm": p, "familia": fam or ""})

    aparatos = []
    for cat in CATEGORIAS_APARATOS:
        for el in FilteredElementCollector(doc).OfCategory(cat) \
                .WhereElementIsNotElementType().ToElements():
            p = punto(el)
            if p is None:
                continue
            fam, tip = fam_tipo(el)
            aparatos.append({"id": id_de(el), "categoria": str(cat),
                             "familia": fam or "", "tipo": tip or "",
                             "mark": texto(el, ["Mark"]) or "",
                             "x": p[0], "y": p[1], "z": p[2]})
    return conduits, fittings, aparatos


def main():
    log("=" * 76)
    log("RE7_EXPORTAR_V02F_SELLADO_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    if not os.path.exists(RUTA_V02F):
        log("ERROR: no existe %s" % RUTA_V02F)
        return 1
    log("archivo: %s (%.1f MB)" % (RUTA_V02F,
                                    os.path.getsize(RUTA_V02F) / 1048576.0))

    app = app_de()
    if app is None:
        log("ERROR: no se obtuvo la Application.")
        return 1

    doc = None
    ya_abierto = False
    try:
        for d in app.Documents:
            try:
                if d.PathName == RUTA_V02F:
                    doc = d
                    ya_abierto = True
                    break
            except Exception:
                continue
    except Exception:
        pass

    if doc is None:
        try:
            doc = app.OpenDocumentFile(RUTA_V02F)
        except Exception:
            log("ERROR abriendo el documento:")
            log(traceback.format_exc())
            return 1
    log("documento %s: %r" % ("ya abierto (reutilizado)" if ya_abierto
                              else "abierto ahora", doc.Title))

    conduits, fittings, aparatos = recolectar(doc)
    log("conduits: %d | fittings: %d | aparatos: %d" % (
        len(conduits), len(fittings), len(aparatos)))

    if conduits:
        xs, ys, zs = [], [], []
        for c in conduits:
            for q in (c["a_mm"], c["b_mm"]):
                if q is None:
                    continue
                xs.append(q[0])
                ys.append(q[1])
                zs.append(q[2])
        if xs:
            log("conduits  X: %.0f..%.0f | Y: %.0f..%.0f | Z: %.0f..%.0f mm" % (
                min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
            en_area = [c for c in conduits
                       if c["a_mm"] and 12000 < 0.5 * (c["a_mm"][0] + c["b_mm"][0]) < 16000
                       and 12000 < 0.5 * (c["a_mm"][2] + c["b_mm"][2]) < 17000]
            log("conduits dentro del area x[12,16] z[12,17]: %d" % len(en_area))
    if aparatos:
        xs = [q["x"] for q in aparatos]
        ys = [q["y"] for q in aparatos]
        zs = [q["z"] for q in aparatos]
        log("aparatos  X: %.0f..%.0f | Y: %.0f..%.0f | Z: %.0f..%.0f mm" % (
            min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))

    # escribir ANTES de intentar cerrar: un fallo de Close no pierde el sello
    try:
        with open(OUT, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"),
                "archivo": RUTA_V02F,
                "reutilizado": ya_abierto,
                "conduits": conduits,
                "conduit_fittings": fittings,
                "aparatos": aparatos,
                "resumen": {
                    "conduits": len(conduits),
                    "conduit_fittings": len(fittings),
                    "aparatos": len(aparatos),
                },
            }, ensure_ascii=True, indent=1))
        log("JSON: %s" % OUT)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)
        log(traceback.format_exc())
        return 1

    if not ya_abierto:
        try:
            doc.Close(False)
            log("documento cerrado SIN guardar.")
        except Exception:
            log("AVISO: el API no permitio cerrar el documento; queda "
                "abierto en memoria (solo lectura, sin cambios).")
    else:
        log("documento ya abierto antes: no se cierra desde aqui.")

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
