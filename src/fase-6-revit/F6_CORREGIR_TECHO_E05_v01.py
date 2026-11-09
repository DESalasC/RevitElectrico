# -*- coding: utf-8 -*-
"""F6_CORREGIR_TECHO_E05_v01.py - Hospeda en techo las instancias de E05 con Z=0.

Las familias face-based (COMBO MOUNTING RING, M_Ventilador, M_Timbre) no aceptan
un punto libre: requieren una cara. Este script busca el cielorraso mas cercano
que cubra el punto XY, toma su cara inferior y recrea la instancia alli.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Reposicion en cara inferior de cielorraso.
2. 2026-11-08: solo actua sobre instancias APT-E-05-P5 con Z cercana a 0.
3. Heredado: sin registro previo disponible.
"""
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    HostObjectUtils,
    Transaction,
    XYZ,
)

FT = 3.280839895
TOL_Z0 = 1.0  # pies


def _bbox(el):
    try:
        return el.get_BoundingBox(None)
    except Exception:
        return None


def corregir(doc, confirmar=False):
    techos = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType())
    candidatos = []
    for bic in (BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_ElectricalFixtures,
                BuiltInCategory.OST_CommunicationDevices):
        for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
            try:
                p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                c = p.AsString() if p is not None else ""
            except Exception:
                c = ""
            if not (c and "APT-E-05" in c):
                continue
            try:
                pt = inst.Location.Point
            except Exception:
                continue
            if pt.Z is not None and abs(pt.Z) <= TOL_Z0:
                candidatos.append(inst)

    print("candidatos_z0=" + str(len(candidatos)))
    if not confirmar:
        return

    t = Transaction(doc, "F6 - Hospedar en techo E05")
    t.Start()
    ok = 0
    fallos = 0
    try:
        for inst in candidatos:
            try:
                pt = inst.Location.Point
                sym = inst.Symbol
                z_obj = pt.Z
                mejor = None
                for techo in techos:
                    bb = _bbox(techo)
                    if bb is None:
                        continue
                    if not (bb.Min.X - 0.01 <= pt.X <= bb.Max.X + 0.01 and
                            bb.Min.Y - 0.01 <= pt.Y <= bb.Max.Y + 0.01):
                        continue
                    dz = abs((bb.Min.Z + bb.Max.Z) / 2.0 - z_obj)
                    if mejor is None or dz < mejor[0]:
                        mejor = (dz, techo)
                if mejor is None:
                    fallos += 1
                    continue
                caras = list(HostObjectUtils.GetBottomFaces(mejor[1]))
                if not caras:
                    fallos += 1
                    continue
                nueva = doc.Create.NewFamilyInstance(caras[0], XYZ(pt.X, pt.Y, z_obj), sym)
                try:
                    cp = nueva.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cp is not None and not cp.IsReadOnly:
                        cp.Set("APT-E-05-P5")
                except Exception:
                    pass
                doc.Delete(inst.Id)
                ok += 1
            except Exception:
                fallos += 1
    finally:
        t.Commit()
    print("hospedados={} fallos={}".format(ok, fallos))


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    corregir(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
