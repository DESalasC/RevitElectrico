# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_PANEL_ANCLA_v02.py
=================================
Aplica la transferencia del Apartamento Tipo E 05 usando su panel como ancla.

Correcciones frente a v01:
  * X,Y,Z se toman de los campos en PIES del JSON (x_revit_ft, y_revit_ft,
    z_abs_ft). La API de Revit trabaja en pies.
  * Solo CREA lo que falta. Nunca mueve ni borra instancias existentes, para no
    tocar los apartamentos de referencia F 01 y F 02.
  * Usa las equivalencias vigentes (sin M_Interruptor bipolar ni M_Toma simple).

Entrada: data/E05_transferencia_panel_ancla_v03.json
Salida:  data/resultado_E05_v02.json

--mode=query  -> simulacion
--mode=modify -> aplica

Ultimos tres cambios
--------------------
1. 2026-11-08 v02: unidades en pies y creacion sin mover nada existente.
2. 2026-11-08: equivalencias v02 sin M_Interruptor bipolar / M_Toma simple.
3. 2026-11-08 v01: primera version (fallo por metros/pies).
"""
import json
import math
import os
import unicodedata

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import Structure

FT_A_M = 0.3048
TOL_EXISTE_M = 0.20

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_ElectricalEquipment,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_LightingDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_TelephoneDevices,
]


def _safe(v):
    if v is None:
        return ""
    try:
        s = str(v)
    except Exception:
        return "<?>"
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
        t = unicode(t)
    except Exception:
        t = str(t)
    try:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return "".join(c for c in t if ord(c) < 128).strip().lower()


def _root():
    return os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")


def _eid(eid):
    for attr in ("Value", "IntegerValue"):
        try:
            return int(getattr(eid, attr))
        except Exception:
            pass
    try:
        return int(eid)
    except Exception:
        return None


def _nivel(doc, nombre):
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _norm(lv.Name) == _norm(nombre):
            return lv
    return None


def _familia(doc, nombre):
    from Autodesk.Revit.DB import Family
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        if _norm(fam.Name) == _norm(nombre):
            return fam
    return None


def _sym_name(sym):
    try:
        p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and p.AsString():
            return _safe(p.AsString())
    except Exception:
        pass
    return ""


def _simbolo(doc, fam, nombre):
    objetivo = _norm(nombre)
    syms = []
    for sid in fam.GetFamilySymbolIds():
        try:
            s = doc.GetElement(sid)
            syms.append((sid, _sym_name(s)))
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


def _instancias(doc):
    out = []
    for bic in CATEGORIAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    fam = _safe(inst.Symbol.Family.Name)
                except Exception:
                    fam = ""
                try:
                    p = inst.Location.Point
                except Exception:
                    continue
                out.append({"familia": _norm(fam), "x_m": p.X * FT_A_M, "y_m": p.Y * FT_A_M})
        except Exception:
            pass
    return out


def aplicar(doc, confirmar=False,
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_out="data/resultado_E05_v02.json"):
    root = _root()
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    data = json.load(open(json_in, "r"))
    nivel = _nivel(doc, data.get("nivel", "Piso 5"))
    if nivel is None:
        print("Nivel no encontrado.")
        return {"ok": False}

    existentes = _instancias(doc)
    res = {"modo": "aplicar" if confirmar else "simulacion",
           "documento": _safe(doc.Title),
           "panel_id": (data.get("panel_ancla") or {}).get("panel_rvt_id"),
           "delta_panel_m": (data.get("panel_ancla") or {}).get("delta_xy_m"),
           "existentes": len(existentes), "omitidos": 0,
           "a_crear": 0, "creados": 0, "fallos": []}

    pendientes = []
    for d in data.get("dispositivos") or []:
        fam = _norm(d.get("familia_revit"))
        x_m = float(d["x_revit_m"])
        y_m = float(d["y_revit_m"])
        ya = False
        for e in existentes:
            if e["familia"] == fam and math.hypot(e["x_m"] - x_m, e["y_m"] - y_m) <= TOL_EXISTE_M:
                ya = True
                break
        if ya:
            res["omitidos"] += 1
        else:
            pendientes.append(d)
    res["a_crear"] = len(pendientes)

    if not confirmar:
        print("SIMULACION: existentes={} omitidos={} a_crear={}".format(
            res["existentes"], res["omitidos"], res["a_crear"]))
        return res

    t = Transaction(doc, "F6 - Crear E05 por panel-ancla (pies)")
    t.Start()
    try:
        for d in pendientes:
            try:
                fam = _familia(doc, d.get("familia_revit"))
                if fam is None:
                    res["fallos"].append({"bloque": d["nombre_bloque_hijo"],
                                          "motivo": "familia no encontrada: " + str(d.get("familia_revit"))})
                    continue
                sym = _simbolo(doc, fam, d.get("simbolo"))
                if sym is None:
                    res["fallos"].append({"bloque": d["nombre_bloque_hijo"], "motivo": "sin simbolo"})
                    continue
                if not sym.IsActive:
                    try:
                        sym.Activate()
                        doc.Regenerate()
                    except Exception:
                        pass
                inst = doc.Create.NewFamilyInstance(
                    XYZ(float(d["x_revit_ft"]), float(d["y_revit_ft"]),
                        nivel.Elevation + float(d["z_local_m"]) * 3.280839895),
                    sym, Structure.StructuralType.NonStructural)
                # Asegurar Z: Revit ignora la Z en algunas familias; se corrige tras regenerar.
                try:
                    from Autodesk.Revit.DB import ElementTransformUtils
                    doc.Regenerate()
                    p_actual = inst.Location.Point
                    z_objetivo = nivel.Elevation + float(d["z_local_m"]) * 3.280839895
                    dz = z_objetivo - p_actual.Z
                    if abs(dz) > 0.01:
                        ElementTransformUtils.MoveElement(doc, inst.Id, XYZ(0, 0, dz))
                        doc.Regenerate()
                except Exception:
                    pass
                try:
                    cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cp is not None and not cp.IsReadOnly:
                        cp.Set("APT-E-05-P5")
                except Exception:
                    pass
                res["creados"] += 1
            except Exception as ex:
                res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                      "motivo": "excepcion: " + _safe(str(ex))})
    finally:
        t.Commit()

    f = open(json_out, "w")
    try:
        json.dump(res, f, indent=2)
    finally:
        f.close()
    print("RESULTADO: creados={} omitidos={} fallos={}".format(
        res["creados"], res["omitidos"], len(res["fallos"])))
    return res


if __name__ == "__main__":
    try:
        _confirmar = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _confirmar = False
    aplicar(__revit__.ActiveUIDocument.Document, confirmar=_confirmar)  # noqa: F821
