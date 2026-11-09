# -*- coding: utf-8 -*-


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
# LISTAR_FAMILIAS_REVIT_v01.py
# Lista todas las familias y símbolos cargados en el documento de Revit activo.
# Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
# IronPython 2.7 (Dentro de Revit / pyRevit Python Shell) — SIN type hints.

import json
import os
from datetime import datetime


def _get_revit_db():
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector,
        Family,
        FamilySymbol,
        BuiltInCategory,
        Level,
    )
    import Autodesk.Revit.DB as _db
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "Family": Family,
        "FamilySymbol": FamilySymbol,
        "BuiltInCategory": BuiltInCategory,
        "Level": Level,
        "BuiltInParameter": _db.BuiltInParameter,
    }


def _obtener_nombre_elemento(elemento, revit_db):
    # Nombre legible de un elemento Revit.
    # Evita AttributeError: Name en IronPython.
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass

    try:
        BuiltInParameter = revit_db["BuiltInParameter"]
        p = elemento.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            valor = p.AsString()
            if valor:
                return valor
    except Exception:
        pass

    return None


def listar_familias(doc, revit_db):
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    Family = revit_db["Family"]

    familias = []
    colector = FilteredElementCollector(doc).OfClass(Family)

    for fam in colector.ToElements():
        try:
            nombre_fam = _obtener_nombre_elemento(fam, revit_db)
        except Exception:
            nombre_fam = "DESCONOCIDA"

        simbolos = []
        try:
            for id_simbolo in fam.GetFamilySymbolIds():
                simbolo = doc.GetElement(id_simbolo)
                if simbolo is None:
                    continue
                try:
                    nombre_sim = _obtener_nombre_elemento(simbolo, revit_db)
                except Exception:
                    nombre_sim = "DESCONOCIDO"
                simbolos.append({
                    "nombre": nombre_sim,
                    "id": simbolo.Id.ToString(),
                })
        except Exception:
            pass

        familias.append({
            "familia": nombre_fam,
            "id": fam.Id.ToString(),
            "cantidad_simbolos": len(simbolos),
            "simbolos": simbolos,
        })

    familias.sort(key=lambda f: (f["familia"] or "").lower())
    return familias


def listar_niveles(doc, revit_db):
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    BuiltInCategory = revit_db["BuiltInCategory"]
    Level = revit_db["Level"]

    niveles = []
    colector = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Levels
    ).OfClass(Level)

    for nivel in colector.ToElements():
        try:
            nombre = _obtener_nombre_elemento(nivel, revit_db)
        except Exception:
            nombre = "DESCONOCIDO"
        try:
            elev = nivel.Elevation
        except Exception:
            elev = None
        niveles.append({
            "nombre": nombre,
            "id": nivel.Id.ToString(),
            "elevacion": elev,
        })

    niveles.sort(key=lambda n: (n["elevacion"] or 0))
    return niveles


def main():
    revit_db = _get_revit_db()

    # pyRevit provee __revit__ como UIApplication (solo dentro de Revit).
    app = __revit__.Application
    uidoc = __revit__.ActiveUIDocument

    doc = None
    if uidoc is not None:
        doc = uidoc.Document
    else:
        docs = app.Documents
        if docs is not None and docs.Size > 0:
            doc = docs.get_Item(0)

    if doc is None:
        print("ERROR: No hay un documento de Revit activo abierto.")
        print("Abra un archivo .rvt en Revit y ejecute desde pyRevit Python Shell.")
        return

    print("=" * 70)
    print("Documento: {}".format(doc.Title))
    print("Familias y símbolos cargados")
    print("=" * 70)

    familias = listar_familias(doc, revit_db)
    niveles = listar_niveles(doc, revit_db)

    print("\n--- NIVELES ({}) ---".format(len(niveles)))
    for niv in niveles:
        print("  {} | elev={} | id={}".format(
            niv["nombre"], niv["elevacion"], niv["id"]))

    print("\n--- FAMILIAS ({}) ---".format(len(familias)))
    for fam in familias:
        print("\nFamilia: {} | símbolos: {} | id={}".format(
            fam["familia"], fam["cantidad_simbolos"], fam["id"]))
        for sim in fam["simbolos"]:
            print("    - {} | id={}".format(sim["nombre"], sim["id"]))

    # Guardar JSON
    root = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())
    out_dir = os.path.join(root, "data")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    out_path = os.path.join(out_dir, "familias_cargadas_prueba01.json")

    datos = {
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "niveles": niveles,
        "familias": familias,
        "resumen": {
            "total_familias": len(familias),
            "total_simbolos": sum(f["cantidad_simbolos"] for f in familias),
            "total_niveles": len(niveles),
        },
    }

    with open(out_path, "w") as f:
        json.dump(datos, f, indent=2)

    print("\n" + "=" * 70)
    print("JSON guardado en: {}".format(out_path))
    print("Total familias: {}".format(datos["resumen"]["total_familias"]))
    print("Total símbolos: {}".format(datos["resumen"]["total_simbolos"]))
    print("=" * 70)

    return datos


if __name__ == "__main__":
    main()
