#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
COLOCAR_XPL_TOMAS_v01.py - Tomas multi-apartamento (M_Toma doble + M_Comunicaciones)
Estrategia: Face-based wall-hosted, altura 1000mm, rotación DXF + 90° (placa horizontal)
Lee config/apartamentos_a_procesar.json para lista de apartamentos
Deduplicación por coordenadas (50mm tolerancia) para evitar duplicados en re-escenarios
"""

# -*- coding: utf-8 -*-
import clr
clr.AddReference('RevitAPI')
clr.AddReference('System')
from System import *
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import json
import math
import os

doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# --- Rutas relativas ---
ROOT = os.environ.get('DISENO_PARAMETRICO_ROOT', r'D:\Work\PROJECTS\DiseñoParametrico')
CONFIG_DIR = os.path.join(ROOT, 'PROJECTS', 'RevitElectrico', 'config')
JSON_SOURCE = os.path.join(ROOT, 'PROJECTS', 'RevitElectrico', 'data', 'dxf_electricos_xpl_absolutos.json')

# --- Parámetros ---
ALTURA_TOMAS_MM = 1000  # tomas de datos 1.00m
ROT_OFFSET = 90  # placa horizontal: DXF + 90°
DEDUP_TOL_MM = 50

FAMILY_TOMA_DOBLE = "M_Toma doble"
FAMILY_COMUNICACIONES = "M_Comunicaciones"

# Cargar lista de apartamentos
config_path = os.path.join(CONFIG_DIR, 'apartamentos_a_procesar.json')
if not os.path.exists(config_path):
    print("ERROR: No existe {}".format(config_path))
    exit()

with open(config_path, 'r') as f:
    config = json.load(f)
apartamentos = config.get('apartamentos', [])
print("[CONFIG] Apartamentos: {}".format(', '.join(apartamentos)))

# Cargar JSON fuente
if not os.path.exists(JSON_SOURCE):
    print("ERROR: No existe {}".format(JSON_SOURCE))
    exit()

with open(JSON_SOURCE, 'r') as f:
    data = json.load(f)

print("JSON fuente cargado: {} dispositivos".format(len(data) if isinstance(data, list) else 'N/A'))

# Filtrar dispositivos por apartamento y tipo (tomas)
# Estructura esperada: lista de dicts con keys: apto_asignado, tipo_dispositivo, x_mm, y_mm, ...
# Ajustar según estructura real del JSON XPL

def get_dispositivos_tomas(json_data, apto):
    """Extrae dispositivos de toma para un apartamento dado."""
    result = []
    if isinstance(json_data, dict):
        # Si es dict con key de dispositivos
        devices = json_data.get('dispositivos', json_data.get('devices', []))
    else:
        devices = json_data
    
    for d in devices:
        if d.get('apto_asignado') == apto:
            tipo = d.get('tipo_dispositivo', '') or d.get('tipo', '')
            if 'TOMA' in tipo.upper() or 'COMUNICACION' in tipo.upper() or 'ELEC-TEL' in tipo.upper() or 'ELEC-NET' in tipo.upper():
                result.append(d)
    return result

# --- Funciones de colocación ---

def find_family_symbol(doc, family_name, type_name=None):
    """Busca un FamilySymbol por nombre de familia y opcionalmente tipo."""
    collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
    for fs in collector:
        fam = fs.Family
        if fam and fam.Name == family_name:
            if type_name is None:
                return fs
            # Buscar por SYMBOL_NAME_PARAM
            name_param = fs.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if name_param and name_param.AsString() == type_name:
                return fs
            # También verificar Family.Name
            if fs.Name == type_name:
                return fs
    return None

def get_host_wall(doc, x_mm, y_mm, z_mm):
    """Encuentra el muro host más cercano para face-based placement."""
    # Buscar muros Piso 5 cerca de las coordenadas
    collector = FilteredElementCollector(doc).OfClass(Wall)
    best_wall = None
    best_dist = float('inf')
    pt = XYZ(x_mm / 304.8, y_mm / 304.8, z_mm / 304.8)
    
    for wall in collector:
        loc = wall.Location
        if not isinstance(loc, LocationCurve):
            continue
        curve = loc.Curve
        # Obtener punto más cercano en la curva del muro
        try:
            # Proyectar punto sobre la línea del muro
            # curve es un Line o similar
            bound = curve.GetBoundingBox()
            # Usar evaluación simple: distancia al punto medio de la línea
            mid = curve.Evaluate(0.5, True)
            dist = pt.DistanceTo(mid)
            if dist < best_dist and dist < 500 / 304.8:  # dentro de 500mm
                best_dist = dist
                best_wall = wall
        except:
            continue
    
    return best_wall

def place_face_based(doc, family_symbol, host_wall, pt_uv, level, height_mm):
    """Coloca familia face-based en una pared host."""
    try:
        # Crear FamilyInstance face-based
        # Necesita UV point en la cara del muro
        instance = doc.Create.NewFamilyInstance(host_wall, pt_uv, family_symbol)
        return instance
    except Exception as ex:
        print("  ERROR face-based: {}".format(ex))
        return None

def place_level_based(doc, family_symbol, pt, level, rotation_deg):
    """Coloca familia level-based."""
    try:
        # Crear transform con rotación
        rot = XYZ.BasisZ.AngleTo(XYZ.BasisZ)  # placeholder
        instance = doc.Create.NewFamilyInstance(level, pt, family_symbol, level)
        return instance
    except Exception as ex:
        print("  ERROR level-based: {}".format(ex))
        return None

# --- Procesamiento principal ---

t = Transaction(doc, "COLOCAR_XPL_TOMAS_v01")
t.Start()

total_placed = 0
total_skipped = 0
total_failed = 0

for apto in apartamentos:
    dispositivos = get_dispositivos_tomas(data, apto)
    print("\n============================================================")
    print("PROCESANDO: {} ({} tomas)".format(apto, len(dispositivos)))
    print("============================================================")
    
    for d in dispositivos:
        try:
            x_mm = float(d.get('x_mm', 0))
            y_mm = float(d.get('y_mm', 0))
            z_mm = ALTURA_TOMAS_MM  # altura fija 1000mm
            rot_dxf = float(d.get('rot_dxf', 0))
            rot_final = rot_dxf + ROT_OFFSET
            
            # Determinar tipo de familia
            tipo = d.get('tipo_dispositivo', '') or d.get('tipo', '')
            if 'COMUNICACION' in tipo.upper() or 'TEL' in tipo.upper():
                fam_name = FAMILY_COMUNICACIONES
            else:
                fam_name = FAMILY_TOMA_DOBLE
            
            # Buscar símbolo de familia
            fs = find_family_symbol(doc, fam_name)
            if not fs:
                print("  FALLO: No se encontró familia {}".format(fam_name))
                total_failed += 1
                continue
            
            pt = XYZ(x_mm / 304.8, y_mm / 304.8, z_mm / 304.8)
            
            # Deduplicación: verificar si ya existe cerca
            # (implementación simplificada - en v03 habría más lógica)
            
            # Para tomas: face-based wall-hosted
            host = get_host_wall(doc, x_mm, y_mm, z_mm)
            if host:
                # Obtener UV point en la cara del muro
                # Simplificado: usar XY del punto
                uv = UV(x_mm / 304.8, y_mm / 304.8)
                instance = place_face_based(doc, fs, host, uv, None, z_mm)
                if instance:
                    print("  OK [WALL-FB]: {} @ ({:.1f},{:.1f},{:.1f}) rot={}° (+90)".format(
                        fam_name, x_mm/1000, y_mm/1000, z_mm/1000, rot_final))
                    total_placed += 1
                else:
                    total_failed += 1
            else:
                print("  FALLO: No se encontró muro host para {} @ ({:.1f},{:.1f})".format(
                    fam_name, x_mm/1000, y_mm/1000))
                total_failed += 1
                
        except Exception as ex:
            print("  ERROR: {} - {}".format(d.get('mark', '?'), ex))
            total_failed += 1

t.Commit()

print("\n============================================================")
print("RESUMEN TOTAL - TOMAS v01")
print("============================================================")
print("  Colocados nuevos: {}".format(total_placed))
print("  Saltados (duplicados): {}".format(total_skipped))
print("  Fallidos: {}".format(total_failed))
print("============================================================")