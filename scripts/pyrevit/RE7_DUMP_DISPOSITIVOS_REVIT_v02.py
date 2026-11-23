# -*- coding: utf-8 -*-
"""
RE7_DUMP_DISPOSITIVOS_REVIT_v02.py
SOLO LECTURA. Vuelca los dispositivos electricos reales de Revit a JSON y
diagnostica el plano de ruteo (Z de conduits existentes).

Categorias incluidas: OST_ElectricalFixtures, OST_LightingFixtures, OST_DataDevices.

No crea, mueve ni borra nada. Solo lee y escribe un JSON en data/.

Salida: data/f7_revit_dispositivos_v02.json
Entorno: pyRevit IronPython 2.7 (consola de Revit)
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
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    StorageType,
)
from System import Int64

VERSION = "v02"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

# Zonas de trabajo (mm, coordenadas de modelo). Margen amplio.
ZONAS = {
    "F17": {"x_min": 6500.0, "x_max": 11000.0, "y_min": 500.0, "y_max": 8800.0},
    "F18": {"x_min": 6500.0, "x_max": 11000.0, "y_min": 8800.0, "y_max": 17000.0},
}


def _raiz():
    r = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if r and os.path.exists(r):
        return r
    return DEFAULT_ROOT


def log(msg):
    try:
        print(msg)
    except Exception:
        pass
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


def mediana(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    if n % 2 == 1:
        return s[n / 2]
    return 0.5 * (s[n / 2 - 1] + s[n / 2])


def punto_loc(loc):
    """Devuelve (x_mm, y_mm, z_mm) o None."""
    if loc is None:
        return None
    pt = None
    if isinstance(loc, LocationPoint):
        pt = loc.Point
    else:
        try:
            pt = loc.Point
        except Exception:
            pt = None
    if pt is None:
        return None
    return pt.X * FT_A_MM, pt.Y * FT_A_MM, pt.Z * FT_A_MM


def familia_tipo(el):
    """Devuelve (familia, tipo) con tolerancia a IronPython quirks."""
    fam, tip = None, None
    try:
        sym = el.Symbol
        if sym is not None:
            try:
                fam = sym.Family.Name
            except Exception:
                fam = None
            try:
                tip = sym.get_Parameter(
                    BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
            except Exception:
                tip = None
    except Exception:
        pass
    return fam, tip


def nivel_nombre(el, doc):
    try:
        lp = el.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if lp is not None and lp.StorageType == StorageType.ElementId:
            lvl = doc.GetElement(lp.AsElementId())
            if lvl is not None:
                return lvl.Name
    except Exception:
        pass
    return None


def main():
    log("=" * 62)
    log("RE7_DUMP_DISPOSITIVOS_REVIT_%s  (SOLO LECTURA)" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1

    titulo = doc.Title
    log("documento=%r" % titulo)
    log("ruta=%s" % doc.PathName)
    log("=" * 62)

    # ---------------- dispositivos electricos (varias categorias) ----------------
    dispositivos = []
    sin_pos = 0
    cats = (BuiltInCategory.OST_ElectricalFixtures,
            BuiltInCategory.OST_LightingFixtures,
            BuiltInCategory.OST_DataDevices)
    for cat in cats:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            try:
                xyz = punto_loc(el.Location)
                if xyz is None:
                    sin_pos += 1
                    continue
                x_mm, y_mm, z_mm = xyz
                apto = apto_de(x_mm, y_mm)
                if apto is None:
                    continue
                fam, tip = familia_tipo(el)
                dispositivos.append({
                    "id": id_de(el),
                    "categoria": str(el.Category.Name) if el.Category else None,
                    "familia": fam,
                    "tipo": tip,
                    "x_mm": round(x_mm, 3),
                    "y_mm": round(y_mm, 3),
                    "z_mm": round(z_mm, 3),
                    "nivel": nivel_nombre(el, doc),
                    "apto": apto,
                })
            except Exception:
                continue

    log("dispositivos electricos en zonas: %d (sin posicion: %d)" % (
        len(dispositivos), sin_pos))
    for a in sorted(ZONAS):
        ds = [d for d in dispositivos if d["apto"] == a]
        log("  %s: %d dispositivos" % (a, len(ds)))
        por_clave = {}
        for d in ds:
            k = "%s | %s | %s" % (d.get("categoria"), d.get("familia"), d.get("tipo"))
            por_clave[k] = por_clave.get(k, 0) + 1
        for k in sorted(por_clave):
            zs = [d["z_mm"] for d in ds
                  if "%s | %s | %s" % (d.get("categoria"), d.get("familia"), d.get("tipo")) == k]
            log("      %-60s n=%-3d Z(med)=%.0f  Z[min..max]=%.0f..%.0f" % (
                k, por_clave[k], mediana(zs), min(zs), max(zs)))

    # ---------------- conduits existentes ----------------
    conduits = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        try:
            loc = el.Location
            if not isinstance(loc, LocationCurve):
                continue
            c = loc.Curve
            p0 = c.GetEndPoint(0)
            p1 = c.GetEndPoint(1)
            z0 = p0.Z * FT_A_MM
            z1 = p1.Z * FT_A_MM
            x_mm = p0.X * FT_A_MM
            y_mm = p0.Y * FT_A_MM
            conduits.append({
                "id": id_de(el),
                "x_mm": round(x_mm, 1),
                "y_mm": round(y_mm, 1),
                "z0_mm": round(z0, 1),
                "z1_mm": round(z1, 1),
                "z_med_mm": round(0.5 * (z0 + z1), 1),
                "apto": apto_de(x_mm, y_mm),
            })
        except Exception:
            continue

    zs_all = [c["z_med_mm"] for c in conduits]
    log("")
    log("conduits existentes: %d" % len(conduits))
    if zs_all:
        log("  Z mediana global: %.1f mm" % mediana(zs_all))
        log("  Z min/max: %.1f / %.1f" % (min(zs_all), max(zs_all)))
        hist = {}
        for z in zs_all:
            k = int(round(z / 100.0)) * 100
            hist[k] = hist.get(k, 0) + 1
        for k in sorted(hist):
            log("      Z~%6d mm : %4d conduits" % (k, hist[k]))
    for a in sorted(ZONAS):
        cs = [c for c in conduits if c["apto"] == a]
        if cs:
            log("  %s: %d conduits" % (a, len(cs)))

    # ---------------- tipos de conduit ----------------
    from Autodesk.Revit.DB.Electrical import ConduitType
    from Autodesk.Revit.DB.Electrical import Conduit
    tipos = []
    for t in FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
        try:
            if not Conduit.IsValidConduitType(doc, t.Id):
                continue
        except Exception:
            continue
        nombre = None
        try:
            nombre = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
        except Exception:
            nombre = None
        params_diam = []
        try:
            for p in t.Parameters:
                try:
                    nm = p.Definition.Name
                except Exception:
                    continue
                if nm and ("DIAM" in nm.upper() or "SIZE" in nm.upper()):
                    val = None
                    try:
                        if p.StorageType == StorageType.Double:
                            val = p.AsDouble() * FT_A_MM
                        elif p.StorageType == StorageType.String:
                            val = p.AsString()
                        elif p.StorageType == StorageType.Integer:
                            val = p.AsInteger()
                    except Exception:
                        val = None
                    params_diam.append({"nombre": nm, "valor": val})
        except Exception:
            pass
        tipos.append({"id": id_de(t), "nombre": nombre, "params": params_diam})

    log("")
    log("tipos de conduit validos: %d" % len(tipos))
    for t in tipos:
        log("  id=%s nombre=%r params=%s" % (t["id"], t["nombre"], t["params"]))

    # ---------------- salida ----------------
    raiz = _raiz()
    salida = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "zonas": ZONAS,
        "dispositivos": dispositivos,
        "conduits_existentes": {
            "total": len(conduits),
            "z_mediana_mm": mediana(zs_all),
            "detalle": conduits,
        },
        "tipos_conduit": tipos,
    }
    ruta_out = os.path.join(raiz, "data", "f7_revit_dispositivos_v02.json")
    try:
        with open(ruta_out, "w") as f:
            f.write(json.dumps(salida, ensure_ascii=True, indent=2))
        log("")
        log("JSON guardado: %s" % ruta_out)
    except Exception:
        log("ERROR escribiendo JSON:")
        log(traceback.format_exc())

    log("FIN (no se modifico el modelo)")
    log("=" * 62)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
