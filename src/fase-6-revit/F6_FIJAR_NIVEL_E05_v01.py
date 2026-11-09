# -*- coding: utf-8 -*-
"""F6_FIJAR_NIVEL_E05_v01.py - Fija el nivel de las instancias de E05 por movimiento.

Hallazgo de la sesion 2026-10-25 (resultado_fijar_levelid_movimiento.json):
mover la FamilyInstance con ElementTransformUtils.MoveElement hace que Revit
re-evalue su nivel y le asigne el nivel correspondiente (37/37, 0 fallos).

Este script:
  1. Toma las instancias con Comments = APT-E-05-P5.
  2. Les calcula la Z objetivo (nivel.Elevation + z_local).
  3. Las mueve en Z (si ya estan en la Z correcta, aplica 1 mm para forzar).
  4. Reporta cuantas quedaron con LevelId valido.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Fija nivel por movimiento, basado en el hallazgo
   del cierre 2026-10-25 (37/37 con LevelId tras mover).
2. 2026-11-08: aplicado a E05 tras detectar LevelId = -1.
3. Heredado: sin registro previo disponible.
"""
import json
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementTransformUtils,
    FilteredElementCollector,
    Level,
    Transaction,
    XYZ,
)

FT = 3.280839895
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


def corregir(doc, confirmar=False):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    data = json.load(open(os.path.join(root, "data", "E05_transferencia_panel_ancla_v03.json"), "r"))
    objs = [(float(d["x_revit_m"]), float(d["y_revit_m"]), float(d["z_local_m"]), d["nombre_bloque_hijo"])
            for d in data["dispositivos"]]

    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _norm(lv.Name) == _norm(data.get("nivel", "Piso 5")):
            nivel = lv
            break
    if nivel is None:
        print("Nivel no encontrado")
        return

    instancias = []
    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = p.AsString() if p is not None else ""
                except Exception:
                    c = ""
                if c and "APT-E-05-P5" in c:
                    instancias.append(inst)
        except Exception:
            pass

    print("instancias=" + str(len(instancias)))
    res = {"instancias": len(instancias), "movidas": 0, "con_nivel": 0, "sin_nivel": 0, "detalle": []}

    if not confirmar:
        return res

    t = Transaction(doc, "F6 - Fijar nivel E05 por movimiento")
    t.Start()
    try:
        for inst in instancias:
            try:
                pt = inst.Location.Point
                x_m = pt.X * 0.3048
                y_m = pt.Y * 0.3048
                best = min(objs, key=lambda o: math.hypot(x_m - o[0], y_m - o[1]))
                z_obj = nivel.Elevation + best[2] * FT
                dz = z_obj - pt.Z
                if abs(dz) < 0.001:
                    dz = 0.001
                ElementTransformUtils.MoveElement(doc, inst.Id, XYZ(0, 0, dz))
                res["movidas"] += 1
            except Exception as ex:
                res["detalle"].append({"motivo": str(ex)})
    finally:
        t.Commit()

    for inst in instancias:
        try:
            lv = doc.GetElement(inst.LevelId)
            if lv is not None:
                res["con_nivel"] += 1
            else:
                res["sin_nivel"] += 1
        except Exception:
            res["sin_nivel"] += 1

    print("movidas={} con_nivel={} sin_nivel={}".format(
        res["movidas"], res["con_nivel"], res["sin_nivel"]))
    return res


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    corregir(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
