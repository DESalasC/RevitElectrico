# -*- coding: utf-8 -*-
"""F6_VERIFICAR_E05_v01.py - Verifica la ubicacion de los 49 dispositivos de E05.

Convierte las coordenadas de Revit (pies) a metros y las compara con el JSON de
transferencia. Reporta cuantos quedan dentro de 0,20 m, cuantos faltan y si hay
aglomeracion (mas de N elementos en un area de 3x3 m).

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Verificacion post-correccion de unidades.
2. 2026-11-08: detecta aglomeracion y dispositivos faltantes.
3. Heredado: sin registro previo disponible.
"""
import json
import math
import os
import unicodedata

from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

FT_A_M = 0.3048
CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_ElectricalEquipment,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_LightingDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_TelephoneDevices,
]
# familias equivalentes cuando el DXF no coincide con el nombre real
EQUIV = {
    "m_toma simple": ["m_toma de telefono - datos", "m_toma-comunicaciones", "m_toma - 220v"],
    "m_interruptor bipolar": ["m_interruptor-doble", "m_pulsador - interruptor", "m_interruptor"],
}


def _safe(v):
    try:
        s = str(v)
    except Exception:
        return ""
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


def verificar(doc, json_in="data/E05_transferencia_panel_ancla_v02.json",
              json_out="data/verificacion_E05_v01.json"):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    data = json.load(open(json_in, "r"))
    instancias = []
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
                instancias.append({"familia": _norm(fam), "x": p.X * FT_A_M, "y": p.Y * FT_A_M})
        except Exception:
            pass

    ok = 0
    cerca = 0
    faltan = 0
    detalle = []
    usados = set()
    for d in data.get("dispositivos") or []:
        fam = _norm(d.get("familia_revit"))
        objetivo = [fam] + EQUIV.get(fam, [])
        x = float(d.get("x_revit_m", d.get("x_revit_esperado", 0)))
        y = float(d.get("y_revit_m", d.get("y_revit_esperado", 0)))
        mejor = None
        for i, e in enumerate(instancias):
            if i in usados:
                continue
            if e["familia"] not in objetivo:
                continue
            dist = math.hypot(e["x"] - x, e["y"] - y)
            if mejor is None or dist < mejor[0]:
                mejor = (dist, i)
        if mejor is None:
            faltan += 1
            detalle.append({"bloque": d["nombre_bloque_hijo"], "estado": "falta"})
            continue
        usados.add(mejor[1])
        if mejor[0] <= 0.20:
            ok += 1
            detalle.append({"bloque": d["nombre_bloque_hijo"], "estado": "ok", "dist": round(mejor[0], 4)})
        else:
            cerca += 1
            detalle.append({"bloque": d["nombre_bloque_hijo"], "estado": "fuera", "dist": round(mejor[0], 4)})

    # aglomeracion: maximo de instancias en ventana 3x3 m
    max_cluster = 0
    for a in instancias:
        n = 0
        for b in instancias:
            if abs(a["x"] - b["x"]) <= 1.5 and abs(a["y"] - b["y"]) <= 1.5:
                n += 1
        if n > max_cluster:
            max_cluster = n

    res = {
        "documento": _safe(doc.Title),
        "objetivos": len(data.get("dispositivos") or []),
        "ok_020m": ok,
        "fuera_020m": cerca,
        "faltan": faltan,
        "instancias_electricas": len(instancias),
        "max_en_3x3m": max_cluster,
        "detalle": detalle,
    }
    f = open(json_out, "w")
    try:
        json.dump(res, f, indent=2)
    finally:
        f.close()
    print("VERIFICACION: objetivos={} ok={} fuera={} faltan={} max_3x3={}".format(
        res["objetivos"], ok, cerca, faltan, max_cluster))
    return res


if __name__ == "__main__":
    verificar(__revit__.ActiveUIDocument.Document)  # noqa: F821
