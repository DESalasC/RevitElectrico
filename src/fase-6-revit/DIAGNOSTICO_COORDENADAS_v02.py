# -*- coding: utf-8 -*-
"""
DIAGNOSTICO_COORDENADAS_v02.py — Lee todas las FamilyInstance creadas en V00
con sus coordenadas reales, nivel y comentario, para comparar fuera de Revit.

IronPython 2.7 (Revit 2026 / pyRevit).


Ultimos tres cambios
--------------------
1. 2026-11-08 v02: version vigente conservada tras la limpieza de duplicados;
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
            "FamilyInstance": getattr(mock_db, "FamilyInstance", None),
            "BuiltInParameter": getattr(mock_db, "BuiltInParameter", None),
        }
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector, FamilyInstance, BuiltInParameter,
    )
    return {
        "FilteredElementCollector": FilteredElementCollector,
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


def _obtener_comentario(inst, revit_db):
    try:
        BuiltInParameter = revit_db.get("BuiltInParameter")
        if BuiltInParameter is None:
            import Autodesk.Revit.DB as _db
            BuiltInParameter = _db.BuiltInParameter
        p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p is not None:
            return p.AsString() or ""
    except Exception:
        pass
    return ""


def diagnosticar_coordenadas_v02(doc, json_out=None, revit_db=None):
    if revit_db is None:
        revit_db = _import_revit_db()

    FilteredElementCollector = revit_db["FilteredElementCollector"]
    FamilyInstance = revit_db["FamilyInstance"]
    BuiltInParameter = revit_db["BuiltInParameter"]

    resultado = {
        "version": "v02-diagnostico-coordenadas",
        "script": "DIAGNOSTICO_COORDENADAS_v02.py",
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
    }

    instancias = []
    colector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    for inst in colector.ToElements():
        try:
            punto = inst.Location.Point if inst.Location is not None else None
            nivel_id = inst.LevelId
            nombre_nivel = ""
            if nivel_id is not None and nivel_id != -1:
                try:
                    elem_nivel = doc.GetElement(nivel_id)
                    if elem_nivel is not None:
                        nombre_nivel = _obtener_nombre_elemento(elem_nivel, revit_db) or ""
                except Exception:
                    nombre_nivel = ""

            comentario = _obtener_comentario(inst, revit_db)

            instancias.append({
                "id": inst.Id.ToString(),
                "categoria": inst.Category.Name if inst.Category else None,
                "nombre_tipo": _obtener_nombre_elemento(inst, revit_db),
                "nivel_id": nivel_id.ToString() if nivel_id else None,
                "nivel_nombre": nombre_nivel,
                "x": punto.X if punto else None,
                "y": punto.Y if punto else None,
                "z": punto.Z if punto else None,
                "comentario": comentario,
            })
        except Exception:
            continue

    resultado["total_instancias"] = len(instancias)
    resultado["instancias"] = instancias

    # Estadísticas rápidas
    niveles_vacios = [i for i in instancias if not i["nivel_nombre"]]
    resultado["estadisticas"] = {
        "con_nivel_vacio": len(niveles_vacios),
        "con_nivel_piso_5": len([i for i in instancias if i["nivel_nombre"] == "Piso 5"]),
        "con_comentario_red_si": len([i for i in instancias if i["comentario"] == "RED=SI"]),
    }

    if json_out:
        _guardar_json(json_out, resultado)

    return resultado


def main():
    print("=" * 60)
    print("DIAGNOSTICO_COORDENADAS_v02 — Lee FamilyInstance con coordenadas")
    print("Version: v02-20261024-diagnostico-coord | {}".format(
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
        description="Lee FamilyInstance con coordenadas reales en Revit 2026"
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
        json_out = os.path.join(root, "data", "diagnostico_coordenadas_v02.json")

    resultado = diagnosticar_coordenadas_v02(doc, json_out, revit_db)

    print()
    print("=== Resultado ===")
    print("Total FamilyInstance: {}".format(resultado["total_instancias"]))
    print("Con nivel vacío: {}".format(resultado["estadisticas"]["con_nivel_vacio"]))
    print("Con nivel 'Piso 5': {}".format(resultado["estadisticas"]["con_nivel_piso_5"]))
    print("Con comentario 'RED=SI': {}".format(resultado["estadisticas"]["con_comentario_red_si"]))
    print()
    print("JSON guardado en: {}".format(json_out))
    print("=" * 60)
    return resultado


if __name__ == "__main__":
    main()
