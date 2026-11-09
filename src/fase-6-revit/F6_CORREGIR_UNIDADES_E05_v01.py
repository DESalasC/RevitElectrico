# -*- coding: utf-8 -*-
"""
F6_CORREGIR_UNIDADES_E05_v01.py
===============================
Corrige el error de unidades de la primera aplicacion de E 05: las coordenadas
X,Y del DXF estan en metros, pero se enviaron a la API de Revit como si fueran
pies. Resultado: los dispositivos quedaron comprimidos cerca del origen.

Este script busca las instancias que quedaron exactamente en el punto erroneo
(x_m, y_m interpretados como pies) y las mueve al punto correcto
(x_m * 3.28084, y_m * 3.28084). No crea ni borra nada.

Uso:
  --mode=query  -> simulacion
  --mode=modify -> aplica

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Correccion de unidades metros/pies en X,Y.
2. 2026-11-08: detectado tras la aplicacion E05 (25 GFCI en 3x3 m).
3. Heredado: sin registro previo disponible.
"""
import json
import math
import os
import unicodedata

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import ElementTransformUtils

METROS_A_PIES = 3.28084
TOL_BUSQUEDA_M = 0.12

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
    t = _safe(t)
    try:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return t.strip().lower()


def _root():
    return os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")


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


def _instancias(doc):
    out = []
    for bic in CATEGORIAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    fam = _safe(inst.Symbol.Family.Name)
                except Exception:
                    fam = ""
                pt = None
                try:
                    loc = inst.Location
                    if loc is not None and hasattr(loc, "Point"):
                        pt = loc.Point
                except Exception:
                    pass
                if pt is None:
                    continue
                out.append({"id": _element_id_int(inst.Id), "familia": fam, "x": pt.X, "y": pt.Y, "z": pt.Z, "el": inst})
        except Exception:
            pass
    return out


def corregir(doc, confirmar=False,
             json_in="data/E05_transferencia_panel_ancla_v02.json",
             json_out="data/resultado_correccion_unidades_E05_v01.json"):
    root = _root()
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    data = json.load(open(json_in, "r"))
    nivel_nombre = data.get("nivel", "Piso 5")

    from Autodesk.Revit.DB import Level
    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _norm(lv.Name) == _norm(nivel_nombre):
            nivel = lv
            break
    if nivel is None:
        print("Nivel no encontrado: " + nivel_nombre)
        return {"aprobado": False}

    elev_ft = nivel.Elevation
    instancias = _instancias(doc)

    pares = []
    for idx, d in enumerate(data.get("dispositivos") or []):
        x_m = float(d["x_revit_esperado"])
        y_m = float(d["y_revit_esperado"])
        fam = _norm(d.get("familia_revit"))
        for e in instancias:
            if _norm(e["familia"]) != fam:
                continue
            dist = math.hypot(e["x"] - x_m, e["y"] - y_m)
            if dist <= TOL_BUSQUEDA_M:
                pares.append((dist, idx, e, x_m, y_m, float(d["z_local_m"])))
    pares.sort(key=lambda t: t[0])

    usados_inst = set()
    usados_idx = set()
    asignados = []
    for dist, idx, e, x_m, y_m, z_local in pares:
        if idx in usados_idx:
            continue
        eid = str(e["id"])
        if eid in usados_inst:
            continue
        usados_idx.add(idx)
        usados_inst.add(eid)
        asignados.append({"inst": e, "x_m": x_m, "y_m": y_m, "z_local": z_local, "dist": dist})

    res = {
        "modo": "aplicar" if confirmar else "simulacion",
        "documento": _safe(doc.Title),
        "nivel": nivel_nombre,
        "objetivos": len(data.get("dispositivos") or []),
        "instancias_electricas": len(instancias),
        "coincidencias": len(asignados),
        "movidos": 0,
        "sin_coincidencia": (len(data.get("dispositivos") or []) - len(asignados)),
        "detalle": [],
    }

    for a in asignados:
        res["detalle"].append({"id": int(a["inst"]["id"]), "familia": a["inst"]["familia"],
                               "de": [round(a["inst"]["x"], 3), round(a["inst"]["y"], 3)],
                               "a": [round(a["x_m"] * METROS_A_PIES, 3), round(a["y_m"] * METROS_A_PIES, 3)]})

    if not confirmar:
        print("SIMULACION: objetivos={} coincidencias={} sin_coincidencia={}".format(
            res["objetivos"], res["coincidencias"], res["sin_coincidencia"]))
        print(json.dumps(res, indent=2, ensure_ascii=True))
        return res

    t = Transaction(doc, "F6 - Corregir unidades E05 (m -> pies)")
    t.Start()
    try:
        for a in asignados:
            inst = a["inst"]["el"]
            destino = XYZ(a["x_m"] * METROS_A_PIES, a["y_m"] * METROS_A_PIES,
                          elev_ft + a["z_local"] * METROS_A_PIES)
            delta = XYZ(destino.X - a["inst"]["x"], destino.Y - a["inst"]["y"],
                        destino.Z - a["inst"]["z"])
            ElementTransformUtils.MoveElement(doc, inst.Id, delta)
            try:
                cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if cp is not None and not cp.IsReadOnly:
                    cp.Set("APT-E-05-P5")
            except Exception:
                pass
            res["movidos"] += 1
    finally:
        t.Commit()

    f = open(json_out, "w")
    try:
        json.dump(res, f, indent=2)
    finally:
        f.close()
    print("RESULTADO: movidos={} sin_coincidencia={} -> {}".format(
        res["movidos"], res["sin_coincidencia"], json_out))
    return res


if __name__ == "__main__":
    try:
        _confirmar = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _confirmar = False
    corregir(__revit__.ActiveUIDocument.Document, confirmar=_confirmar)  # noqa: F821
