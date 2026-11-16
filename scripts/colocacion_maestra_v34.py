# -*- coding: utf-8 -*-
# colocacion_maestra_v34.py | v34.0 | 2026-11-14
# Script Maestro: Integra todas las reglas validadas del Apto E06
import io, json, math, datetime

VER = "34.0"
print("=" * 78)
print("COLOCACION MAESTRA v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 78)

try:
    _ = doc.Title
except:
    doc = __revit__.ActiveUIDocument.Document
print("Documento: " + doc.Title)

try:
    from Autodesk.Revit.DB import *
    from Autodesk.Revit.DB.Structure import StructuralType
except:
    import clr
    clr.AddReference('RevitAPI')
    from Autodesk.Revit.DB import *
    from Autodesk.Revit.DB.Structure import StructuralType

FT = 0.3048
M2FT = 3.28084

def iid(e):
    if e is None: return -1
    try: return int(e.Value)
    except:
        try: return int(e.IntegerValue)
        except: return -1

def by_id(d, n):
    for e in FilteredElementCollector(d).WhereElementIsNotElementType().ToElements():
        if iid(e.Id) == n: return e
    return None

def clean(s):
    if not s: return s
    return s.replace("\ufeff", "").replace("\u200b", "").strip()

def get_type_name(fs):
    try:
        p = fs.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.HasValue: return clean(p.AsString())
    except: pass
    return None

# ============================================================================
# 1. CONFIGURACIÓN (AJUSTAR PARA EL NUEVO APARTAMENTO)
# ============================================================================
# --- Parámetros del nuevo apartamento ---
APTO_NAME = "E05"  # Cambiar según el apartamento
PANEL_ID = 5501144 # ID del panel del nuevo apartamento (ej: TE 05)
CEILING_ID = 2766255 # ID del cielorraso del nuevo apartamento (cambiar)
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E05_v01.json" # Cambiar ruta

# --- Origen del bloque en el DXF general (validado en E06) ---
ORIG_X = 2.251292587795678
ORIG_Y = 9.6726566239697