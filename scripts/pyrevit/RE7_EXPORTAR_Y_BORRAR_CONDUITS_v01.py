# -*- coding: utf-8 -*-
"""
RE7_EXPORTAR_Y_BORRAR_CONDUITS_v01.py

FASE 1 (lectura): exporta a JSON, antes de borrar nada,
  * todos los conduits (geometria, tipo, diametro, grupo)
  * todos los conduit fittings
  * todo el equipamiento electrico (tableros/paneles): id, nombre, Mark,
    familia/tipo, posicion y nivel  -> necesario para anclar el CP
  * los dispositivos con Mark (para el ruteo)
Salida: data/f7_referencias_v01.json

FASE 2 (borrado): borra TODOS los conduits y fittings del documento.
  * Nunca borra elementos con GroupId valido (miembros de grupo).
  * Una sola transaccion; RollBack si falla.
  * Verifica que ya no existan.
Salida: data/f7_borrado_conduits_v01.json

Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import os
import sys
import traceback
from collections import Counter

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
    Transaction,
)
from System import Int64

VERSION = "v01_exportar_borrar"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

CATEGORIAS_DISP = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]

NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size"]


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


def group_id(el):
    try:
        g = el.GroupId
        if g is None:
            return 0
        v = g.IntegerValue if hasattr(g, "IntegerValue") else g.Value
        return int(v)
    except Exception:
        return 0


def es_miembro_grupo(el):
    g = group_id(el)
    return g != 0 and g != -1


def punto(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            p = loc.Point
            return [p.X * FT_A_MM, p.Y * FT_A_MM, p.Z * FT_A_MM]
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            a = c.GetEndPoint(0)
            b = c.GetEndPoint(1)
            return [0.5 * (a.X + b.X) * FT_A_MM,
                    0.5 * (a.Y + b.Y) * FT_A_MM,
                    0.5 * (a.Z + b.Z) * FT_A_MM]
    except Exception:
        pass
    return None


def extremos(el):
    try:
        loc = el.Location
        if not isinstance(loc, LocationCurve):
            return None, None
        c = loc.Curve
        a = c.GetEndPoint(0)
        b = c.GetEndPoint(1)
        return ([a.X * FT_A_MM, a.Y * FT_A_MM, a.Z * FT_A_MM],
                [b.X * FT_A_MM, b.Y * FT_A_MM, b.Z * FT_A_MM])
    except Exception:
        return None, None


def texto(el, nombres):
    for n in nombres:
        try:
            p = el.LookupParameter(n)
            if p is not None:
                s = p.AsString()
                if s is not None:
                    return s
        except Exception:
            pass
    return None


def fam_tipo(el):
    fam = tip = None
    try:
        if el.Symbol is not None:
            if el.Symbol.Family is not None:
                fam = el.Symbol.Family.Name
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                tip = p.AsString()
    except Exception:
        pass
    return fam, tip


def diametro(el):
    for n in NOMBRES_DIAM:
        try:
            p = el.LookupParameter(n)
            if p is not None:
                return round(p.AsDouble() * FT_A_MM, 2)
        except Exception:
            pass
    return None


def tipo_conduit(el, doc):
    try:
        t = el.GetTypeId()
        if t is not None and t.IntegerValue > 0:
            te = doc.GetElement(t)
            if te is not None:
                p = te.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                return p.AsString() if p is not None else None
    except Exception:
        pass
    return None


def main():
    log("=" * 74)
    log("RE7_EXPORTAR_Y_BORRAR_CONDUITS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT

    # ---------------- FASE 1: exportar ----------------
    conduits = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        a, b = extremos(el)
        if a is None:
            continue
        conduits.append({
            "id": id_de(el),
            "tipo": tipo_conduit(el, doc),
            "diametro_mm": diametro(el),
            "a": [round(v, 1) for v in a],
            "b": [round(v, 1) for v in b],
            "grupo": es_miembro_grupo(el),
        })

    fittings = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_ConduitFitting).ToElements():
        pt = punto(el)
        fittings.append({
            "id": id_de(el),
            "familia": fam_tipo(el)[0],
            "tipo": fam_tipo(el)[1],
            "pos": [round(v, 1) for v in pt] if pt else None,
            "grupo": es_miembro_grupo(el),
        })

    equipos = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_ElectricalEquipment).ToElements():
        pt = punto(el)
        fam, tip = fam_tipo(el)
        equipos.append({
            "id": id_de(el),
            "nombre": texto(el, ["Name", "Panel Name", "Panel"]),
            "mark": texto(el, ["Mark"]),
            "familia": fam,
            "tipo": tip,
            "pos": [round(v, 1) for v in pt] if pt else None,
            "group_id": group_id(el),
        })

    disp = []
    for cat in CATEGORIAS_DISP:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto(el)
            if pt is None:
                continue
            fam, tip = fam_tipo(el)
            mk = texto(el, ["Mark"]) or ""
            disp.append({
                "id": id_de(el),
                "apto": mk.split("|")[0] if "|" in mk else None,
                "mark": mk,
                "familia": fam,
                "tipo": tip,
                "comment": texto(el, ["Comments"]),
                "pos": [round(v, 1) for v in pt],
            })

    log("")
    log("FASE 1 - exportado")
    log("   conduits=%d | fittings=%d | equipos electricos=%d | dispositivos=%d" % (
        len(conduits), len(fittings), len(equipos), len(disp)))
    log("   conduits por tipo: %s" % dict(Counter(c["tipo"] for c in conduits)))
    log("   diametros: %s" % dict(Counter(c["diametro_mm"] for c in conduits)))
    log("")
    log("   TABLEROS (equipos electricos):")
    for e in equipos:
        log("      id=%-9s mark=%-10r nombre=%-18r %s | pos=%s" % (
            e["id"], e["mark"], e["nombre"], e["familia"], e["pos"]))

    ref = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {"conduits": len(conduits), "fittings": len(fittings),
                    "equipos": len(equipos), "dispositivos": len(disp)},
        "conduits": conduits,
        "fittings": fittings,
        "equipos": equipos,
        "dispositivos": disp,
    }
    p_ref = os.path.join(raiz, "data", "f7_referencias_v01.json")
    try:
        with open(p_ref, "w") as f:
            f.write(json.dumps(ref, ensure_ascii=True, indent=1))
        log("")
        log("JSON referencias: %s" % p_ref)
    except Exception as ex:
        log("ERROR guardando referencias: %s" % ex)
        log("Se aborta el borrado: sin respaldo no se toca nada.")
        return 1

    # ---------------- FASE 2: borrar ----------------
    ids_conduits = [c["id"] for c in conduits if not c["grupo"]]
    ids_fittings = [f["id"] for f in fittings if not f["grupo"]]
    protegidos = [c["id"] for c in conduits if c["grupo"]] + \
                 [f["id"] for f in fittings if f["grupo"]]

    log("")
    log("FASE 2 - borrado")
    log("   a borrar: %d conduits + %d fittings" % (len(ids_conduits), len(ids_fittings)))
    if protegidos:
        log("   PROTEGIDOS por pertenecer a grupos: %d" % len(protegidos))

    borrados_c = 0
    borrados_f = 0
    fallos = []

    trans = Transaction(doc, "RE7_BORRAR_CONDUITS_FITTINGS_v01")
    trans.Start()
    try:
        for eid in ids_conduits:
            try:
                el = doc.GetElement(ElementId(Int64(eid)))
                if el is None:
                    continue
                if es_miembro_grupo(el):
                    fallos.append({"id": eid, "err": "grupo (guard)"})
                    continue
                doc.Delete(el.Id)
                borrados_c += 1
            except Exception as ex:
                fallos.append({"id": eid, "err": str(ex)[:110]})
        for eid in ids_fittings:
            try:
                el = doc.GetElement(ElementId(Int64(eid)))
                if el is None:
                    continue
                if es_miembro_grupo(el):
                    fallos.append({"id": eid, "err": "grupo (guard)"})
                    continue
                doc.Delete(el.Id)
                borrados_f += 1
            except Exception as ex:
                fallos.append({"id": eid, "err": str(ex)[:110]})
        # barrido final: conduits/fittings sin geometria valida que no entraron al export
        restantes = 0
        for el in FilteredElementCollector(doc).OfCategory(
                BuiltInCategory.OST_Conduit).ToElements():
            try:
                if es_miembro_grupo(el):
                    continue
                doc.Delete(el.Id)
                restantes += 1
            except Exception:
                pass
        for el in FilteredElementCollector(doc).OfCategory(
                BuiltInCategory.OST_ConduitFitting).ToElements():
            try:
                if es_miembro_grupo(el):
                    continue
                doc.Delete(el.Id)
                restantes += 1
            except Exception:
                pass
        trans.Commit()
        log("   Transaccion COMMIT (incluye barrido final: %d)" % restantes)
    except Exception:
        trans.RollBack()
        log("   ERROR: transaccion revertida, no se borro nada.")
        log(traceback.format_exc())
        return 1

    quedan_c = len(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Conduit).ToElements())
    quedan_f = len(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_ConduitFitting).ToElements())

    log("")
    log("=" * 74)
    log("RESULTADO")
    log("   borrados: %d conduits + %d fittings" % (borrados_c, borrados_f))
    log("   fallos: %d | protegidos por grupo: %d" % (len(fallos), len(protegidos)))
    log("   quedan en el documento: %d conduits | %d fittings" % (quedan_c, quedan_f))
    for f in fallos[:10]:
        log("      %s" % f)
    log("=" * 74)

    rep = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "conduits_antes": len(conduits),
            "fittings_antes": len(fittings),
            "borrados_conduits": borrados_c,
            "borrados_fittings": borrados_f,
            "protegidos_grupo": len(protegidos),
            "fallos": len(fallos),
            "quedan_conduits": quedan_c,
            "quedan_fittings": quedan_f,
            "barrido_final": restantes,
        },
        "fallos": fallos,
    }
    p_rep = os.path.join(raiz, "data", "f7_borrado_conduits_v01.json")
    try:
        with open(p_rep, "w") as f:
            f.write(json.dumps(rep, ensure_ascii=True, indent=1))
        log("JSON borrado: %s" % p_rep)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0 if not fallos else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
