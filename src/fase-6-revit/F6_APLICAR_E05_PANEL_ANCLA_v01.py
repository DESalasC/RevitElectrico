# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_PANEL_ANCLA_v01.py
=================================
Aplica la transferencia DXF -> RVT del Apartamento Tipo E 05 usando su panel
como ancla. Es idempotente:

  * Si ya existe una instancia de la misma familia a menos de 0,20 m del punto
    objetivo, no hace nada.
  * Si existe a menos de 1,50 m, la mueve al punto objetivo (reposiciona).
  * Si no existe, la crea con NewFamilyInstance en el nivel destino.

No toca F 01 ni F 02. No toca conduits.

Entrada:
  data/E05_transferencia_panel_ancla_v02.json

Salida:
  data/resultado_E05_v01.json

Uso (pyRevit agent):
  --mode=query  -> simulacion (no modifica)
  --mode=modify -> aplica

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Reposicion/creacion por panel-ancla, idempotente,
   con exclusion explicita de F 01 y F 02.
2. 2026-11-08: validacion previa DXF vs RVT con RE_VALIDAR_TRANSFERENCIA_v01.py.
3. Heredado: sin registro previo disponible.
"""
import json
import math
import os
import unicodedata
import traceback

import clr

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import ElementTransformUtils
from Autodesk.Revit.DB import Structure

METROS_A_PIES = 3.28084
TOL_OK_M = 0.20
TOL_MOVER_M = 1.50

CATEGORIAS_ELECTRICAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_ElectricalEquipment,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_LightingDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_TelephoneDevices,
]


def _safe_str(valor):
    if valor is None:
        return ""
    try:
        s = str(valor)
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


def _norm(texto):
    if texto is None:
        return ""
    t = _safe_str(texto)
    try:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return t.strip().lower()


def _obtener_root():
    env = os.environ.get("REVITELECTRICO_ROOT")
    if env:
        return env
    try:
        return os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    except NameError:
        pass
    return os.path.abspath(".")


def _element_id_int(element_id):
    if element_id is None:
        return None
    for attr in ("Value", "IntegerValue"):
        try:
            return int(getattr(element_id, attr))
        except Exception:
            pass
    try:
        return int(element_id)
    except Exception:
        return None


def _buscar_nivel(doc, nombre):
    for nivel in FilteredElementCollector(doc).OfClass(Level):
        try:
            if _norm(nivel.Name) == _norm(nombre):
                return nivel
        except Exception:
            pass
    return None


def _buscar_familia(doc, nombre):
    if not nombre:
        return None
    from Autodesk.Revit.DB import Family
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            if _norm(fam.Name) == _norm(nombre):
                return fam
        except Exception:
            pass
    return None


def _nombre_simbolo(sym):
    try:
        p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and p.AsString():
            return _safe_str(p.AsString())
    except Exception:
        pass
    return None


def _buscar_simbolo(doc, familia, nombre):
    objetivo = _norm(nombre)
    simbolos = []
    for sid in familia.GetFamilySymbolIds():
        try:
            sym = doc.GetElement(sid)
            n = _nombre_simbolo(sym)
            simbolos.append((sid, n or ""))
        except Exception:
            pass
    for sid, n in simbolos:
        if _norm(n) == objetivo:
            return doc.GetElement(sid)
    for sid, n in simbolos:
        nn = _norm(n)
        if objetivo and (objetivo in nn or nn in objetivo):
            return doc.GetElement(sid)
    if simbolos:
        return doc.GetElement(simbolos[0][0])
    return None


def _instancias_electricas(doc):
    salida = []
    for bic in CATEGORIAS_ELECTRICAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    fam = inst.Symbol.Family.Name if inst.Symbol else ""
                except Exception:
                    fam = ""
                pt = None
                try:
                    loc = inst.Location
                    if loc is not None and hasattr(loc, "Point"):
                        pt = loc.Point
                except Exception:
                    pass
                salida.append({"id": _element_id_int(inst.Id), "familia": _safe_str(fam),
                               "x": None if pt is None else pt.X,
                               "y": None if pt is None else pt.Y,
                               "el": inst})
        except Exception:
            pass
    return salida


def aplicar(doc, confirmar=False,
            json_in="data/E05_transferencia_panel_ancla_v02.json",
            json_out="data/resultado_E05_v01.json"):
    root = _obtener_root()
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    res = {
        "documento": _safe_str(doc.Title),
        "modo": "aplicar" if confirmar else "simulacion",
        "apartamento": "Apartamento Tipo E 05",
        "panel_id": None,
        "delta_panel_m": None,
        "existentes": 0,
        "omitidos_ok": 0,
        "movidos": 0,
        "creados": 0,
        "fallos": [],
    }

    try:
        f = open(json_in, "r")
        try:
            data = json.load(f)
        finally:
            f.close()
    except Exception as ex:
        res["fallos"].append("No se pudo leer {}: {}".format(json_in, ex))
        print(json.dumps(res, indent=2, ensure_ascii=True))
        return res

    nivel = _buscar_nivel(doc, data.get("nivel", "Piso 5"))
    if nivel is None:
        res["fallos"].append("Nivel no encontrado: " + str(data.get("nivel")))
        print(json.dumps(res, indent=2, ensure_ascii=True))
        return res

    elev_ft = nivel.Elevation
    panel = data.get("panel_ancla") or {}
    res["panel_id"] = panel.get("panel_rvt_id")
    res["delta_panel_m"] = panel.get("delta_xy_m")

    existentes = _instancias_electricas(doc)
    res["existentes"] = len(existentes)

    dispositivos = data.get("dispositivos") or []
    pendientes = []

    for d in dispositivos:
        x_obj = float(d["x_revit_esperado"])
        y_obj = float(d["y_revit_esperado"])
        z_obj = elev_ft + float(d["z_local_m"]) * METROS_A_PIES
        fam_obj = d.get("familia_revit") or ""

        candidatos = []
        for e in existentes:
            if e["x"] is None or not e["familia"]:
                continue
            if _norm(e["familia"]) != _norm(fam_obj):
                continue
            dist = math.hypot(x_obj - e["x"], y_obj - e["y"])
            if dist <= TOL_MOVER_M:
                candidatos.append((dist, e))
        candidatos.sort(key=lambda t: t[0])

        if candidatos and candidatos[0][0] <= TOL_OK_M:
            res["omitidos_ok"] += 1
            continue
        if candidatos:
            dist, e = candidatos[0]
            pendientes.append({"accion": "mover", "dist": dist, "existente": e,
                               "objetivo": d, "x": x_obj, "y": y_obj, "z": z_obj})
        else:
            pendientes.append({"accion": "crear", "dist": None, "existente": None,
                               "objetivo": d, "x": x_obj, "y": y_obj, "z": z_obj})

    res["a_mover"] = sum(1 for p in pendientes if p["accion"] == "mover")
    res["a_crear"] = sum(1 for p in pendientes if p["accion"] == "crear")

    if not confirmar:
        print("SIMULACION: existentes={} omitidos_ok={} a_mover={} a_crear={}".format(
            res["existentes"], res["omitidos_ok"], res["a_mover"], res["a_crear"]))
        print(json.dumps(res, indent=2, ensure_ascii=True))
        try:
            f = open(json_out, "w")
            try:
                json.dump(res, f, indent=2)
            finally:
                f.close()
        except Exception:
            pass
        return res

    t = Transaction(doc, "F6 - Aplicar E05 por panel-ancla")
    t.Start()
    try:
        for p in pendientes:
            d = p["objetivo"]
            try:
                if p["accion"] == "mover":
                    inst = p["existente"]["el"]
                    actual = inst.Location.Point
                    delta = XYZ(p["x"] - actual.X, p["y"] - actual.Y, p["z"] - actual.Z)
                    ElementTransformUtils.MoveElement(doc, inst.Id, delta)
                    p["existente"]["x"] = p["x"]
                    p["existente"]["y"] = p["y"]
                    res["movidos"] += 1
                else:
                    familia = _buscar_familia(doc, d.get("familia_revit"))
                    if familia is None:
                        res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                              "motivo": "familia no encontrada: " + str(d.get("familia_revit"))})
                        continue
                    sym = _buscar_simbolo(doc, familia, d.get("simbolo"))
                    if sym is None:
                        res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                              "motivo": "simbolo no encontrado: " + str(d.get("simbolo"))})
                        continue
                    if not sym.IsActive:
                        try:
                            sym.Activate()
                            doc.Regenerate()
                        except Exception:
                            pass
                    inst = doc.Create.NewFamilyInstance(
                        XYZ(p["x"], p["y"], p["z"]), sym, nivel,
                        Structure.StructuralType.NonStructural)
                    try:
                        cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                        if cp is not None and not cp.IsReadOnly:
                            cp.Set("APT-E-05-P5")
                    except Exception:
                        pass
                    rot = float(d.get("rotacion") or 0)
                    if rot:
                        try:
                            rp = inst.get_Parameter(BuiltInParameter.ROTATION)
                            if rp is not None and not rp.IsReadOnly:
                                rp.Set(rot * 3.141592653589793 / 180.0)
                        except Exception:
                            pass
                    res["creados"] += 1
            except Exception as ex:
                res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                      "motivo": "excepcion: " + _safe_str(str(ex))})
                traceback.print_exc()
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

    print("RESULTADO: movidos={} creados={} omitidos_ok={} fallos={}".format(
        res["movidos"], res["creados"], res["omitidos_ok"], len(res["fallos"])))
    print(json.dumps(res, indent=2, ensure_ascii=True))
    return res


if __name__ == "__main__":
    try:
        _confirmar = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _confirmar = False
    aplicar(__revit__.ActiveUIDocument.Document, confirmar=_confirmar)  # noqa: F821
