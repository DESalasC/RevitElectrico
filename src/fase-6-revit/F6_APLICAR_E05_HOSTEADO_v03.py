# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_HOSTEADO_v03.py
=============================
Coloca los 49 dispositivos de E 05 sobre las caras reales:

  * tomas / interruptores -> cara lateral del muro existente en Piso 5
  * luminarias / ventiladores / timbre -> cara inferior del Compound Ceiling
    "Falso techo continuo de placa de yeso laminado" a 2,60 m

Correcciones frente a v02:
  * Llamada directa a doc.Create.NewFamilyInstance(Reference, XYZ, FamilySymbol)
    sin reflection (Invoke fallaba en IronPython 2.7 / Revit 2026).
  * No se fuerza LevelId en familias face-based (no aplicable).
  * Ajuste de Z via parametro INSTANCE_ELEVATION_PARAM cuando Location.Point falla.
  * Verifica Host con inst.Host (no None esperado para face-based).
  * Elimina solo instancias con Comments APT-E-05-P5. No toca F 01 ni F 02.

--mode=query  -> simulacion
--mode=modify -> aplica
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
from Autodesk.Revit.DB import ElementTransformUtils

FT = 3.280839895
TOL_MURO_M = 2.50
TOL_TECHO_M = 1.50

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


def _cara_muro(wall, punto):
    refs = []
    for lado in (ShellLayerType.Exterior, ShellLayerType.Interior):
        try:
            refs.extend(list(HostObjectUtils.GetSideFaces(wall, lado)))
        except Exception:
            pass
    mejor = None
    for r in refs:
        try:
            f = wall.GetGeometryObjectFromReference(r)
            if f is None:
                continue
            pr = f.Project(punto)
            if pr is None:
                continue
            if mejor is None or pr.Distance < mejor[0]:
                mejor = (pr.Distance, r, pr.XYZPoint)
        except Exception:
            pass
    return mejor


def _cara_techo(ceiling, punto):
    refs = []
    try:
        refs.extend(list(HostObjectUtils.GetBottomFaces(ceiling)))
    except Exception:
        pass
    mejor = None
    for r in refs:
        try:
            f = ceiling.GetGeometryObjectFromReference(r)
            if f is None:
                continue
            pr = f.Project(punto)
            if pr is None:
                continue
            if mejor is None or pr.Distance < mejor[0]:
                mejor = (pr.Distance, r, pr.XYZPoint)
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


def _dist_curva(w, x, y):
    try:
        c = w.Location.Curve
        r = c.Project(XYZ(x, y, 0))
        p = r.XYZPoint
        return math.hypot(p.X - x, p.Y - y)
    except Exception:
        return 999.0


def _punto_actual(inst):
    """Obtiene la posicion actual de forma segura para familias face-based."""
    try:
        return inst.Location.Point
    except Exception:
        pass
    # Fallback: parametro de elevacion
    try:
        p = inst.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM)
        if p is not None:
            return XYZ(0, 0, p.AsDouble())
    except Exception:
        pass
    return None


