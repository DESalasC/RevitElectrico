# -*- coding: utf-8 -*-
"""
DIAGNOSTICO_ESTADO_ELECTRICO_v01.py — Cuenta FamilyInstance eléctricas en V00
por categoría y nivel, para verificar el estado real del modelo.


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


def _ascii_safe(valor):
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor
    try:
        return str(valor).encode("ascii", "replace").decode("ascii")
    except Exception:
        return "?"


def _sanitizar_dict(d):
    if isinstance(d, dict):
        return {_ascii_safe(k): _sanitizar_dict(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [_sanitizar_dict(v) for v in d]
    elif isinstance(d, tuple):
        return tuple(_sanitizar_dict(v) for v in d)
    else:
        return _ascii_safe(d)


def _guardar_json(ruta, datos):
    dirpath = os.path.dirname(ruta)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath)
    datos_limpios = _sanitizar_dict(datos)
    contenido = json.dumps(datos_limpios, indent=2, ensure_ascii=True)
    with open(ruta, "w") as f:
        f.write(contenido)


def _import_revit_db():
    import sys
    mock_db = sys.modules.get("Autodesk.Revit.DB")
    if mock_db is not None:
        return {
            "FilteredElementCollector": getattr(mock_db, "FilteredElementCollector", None),
            "BuiltInCategory": getattr(mock_db, "BuiltInCategory", None),
            "FamilyInstance": getattr(mock_db, "FamilyInstance", None),
            "BuiltInParameter": getattr(mock_db, "BuiltInParameter", None),
        }
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector, BuiltInCategory, FamilyInstance,
        BuiltInParameter,
    )
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "BuiltInCategory": BuiltInCategory,
        "FamilyInstance": FamilyInstance,
        "BuiltInParameter": BuiltInParameter,
    }


def _obtener_nombre_elemento(elemento, revit_db):
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return nombre
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
                return valor
    except Exception:
        pass
    return None


def _obtener_nivel_nombre(inst, doc, revit_db):
    try:
        nivel_id = inst.LevelId
        if nivel_id is None or nivel_id == -1:
            return "(vacío)"
        elem = doc.GetElement(nivel_id)
        if elem is None:
            return "(nulo)"
        return _obtener_nombre_elemento(elem, revit_db) or "(sin nombre)"
    except Exception:
        return "(error)"


def diagnosticar_estado_electrico(doc, json_out=None, revit_db=None):
    if revit_db is None:
        revit_db = _import_revit_db()

    FilteredElementCollector = revit_db["FilteredElementCollector"]
    BuiltInCategory = revit_db["BuiltInCategory"]
    FamilyInstance = revit_db["FamilyInstance"]

    resultado = {
        "version": "v01-estado-electrico",
        "script": "DIAGNOSTICO_ESTADO_ELECTRICO_v01.py",
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
    }

    # Categorías eléctricas de interés
    cats_electricas = {
        "OST_ElectricalFixtures": BuiltInCategory.OST_ElectricalFixtures,
        "OST_LightingDevices": BuiltInCategory.OST_LightingDevices,
        "OST_LightingFixtures": BuiltInCategory.OST_LightingFixtures,
        "OST_ElectricalEquipment": BuiltInCategory.OST_ElectricalEquipment,
    }

    por_categoria = {}
    por_nivel = {}
    con_comentario_red = 0
    total_electricas = 0

    for cat_name, cat_enum in cats_electricas.items():
        colector = FilteredElementCollector(doc).OfCategory(cat_enum)
        items = []
        for inst in colector.ToElements():
            items.append(inst)

        total_electricas += len(items)
        por_categoria[cat_name] = len(items)

        for inst in items:
            nivel = _obtener_nivel_nombre(inst, doc, revit_db)
            por_nivel[nivel] = por_nivel.get(nivel, 0) + 1

            try:
                p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if p is not None and p.AsString() == "RED=SI":
                    con_comentario_red += 1
            except Exception:
                pass

    resultado["total_electricas"] = total_electricas
    resultado["por_categoria"] = por_categoria
    resultado["por_nivel"] = por_nivel
    resultado["con_comentario_red_si"] = con_comentario_red

    if json_out:
        _guardar_json(json_out, resultado)

    return resultado


def main():
    print("=" * 60)
    print("DIAGNOSTICO_ESTADO_ELECTRICO_v01 — Estado de lo modelado eléctrico")
    print("Version: v01-20261024-estado | {}".format(
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

    import argparse
    parser = argparse.ArgumentParser(
        description="Diagnostica estado eléctrico en Revit 2026"
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de diagnóstico de salida",
    )
    args = parser.parse_args()

    if args.json_out:
        json_out = args.json_out
    else:
        root = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())
        json_out = os.path.join(root, "data", "diagnostico_estado_electrico.json")

    resultado = diagnosticar_estado_electrico(doc, json_out, revit_db)

    print()
    print("=== Resultado ===")
    print("Total FamilyInstance eléctricas: {}".format(resultado["total_electricas"]))
    print("Con comentario RED=SI: {}".format(resultado["con_comentario_red_si"]))
    print()
    print("Por categoría:")
    for cat, cant in sorted(resultado["por_categoria"].items()):
        print("  {}: {}".format(cat, cant))
    print()
    print("Por nivel (top 15):")
    for nivel, cant in sorted(
        resultado["por_nivel"].items(), key=lambda x: -x[1]
    )[:15]:
        print("  {}: {}".format(nivel, cant))

    print()
    print("JSON guardado en: {}".format(json_out))
    print("=" * 60)
    return resultado


if __name__ == "__main__":
    main()
