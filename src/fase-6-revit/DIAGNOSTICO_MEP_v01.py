
Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.


# -*- coding: utf-8 -*-
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
import json
import os

def diagnosticar_mep(doc, json_out=None):
    print("DIAGNOSTICO MEP - REVIT 2026")
    print("=" * 60)
    categorias_mep = [
        ("OST_MechanicalEquipment", "Equipo mecanico"),
        ("OST_DuctCurves", "Ductos HVAC"),
        ("OST_PipeCurves", "Tuberias plomeria"),
        ("OST_Conduit", "Conductos electrico"),
        ("OST_ElectricalEquipment", "Equipo electrico"),
        ("OST_StructuralFraming", "Estructura"),
        ("OST_GenericModel", "Modelo generico"),
        ("OST_ElectricalFixtures", "Accesorios electricos"),
        ("OST_LightingFixtures", "Luminarias"),
    ]
    resultados = {}
    for bic_key, descripcion in categorias_mep:
        try:
            elementos = FilteredElementCollector(doc).OfCategory(
                getattr(BuiltInCategory, bic_key)
            ).ToElements()
            count = len(elementos)
            print("{:30s} - {:4d} elementos".format(descripcion, count))
            resultados[bic_key] = {
                "descripcion": descripcion,
                "count": count,
                "ids": [e.Id.ToString() for e in elementos[:5]],
            }
        except Exception as exc:
            print("{:30s} - ERROR: {}".format(descripcion, exc))
            resultados[bic_key] = {
                "descripcion": descripcion,
                "error": str(exc),
            }
    print("=" * 60)
    if json_out:
        dirpath = os.path.dirname(json_out)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        with open(json_out, "w") as f:
            f.write(json.dumps({
                "fecha_ejecucion": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "categorias": resultados,
            }, indent=2, ensure_ascii=True))
        print("JSON guardado en: {}".format(json_out))
    return resultados
