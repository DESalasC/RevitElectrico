# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_FACE_v01.py
==========================
Coloca los 49 dispositivos de E 05 sobre las caras reales usando la sobrecarga
correcta de la API:

    NewFamilyInstance(Face, XYZ location, XYZ referenceDir, FamilySymbol)

  * tomas / interruptores (z_local < 2,0) -> cara lateral del muro en Piso 5,
    con direccion de referencia vertical (0,0,1) => Hand vertical como F01/F02.
  * luminarias / ventiladores / timbre (z_local >= 2,0) -> cara inferior del
    Compound Ceiling a 2,60 m, con direccion (1,0,0).

No usa fallback libre: si la cara falla, el dispositivo queda pendiente y se
reporta el error.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: firma (Face, XYZ, XYZ, FamilySymbol) validada contra las
   sobrecargas reales del API.
2. 2026-11-08: comparacion con F01/F02 (Host=muro, Hand vertical).
3. Heredado: intentos previos con Reference fallaban por firma equivocada.
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
    ShellLayerType,
    Transaction,
    XYZ,
)

FT = 3.280839895
TOL_MURO_M = 2.50
TOL_TECHO_M = 0.80

CATS = [BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
        BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_TelephoneDevices]


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


def _dist_curva(w, x, y):
    try:
        c = w.Location.Curve
        r = c.Project(XYZ(x, y, 0))
        p = r.XYZPoint
        return math.hypot(p.X - x, p.Y - y)
    except Exception:
        return 999.0


def _caras(host, punto, es_techo):
    """Caras con referencia valida: geometria con ComputeReferences=True."""
    from Autodesk.Revit.DB import Options, Solid, GeometryInstance
    opts = Options()
    opts.ComputeReferences = True
    salida = []

    def tratar_solid(sol):
        try:
            for f in sol.Faces:
                try:
                    pr = f.Project(punto)
                    if pr is None:
                        continue
                    n = f.ComputeNormal(pr.UVPoint)
                    if es_techo:
                        if n.Z > -0.7:
                            continue
                        if abs(pr.XYZPoint.Z - punto.Z) > TOL_TECHO_M * FT:
                            continue
                    else:
                        if abs(n.Z) > 0.3:
                            continue
                    salida.append((pr.Distance, f, pr.XYZPoint))
                except Exception:
                    pass
        except Exception:
            pass

    try:
        for g in host.get_Geometry(opts):
            if g is None:
                continue
            if isinstance(g, Solid):
                tratar_solid(g)
            elif isinstance(g, GeometryInstance):
                try:
                    for gg in g.GetInstanceGeometry():
                        if isinstance(gg, Solid):
                            tratar_solid(gg)
                except Exception:
                    pass
    except Exception:
        pass
    return salida


def _instancias_e05(doc):
    out = []
    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = p.AsString() if p is not None else ""
                except Exception:
                    c = ""
                if c and "APT-E-05-P5" in c:
                    out.append(inst)
        except Exception:
            pass
    return out


