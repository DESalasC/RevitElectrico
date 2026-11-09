# -*- coding: utf-8 -*-
"""F6_REHOSPEDAR_TECHO_E05_v01.py - Rehospeda los accesorios de techo de E05.

Solo actua sobre instancias APT-E-05-P5 cuya altura absoluta esta cerca de 0
(hospedadas por error en un cielorraso a cota 0). Las reasigna al Compound
Ceiling cuya cara inferior esta a la cota objetivo (2,60 m sobre Piso 5).

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Rehospedaje por cara inferior proyectada.
2. 2026-11-08: corrige los 12 accesorios que quedaron a Z=0.
3. Heredado: sin registro previo disponible.
"""
import json
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    HostObjectUtils,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import Structure

FT = 3.280839895
TOL_Z_M = 0.60

CATS = [BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_ElectricalFixtures,
        BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_LightingDevices]


def _eid(e):
    for a in ("Value", "IntegerValue"):
        try:
            return int(getattr(e, a))
        except Exception:
            pass
    return None


def _safe(v):
    try:
        s = str(v)
    except Exception:
        return "?"
    out = ""
    for c in s:
        try:
            c.encode("ascii")
            out += c
        except Exception:
            out += "_"
    return out


def _norm(t):
    if t is None:
        return ""
    try:
        t = unicode(t)  # noqa: F821
    except Exception:
        t = str(t)
    import unicodedata
    try:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return "".join(c for c in t if ord(c) < 128).strip().lower()


def _familia(doc, nombre):
    from Autodesk.Revit.DB import Family
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        if _norm(fam.Name) == _norm(nombre):
            return fam
    return None


def _simbolo(doc, fam, nombre):
    objetivo = _norm(nombre)
    syms = []
    for sid in fam.GetFamilySymbolIds():
        try:
            s = doc.GetElement(sid)
            p = s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            syms.append((sid, (p.AsString() if p is not None else "") or ""))
        except Exception:
            pass
    for sid, n in syms:
        if _norm(n) == objetivo:
            return doc.GetElement(sid)
    for sid, n in syms:
        nn = _norm(n)
        if objetivo and (objetivo in nn or nn in objetivo):
            return doc.GetElement(sid)
    return doc.GetElement(syms[0][0]) if syms else None


def corregir(doc, confirmar=False):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    data = json.load(open(os.path.join(root, "data", "E05_transferencia_panel_ancla_v03.json"), "r"))
    objs = [(float(d["x_revit_m"]), float(d["y_revit_m"]), float(d["z_local_m"]),
             d["familia_revit"], d.get("simbolo"), d["nombre_bloque_hijo"])
            for d in data["dispositivos"]]

    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _norm(lv.Name) == _norm(data.get("nivel", "Piso 5")):
            nivel = lv
            break
    if nivel is None:
        print("Nivel no encontrado")
        return

    techos = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType())

    pendientes = []
    for bic in CATS:
        for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
            try:
                p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                c = p.AsString() if p is not None else ""
            except Exception:
                c = ""
            if not (c and "APT-E-05-P5" in c):
                continue
            try:
                z_rel = (inst.Location.Point.Z - nivel.Elevation) * 0.3048
            except Exception:
                continue
            if z_rel < 1.0:
                pendientes.append(inst)

    print("pendientes_techo=" + str(len(pendientes)))
    if not confirmar:
        return

    t = Transaction(doc, "F6 - Rehospedar techo E05")
    t.Start()
    creados = 0
    fallos = []
    try:
        for inst in pendientes:
            try:
                pt = inst.Location.Point
                x_m = pt.X * 0.3048
                y_m = pt.Y * 0.3048
                best = min(objs, key=lambda o: math.hypot(x_m - o[0], y_m - o[1]))
                z_obj = nivel.Elevation + best[2] * FT

                elegido = None
                for techo in techos:
                    bb = techo.get_BoundingBox(None)
                    if bb is None:
                        continue
                    if not (bb.Min.X - 0.5 <= pt.X <= bb.Max.X + 0.5 and bb.Min.Y - 0.5 <= pt.Y <= bb.Max.Y + 0.5):
                        continue
                    refs = []
                    try:
                        refs.extend(list(HostObjectUtils.GetBottomFaces(techo)))
                    except Exception:
                        pass
                    for r in refs:
                        try:
                            f = techo.GetGeometryObjectFromReference(r)
                            if f is None:
                                continue
                            pr = f.Project(XYZ(pt.X, pt.Y, z_obj))
                            if pr is None:
                                continue
                            dz = abs(pr.XYZPoint.Z - z_obj)
                            if dz <= TOL_Z_M * FT and (elegido is None or dz < elegido[0]):
                                elegido = (dz, techo, r, pr.XYZPoint)
                        except Exception:
                            pass
                if elegido is None:
                    fallos.append({"bloque": best[5], "motivo": "sin cielorraso a 2,60 m"})
                    continue

                fam = _familia(doc, best[3])
                sym = _simbolo(doc, fam, best[4]) if fam is not None else None
                if sym is None:
                    fallos.append({"bloque": best[5], "motivo": "sin familia/simbolo"})
                    continue
                if not sym.IsActive:
                    sym.Activate()
                    doc.Regenerate()

                nueva = doc.Create.NewFamilyInstance(elegido[3], sym, elegido[1], nivel, Structure.StructuralType.NonStructural)
                try:
                    cp = nueva.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cp is not None and not cp.IsReadOnly:
                        cp.Set("APT-E-05-P5")
                except Exception:
                    pass
                try:
                    sp = nueva.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM)
                    if sp is not None and not sp.IsReadOnly:
                        sp.Set(nivel.Id)
                except Exception:
                    pass
                doc.Delete(inst.Id)
                creados += 1
            except Exception as ex:
                fallos.append({"motivo": _safe(ex)})
    finally:
        t.Commit()

    print("creados={} fallos={}".format(creados, len(fallos)))
    if fallos:
        print("primeros_fallos=" + str(fallos[:3]))
    return {"creados": creados, "fallos": fallos}


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    corregir(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
