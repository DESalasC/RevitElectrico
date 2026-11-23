# -*- coding: utf-8 -*-
"""
RE7_DIAGNOSTICO_ESTADO_v01.py

SOLO LECTURA. No modifica ni borra nada, no abre transacciones.
Sirve para distinguir "se borro de verdad" de "no se ve en la vista".

Imprime:
  * documento, ruta, si tiene cambios sin guardar, si es de solo lectura
  * conteo por categoria electrica y de conduits
  * cuantos dispositivos tienen Mark de apartamento
  * grupos de modelo (OST_IOSModelGroups), muros, niveles
  * vista activa: nombre, tipo, crop activo, section box
  * rango Z de los dispositivos

Referencias de esta sesion (para comparar):
  * 23:09  -> 876 dispositivos con posicion (+33 sin Location)
  * 23:42  -> 840 con Mark de apartamento
  * 22:37  -> 126 conduits (78 verticales/previos + 48 horizontales F17/F18)

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
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    Level,
    View,
)

VERSION = "v01_diagnostico"
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
            return [0.5 * (p0.X + p1.X) * FT_A_MM,
                    0.5 * (p0.Y + p1.Y) * FT_A_MM,
                    0.5 * (p0.Z + p1.Z) * FT_A_MM]
    except Exception:
        pass
    return None


def contar(doc, bic):
    try:
        return len(FilteredElementCollector(doc).OfCategory(bic).ToElements())
    except Exception:
        return -1


def main():
    log("=" * 72)
    log("RE7_DIAGNOSTICO_ESTADO_%s  (SOLO LECTURA)" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1

    log("documento=%r" % doc.Title)
    path = None
    try:
        path = doc.PathName
    except Exception:
        pass
    log("ruta=%r" % path)

    modificado = None
    try:
        modificado = doc.IsModified
    except Exception:
        try:
            modificado = doc.get_IsModified()
        except Exception:
            modificado = None
    log("cambios sin guardar (IsModified)=%s" % modificado)

    try:
        log("solo lectura (IsReadOnly)=%s" % doc.IsReadOnly)
    except Exception:
        pass

    log("")
    log("-" * 72)
    log("CONTEO POR CATEGORIA")
    total_disp = 0
    por_cat = {}
    for (nombre, bic) in CATEGORIAS:
        n = contar(doc, bic)
        por_cat[nombre] = n
        total_disp += max(0, n)
        log("   %-24s %d" % (nombre, n))
    log("   %-24s %d" % ("TOTAL DISPOSITIVOS", total_disp))
    log("   %-24s %d" % ("Conduits", contar(doc, BuiltInCategory.OST_Conduit)))
    log("   %-24s %d" % ("Conduit Fittings", contar(doc, BuiltInCategory.OST_ConduitFitting)))
    log("   %-24s %d" % ("Cable Trays", contar(doc, BuiltInCategory.OST_CableTray)))
    log("   %-24s %d" % ("Muros (OST_Walls)", contar(doc, BuiltInCategory.OST_Walls)))
    log("   %-24s %d" % ("Grupos modelo", contar(doc, BuiltInCategory.OST_IOSModelGroups)))

    # niveles
    try:
        niveles = FilteredElementCollector(doc).OfClass(Level).ToElements()
        log("   %-24s %d" % ("Niveles", len(niveles)))
    except Exception:
        pass

    # Marks
    log("")
    log("-" * 72)
    log("MARKS")
    con_mark = 0
    con_mark_apto = 0
    por_apto = defaultdict(int)
    zs = []
    sin_punto = 0
    for (nombre, bic) in CATEGORIAS:
        try:
            for el in FilteredElementCollector(doc).OfCategory(bic).ToElements():
                pt = punto_real(el)
                if pt is None:
                    sin_punto += 1
                    continue
                zs.append(pt[2])
                mk = valor_texto(el, ["Mark"]) or ""
                if mk:
                    con_mark += 1
                    if "|" in mk:
                        con_mark_apto += 1
                        por_apto[mk.split("|")[0]] += 1
        except Exception:
            continue
    log("   sin Location: %d" % sin_punto)
    log("   con Mark: %d | con Mark de apartamento: %d" % (con_mark, con_mark_apto))
    if por_apto:
        log("   apartamentos: %s" % ", ".join(
            "%s=%d" % (k, por_apto[k]) for k in sorted(por_apto.keys())))
    if zs:
        log("   Z dispositivos: min=%.0f max=%.0f mm" % (min(zs), max(zs)))

    # vista activa
    log("")
    log("-" * 72)
    log("VISTA ACTIVA")
    try:
        v = doc.ActiveView
        log("   nombre=%r" % v.Name)
        log("   tipo=%s" % v.ViewType)
        try:
            log("   crop activo=%s" % v.CropBoxActive)
        except Exception:
            try:
                log("   crop activo=%s" % v.get_CropBoxActive())
            except Exception:
                log("   crop activo=(no legible)")
        try:
            log("   section box activo=%s" % v.IsSectionBoxActive)
        except Exception:
            pass
        try:
            log("   detail level=%s" % v.DetailLevel)
        except Exception:
            pass
        try:
            log("   escala=%s" % v.Scale)
        except Exception:
            pass
        try:
            log("   fase (phase)=%r" % (v.get_Parameter(
                __import__("Autodesk.Revit.DB", fromlist=["BuiltInParameter"]).BuiltInParameter.VIEW_PHASE)))
        except Exception:
            pass
    except Exception:
        log("   (no se pudo leer la vista activa)")

    # parametros de fase del view
    try:
        from Autodesk.Revit.DB import BuiltInParameter
        p = doc.ActiveView.get_Parameter(BuiltInParameter.VIEW_PHASE)
        if p is not None:
            log("   fase id=%s" % p.AsElementId())
    except Exception:
        pass

    log("")
    log("=" * 72)
    log("INTERPRETACION")
    log("  Si TOTAL DISPOSITIVOS ~ 876 y Conduits ~ 126 -> nada se borro:")
    log("  es un problema de visibilidad (crop, section box, fase, filtro, workset).")
    log("  Si los conteos son mucho menores -> cerrar SIN GUARDAR y reabrir.")
    log("=" * 72)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    rep = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "ruta": path,
        "is_modified": bool(modificado) if modificado is not None else None,
        "por_categoria": por_cat,
        "total_dispositivos": total_disp,
        "conduits": contar(doc, BuiltInCategory.OST_Conduit),
        "conduit_fittings": contar(doc, BuiltInCategory.OST_ConduitFitting),
        "marks": {"con_mark": con_mark, "con_mark_apartamento": con_mark_apto,
                  "sin_location": sin_punto, "por_apartamento": dict(por_apto)},
        "z_rango": [round(min(zs), 1), round(max(zs), 1)] if zs else None,
    }
    out = os.path.join(raiz, "data", "f7_diagnostico_estado_v01.json")
    try:
        with open(out, "w") as f:
            f.write(json.dumps(rep, ensure_ascii=True, indent=1))
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
