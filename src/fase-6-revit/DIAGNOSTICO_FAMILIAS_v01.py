# -*- coding: utf-8 -*-
"""
DIAGNOSTICO_FAMILIAS_v01.py — Lista familias cargadas en el RVT activo
para verificar qué familias eléctricas faltan antes de ejecutar Tarea F.

USO (dentro de Revit con pyRevit):
  pyrevit agent run "src/fase-6-revit/DIAGNOSTICO_FAMILIAS_v01.py" --revit=<PID> --mode=query --title="Diagnostico familias"


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
    with open(ruta, "w") as f:
        datos_limpios = _sanitizar_dict(datos)
        contenido = json.dumps(datos_limpios, indent=2, ensure_ascii=True)
        f.write(contenido)


def _import_revit_db():
    import sys
    mock_db = sys.modules.get("Autodesk.Revit.DB")
    if mock_db is not None:
        return {
            "FilteredElementCollector": getattr(mock_db, "FilteredElementCollector", None),
            "BuiltInCategory": getattr(mock_db, "BuiltInCategory", None),
            "Family": getattr(mock_db, "Family", None),
            "Level": getattr(mock_db, "Level", None),
        }
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector,
        BuiltInCategory,
        Family,
        Level,
    )
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "BuiltInCategory": BuiltInCategory,
        "Family": Family,
        "Level": Level,
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


def listar_familias(doc, revit_db):
    """Lista todas las familias cargadas en el documento."""
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    Family = revit_db["Family"]
    familias = []
    colector = FilteredElementCollector(doc).OfClass(Family)
    for fam in colector.ToElements():
        try:
            nombre = _obtener_nombre_elemento(fam, revit_db)
            simbolos = []
            for id_elem in fam.GetFamilySymbolIds():
                simbolo = doc.GetElement(id_elem)
                if simbolo is None:
                    continue
                nombre_sim = _obtener_nombre_elemento(simbolo, revit_db)
                activo = getattr(simbolo, "IsActive", None)
                simbolos.append({
                    "nombre_simbolo": nombre_sim,
                    "activo": activo,
                })
            familias.append({
                "nombre_familia": nombre,
                "id": fam.Id.ToString() if hasattr(fam.Id, "ToString") else str(fam.Id),
                "simbolos": simbolos,
                "num_simbolos": len(simbolos),
            })
        except Exception as exc:
            familias.append({
                "nombre_familia": "ERROR: {}".format(exc),
                "id": "?",
                "simbolos": [],
                "num_simbolos": 0,
            })
    return familias


def listar_niveles(doc, revit_db):
    """Lista los niveles del documento."""
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    BuiltInCategory = revit_db["BuiltInCategory"]
    niveles = []
    colector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Levels)
    for niv in colector.ToElements():
        try:
            nombre = _obtener_nombre_elemento(niv, revit_db)
            elev = getattr(niv, "Elevation", None)
            niveles.append({
                "nombre": nombre,
                "id": niv.Id.ToString() if hasattr(niv.Id, "ToString") else str(niv.Id),
                "elevacion_pies": elev,
            })
        except Exception:
            continue
    return niveles


def main():
    print("=" * 60)
    print("DIAGNOSTICO_FAMILIAS_v01 — Familias cargadas en RVT activo")
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
        print("ERROR: No hay un documento de Revit activo abierto.")
        return {"conectado": False}

    print("Documento: {}".format(doc.Title))

    familias = listar_familias(doc, revit_db)
    niveles = listar_niveles(doc, revit_db)

    print("\n--- NIVELES ({}) ---".format(len(niveles)))
    for n in niveles:
        print("  {} | id={} | elev={} pies".format(
            n["nombre"], n["id"], n["elevacion_pies"]))

    print("\n--- FAMILIAS CARGADAS ({}) ---".format(len(familias)))
    for f in sorted(familias, key=lambda x: (x["nombre_familia"] or "")):
        print("  {} | simbolos={}".format(f["nombre_familia"], f["num_simbolos"]))
        for s in f["simbolos"][:5]:
            print("     - {} | activo={}".format(s["nombre_simbolo"], s["activo"]))
        if f["num_simbolos"] > 5:
            print("     ... ({} simbolos mas)".format(f["num_simbolos"] - 5))

    resultado = {
        "version": "v01",
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "niveles": niveles,
        "familias": familias,
        "total_familias": len(familias),
        "total_niveles": len(niveles),
    }

    root = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())
    json_out = os.path.join(root, "data", "diagnostico_familias_resultado.json")
    _guardar_json(json_out, resultado)
    print("\nJSON guardado en: {}".format(json_out))
    return resultado


if __name__ == "__main__":
    main()
