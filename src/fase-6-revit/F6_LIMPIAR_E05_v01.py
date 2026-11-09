# -*- coding: utf-8 -*-
"""F6_LIMPIAR_E05_v01.py - Elimina las instancias creadas para E05.

Borra unicamente FamilyInstance cuyo parametro Comments contiene "APT-E-05-P5".
Son las creadas por los scripts de aplicacion de E05; no toca F 01 ni F 02 ni
ningun elemento preexistente del modelo.

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: creacion. Limpieza selectiva por Comments antes de recrear.
2. 2026-11-08: corrige residuos en el origen de la primera aplicacion.
3. Heredado: sin registro previo disponible.
"""
from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Transaction,
)

CATS = [BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
        BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_TelephoneDevices]


def limpiar(doc):
    objetivos = []
    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = p.AsString() if p is not None else ""
                except Exception:
                    c = ""
                if c and "APT-E-05-P5" in c:
                    objetivos.append(inst.Id)
        except Exception:
            pass

    print("a_eliminar=" + str(len(objetivos)))
    if not objetivos:
        return {"eliminados": 0}

    t = Transaction(doc, "F6 - Limpiar E05 por Comments")
    t.Start()
    n = 0
    try:
        for eid in objetivos:
            try:
                doc.Delete(eid)
                n += 1
            except Exception:
                pass
    finally:
        t.Commit()
    print("eliminados=" + str(n))
    return {"eliminados": n}


if __name__ == "__main__":
    limpiar(__revit__.ActiveUIDocument.Document)  # noqa: F821
