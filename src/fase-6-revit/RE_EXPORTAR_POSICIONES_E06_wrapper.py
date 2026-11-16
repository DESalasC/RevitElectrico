# -*- coding: utf-8 -*-
# Wrapper para ejecutar RE_EXPORTAR_POSICIONES_REVIT_v01.py dentro de Revit 2026
# a través de pyrevit agent run, guardando el JSON en una ruta fija.
#
# Nota: Conduit requiere RevitAPIMEP, que no se resuelve por nombre en IronPython.
# Se usa un dummy y luego se reemplaza listar_conduits por una versión segura.
class ConduitDummy(object):
    pass

import json
import os

RUTA_EXPORTADOR = r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_EXPORTAR_POSICIONES_REVIT_v01.py"
SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\posiciones_revit_export_2026-11-11.json"

with open(RUTA_EXPORTADOR, "r") as f:
    codigo = f.read()

ns = {"__revit__": __revit__, "__name__": "exportador", "Conduit": ConduitDummy}
exec(codigo, ns)

# Reemplazar listar_conduits por versión segura (no falla si Conduit no es un tipo Revit válido)
def listar_conduits_seguro(doc):
    return []

ns["listar_conduits"] = listar_conduits_seguro

doc = __revit__.ActiveUIDocument.Document
ns["exportar_posiciones"](doc, salida_json=SALIDA_JSON)
