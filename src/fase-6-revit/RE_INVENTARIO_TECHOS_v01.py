# -*- coding: utf-8 -*-
# RE_INVENTARIO_TECHOS_v01.py
# Inventario de elementos techo / cielorraso en el documento Revit activo.
# SOLO LECTURA: no crea, ni borra, ni modifica nada.
#
# Ejecutar en pyRevit Python Shell (IronPython 2.7):
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_INVENTARIO_TECHOS_v01.py")
#   inventario_techos(doc)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
from System import Int64

FEET_PER_METER = 3.280839895
ELEMENTID_CIELORRASO_E06 = 2766255  # ElementID específico del cielorraso de E 06


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


def _m(ft):
    return ft / FEET_PER_METER


def obtener_nivel_nombre(doc, elemento):
    try:
        lid = elemento.LevelId
        if lid and lid != ElementId.InvalidElementId:
            nivel = doc.GetElement(lid)
            if nivel:
                return nivel.Name
    except Exception:
        pass
    return "SinNivel"


def obtener_nombre_categoria(elemento):
    try:
        cat = elemento.Category
        if cat:
            return cat.Name
    except Exception:
        pass
    return "SinCategoria"


def obtener_nombre_familia(elemento):
    try:
        if hasattr(elemento, "Symbol") and elemento.Symbol:
            fam = elemento.Symbol.Family
            if fam:
                return fam.Name
    except Exception:
        pass
    try:
        fam = elemento.Family
        if fam:
            return fam.Name
    except Exception:
        pass
    return "Desconocida"


def obtener_nombre_tipo(elemento):
    try:
        return elemento.Name
    except Exception:
        return "Desconocido"


def inventario_techos(doc):
    print("=== RE_INVENTARIO_TECHOS_v01 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: SOLO LECTURA")

    # 1. Buscar específicamente el ElementID 2766255 (cielorraso de E 06)
    print("\n--- Buscando ElementID 2766255 (cielorraso de E 06) ---")
    eid_objetivo = ElementId(Int64(ELEMENTID_CIELORRASO_E06))
    elemento_objetivo = doc.GetElement(eid_objetivo)
    if elemento_objetivo is not None:
        loc = elemento_objetivo.Location
        punto = loc.Point if (loc and hasattr(loc, "Point")) else None
        print("  ENCONTRADO: ID={}".format(_eid(elemento_objetivo.Id)))
        print("    Categoria: {}".format(obtener_nombre_categoria(elemento_objetivo)))
        print("    Familia: {}".format(obtener_nombre_familia(elemento_objetivo)))
        print("    Tipo: {}".format(obtener_nombre_tipo(elemento_objetivo)))
        print("    Nivel: {}".format(obtener_nivel_nombre(doc, elemento_objetivo)))
        if punto:
            print("    XYZ (ft): ({}, {}, {})".format(round(punto.X, 4), round(punto.Y, 4), round(punto.Z, 4)))
            print("    XYZ (m): ({}, {}, {})".format(round(_m(punto.X), 4), round(_m(punto.Y), 4), round(_m(punto.Z), 4)))
    else:
        print("  NO ENCONTRADO: ElementID 2766255 no existe en este documento")

    # 2. Buscar todos los elementos con categoría relacionada a techos/cielorrasos
    print("\n--- Buscando elementos de categoría Ceilings (OST_Ceilings) ---")
    cat_techos = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
    techos_ost = list(FilteredElementCollector(doc).WherePasses(cat_techos))
    print("  Total con OST_Ceilings: {}".format(len(techos_ost)))

    # 3. Buscar elementos cuyo nombre de categoría contenga "ceiling" o "cielo" (case-insensitive)
    print("\n--- Buscando elementos por nombre de categoría (filtro textual) ---")
    categorias_encontradas = {}
    for cat in doc.Settings.Categories:
        try:
            cat_name = cat.Name
            if any(k in cat_name.lower() for k in ["ceiling", "cielo", "techo", "plafon"]):
                elementos_cat = list(FilteredElementCollector(doc).OfCategoryId(cat.Id))
                categorias_encontradas[cat_name] = elementos_cat
                print("  Categoria '{}': {} elementos".format(cat_name, len(elementos_cat)))
        except Exception:
            continue

    # 4. Listar todos los techos encontrados con detalles
    todos_techos = []
    for cat_name, elementos in categorias_encontradas.items():
        for el in elementos:
            try:
                loc = el.Location
                punto = loc.Point if (loc and hasattr(loc, "Point")) else None
                nivel = obtener_nivel_nombre(doc, el)
                familia = obtener_nombre_familia(el)
                tipo = obtener_nombre_tipo(el)
                todos_techos.append({
                    "id": _eid(el.Id),
                    "categoria": cat_name,
                    "familia": familia,
                    "tipo": tipo,
                    "nivel": nivel,
                    "x_m": round(_m(punto.X), 4) if punto else None,
                    "y_m": round(_m(punto.Y), 4) if punto else None,
                    "z_m": round(_m(punto.Z), 4) if punto else None,
                })
            except Exception:
                continue

    # 5. Resumen por nivel
    print("\n--- Resumen de techos por nivel ---")
    por_nivel = {}
    for t in todos_techos:
        n = t["nivel"]
        por_nivel[n] = por_nivel.get(n, 0) + 1
    for n in sorted(por_nivel.keys()):
        print("  {}: {} techos".format(n, por_nivel[n]))

    # 6. Listar techos en Piso 5 específicamente
    print("\n--- Techos en 'Piso 5' ---")
    techos_piso5 = [t for t in todos_techos if t["nivel"] == "Piso 5"]
    for t in techos_piso5:
        print("  ID={} Familia={} Tipo={} XYZ_m=({},{},{})".format(
            t["id"], t["familia"], t["tipo"], t["x_m"], t["y_m"], t["z_m"]))
    if not techos_piso5:
        print("  (ninguno)")

    # 7. Verificar si el ElementID 2766255 está en la lista de techos
    print("\n--- Verificación de ElementID 2766255 en inventario de techos ---")
    encontrado_en_lista = any(t["id"] == ELEMENTID_CIELORRASO_E06 for t in todos_techos)
    print("  Esta en inventario de techos: {}".format(encontrado_en_lista))

    return {
        "elemento_2766255": elemento_objetivo is not None,
        "techos_ost_count": len(techos_ost),
        "techos_todos": todos_techos,
        "categorias_encontradas": list(categorias_encontradas.keys()),
    }


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        inventario_techos(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
