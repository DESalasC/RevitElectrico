# -*- coding: utf-8 -*-
"""
RE_ASIGNAR_RED_V01.py — Ejecuta la asignacion de RED=SI a 5 dispositivos
electricos sobre el documento activo de Revit 2026.

Depende de: src/fase-6-revit\ASIGNAR_RED_v04.py

USO (desde pyRevit Python Shell dentro de Revit):
  exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_ASIGNAR_RED_V01.py").read())
  app = __revit__.Application
  uidoc = __revit__.ActiveUIDocument
  doc = uidoc.Document
  ejecutar_asignar_red(doc)


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
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import os
import imp
from datetime import datetime

JSON_OUT = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\asignar_red_resultado.json"
SCRIPT_RED = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\ASIGNAR_RED_v04.py"

IDS_RED = [
    "5554265",   # ELEC-NET-PAU
    "5554262",   # ELEC-TEL 1
    "5554263",   # ELEC-TEL 2
    "5554264",   # ELEC-TEL 3
    "5554269",   # ELEC-TEL 4
]


def _cargar_modulo_red(script_red):
    """Carga el script de asignacion RED como modulo real (imp.load_source)
    para evitar problemas de scope con exec() en IronPython 2.7."""
    return imp.load_source("mod_asignar_red", script_red)


def ejecutar_asignar_red(doc=None, json_out=JSON_OUT, script_red=SCRIPT_RED,
                         ids_red=IDS_RED):
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
    print("RE_ASIGNAR_RED_V01 — Asignar RED=SI a dispositivos electricos")
    print("Fecha: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("Documento: {}".format(doc.Title))
    print("=" * 60)

    # Cargar el script de asignacion RED como modulo real
    mod = _cargar_modulo_red(script_red)

    # Inyectar IDS_RED en el modulo cargado para que asignar_red() lo pueda usar
    mod.IDS_RED = ids_red

    # Ejecutar asignacion
    resultado = mod.asignar_red(doc, json_out)

    print()
    print("Fecha ejecucion: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=== Resultado ===")
    print("Exitos: {}".format(resultado["exitos"]))
    print("Fallos: {}".format(resultado["fallos"]))
    print("JSON guardado en: {}".format(json_out))
    print("=" * 60)

    return resultado

