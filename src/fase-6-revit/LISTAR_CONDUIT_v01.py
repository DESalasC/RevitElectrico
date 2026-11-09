# -*- coding: utf-8 -*-
"""
LISTAR_CONDUIT_v01.py — Lista los elementos Conduit existentes en el documento
y sus parametros de diametro, para ver que esta disponible sin crear tipos nuevos.

USO (desde pyRevit Python Shell dentro de Revit):
  exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\LISTAR_CONDUIT_v01.py").read())
  listar_conduit(doc)


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    Conduit,
    BuiltInParameter,
    UnitUtils,
    UnitTypeId,
)
import json
import os


def _pies_a_mm(pies):
    try:
        return UnitUtils.ConvertFromInternalUnits(pies, UnitTypeId.Millimeters)
    except Exception:
        return pies * 304.8


def _nombre_conduit(conduit):
    try:
        n = conduit.Name
        if n:
            return n
    except Exception:
        pass
    try:
        p = conduit.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    return "?"


def listar_conduit(doc, json_out=None):
    conduits = FilteredElementCollector(doc).OfClass(Conduit).ToElements()

    print("ELEMENTOS CONDUIT EN EL DOCUMENTO")
    print("=" * 60)
    print("Total: {}".format(len(conduits)))
    print("=" * 60)

    resultados = []
    for i, c in enumerate(conduits, 1):
        nombre = _nombre_conduit(c)
        diametro_mm = None
        for bip in [BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM, BuiltInParameter.RBS_CONDUIT_OUTER_DIAMETER,
                    BuiltInParameter.RBS_CONDUIT_INNER_DIAMETER, BuiltInParameter.RBS_CONDUIT_NOMINAL_DIAMETER]:
            try:
                p = c.get_Parameter(bip)
                if p is not None:
                    diametro_mm = _pies_a_mm(p.AsDouble())
                    if diametro_mm and diametro_mm > 0:
                        break
            except Exception:
                continue

        diametro_str = "{:.1f} mm".format(diametro_mm) if diametro_mm else "N/D"
        print("{:3d}. {} — diámetro: {}".format(i, nombre, diametro_str))

        resultados.append({
            "indice": i,
            "nombre": nombre,
            "diametro_mm": round(diametro_mm, 2) if diametro_mm else None,
            "element_id": c.Id.ToString(),
        })

    print("=" * 60)
    print("\nSi no hay conduits modelados, necesitas crearlos como elementos de sistema.")
    print("Los conduits se crean con doc.Create.NewConduit(...) en Revit API.")

    if json_out:
        dirpath = os.path.dirname(json_out)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        with open(json_out, "w") as f:
            f.write(json.dumps({
                "fecha_ejecucion": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "total_conduits": len(conduits),
                "conduits": resultados,
            }, indent=2, ensure_ascii=True))
        print("JSON guardado en: {}".format(json_out))

    return resultados
