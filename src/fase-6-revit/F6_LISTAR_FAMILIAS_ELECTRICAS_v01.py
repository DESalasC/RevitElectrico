# -*- coding: utf-8 -*-
"""F6_LISTAR_FAMILIAS_ELECTRICAS_v01.py - Lista familias y simbolos electricos reales.

Salida: data/familias_electricas_reales_v01.json

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Inventario de familias/simbolos por categoria
   electrica para resolver mapeos faltantes.
2. 2026-11-08: soporte para F6_APLICAR_E05_PANEL_ANCLA_v01.py.
3. Heredado: sin registro previo disponible.
"""
import json
import os
import unicodedata

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
)

CATEGORIAS = [
    ("ElectricalFixtures", BuiltInCategory.OST_ElectricalFixtures),
    ("ElectricalEquipment", BuiltInCategory.OST_ElectricalEquipment),
    ("LightingFixtures", BuiltInCategory.OST_LightingFixtures),
    ("LightingDevices", BuiltInCategory.OST_LightingDevices),
    ("DataDevices", BuiltInCategory.OST_DataDevices),
    ("CommunicationDevices", BuiltInCategory.OST_CommunicationDevices),
    ("TelephoneDevices", BuiltInCategory.OST_TelephoneDevices),
]


def _safe(valor):
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


def _norm(t):
    t = _safe(t)
    try:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return t.strip().lower()


def _sym_name(sym):
    try:
        p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and p.AsString():
            return _safe(p.AsString())
    except Exception:
        pass
    return ""


def main(doc):
    salida = {}
    for nombre, bic in CATEGORIAS:
        familias = {}
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    sym = inst.Symbol
                    fam = sym.Family
                    fname = _safe(fam.Name)
                    sname = _sym_name(sym)
                except Exception:
                    continue
                item = familias.setdefault(fname, {"simbolos": [], "instancias": 0})
                item["instancias"] += 1
                if sname and sname not in item["simbolos"]:
                    item["simbolos"].append(sname)
        except Exception:
            pass
        salida[nombre] = familias

    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    destino = os.path.join(root, "data", "familias_electricas_reales_v01.json")
    try:
        f = open(destino, "w")
        try:
            json.dump(salida, f, indent=2)
        finally:
            f.close()
    except Exception:
        pass

    print("=== FAMILIAS ELECTRICAS REALES ===")
    for cat in salida:
        print("[" + cat + "]")
        for fam in sorted(salida[cat]):
            d = salida[cat][fam]
            print("  {} | inst={} | simbolos={}".format(fam, d["instancias"], len(d["simbolos"])))
    print("JSON: " + destino)
    return salida


if __name__ == "__main__":
    main(__revit__.ActiveUIDocument.Document)  # noqa: F821
