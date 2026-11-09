# -*- coding: utf-8 -*-
"""
Macro pyRevit: REVIT6_CLASH_DETECTION
Detección de interferencias (clashes) contra HVAC, fontanería y estructura.
Nota: verificar la firma exacta de CLASH_DETECTION_v01.py antes de usar.
"""

__title__ = "6.4 Clash Detection"
__author__ = "RevitElectrico / T5-SantaMarta"
__doc__ = "Ejecuta deteccion de interferencias contra HVAC, fontaneria y estructura"

from pyrevit import revit, DB, forms, script
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import os
import json
from datetime import datetime

JSON_OUT = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\clash_detection_resultado.json"


def run():
    doc = revit.doc
    output = script.get_output()
    output.print_md("# 6.4 Deteccion de interferencias (Clash Detection)")
    output.print_md("Fecha: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    output.print_md("Documento: {}".format(doc.Title))
    output.print_md("---")

    # Categorías a verificar contra las FamilyInstance eléctricas
    categorias_mep = [
        (DB.BuiltInCategory.OST_DuctCurves, "HVAC (ductos)"),
        (DB.BuiltInCategory.OST_PipeCurves, "Fontanería (tuberías)"),
        (DB.BuiltInCategory.OST_Conduit, "Conduit existente"),
        (DB.BuiltInCategory.OST_CableTray, "Bandejas portacables"),
        (DB.BuiltInCategory.OST_StructuralFraming, "Estructura (framing)"),
        (DB.BuiltInCategory.OST_StructuralColumns, "Estructura (columnas)"),
        (DB.BuiltInCategory.OST_Walls, "Muros"),
        (DB.BuiltInCategory.OST_Floors, "Losas"),
        (DB.BuiltInCategory.OST_Ceilings, "Cielorrasos"),
    ]

    electricas = DB.FilteredElementCollector(doc).OfClass(DB.FamilyInstance).ToElements()
    output.print_md("FamilyInstance eléctricas encontradas: {}".format(len(electricas)))

    resultados = []
    total_clashes = 0

    for cat_id, nombre_cat in categorias_mep:
        try:
            otros = DB.FilteredElementCollector(doc).OfCategory(cat_id).WhereElementIsNotElementType().ToElements()
            output.print_md("  Comparando contra {} ({} elementos)...".format(nombre_cat, len(otros)))
            # Placeholder: aquí iría la lógica real de intersección de bounding boxes / geometría
            resultados.append({
                "categoria": nombre_cat,
                "elementos_comparados": len(otros),
                "clashes": 0,
                "nota": "Placeholder — implementar intersección de geometría real",
            })
        except Exception as exc:
            output.print_md("  ERROR con {}: {}".format(nombre_cat, exc))

    output.print_md("## Resultado")
    output.print_md("Total clashes detectados: {}".format(total_clashes))
    output.print_md("Fecha ejecucion: {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    output.print_md("**Estado: Placeholder — requiere implementación de intersección de geometría.**")

    dirpath = os.path.dirname(JSON_OUT)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath)
    with open(JSON_OUT, "w") as f:
        f.write(json.dumps({
            "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "documento": doc.Title,
            "total_clashes": total_clashes,
            "resultados": resultados,
        }, indent=2, ensure_ascii=True))
    output.print_md("JSON guardado en: `{}`".format(JSON_OUT))

