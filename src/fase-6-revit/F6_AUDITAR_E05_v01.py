# -*- coding: utf-8 -*-
"""F6_AUDITAR_E05_v01.py - Audita las instancias creadas para E05.

Lista las instancias con Comments = APT-E-05-P5 y mide su distancia al punto
objetivo mas cercano del JSON de transferencia (sin filtrar por familia).
Sirve para separar un error real de posicion de un problema de nombres.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Auditoria por Comments y distancia al objetivo.
2. 2026-11-08: diagnostico tras aplicacion v02.
3. Heredado: sin registro previo disponible.
"""
import json
import math
import os

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter, FilteredElementCollector

FT_A_M = 0.3048
CATS = [BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
        BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_TelephoneDevices]


def main(doc):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    data = json.load(open(os.path.join(root, "data", "E05_transferencia_panel_ancla_v03.json"), "r"))
    objetivos = [(float(d["x_revit_m"]), float(d["y_revit_m"])) for d in data["dispositivos"]]

    creadas = []
    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = p.AsString() if p is not None else ""
                except Exception:
                    c = ""
                if c and "APT-E-05" in c:
                    pt = inst.Location.Point
                    creadas.append((inst.Id, pt.X * FT_A_M, pt.Y * FT_A_M))
        except Exception:
            pass

    dists = []
    for eid, x, y in creadas:
        d = min(math.hypot(x - ox, y - oy) for ox, oy in objetivos)
        dists.append(d)

    print("creadas={} max_dist={:.3f} m prom={:.3f} m".format(
        len(creadas), max(dists) if dists else -1, sum(dists) / len(dists) if dists else -1))
    malas = [(eid, round(d, 2)) for (eid, x, y), d in zip(creadas, dists) if d > 0.20]
    print("fuera_de_020=" + str(len(malas)))
    print("peores=" + str(sorted(malas, key=lambda t: -t[1])[:10]))


if __name__ == "__main__":
    main(__revit__.ActiveUIDocument.Document)  # noqa: F821
