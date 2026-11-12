# -*- coding: utf-8 -*-
# RE_DIAG_TECHOS_BB_v01.py
# Diagnostica si los techos tienen BoundingBox válido para obtener XY.
# SOLO LECTURA.
#
# Ejecutar en pyRevit Python Shell:
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_DIAG_TECHOS_BB_v01.py")
#   diag_techos_bb(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *

FEET_PER_METER = 3.280839895


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


def _m(ft):
    return ft / FEET_PER_METER


def diag_techos_bb(doc, nivel_filtro="Piso 5"):
    print("=== RE_DIAG_TECHOS_BB_v01 ===")
    print("Documento: {}".format(doc.Title))

    cat_techos = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
    collector = FilteredElementCollector(doc).WherePasses(cat_techos)

    total = 0
    con_bb = 0
    sin_bb = 0
    con_bb_piso5 = 0
    ejemplos_piso5 = []

    for c in collector:
        total += 1
        try:
            bb = c.get_BoundingBox(None)
            if bb is None:
                sin_bb += 1
                continue
            con_bb += 1
            # Obtener nivel
            nivel_nombre = "SinNivel"
            try:
                lid = c.LevelId
                if lid and lid != ElementId.InvalidElementId:
                    nivel = doc.GetElement(lid)
                    if nivel:
                        nivel_nombre = nivel.Name
            except Exception:
                pass

            if nivel_nombre == nivel_filtro:
                con_bb_piso5 += 1
                centro_x = (bb.Min.X + bb.Max.X) / 2.0
                centro_y = (bb.Min.Y + bb.Max.Y) / 2.0
                centro_z = (bb.Min.Z + bb.Max.Z) / 2.0
                if len(ejemplos_piso5) < 10:
                    ejemplos_piso5.append({
                        "id": _eid(c.Id),
                        "nombre": c.Name,
                        "nivel": nivel_nombre,
                        "bb_min_m": (_m(bb.Min.X), _m(bb.Min.Y), _m(bb.Min.Z)),
                        "bb_max_m": (_m(bb.Max.X), _m(bb.Max.Y), _m(bb.Max.Z)),
                        "centro_m": (_m(centro_x), _m(centro_y), _m(centro_z)),
                    })
        except Exception:
            sin_bb += 1

    print("Total techos OST_Ceilings: {}".format(total))
    print("  Con BoundingBox: {}".format(con_bb))
    print("  Sin BoundingBox: {}".format(sin_bb))
    print("  Con BoundingBox en '{}': {}".format(nivel_filtro, con_bb_piso5))

    print("\n--- Primeros 10 techos en '{}' con BoundingBox ---".format(nivel_filtro))
    for e in ejemplos_piso5:
        print("  ID={} Nombre={} Centro_m=({:.4f},{:.4f},{:.4f}) BB_min_m=({:.4f},{:.4f},{:.4f}) BB_max_m=({:.4f},{:.4f},{:.4f})".format(
            e["id"], e["nombre"],
            e["centro_m"][0], e["centro_m"][1], e["centro_m"][2],
            e["bb_min_m"][0], e["bb_min_m"][1], e["bb_min_m"][2],
            e["bb_max_m"][0], e["bb_max_m"][1], e["bb_max_m"][2],
        ))

    # Verificar ElementID 2766255
    print("\n--- ElementID 2766255 ---")
    el = doc.GetElement(ElementId(Int64(2766255)))
    if el is not None:
        bb = el.get_BoundingBox(None)
        if bb:
            cx = (bb.Min.X + bb.Max.X) / 2.0
            cy = (bb.Min.Y + bb.Max.Y) / 2.0
            cz = (bb.Min.Z + bb.Max.Z) / 2.0
            print("  BoundingBox centro_m=({:.4f},{:.4f},{:.4f})".format(_m(cx), _m(cy), _m(cz)))
        else:
            print("  Sin BoundingBox")
    else:
        print("  No encontrado")


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        diag_techos_bb(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
