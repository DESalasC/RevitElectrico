# -*- coding: utf-8 -*-
"""
F7_RUTEO_PYREVIT_v01.py - 2026-11-19 - IronPython 2.7 para pyRevit

Rutea conductos REALES F01/F02 en CENTRAL-V01 usando:
- JSON maestro global (dxf_master_global.json) para posiciones de dispositivos
- TypeIds de conduit desde V02-f: 112216 (Ø21mm), 112217 (Ø27mm), 5508657 (Ø16mm)
- Patrón V02-f: Vertical panel→techo → Horizontales por servicio → Bajadas

USO: Copiar/pegar en pyRevit Python Shell con CENTRAL-V01.rvt abierto.
"""

import json
import math
import clr
import datetime
import sys

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    XYZ, Line, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Level, FamilyInstance, Conduit, ConduitType,
    Transaction, MEPModel, Connector, ConnectorSet, ConnectorDomain,
    ConnectorType, MEPSystem, ElectricalSystem, Wire, WireType,
    Options, Solid, Face, PlanarFace, Reference, UV,
    ElementTransformUtils
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.DB.Electrical import CableTray, CableTrayType
from System import Int64, Array, Guid

# ════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════

JSON_MAESTRO_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global.json"

# TypeIds de conduit desde V02-f (CENTRA_V02-f.rvt)
CONDUIT_TYPE_IDS = {
    "TOMAS": 112216,       # Ø21mm (3/4") - Tubo EMT
    "ILUMINACION": 112216, # Ø21mm - Tubo EMT
    "COMUNICACIONES": 112217, # Ø27mm (1") - Tubo Comunicaciones
    "FUERZA": 112217,      # Ø27mm - Tubo EMT
    "DROPS": 5508657,      # Ø16mm (1/2") - Bajadas a dispositivos
}

# Techos por apartamento (confirmados, NO mover)
CEILING_IDS = {
    "F01": 2764963,
    "F02": 2766313,
}

TECHO_Z_FT = 51.9029  # 15.82 m - altura de los techos falsos

# Paneles eléctricos (posición del tablero en cada apartamento)
PANEL_POS = {
    "F01": XYZ(13990.9 / 304.8, 8010.6 / 304.8, 14420.0 / 304.8),  # TF 01
    "F02": XYZ(14037.4 / 304.8, 9654.7 / 304.8, 14420.0 / 304.8),  # TF 02
}

# Nivel Piso 5
TARGET_LEVEL_NAMES = ["PISO 5", "NIVEL 5", "LEVEL 5", "P5", "N5"]
TARGET_LEVEL_ELEV = 43.37

# Agrupación de servicios (según V02-f)
SERVICE_MAP = {
    "M_Toma doble": "TOMAS",
    "M_Comunicaciones": "COMUNICACIONES",
    "M_Interruptores": "TOMAS",
    "M_Pulsador - Interruptor": "TOMAS",
    "M_Timbre": "TOMAS",
    "EA": "TOMAS",
    "M_ClimatizacionV": "ILUMINACION",
    "M_Iluminacion": "ILUMINACION",
    "Consolidation_Point": "COMUNICACIONES",
}

# Offset para bajadas (desde techo Z=51.90 ft hasta altura dispositivo)
# Dispositivos level-based: Z = 43.37 + altura_montaje
# Dispositivos ceiling-based: Z = techo - offset

# ════════════════════════════════════════════════════════════════
# UTILIDADES
# ════════════════════════════════════════════════════════════════

exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)

def log(msg):
    print(msg)

def clean(s):
    return s.replace('\ufeff','').replace('\u200b','').strip() if s else s

def elem_id(elem):
    if elem is None: return 0
    try:
        if hasattr(elem, 'Id'): eid_obj = elem.Id
        else: eid_obj = elem
        if hasattr(eid_obj, 'IntegerValue'): return int(eid_obj.IntegerValue)
        if hasattr(eid_obj, 'Value'): return int(eid_obj.Value)
        import re; m = re.search(r'(\d+)', str(eid_obj))
        return int(m.group(1)) if m else 0
    except: return 0

def eid(val):
    return ElementId(Int64(val))

def load_json(p):
    with open(p, 'r') as f:
        return json.load(f)

def mm_to_ft(mm):
    return mm / 304.8

def m_to_ft(m):
    return m * 3.280839895

# ════════════════════════════════════════════════════════════════
# DOCUMENTO Y NIVEL
# ════════════════════════════════════════════════════════════════

doc = None
try:
    doc = __revit__.ActiveUIDocument.Document
except:
    try:
        from pyrevit import revit
        doc = revit.doc
    except:
        pass
if not doc:
    log("[ERROR] No documento")
    sys.exit()

