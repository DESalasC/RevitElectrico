# -*- coding: utf-8 -*-
"""
DIAGNOSTICO_MUROS_F02_v01 — Lista muros existentes en el modelo con sus
coordenadas para descubrir el offset entre DXF local y Revit global.

IronPython 2.7 (Revit 2026 / pyRevit), modo query (solo lectura).


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import json
import os
from datetime import datetime


def _import_revit_db():
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector, BuiltInCategory, Wall, XYZ, BoundingBoxXYZ,
    )
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "BuiltInCategory": BuiltInCategory,
        "Wall": Wall,
        "XYZ": XYZ,
        "BoundingBoxXYZ": BoundingBoxXYZ,
    }


def _limpiar_texto(texto):
    if texto is None:
        return ""
    try:
        return texto.encode("ascii", "replace").decode("ascii")
    except Exception:
        return ""


def _obtener_nombre_elemento(elemento, revit_db):
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return _limpiar_texto(nombre)
    except Exception:
        pass
    try:
        BuiltInParameter = revit_db.get("BuiltInParameter")
        if BuiltInParameter is None:
            import Autodesk.Revit.DB as _db
            BuiltInParameter = _db.BuiltInParameter
        p = elemento.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            valor = p.AsString()
            if valor:
                return _limpiar_texto(valor)
    except Exception:
        pass
    return ""


def diagnosticar_muros(doc, revit_db=None):
    if revit_db is None:
        revit_db = _import_revit_db()

    FilteredElementCollector = revit_db["FilteredElementCollector"]
    BuiltInCategory = revit_db["BuiltInCategory"]
    Wall = revit_db.get("Wall")

    muros = []
    colector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls)
    for muro in colector.ToElements():
        try:
            bbox = muro.get_BoundingBox(None)
            if bbox is None:
                continue
            min_pt = bbox.Min
            max_pt = bbox.Max
            centro_x = (min_pt.X + max_pt.X) / 2.0
            centro_y = (min_pt.Y + max_pt.Y) / 2.0
            centro_z = (min_pt.Z + max_pt.Z) / 2.0
            nombre = _obtener_nombre_elemento(muro, revit_db) or "(sin nombre)"
            muros.append({
                "id": muro.Id.ToString(),
                "nombre": nombre,
                "min_x_ft": min_pt.X, "min_y_ft": min_pt.Y, "min_z_ft": min_pt.Z,
                "max_x_ft": max_pt.X, "max_y_ft": max_pt.Y, "max_z_ft": max_pt.Z,
                "centro_x_ft": centro_x, "centro_y_ft": centro_y, "centro_z_ft": centro_z,
                "centro_x_m": centro_x / 3.28084, "centro_y_m": centro_y / 3.28084, "centro_z_m": centro_z / 3.28084,
            })
        except Exception:
            continue

    # Filtrar muros cerca del área de F-02 (X: 2–7 m, Y: 2–10 m)
    # Esto ayuda a encontrar el offset entre DXF local y Revit global
    muros_f02_area = [m for m in muros if 1.0 < m["centro_x_m"] < 8.0 and 1.0 < m["centro_y_m"] < 11.0]

    # Ordenar todos por coordenadas para facilitar lectura
    muros.sort(key=lambda m: (m["centro_x_m"], m["centro_y_m"]))
    muros_f02_area.sort(key=lambda m: (m["centro_x_m"], m["centro_y_m"]))

    resultado = {
        "version": "v01-diagnostico-muros-f02",
        "script": "DIAGNOSTICO_MUROS_F02_v01.py",
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "total_muros": len(muros),
        "muros_area_f02": muros_f02_area,
        "total_muros_area_f02": len(muros_f02_area),
        "muros": muros[:200],  # primeros 200 para no saturar
    }
    return resultado


def main():
    print("=" * 60)
    print("DIAGNOSTICO_MUROS_F02_v01")
    print("Version: v01-20261025-diagnostico-muros | {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 60)

    revit_db = _import_revit_db()
    app = __revit__.Application
    uidoc = __revit__.ActiveUIDocument

    doc = None
    if uidoc is not None:
        doc = uidoc.Document
    else:
        try:
            docs = app.Documents
            if docs is not None and docs.Size > 0:
                doc = docs.get_Item(0)
        except Exception:
            doc = None

    if doc is None:
        print("ERROR: No hay documento de Revit activo.")
        return {"conectado": False, "documento_activo": False}

    print("Documento: {}".format(doc.Title))

    resultado = diagnosticar_muros(doc, revit_db)

    print()
    print("Total de muros en el modelo: {}".format(resultado["total_muros"]))
    print("Total de muros en área F-02 (X: 1–8 m, Y: 1–11 m): {}".format(
        resultado["total_muros_area_f02"]))
    print()
    print("Muros en área F-02 (primeros 50):")
    for m in resultado["muros_area_f02"][:50]:
        print("  id={} | nombre='{}' | centro=({:.2f}, {:.2f}, {:.2f}) m | bbox=({:.2f},{:.2f})-({:.2f},{:.2f}) m".format(
            m["id"], m["nombre"], m["centro_x_m"], m["centro_y_m"], m["centro_z_m"],
            m["min_x_ft"] / 3.28084, m["min_y_ft"] / 3.28084,
            m["max_x_ft"] / 3.28084, m["max_y_ft"] / 3.28084))

    json_out = os.path.join(os.getcwd(), "data", "diagnostico_muros_f02.json")
    dirpath = os.path.dirname(json_out)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath)
    with open(json_out, "w") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=True)
    print()
    print("JSON guardado en: {}".format(json_out))
    print("=" * 60)
    return resultado


if __name__ == "__main__":
    main()
