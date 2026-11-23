# -*- coding: utf-8 -*-
"""
RE7_DIAGNOSTICO_GRUPOS_CONDUITS_v01.py

SOLO LECTURA. Explica por que los conduits no se pudieron borrar: todos
reportan GroupId valido.

Para cada grupo que contiene conduits/fittings informa:
  * id y nombre del grupo, si es adjunto (IsAttached)
  * numero de miembros totales
  * composicion: cuantos conduits, fittings, dispositivos y otros
  * cuantos elementos del grupo son de nuestro interes

Salida: data/f7_diagnostico_grupos_conduits_v01.json
Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import os
import sys
import traceback
from collections import defaultdict, Counter

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    ElementId,
    FilteredElementCollector,
    Group,
)

VERSION = "v01_diag_grupos"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"


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


def gid_de(el):
    try:
        g = el.GroupId
        if g is None:
            return 0
        v = g.IntegerValue if hasattr(g, "IntegerValue") else g.Value
        return int(v)
    except Exception:
        return 0


def cat_de(el):
    try:
        if el.Category is not None:
            return el.Category.Name
    except Exception:
        pass
    return "?"


def main():
    log("=" * 74)
    log("RE7_DIAGNOSTICO_GRUPOS_CONDUITS_%s  (SOLO LECTURA)" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    conduits = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Conduit).ToElements()
    fittings = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_ConduitFitting).ToElements()

    log("conduits=%d | fittings=%d" % (len(conduits), len(fittings)))

    dist_c = Counter(gid_de(c) for c in conduits)
    dist_f = Counter(gid_de(f) for f in fittings)
    log("")
    log("Distribucion de GroupId en conduits (top 15):")
    for gid, n in dist_c.most_common(15):
        log("   grupo=%-10s %d" % (gid, n))
    log("conduits SIN grupo (GroupId=0 o -1): %d" % (
        dist_c.get(0, 0) + dist_c.get(-1, 0)))
    log("fittings SIN grupo: %d" % (dist_f.get(0, 0) + dist_f.get(-1, 0)))

    grupos = sorted(set([g for g in dist_c.keys() if g not in (0, -1)]))
    log("")
    log("Grupos distintos que contienen conduits: %d" % len(grupos))

    detalle = []
    for gid in grupos:
        el = None
        try:
            el = doc.GetElement(ElementId(__import__("System").Int64(gid)))
        except Exception:
            try:
                el = doc.GetElement(ElementId(gid))
            except Exception:
                el = None
        if el is None:
            detalle.append({"id": gid, "error": "no se pudo leer el grupo"})
            continue
        nombre = None
        adjunto = None
        miembros = []
        try:
            nombre = el.Name
        except Exception:
            pass
        try:
            adjunto = el.IsAttached
        except Exception:
            pass
        try:
            miembros = list(el.GetMemberIds())
        except Exception:
            miembros = []

        comp = Counter()
        n_conduits = 0
        for mid in miembros:
            m = doc.GetElement(mid)
            if m is None:
                continue
            c = cat_de(m)
            comp[c] += 1
            if c == "Conduits":
                n_conduits += 1

        detalle.append({
            "id": gid, "nombre": nombre, "is_attached": adjunto,
            "miembros": len(miembros), "conduits_miembro": n_conduits,
            "composicion": dict(comp),
        })
        log("")
        log("   GRUPO id=%-10s nombre=%-24r adjunto=%s" % (gid, nombre, adjunto))
        log("      miembros=%d | conduits dentro=%d" % (len(miembros), n_conduits))
        log("      composicion: %s" % dict(comp))

    # veredicto
    log("")
    log("=" * 74)
    solo_conductos = [d for d in detalle
                      if d.get("miembros") and d.get("conduits_miembro") == d.get("miembros")]
    mixtos = [d for d in detalle
              if d.get("miembros") and 0 < d.get("conduits_miembro", 0) < d.get("miembros")]
    log("Grupos SOLO de conduits: %d" % len(solo_conductos))
    log("Grupos MIXTOS (conduits + otros elementos): %d" % len(mixtos))
    if mixtos:
        log("   En los mixtos, borrar un conduit lo quita de la definicion del grupo")
        log("   y por tanto de todas sus instancias. Hay que decidir por grupo.")
    log("=" * 74)

    out = os.path.join(DEFAULT_ROOT, "data",
                       "f7_diagnostico_grupos_conduits_v01.json")
    try:
        with open(out, "w") as f:
            f.write(json.dumps({
                "version": VERSION,
                "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "conduits": len(conduits),
                "fittings": len(fittings),
                "sin_grupo_conduits": dist_c.get(0, 0) + dist_c.get(-1, 0),
                "grupos": detalle,
            }, ensure_ascii=True, indent=1))
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