def aplicar(doc, confirmar=False,
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_out="data/resultado_E05_face_v01.json"):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    data = json.load(open(json_in, "r"))
    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _norm(lv.Name) == _norm(data.get("nivel", "Piso 5")):
            nivel = lv
            break
    if nivel is None:
        print("Nivel no encontrado")
        return {"ok": False}

    res = {"modo": "aplicar" if confirmar else "simulacion",
           "documento": _safe(doc.Title),
           "dispositivos": len(data.get("dispositivos") or []),
           "con_cara": 0, "sin_cara": 0, "creados": 0, "eliminados": 0,
           "con_host": 0, "hand_vertical": 0, "fallos": []}

    if confirmar:
        previas = _instancias_e05(doc)
        if previas:
            t = Transaction(doc, "F6 - Limpiar E05 face")
            t.Start()
            try:
                for inst in previas:
                    try:
                        doc.Delete(inst.Id)
                        res["eliminados"] += 1
                    except Exception:
                        pass
            finally:
                t.Commit()

    muros = []
    for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType():
        try:
            if _eid(w.LevelId) != _eid(nivel.Id):
                continue
            muros.append(w)
        except Exception:
            pass

    techos = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType())

    planes = []
    for d in data.get("dispositivos") or []:
        x_ft = float(d["x_revit_ft"])
        y_ft = float(d["y_revit_ft"])
        z_ft = nivel.Elevation + float(d["z_local_m"]) * FT
        punto = XYZ(x_ft, y_ft, z_ft)
        es_techo = float(d["z_local_m"]) >= 2.0

        elegido = None
        if es_techo:
            for techo in techos:
                bb = techo.get_BoundingBox(None)
                if bb is None:
                    continue
                if not (bb.Min.X - 0.5 <= x_ft <= bb.Max.X + 0.5 and bb.Min.Y - 0.5 <= y_ft <= bb.Max.Y + 0.5):
                    continue
                for dist, f, pt in _caras(techo, punto, True):
                    if abs(pt.Z - z_ft) <= TOL_TECHO_M * FT and (elegido is None or dist < elegido[0]):
                        elegido = (dist, f, pt)
        else:
            cercanos = sorted((_dist_curva(w, x_ft, y_ft), w) for w in muros)[:10]
            for dist_w, w in cercanos:
                if dist_w > TOL_MURO_M * FT:
                    continue
                for dist, f, pt in _caras(w, punto, False):
                    if elegido is None or dist < elegido[0]:
                        elegido = (dist, f, pt)

        if elegido is None:
            res["sin_cara"] += 1
            res["fallos"].append({"bloque": d["nombre_bloque_hijo"], "motivo": "sin cara"})
            continue
        res["con_cara"] += 1
        direccion = XYZ(1, 0, 0) if es_techo else XYZ(0, 0, 1)
        planes.append({"d": d, "cara": elegido[1], "punto": elegido[2], "dir": direccion})

    print("SIMULACION: dispositivos={} con_cara={} sin_cara={}".format(
        res["dispositivos"], res["con_cara"], res["sin_cara"]))
    if not confirmar:
        return res

    t = Transaction(doc, "F6 - Crear E05 sobre caras (Face)")
    t.Start()
    try:
        for p in planes:
            d = p["d"]
            try:
                fam = _familia(doc, d.get("familia_revit"))
                sym = _simbolo(doc, fam, d.get("simbolo")) if fam is not None else None
                if sym is None:
                    res["fallos"].append({"bloque": d["nombre_bloque_hijo"], "motivo": "sin familia/simbolo"})
                    continue
                if not sym.IsActive:
                    sym.Activate()
                    doc.Regenerate()
                inst = doc.Create.NewFamilyInstance(p["cara"], p["punto"], p["dir"], sym)
                try:
                    cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cp is not None and not cp.IsReadOnly:
                        cp.Set("APT-E-05-P5")
                except Exception:
                    pass
                try:
                    sp = inst.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM)
                    if sp is not None and not sp.IsReadOnly:
                        sp.Set(nivel.Id)
                except Exception:
                    pass
                res["creados"] += 1
                try:
                    if inst.Host is not None:
                        res["con_host"] += 1
                except Exception:
                    pass
                try:
                    if abs(inst.HandOrientation.Z) > 0.9:
                        res["hand_vertical"] += 1
                except Exception:
                    pass
            except Exception as ex:
                res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"), "motivo": _safe(ex)})
    finally:
        t.Commit()

    try:
        f = open(json_out, "w")
        try:
            json.dump(res, f, indent=2)
        finally:
            f.close()
    except Exception:
        pass
    print("RESULTADO: creados={} con_host={} hand_vertical={} fallos={}".format(
        res["creados"], res["con_host"], res["hand_vertical"], len(res["fallos"])))
    return res


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    aplicar(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
