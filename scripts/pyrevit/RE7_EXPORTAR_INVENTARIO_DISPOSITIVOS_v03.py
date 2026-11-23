# -*- coding: utf-8 -*-
"""
RE7_EXPORTAR_INVENTARIO_DISPOSITIVOS_v03.py

SOLO LECTURA. Exporta TODO el inventario de dispositivos electricos del
documento activo a JSON, para cruzarlo fuera de Revit con:
  - data/maestro_colocacion_piso5_ABSOLUTO.json  (apto por posicion)
  - ArchivosBase/STM-T5-P5_bloques_electricos-XPL.dxf (circuito por bloque)
  - INSERT TB-Panel del DXF (nombre de tablero por apartamento)

Campos por dispositivo: id, categoria, familia, tipo, x/y/z en mm, mark,
comment, nivel.

Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
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
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
)

VERSION = "v03_inventario"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

CATEGORIAS = [
    ("ElectricalFixtures", BuiltInCategory.OST_ElectricalFixtures),
    ("LightingFixtures", BuiltInCategory.OST_LightingFixtures),
    ("DataDevices", BuiltInCategory.OST_DataDevices),
    ("TelephoneDevices", BuiltInCategory.OST_TelephoneDevices),
    ("CommunicationDevices", BuiltInCategory.OST_CommunicationDevices),
    ("MechanicalEquipment", BuiltInCategory.OST_MechanicalEquipment),
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


def valor_texto(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None:
                s = p.AsString()
                if s:
                    return s
        except Exception:
            pass
    return None


def nombre_familia(el):
    try:
        sym = el.Symbol
        if sym is not None:
            fam = sym.Family
            if fam is not None:
                return fam.Name
    except Exception:
        pass
    return None


def nombre_tipo(el):
    try:
        sym = el.Symbol
        if sym is not None:
            p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                return p.AsString()
    except Exception:
        pass
    return None


def nombre_nivel(el):
    try:
        lid = el.LevelId
        if lid is not None and lid.IntegerValue > 0:
            lvl = el.Document.GetElement(lid)
            if lvl is not None:
                return lvl.Name
    except Exception:
        pass
    return None


def main():
    log("=" * 70)
    log("RE7_EXPORTAR_INVENTARIO_DISPOSITIVOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    dispositivos = []
    por_cat = defaultdict(int)
    sin_punto = 0

    for (nombre_cat, bic) in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(bic).ToElements():
            pt = punto_real(el)
            if pt is None:
                sin_punto += 1
                continue
            d = {
                "id": id_de(el),
                "categoria": nombre_cat,
                "familia": nombre_familia(el),
                "tipo": nombre_tipo(el),
                "x": round(pt[0], 3),
                "y": round(pt[1], 3),
                "z": round(pt[2], 3),
                "mark": valor_texto(el, ["Mark"]),
                "comment": valor_texto(el, ["Comments"]),
                "nivel": nombre_nivel(el),
            }
            dispositivos.append(d)
            por_cat[nombre_cat] += 1

    con_mark = sum(1 for d in dispositivos if d["mark"])
    con_apto = sum(1 for d in dispositivos if d["mark"] and "|" in d["mark"])
    sin_apto = len(dispositivos) - con_apto

    log("Dispositivos exportados: %d (sin punto: %d)" % (len(dispositivos), sin_punto))
    log("Con Mark: %d | con Mark completo (apto|tablero|circuito): %d | sin apto: %d" % (
        con_mark, con_apto, sin_apto))
    log("Por categoria:")
    for c in sorted(por_cat.keys(), key=lambda kk: -por_cat[kk]):
        log("   %-24s %d" % (c, por_cat[c]))

    # distribucion de apartamentos ya asignados
    aptos = defaultdict(int)
    for d in dispositivos:
        if d["mark"] and "|" in d["mark"]:
            aptos[d["mark"].split("|")[0]] += 1
    if aptos:
        log("Apartamentos ya asignados (Mark):")
        for a in sorted(aptos.keys(), key=lambda kk: -aptos[kk]):
            log("   %-8s %d" % (a, aptos[a]))

    raiz = _raiz()
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": doc.Title, "path": doc.PathName},
        "resumen": {
            "total": len(dispositivos),
            "sin_punto": sin_punto,
            "con_mark": con_mark,
            "con_mark_completo": con_apto,
            "sin_apto": sin_apto,
            "por_categoria": dict(por_cat),
            "apartamentos_con_mark": dict(aptos),
        },
        "dispositivos": dispositivos,
    }
    out_path = os.path.join(raiz, "data", "f7_inventario_revit_v03.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=1))
        log("JSON guardado: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    log("=" * 70)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
