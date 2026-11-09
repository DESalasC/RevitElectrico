# -*- coding: utf-8 -*-
"""F6_CORREGIR_Z_E05_v01.py - Corrige la altura Z de las instancias de E05.

Busca las instancias con Comments = APT-E-05-P5, les asigna la Z objetivo
(nivel.Elevation + z_local) segun el punto XY mas cercano del JSON y las mueve
solo en Z.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Correccion de Z independiente de la creacion.
2. 2026-11-08: NewFamilyInstance ignora la Z en familias no hosteadas.
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


def corregir(doc, confirmar=False):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    data = json.load(open(os.path.join(root, "data", "E05_transferencia_panel_ancla_v03.json"), "r"))
    objs = [(float(d["x_revit_m"]), float(d["y_revit_m"]), float(d["z_local_m"]), d["nombre_bloque_hijo"])
            for d in data["dispositivos"]]
    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if lv.Name == data.get("nivel", "Piso 5"):
            nivel = lv
            break
    if nivel is None:
        print("Nivel no encontrado")
        return

    objetivos = []
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
                    x_m = pt.X * 0.3048
                    y_m = pt.Y * 0.3048
                    best = min(objs, key=lambda o: math.hypot(x_m - o[0], y_m - o[1]))
                    z_obj = nivel.Elevation + best[2] * FT
                    objetivos.append((inst, pt, z_obj, best[3]))
        except Exception:
            pass

    print("a_corregir=" + str(len(objetivos)))
    if not confirmar:
        for inst, pt, z_obj, nombre in objetivos[:5]:
            print("  {} z_actual_ft={:.3f} z_obj_ft={:.3f}".format(nombre, pt.Z, z_obj))
        return

    t = Transaction(doc, "F6 - Corregir Z E05")
    t.Start()
    n = 0
    try:
        for inst, pt, z_obj, nombre in objetivos:
            dz = z_obj - pt.Z
            if abs(dz) > 0.01:
                try:
                    ElementTransformUtils.MoveElement(doc, inst.Id, XYZ(0, 0, dz))
                    n += 1
                except Exception as ex:
                    print("  fallo {}: {}".format(nombre, ex))
    finally:
        t.Commit()
    print("movidos_z=" + str(n))


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    corregir(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
