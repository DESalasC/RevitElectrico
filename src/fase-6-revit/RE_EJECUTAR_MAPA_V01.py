# -*- coding: utf-8 -*-
"""
RE_EJECUTAR_MAPA_V01.py — Ejecuta aplicacion del mapa de bloques Revit
sobre el documento activo (modela FamilyInstance de dispositivos electricos).

Depende de: src/fase-6-revit\RE_APLICAR_MAPA_V3_REVIT_v02.py

USO (desde pyRevit Python Shell dentro de Revit):
  exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_EJECUTAR_MAPA_V01.py").read())
  app = __revit__.Application
  uidoc = __revit__.ActiveUIDocument
  doc = uidoc.Document
  ejecutar_mapa(doc)


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
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    XYZ,
    FamilyInstance,
    FamilySymbol,
    Family,
    Level,
    Structure,
    Transaction,
    Options,
)
from Autodesk.Revit.UI import *

import json
import os
import imp
from datetime import datetime

JSON_IN = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\reporte_bloques_todos.json"
JSON_OUT = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\resultado_modelado_apto_F02.json"
SCRIPT_MAPA = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_APLICAR_MAPA_V3_REVIT_v02.py"


def _cargar_modulo_mapa(script_mapa):
    """Carga el script de mapa como un modulo real (imp.load_source) para que
    sus funciones queden accesibles como atributos y no haya problemas de scope
    con exec() en IronPython 2.7."""
    return imp.load_source("mod_mapa_revit", script_mapa)


def _construir_revit_db():
    """Construye el diccionario de clases de la API de Revit directamente."""
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "BuiltInCategory": BuiltInCategory,
        "XYZ": XYZ,
        "FamilyInstance": FamilyInstance,
        "FamilySymbol": FamilySymbol,
        "Family": Family,
        "Level": Level,
        "Structure": Structure,
        "Transaction": Transaction,
        "Options": Options,
    }


def ejecutar_mapa(doc=None, json_in=JSON_IN, json_out=JSON_OUT, script_mapa=SCRIPT_MAPA):
    """Si no se recibe doc, lo resuelve desde __revit__ (pyRevit/RevitPythonShell)."""
    if doc is None:
        try:
            app = __revit__.Application
            uidoc = __revit__.ActiveUIDocument
            doc = uidoc.Document if uidoc is not None else None
        except Exception:
            doc = None
        if doc is None:
            print("ERROR: No hay un documento de Revit activo abierto.")
            return {"conectado": False, "documento_activo": False}

    print("=" * 60)
    print("RE_EJECUTAR_MAPA_V01 — Modelar FamilyInstance en Revit 2026")
    print("Fecha: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("Documento: {}".format(doc.Title))
    print("=" * 60)

    # Cargar el script de mapa como modulo real
    mod = _cargar_modulo_mapa(script_mapa)

    # Construir el diccionario de la API de Revit
    revit_db = _construir_revit_db()

    # Ejecutar aplicacion via el modulo cargado (funciones accesibles como atributos)
    resultado = mod.aplicar_mapa_revit(doc, json_in, json_out, revit_db)

    print()
    print("Fecha ejecucion: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=== Resultado ===")
    print("Total a modelar: {}".format(resultado["estadisticas"]["total_modelar"]))
    print("Exitos: {}".format(resultado["estadisticas"]["exitos"]))
    print("Fallos: {}".format(resultado["estadisticas"]["fallos"]))
    print("Saltados (marcador): {}".format(resultado["estadisticas"]["saltados_marcador"]))
    print("Sin mapeo: {}".format(resultado["estadisticas"]["sin_mapeo"]))
    print("JSON guardado en: {}".format(json_out))
    print("=" * 60)

    return resultado

