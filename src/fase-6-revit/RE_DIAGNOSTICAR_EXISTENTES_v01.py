# -*- coding: utf-8 -*-
# RE_DIAGNOSTICAR_EXISTENTES_v01.py (v2)
# Diagnostica FamilyInstances eléctricas existentes en el documento Revit activo.
# Solo lectura: no crea, ni borra, ni modifica nada.
#
# Ejecutar en pyRevit Python Shell (IronPython 2.7):
#   doc = __revit__.ActiveUIDocument.Document
#   execfile(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_DIAGNOSTICAR_EXISTENTES_v01.py")
#   diagnosticar_existentes(doc)

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


def obtener_nivel_nombre(doc, fi):
    """Obtiene el nombre del nivel de una FamilyInstance de forma robusta."""
    try:
        lid = fi.LevelId
        if lid and lid != ElementId.InvalidElementId:
            nivel = doc.GetElement(lid)
            if nivel:
                return nivel.Name
    except Exception:
        pass
    return "SinNivel"


def obtener_nivel_elev_ft(doc, fi):
    """Obtiene la elevación del nivel de una FamilyInstance."""
    try:
        lid = fi.LevelId
        if lid and lid != ElementId.InvalidElementId:
            nivel = doc.GetElement(lid)
            if nivel:
                return nivel.Elevation
    except Exception:
        pass
    return 0.0


def obtener_nombre_categoria(elemento):
    try:
        cat = elemento.Category
        if cat:
            return cat.Name
    except Exception:
        pass
    return "SinCategoria"


def diagnosticar_existentes(doc, nivel_filtro=None, solo_electricas=True):
    print("=== RE_DIAGNOSTICAR_EXISTENTES_v01 (v2) ===")
    print("Documento: {}".format(doc.Title))

    categorias_electricas = [
        "Electrical Equipment",
        "Lighting Fixtures",
        "Switches",
        "Data Devices",
        "Electrical Fixtures",
        "Devices",
    ]

    prefijos_electricos = (
        "M_", "E_", "ELEC", "Interruptor", "Toma", "Telefono",
        "Timbre", "Iluminacion", "Climatizacion", "Consolidation",
    )

    collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    instancias = []
    errores = 0

    for fi in collector:
        try:
            if fi is None:
                continue
            try:
                nombre_familia = fi.Symbol.Family.Name
            except Exception:
                nombre_familia = "Desconocida"

            cat_name = obtener_nombre_categoria(fi)

            if solo_electricas:
                es_electrica = any(
                    c.lower() in cat_name.lower() for c in categorias_electricas
                )
                nombre_match = any(p in nombre_familia for p in prefijos_electricos)
                if not (es_electrica or nombre_match):
                    continue

            loc = fi.Location
            punto = None
            if loc and hasattr(loc, "Point"):
                punto = loc.Point

            nivel_nombre = obtener_nivel_nombre(doc, fi)
            nivel_elev_ft = obtener_nivel_elev_ft(doc, fi)

            if nivel_filtro and nivel_nombre != nivel_filtro:
                continue

            instancias.append({
                "id": _eid(fi.Id),
                "familia": nombre_familia,
                "categoria": cat_name,
                "nivel": nivel_nombre,
                "elev_ft": round(nivel_elev_ft, 4),
                "elev_m": round(_m(nivel_elev_ft), 4),
                "x_ft": round(punto.X, 4) if punto else None,
                "y_ft": round(punto.Y, 4) if punto else None,
                "z_ft": round(punto.Z, 4) if punto else None,
                "z_m": round(_m(punto.Z), 4) if punto else None,
            })
        except Exception as ex:
            errores += 1
            continue

    print("Total instancias eléctricas encontradas: {}".format(len(instancias)))
    print("Errores durante procesamiento: {}".format(errores))

    # Resumen por nivel
    por_nivel = {}
    for inst in instancias:
        n = inst["nivel"]
        por_nivel[n] = por_nivel.get(n, 0) + 1

    print("\n--- Resumen por nivel ---")
    for n in sorted(por_nivel.keys()):
        print("  {}: {}".format(n, por_nivel[n]))

    # Resumen por familia (top 20)
    por_familia = {}
    for inst in instancias:
        f = inst["familia"]
        por_familia[f] = por_familia.get(f, 0) + 1

    print("\n--- Resumen por familia (top 20) ---")
    items_familia = sorted(por_familia.items(), key=lambda x: -x[1])
    for f, c in items_familia[:20]:
        print("  {}: {}".format(f, c))

    # Instancias en nivel 0.00 (sospechosos)
    print("\n--- Instancias en nivel 0.00 (elev ~0) ---")
    nivel0 = [i for i in instancias if abs(i["elev_ft"]) < 0.1]
    for i in nivel0[:60]:
        print("  ID={} Familia={} Nivel={} Z_m={} XY_m=({},{})".format(
            i["id"], i["familia"], i["nivel"],
            i["z_m"], i["x_ft"] / FEET_PER_METER if i["x_ft"] is not None else None,
            i["y_ft"] / FEET_PER_METER if i["y_ft"] is not None else None,
        ))
    if len(nivel0) > 60:
        print("  ... y {} más".format(len(nivel0) - 60))

    # Instancias en Piso 5
    print("\n--- Instancias en 'Piso 5' ---")
    piso5 = [i for i in instancias if i["nivel"] == "Piso 5"]
    for i in piso5[:60]:
        print("  ID={} Familia={} Z_m={} XY_m=({},{})".format(
            i["id"], i["familia"], i["z_m"],
            i["x_ft"] / FEET_PER_METER if i["x_ft"] is not None else None,
            i["y_ft"] / FEET_PER_METER if i["y_ft"] is not None else None,
        ))
    if len(piso5) > 60:
        print("  ... y {} más".format(len(piso5) - 60))

    # Instancias con alturas negativas (corrupción probable)
    print("\n--- Instancias con Z negativo (sospechoso de corrupción) ---")
    negativos = [i for i in instancias if i["z_m"] is not None and i["z_m"] < 0]
    for i in negativos[:60]:
        print("  ID={} Familia={} Nivel={} Z_m={} XY_m=({},{})".format(
            i["id"], i["familia"], i["nivel"], i["z_m"],
            i["x_ft"] / FEET_PER_METER if i["x_ft"] is not None else None,
            i["y_ft"] / FEET_PER_METER if i["y_ft"] is not None else None,
        ))
    if len(negativos) > 60:
        print("  ... y {} más".format(len(negativos) - 60))

    return instancias


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        diagnosticar_existentes(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
