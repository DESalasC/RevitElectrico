# -*- coding: utf-8 -*-
"""
RE7_MARCAR_COCINA_v01.py

Asigna Comment='Cocina' a los dispositivos de cocina, sin sobrescribir
comentarios existentes:

  * dispositivos cuyo TIPO o FAMILIA contenga 'Campana'
  * dispositivos a <= 1000 mm (XY) de una campana del mismo apartamento
    (segun el apartamento del Mark)

Corrige el fallo de RE7_APLICAR_MARKS_TODOS_v01, que buscaba 'campana' solo
en el nombre de familia y no encontraba ninguna (la campana es
M_Timbre | tipo 'Campana').

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
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    Transaction,
)

VERSION = "v01_cocina"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
RADIO_COCINA_MM = 1000.0

CATEGORIAS = [
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
    try:
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
    except Exception:
        pass
    return None


def nombre_tipo(el):
    try:
        if el.Symbol is not None:
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                return p.AsString()
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


def main():
    log("=" * 70)
    log("RE7_MARCAR_COCINA_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    dispositivo = {}
    campanas = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto_real(el)
            if pt is None:
                continue
            eid = id_de(el)
            tipo = nombre_tipo(el) or ""
            fam = nombre_familia(el) or ""
            mark = valor_texto(el, ["Mark"]) or ""
            apto = mark.split("|")[0] if "|" in mark else None
            dispositivo[eid] = {
                "el": el, "pt": pt, "tipo": tipo, "familia": fam,
                "mark": mark, "apto": apto,
                "comment": valor_texto(el, ["Comments"]),
            }
            if "campana" in tipo.lower() or "campana" in fam.lower():
                campanas.append({"id": eid, "pt": pt, "apto": apto})

    log("Dispositivos con posicion: %d | campanas: %d" % (len(dispositivo), len(campanas)))

    candidatos = []
    for eid, d in dispositivo.items():
        if d["comment"]:
            continue
        es_campana = "campana" in d["tipo"].lower() or "campana" in d["familia"].lower()
        cerca = False
        for c in campanas:
            if c["apto"] and d["apto"] and c["apto"] != d["apto"]:
                continue
            if math.hypot(c["pt"][0] - d["pt"][0], c["pt"][1] - d["pt"][1]) <= RADIO_COCINA_MM:
                cerca = True
                break
        if es_campana or cerca:
            candidatos.append({"id": eid, "es_campana": es_campana, "apto": d["apto"],
                               "tipo": d["tipo"], "familia": d["familia"]})

    log("Candidatos a Comment='Cocina': %d" % len(candidatos))

    ok = 0
    fallos = 0
    trans = Transaction(doc, "RE7_MARCAR_COCINA_v01")
    trans.Start()
    try:
        for c in candidatos:
            el = dispositivo[c["id"]]["el"]
            p = None
            for nombre in ("Comments",):
                try:
                    pp = el.LookupParameter(nombre)
                    if pp is not None and not pp.IsReadOnly:
                        p = pp
                        break
                except Exception:
                    pass
            if p is None:
                fallos += 1
                continue
            try:
                p.Set("Cocina")
                ok += 1
            except Exception:
                fallos += 1
        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida.")
        log(traceback.format_exc())
        return 1

    log("")
    log("=" * 70)
    log("Comment='Cocina' asignado: %d | fallos: %d" % (ok, fallos))
    log("Campanas: %d | por proximidad: %d" % (
        sum(1 for c in candidatos if c["es_campana"]),
        sum(1 for c in candidatos if not c["es_campana"])))
    log("=" * 70)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "dispositivos": len(dispositivo),
            "campanas": len(campanas),
            "candidatos": len(candidatos),
            "asignados": ok,
            "fallos": fallos,
        },
        "candidatos": candidatos,
    }
    out_path = os.path.join(raiz, "data", "f7_cocina_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=1))
        log("JSON: %s" % out_path)
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