log("=" * 70)
log("F7_RUTEO_PYREVIT_v01 - CONDUCTOS REALES F01/F02")
log("Ejecutado: " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S") + " (Bogotá GMT-5)")
log("=" * 70)
log("[OK] " + doc.Title)

# Nivel Piso 5
PISO5_LEVEL = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    name = lvl.Name if hasattr(lvl, 'Name') else ""
    if any(kw in name.upper() for kw in TARGET_LEVEL_NAMES):
        PISO5_LEVEL = lvl
        break
if not PISO5_LEVEL:
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if abs(lvl.Elevation - TARGET_LEVEL_ELEV) < 0.5:
            PISO5_LEVEL = lvl
            break
if not PISO5_LEVEL:
    PISO5_LEVEL = list(FilteredElementCollector(doc).OfClass(Level).ToElements())[0]

NIVEL5_ELEV = PISO5_LEVEL.Elevation
PISO5_LEVEL_ID_INT = elem_id(PISO5_LEVEL)
log("[LEVEL] '" + PISO5_LEVEL.Name + "' Id=" + str(PISO5_LEVEL_ID_INT) + " Elev=" + str(round(NIVEL5_ELEV,4)) + "ft")

# Verificar TypeIds de conduit existen
CONDUIT_TYPES = {}
for servicio, type_id in CONDUIT_TYPE_IDS.items():
    ct = doc.GetElement(eid(type_id))
    if ct and isinstance(ct, ConduitType):
        CONDUIT_TYPES[servicio] = ct
        diam = "?"
        try:
            p = ct.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
            if p and p.HasValue:
                diam = str(round(p.AsDouble() * 304.8, 1)) + "mm"
        except:
            pass
        log("[TYPE] " + servicio + " -> TypeId=" + str(type_id) + " (" + diam + ")")
    else:
        log("[WARN] TypeId " + str(type_id) + " no encontrado para " + servicio)

if not CONDUIT_TYPES:
    log("[ERROR] No se encontraron tipos de conduit válidos")
    sys.exit()

# ════════════════════════════════════════════════════════════════
# CARGAR JSON MAESTRO
# ════════════════════════════════════════════════════════════════

data = load_json(JSON_MAESTRO_PATH)
f01_devices = data.get('apartamentos',{}).get('F01',{}).get('devices',[])
f02_devices = data.get('apartamentos',{}).get('F02',{}).get('devices',[])

log("[JSON] F01: {} dispositivos, F02: {} dispositivos".format(len(f01_devices), len(f02_devices)))

# ════════════════════════════════════════════════════════════════
# AGRUPAR DISPOSITIVOS POR SERVICIO Y APARTAMENTO
# ════════════════════════════════════════════════════════════════

def group_devices_by_service(devices):
    groups = {"TOMAS": [], "ILUMINACION": [], "COMUNICACIONES": [], "FUERZA": []}
    for d in devices:
        fam = d.get('familia_revit', '')
        if not fam:
            continue
        servicio = SERVICE_MAP.get(fam, "TOMAS")
        groups[servicio].append(d)
    return groups

f01_groups = group_devices_by_service(f01_devices)
f02_groups = group_devices_by_service(f02_devices)

for apto_name, groups in [("F01", f01_groups), ("F02", f02_groups)]:
    log("\n" + apto_name + " dispositivos por servicio:")
    for s, devs in groups.items():
        log("  " + s + ": " + str(len(devs)))

# ════════════════════════════════════════════════════════════════
# CALCULAR CENTROIDES POR SERVICIO
# ════════════════════════════════════════════════════════════════

def calc_centroid(devices):
    if not devices:
        return None
    x_sum = sum(d['x'] for d in devices)
    y_sum = sum(d['y'] for d in devices)
    return XYZ(x_sum / len(devices), y_sum / len(devices), TECHO_Z_FT)

f01_centroids = {}
f02_centroids = {}
for s in ["TOMAS", "ILUMINACION", "COMUNICACIONES", "FUERZA"]:
    f01_centroids[s] = calc_centroid(f01_groups.get(s, []))
    f02_centroids[s] = calc_centroid(f02_groups.get(s, []))

# ════════════════════════════════════════════════════════════════
# CREAR CONDUCTOS REALES
# ════════════════════════════════════════════════════════════════

def create_conduit(doc, conduit_type, start_pt, end_pt, level_id, servicio):
    """Crea un conduit real entre dos puntos."""
    try:
        # Crear línea
        line = Line.CreateBound(start_pt, end_pt)
        
        # Crear conduit
        conduit = Conduit.Create(doc, conduit_type.Id, level_id, start_pt, end_pt)
        
        if conduit:
            # Parámetro Servicio
            p_svc = conduit.get_Parameter(BuiltInParameter.RBS_CONDUIT_SYSTEM_CLASSIFICATION_PARAM)
            if not p_svc:
                p_svc = conduit.LookupParameter("Servicio")
            if p_svc and not p_svc.IsReadOnly:
                p_svc.Set(servicio)
            
            # Parámetro Diameter (ya viene del tipo)
            return conduit
    except Exception as e:
        log("  [ERR CREATE] " + str(e))
    return None

def create_vertical_riser(doc, panel_pt, techo_z, conduit_type, level_id, servicio, apto):
    """Crea subida vertical panel -> techo."""
    start = panel_pt
    end = XYZ(panel_pt.X, panel_pt.Y, techo_z)
    log("  [VERTICAL " + servicio + "] " + apto + " panel->techo Z=" + str(round(panel_pt.Z,2)) + "->" + str(round(techo_z,2)))
    return create_conduit(doc, conduit_type, start, end, level_id, servicio)

def create_horizontal_run(doc, panel_pt, centroid, conduit_type, level_id, servicio, apto):
    """Crea tramo horizontal panel/centroide -> centroide servicio."""
    if not centroid:
        return None
    start = XYZ(panel_pt.X, panel_pt.Y, TECHO_Z_FT)
    end = centroid
    log("  [HORIZ " + servicio + "] " + apto + " (" + str(round(start.X,2)) + "," + str(round(start.Y,2)) + ") -> (" + str(round(end.X,2)) + "," + str(round(end.Y,2)) + ")")
    return create_conduit(doc, conduit_type, start, end, level_id, servicio)

def create_drops(doc, devices, conduit_type, level_id, servicio, apto):
    """Crea bajadas techo -> cada dispositivo."""
    created = 0
    for d in devices:
        x = d['x']
        y = d['y']
        fam = d['familia_revit']
        
        # Z destino según tipo de dispositivo
        # Level-based: NIVEL5_ELEV + altura_montaje
        # Ceiling-based: TECHO_Z_FT (ya hosteados en techo)
        if fam in ["M_Iluminacion", "Consolidation_Point"]:
            z_target = TECHO_Z_FT  # Face-based techo
        elif fam in ["M_ClimatizacionV", "M_Timbre"]:
            z_target = TECHO_Z_FT - 0.65  # Con offset -0.65ft
        else:
            # Level-based: usar alturas estándar
            alturas = {
                "M_Toma doble": 0.30, "M_Comunicaciones": 0.30,
                "M_Interruptores": 1.10, "M_Pulsador - Interruptor": 1.10,
                "EA": 1.90,
            }
            h = alturas.get(fam, 0.30)
            z_target = NIVEL5_ELEV + m_to_ft(h)
        
        start = XYZ(x, y, TECHO_Z_FT)
        end = XYZ(x, y, z_target)
        
        # Solo crear si hay diferencia significativa en Z
        if abs(start.Z - end.Z) > 0.1:
            c = create_conduit(doc, conduit_type, start, end, level_id, servicio + "_DROP")
            if c:
                created += 1
    return created

# ════════════════════════════════════════════════════════════════
# EJECUTAR RUTEO
# ════════════════════════════════════════════════════════════════

total_created = 0
total_failed = 0

tx = Transaction(doc, "Ruteo Conductos F01/F02")
tx.Start()

try:
    for apto_name in ["F01", "F02"]:
        log("\n===== RUTEO " + apto_name + " =====")
        panel_pt = PANEL_POS[apto_name]
        groups = f01_groups if apto_name == "F01" else f02_groups
        centroids = f01_centroids if apto_name == "F01" else f02_centroids
        
        # 1. Vertical principal panel -> techo (FUERZA Ø27)
        conduit_type_main = CONDUIT_TYPES.get("FUERZA")
        if conduit_type_main:
            c = create_vertical_riser(doc, panel_pt, TECHO_Z_FT, conduit_type_main, PISO5_LEVEL_ID_INT, "PRINCIPAL", apto_name)
            if c: total_created += 1
            else: total_failed += 1
        
        # 2. Horizontales por servicio
        for servicio in ["TOMAS", "ILUMINACION", "COMUNICACIONES", "FUERZA"]:
            centroid = centroids.get(servicio)
            if not centroid:
                continue
            
            conduit_type = CONDUIT_TYPES.get(servicio)
            if not conduit_type:
                log("  [SKIP] " + servicio + " - TypeId no disponible")
                continue
            
            # Horizontal desde panel a centroide
            c = create_horizontal_run(doc, panel_pt, centroid, conduit_type, PISO5_LEVEL_ID_INT, servicio, apto_name)
            if c: total_created += 1
            else: total_failed += 1
        
        # 3. Bajadas por servicio
        for servicio in ["TOMAS", "ILUMINACION", "COMUNICACIONES", "FUERZA"]:
            devices = groups.get(servicio, [])
            if not devices:
                continue
            
            conduit_type = CONDUIT_TYPES.get("DROPS")  # Ø16mm para bajadas
            if not conduit_type:
                conduit_type = CONDUIT_TYPES.get(servicio)  # fallback
            
            created = create_drops(doc, devices, conduit_type, PISO5_LEVEL_ID_INT, servicio, apto_name)
            total_created += created
            log("  [DROPS " + servicio + "] " + apto_name + " -> " + str(created) + " bajadas")

    tx.Commit()
    log("\n" + "=" * 70)
    log("RUTEO COMPLETADO")
    log("Conductos creados: " + str(total_created))
    log("Fallos: " + str(total_failed))
    log("=" * 70)

except Exception as e:
    tx.RollBack()
    log("[TXN ERROR] " + str(e))
    import traceback
    traceback.print_exc()