def aplicar(doc, confirmar=False,
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_out="data/resultado_E05_hosteado_v03.json"):
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
           "con_host": 0, "con_nivel": 0, "fallos": []}

    if confirmar:
        previas = _instancias_e05(doc)
        if previas:
            t = Transaction(doc, "F6 - Limpiar E05 v03")
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
        print("LIMPIEZA: eliminadas={} instancias previas APT-E-05-P5".format(res["eliminados"]))

    muros = []
    for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType():
        try:
            if _eid(w.LevelId) != _eid(nivel.Id):
                continue
            bb = w.get_BoundingBox(None)
            if bb is None:
                continue
            muros.append(w)
        except Exception:
            pass

    techos = []
    for c in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType():
        try:
            bb = c.get_BoundingBox(None)
            if bb is None:
                continue
            techos.append(c)
        except Exception:
            pass

    planes = []
    for d in data.get("dispositivos") or []:
        x_ft = float(d["x_revit_ft"])
        y_ft = float(d["y_revit_ft"])
        z_ft = nivel.Elevation + float(d["z_local_m"]) * FT
        punto = XYZ(x_ft, y_ft, z_ft)
        es_techo = float(d["z_local_m"]) >= 2.0

        elegido = None
        if es_techo:
            candidatos = []
            for c in techos:
                bb = c.get_BoundingBox(None)
                if bb is None:
                    continue
                if abs(bb.Min.Z - z_ft) > TOL_TECHO_M * FT:
                    continue
                if not (bb.Min.X - 0.5 <= x_ft <= bb.Max.X + 0.5 and bb.Min.Y - 0.5 <= y_ft <= bb.Max.Y + 0.5):
                    continue
                mc = _cara_techo(c, punto)
                if mc is not None:
                    candidatos.append((mc[0], c, mc[1], mc[2]))
            if candidatos:
                candidatos.sort(key=lambda t: t[0])
                elegido = candidatos[0]
        else:
            cercanos = sorted((_dist_curva(w, x_ft, y_ft), w) for w in muros)[:10]
            for dist, w in cercanos:
                if dist > TOL_MURO_M * FT:
                    continue
                mc = _cara_muro(w, punto)
                if mc is not None:
                    elegido = (mc[0], w, mc[1], mc[2])
                    break

        if elegido is None:
            res["sin_cara"] += 1
            res["fallos"].append({"bloque": d["nombre_bloque_hijo"], "motivo": "sin cara de host"})
            continue
        res["con_cara"] += 1
        planes.append({"d": d, "host": elegido[1], "cara": elegido[2], "punto": elegido[3],
                       "tipo": "techo" if es_techo else "muro"})

    print("SIMULACION: dispositivos={} con_cara={} sin_cara={}".format(
        res["dispositivos"], res["con_cara"], res["sin_cara"]))
    if not confirmar:
        return res

    t = Transaction(doc, "F6 - Crear E05 sobre caras reales v03")
    t.Start()
    try:
        for p in planes:
            d = p["d"]
            try:
                fam = _familia(doc, d.get("familia_revit"))
                if fam is None:
                    res["fallos"].append({"bloque": d["nombre_bloque_hijo"],
                                          "motivo": "familia no encontrada: " + str(d.get("familia_revit"))})
                    continue
                sym = _simbolo(doc, fam, d.get("simbolo"))
                if sym is None:
                    res["fallos"].append({"bloque": d["nombre_bloque_hijo"],
                                          "motivo": "simbolo no encontrado: " + str(d.get("simbolo"))})
                    continue
                if not sym.IsActive:
                    try:
                        sym.Activate()
                        doc.Regenerate()
                    except Exception:
                        pass
                inst = None
                err = ""
                # Llamada directa sin reflection (firma Reference/XYZ/FamilySymbol)
                try:
                    inst = doc.Create.NewFamilyInstance(p["cara"], p["punto"], sym)
                except Exception as ex1:
                    err = _safe(ex1)
                    # Fallback: NewFamilyInstance(XYZ, symbol, host, level, structural)
                    try:
                        inst = doc.Create.NewFamilyInstance(p["punto"], sym, p["host"], nivel,
                                                            Structure.StructuralType.NonStructural)
                    except Exception as ex2:
                        err = err + " | " + _safe(ex2)
                if inst is None:
                    res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"), "motivo": err})
                    continue
                # Comment
                try:
                    cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cp is not None and not cp.IsReadOnly:
                        cp.Set("APT-E-05-P5")
                except Exception:
                    pass
                # Nivel: solo si es escribible (no es para face-based)
                try:
                    inst.LevelId = nivel.Id
                    res["con_nivel"] += 1
                except Exception:
                    pass  # face-based: LevelId no aplicable, no es error
                # Verificar host
                try:
                    if inst.Host is not None:
                        res["con_host"] += 1
                except Exception:
                    pass
                # Ajuste de Z objetivo
                try:
                    doc.Regenerate()
                    actual = _punto_actual(inst)
                    if actual is not None:
                        dz = p["punto"].Z - actual.Z
                        if abs(dz) > 0.01:
                            ElementTransformUtils.MoveElement(doc, inst.Id, XYZ(0, 0, dz))
                            doc.Regenerate()
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
    print("RESULTADO: creados={} con_host={} con_nivel={} fallos={}".format(
        res["creados"], res["con_host"], res["con_nivel"], len(res["fallos"])))
    return res


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    aplicar(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
