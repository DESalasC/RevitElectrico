# -*- coding: utf-8 -*-
# RE_DIAG_TECHOS_MINIMAL_v01.py
# Diagnostica minimal: cuenta techos con exactamente el mismo enfoque que
# RE_COLOCAR_DISPOSITIVOS_generico.py para ver por qué devuelve 0.
# SOLO LECTURA.
#
# Ejecutar en pyRevit Python Shell:
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_DIAG_TECHOS_MINIMAL_v01.py")
#   contar_techos(doc)

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


def contar_techos(doc):
    print("=== RE_DIAG_TECHOS_MINIMAL_v01 ===")
    print("Documento: {}".format(doc.Title))

    # Enfoque 1: ElementCategoryFilter OST_Ceilings (mismo que el script de colocación)
    print("\n--- Enfoque 1: ElementCategoryFilter(OST_Ceilings) ---")
    cat_techos = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
    collector1 = FilteredElementCollector(doc).WherePasses(cat_techos)
    count1 = 0
    errores_loc = 0
    sin_loc = 0
    sin_point_y_curve = 0
    for c in collector1:
        count1 += 1
        try:
            loc = c.Location
            if not loc:
                sin_loc += 1
                continue
            p = None
            if hasattr(loc, "Point"):
                p = loc.Point
            elif hasattr(loc, "Curve"):
                curva = loc.Curve
                if curva is not None:
                    p_mid = curva.Evaluate(0.5, True)
                    p = p_mid
            if p is None:
                sin_point_y_curve += 1
        except Exception:
            errores_loc += 1

    print("  Total elementos con OST_Ceilings: {}".format(count1))
    print("  Sin Location: {}".format(sin_loc))
    print("  Errores accediendo Location: {}".format(errores_loc))
    print("  Sin Point ni Curve: {}".format(sin_point_y_curve))
    print("  Con Point o Curve: {}".format(count1 - sin_loc - errores_loc - sin_point_y_curve))

    # Enfoque 2: Filtro textual por nombre de categoría
    print("\n--- Enfoque 2: Filtro textual por nombre de categoría ---")
    count2 = 0
    for cat in doc.Settings.Categories:
        try:
            cat_name = cat.Name
            if "ceiling" in cat_name.lower() or "cielo" in cat_name.lower():
                elementos = FilteredElementCollector(doc).OfCategoryId(cat.Id)
                n = 0
                for e in elementos:
                    n += 1
                if n > 0:
                    print("  Categoria '{}': {} elementos".format(cat_name, n))
                    count2 += n
        except Exception:
            continue
    print("  Total por filtro textual: {}".format(count2))

    # Verificar ElementID 2766255 específicamente
    print("\n--- ElementID 2766255 ---")
    eid_objetivo = ElementId(Int64(2766255))
    el = doc.GetElement(eid_objetivo)
    if el is not None:
        cat_name = obtener_nombre_categoria(el)
        print("  Encontrado: ID={} Categoria={} Nombre={}".format(
            _eid(el.Id), cat_name, el.Name))
        loc = el.Location
        if loc:
            if hasattr(loc, "Point"):
                p = loc.Point
                print("  LocationPoint: XYZ_m=({},{},{})".format(
                    round(_m(p.X), 4), round(_m(p.Y), 4), round(_m(p.Z), 4)))
            elif hasattr(loc, "Curve"):
                print("  LocationCurve (no Point)")
            else:
                print("  Location sin Point ni Curve")
        else:
            print("  Sin Location")
    else:
        print("  NO ENCONTRADO")


def obtener_nombre_categoria(elemento):
    try:
        cat = elemento.Category
        if cat:
            return cat.Name
    except Exception:
        pass
    return "SinCategoria"


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        contar_techos(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
