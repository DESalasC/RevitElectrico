# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_HOSTEADO_v01.py
=============================
Coloca los 49 dispositivos de E 05 usando muros y techos REALES como host,
segun la propuesta del acta 2026-10-25:

  * toma/interruptor -> cara lateral del muro existente mas cercano en Piso 5
  * luminaria/ventilador/timbre -> cara inferior del cielorraso existente

Ventajas frente a la creacion libre:
  * LevelId queda en Piso 5 (no en nivel 0).
  * La cara principal queda vertical (x,z / y,z), no acostada en planta.
  * El equipo queda apoyado en el paramento, no flotando.

Ademas aplica el simbolo correcto por bloque:
  ELEC-T-D-t-15A    -> toma normal (Estandar)
  ELEC-T-GFCI-t-15A -> toma GFCI

No toca F 01 ni F 02. Solo crea/elimina instancias con Comments APT-E-05-P5.

--mode=query  -> simulacion (cuenta hosts encontrados)
--mode=modify -> aplica

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Hospedaje en muro/techo real.
2. 2026-11-08: corrige orientacion (plano vertical), LevelId y simbolo GFCI/normal.
3. Heredado: propuesta del acta RE-2026-10-25 (hosts reales, sin muros temporales).
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
from Autodesk.Revit.DB import Structure

FT = 3.280839895
TOL_MURO_M = 2.00
TOL_TECHO_M = 3.00

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
    try:
        return int(e)
    except Exception:
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
            n = p.AsString() if p is not None else ""
            syms.append((sid, n or ""))
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


def _muros_piso(doc, nivel, xmin, xmax, ymin, ymax):
    out = []
    for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType():
        try:
            if _eid(w.LevelId) != _eid(nivel.Id):
                continue
            bb = w.get_BoundingBox(None)
            if bb is None:
                continue
            if bb.Max.X < xmin or bb.Min.X > xmax or bb.Max.Y < ymin or bb.Min.Y > ymax:
                continue
            out.append(w)
        except Exception:
            pass
    return out


def _techos(doc, xmin, xmax, ymin, ymax):
    out = []
    for c in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType():
        try:
            bb = c.get_BoundingBox(None)
            if bb is None:
                continue
            if bb.Max.X < xmin or bb.Min.X > xmax or bb.Max.Y < ymin or bb.Min.Y > ymax:
                continue
            out.append(c)
        except Exception:
            pass
    return out


def _dist_curva(w, x, y):
    try:
        c = w.Location.Curve
        r = c.Project(XYZ(x, y, 0))
        p = r.XYZPoint
        return math.hypot(p.X - x, p.Y - y)
    except Exception:
        return 999.0


def _mejor_cara(host, punto, lados=True):
    refs = []
    try:
        refs.extend(list(HostObjectUtils.GetSideFaces(host, ShellLayerType.Exterior)))
    except Exception:
        pass
    try:
        refs.extend(list(HostObjectUtils.GetSideFaces(host, ShellLayerType.Interior)))
    except Exception:
        pass
    if not refs:
        try:
            refs.extend(list(HostObjectUtils.GetBottomFaces(host)))
        except Exception:
            pass
    mejor = None
    for r in refs:
        try:
            f = host.GetGeometryObjectFromReference(r)
            if f is None:
                continue
            res = f.Project(punto)
            if res is None:
                continue
            d = res.Distance
            if mejor is None or d < mejor[0]:
                mejor = (d, r, res.XYZPoint)
        except Exception:
            pass
    return mejor


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
            json_out="data/resultado_E05_hosteado_v01.json"):
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
           "existentes_e05": len(_instancias_e05(doc)),
           "con_host": 0, "sin_host": 0, "creados": 0, "eliminados": 0, "fallos": []}

    if confirmar:
        previas = _instancias_e05(doc)
        if previas:
            t = Transaction(doc, "F6 - Limpiar E05 antes de hospedar")
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

    muros = _muros_piso(doc, nivel, 0, 40, 0, 50)
    techos = _techos(doc, 0, 40, 0, 50)

    planes = []
    for d in data.get("dispositivos") or []:
        x_ft = float(d["x_revit_ft"])
        y_ft = float(d["y_revit_ft"])
        z_ft = nivel.Elevation + float(d["z_local_m"]) * FT
        punto = XYZ(x_ft, y_ft, z_ft)
        es_techo = float(d["z_local_m"]) >= 2.0
        host = None
        cara = None
        punto_host = punto
        mejor_d = 999
        if es_techo:
            for c in techos:
                bb = c.get_BoundingBox(None)
                if bb is None:
                    continue
                if abs(bb.Min.Z - z_ft) > 5.0:
                    continue
                if not (bb.Min.X - 1 <= x_ft <= bb.Max.X + 1 and bb.Min.Y - 1 <= y_ft <= bb.Max.Y + 1):
                    continue
                mc = _mejor_cara(c, punto)
                if mc and mc[0] <= TOL_TECHO_M * FT:
                    prioridad = abs(bb.Min.Z - z_ft)
                    if host is None or prioridad < mejor_d:
                        host, cara, punto_host, mejor_d = c, mc[1], mc[2], prioridad
        else:
            cands = sorted((_dist_curva(w, x_ft, y_ft), w) for w in muros)[:8]
            for dist, w in cands:
                if dist > TOL_MURO_M * FT:
                    continue
                mc = _mejor_cara(w, punto)
                if mc and mc[0] < mejor_d:
                    host, cara, punto_host, mejor_d = w, mc[1], mc[2], mc[0]
        if host is None:
            res["sin_host"] += 1
            res["fallos"].append({"bloque": d["nombre_bloque_hijo"], "motivo": "sin host cercano"})
            continue
        res["con_host"] += 1
        planes.append({"d": d, "cara": cara, "punto": punto_host, "host": host, "tipo": "techo" if es_techo else "muro"})

    print("SIMULACION: dispositivos={} con_host={} sin_host={}".format(
        res["dispositivos"], res["con_host"], res["sin_host"]))
    if not confirmar:
        return res

    t = Transaction(doc, "F6 - Crear E05 hospedado")
    t.Start()
    try:
        for p in planes:
            d = p["d"]
            try:
                fam = _familia(doc, d.get("familia_revit"))
                if fam is None:
                    res["fallos"].append({"bloque": d["nombre_bloque_hijo"], "motivo": "familia " + str(d.get("familia_revit"))})
                    continue
                sym = _simbolo(doc, fam, d.get("simbolo"))
                if sym is None:
                    res["fallos"].append({"bloque": d["nombre_bloque_hijo"], "motivo": "simbolo " + str(d.get("simbolo"))})
                    continue
                if not sym.IsActive:
                    sym.Activate()
                    doc.Regenerate()
                inst = None
                try:
                    inst = doc.Create.NewFamilyInstance(p["punto"], sym, p["host"], nivel, Structure.StructuralType.NonStructural)
                except Exception:
                    try:
                        inst = doc.Create.NewFamilyInstance(p["cara"], p["punto"], sym)
                    except Exception:
                        inst = None
                if inst is None:
                    res["fallos"].append({"bloque": d["nombre_bloque_hijo"], "motivo": "no se pudo hospedar"})
                    continue
                try:
                    cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cp is not None and not cp.IsReadOnly:
                        cp.Set("APT-E-05-P5")
                except Exception:
                    pass
                res["creados"] += 1
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
    print("RESULTADO: creados={} eliminados={} fallos={}".format(
        res["creados"], res["eliminados"], len(res["fallos"])))
    return res


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    aplicar(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
