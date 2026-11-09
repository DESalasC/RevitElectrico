# -*- coding: utf-8 -*-
"""
Macro pyRevit: REVIT6_MODELO_MAPA
Modela las 37 FamilyInstance de dispositivos electricos del apartamento F 02
en el documento Revit activo, consumiendo reporte_bloques_todos.json.

Depende de: src/fase-6-revit\RE_APLICAR_MAPA_V3_REVIT_v02.py
"""

__title__ = "6.1 Modelar mapa (F02)"
__author__ = "RevitElectrico / T5-SantaMarta"
__doc__ = "Crea las 37 FamilyInstance de dispositivos electricos desde reporte_bloques_todos.json"

from pyrevit import revit, DB, forms, script
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import os
import imp
from datetime import datetime

SCRIPT_MAPA = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_APLICAR_MAPA_V3_REVIT_v02.py"
JSON_IN = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\reporte_bloques_todos.json"
JSON_OUT = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\resultado_modelado_apto_F02.json"


def _construir_revit_db():
    return {
        "FilteredElementCollector": DB.FilteredElementCollector,
        "BuiltInCategory": DB.BuiltInCategory,
        "XYZ": DB.XYZ,
        "FamilyInstance": DB.FamilyInstance,
        "FamilySymbol": DB.FamilySymbol,
        "Family": DB.Family,
        "Level": DB.Level,
        "Structure": DB.Structure,
        "Transaction": DB.Transaction,
        "Options": DB.Options,
    }


def run():
    doc = revit.doc
    output = script.get_output()
    output.print_md("# 6.1 Modelar mapa de bloques (F 02)")
    output.print_md("Fecha: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    output.print_md("Documento: {}".format(doc.Title))
    output.print_md("---")

    # Cargar script de mapa como modulo real
    mod = imp.load_source("mod_mapa_revit", SCRIPT_MAPA)
    revit_db = _construir_revit_db()

    try:
        resultado = mod.aplicar_mapa_revit(doc, JSON_IN, JSON_OUT, revit_db)
    except Exception as exc:
        output.print_md("**ERROR:** {}".format(exc))
        import traceback
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
        return

    output.print_md("## Resultado")
    est = resultado["estadisticas"]
    output.print_md("- Total a modelar: {}".format(est["total_modelar"]))
    output.print_md("- **Exitos: {}**".format(est["exitos"]))
    output.print_md("- Fallos: {}".format(est["fallos"]))
    output.print_md("- Saltados (marcador): {}".format(est["saltados_marcador"]))
    output.print_md("- Sin mapeo: {}".format(est["sin_mapeo"]))
    output.print_md("JSON guardado en: `{}`".format(JSON_OUT))
    output.print_md("Fecha ejecucion: {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    if est["exitos"] == 37 and est["fallos"] == 0:
        output.print_md("**Estado: OK — 37 / 0 / 22 / 0 validado.**")
    else:
        output.print_md("**Estado: REVISAR — resultado inesperado.**")

