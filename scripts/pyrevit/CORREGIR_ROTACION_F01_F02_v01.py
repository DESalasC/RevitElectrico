# -*- coding: utf-8 -*-
"""
CORREGIR_ROTACION_F01_F02_v01.py - IronPython 2.7 para pyRevit
Corrige rotación de dispositivos YA COLOCADOS en F01/F02 según lógica:
- M_Toma doble / M_Comunicaciones: rot_dxf + 90° (placa horizontal)
- M_Interruptores (Simple/Doble/Control): rot_dxf directo
- M_Pulsador-Interruptor (FB-MURO): rot_dxf directo
- M_Iluminacion / M_Timbre / M_ClimatizacionV (FB-TECHO): rot_dxf directo
"""

import json, math, clr, datetime, sys
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, BuiltInCategory, FilteredElementCollector, FamilyInstance, LocationPoint, Line, BuiltInParameter)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"
APTO_TARGETS = ["F01", "F02"]  # corregir ambos

METER_TO_FOOT = 3.280839895
FOOT_TO_METER = 1.0 / METER_TO_FOOT
NIVEL5_ELEV_FT = 43.37
UMBRAL_MATCH_FT = 2.0  # tolerancia matching XY (pies)

def clean(s): return s.replace('\ufeff','').replace('\u200b','').strip() if s else s
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
def load_json(p):
    with open(p, 'r') as f: return json.load(f)
def dist_xy_ft(p1, p2):
    dx = p1.X - p2.X; dy = p1.Y - p2.Y
    return math.sqrt(dx*dx + dy*dy)

exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)

doc = None
try: doc = __revit__.ActiveUIDocument.Document
except:
    try:
        from pyrevit import revit; doc = revit.doc
    except: pass
if not doc: print("[ERROR] No documento"); sys.exit()

print("=" * 70)
print("CORREGIR ROTACION F01/F02")
print("Ejecutado: " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 70)

# 1. CARGAR JSON MAESTRO - F01 y F02
maestro = load_json(JSON_PATH)
expected_by_apto = {}
for apto in APTO_TARGETS:
    apto_data = maestro.get('apartamentos', {}).get(apto, {})
    devices = apto_data.get('devices', [])
    expected_by_apto[apto] = devices
    print("[JSON] {}: {} dispositivos".format(apto, len(devices)))

# 2. RECOLECTAR DISPOSITIVOS EN REVIT - ÁREA F01+F02
# Bounds globales combinados F01+F02 (del JSON)
cats = [BuiltInCategory.OST_ElectricalEquipment, BuiltInCategory.OST_ElectricalFixtures,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_DataDevices,
        BuiltInCategory.OST_TelephoneDevices, BuiltInCategory.OST_CommunicationDevices]

# Bounds amplios F01 (X 25-55, Y -5-40) + F02 (X 25-55, Y 25-65)
X_MIN, X_MAX = 20.0, 60.0
Y_MIN, Y_MAX = -10.0, 70.0

devices_rvt = []
for cat in cats:
    for fi in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
        if not isinstance(fi, FamilyInstance): continue
        loc = fi.Location
        fam = clean(fi.Symbol.FamilyName)
        typ = ""
        try:
            p = fi.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p and p.HasValue: typ = clean(p.AsString()) or ""
        except: pass
        pt = None
        if isinstance(loc, LocationPoint):
            pt = loc.Point
            if pt is not None and abs(pt.Z) < 0.01: pt = None
            if pt is not None and abs(pt.Z - NIVEL5_ELEV_FT) < 0.5: pt = None
        if pt is None:
            try:
                bb = fi.get_BoundingBox(None)
                if bb:
                    pt = XYZ((bb.Min.X+bb.Max.X)/2, (bb.Min.Y+bb.Max.Y)/2, (bb.Min.Z+bb.Max.Z)/2)
            except: pass
        if pt is None: continue
        if not (X_MIN <= pt.X <= X_MAX and Y_MIN <= pt.Y <= Y_MAX): continue
        
        rot_actual = 0
        try:
            if isinstance(loc, LocationPoint):
                rot_actual = int(round(loc.Rotation * 180.0 / math.pi)) % 360
        except: pass
        
        devices_rvt.append({
            "id": elem_id(fi),
            "family": fam,
            "type": typ,
            "pt": pt,
            "rot_actual": rot_actual,
            "loc": loc,
            "instance": fi,
        })

print("\n[REVIT] Dispositivos en área F01+F02: {}".format(len(devices_rvt)))

# 3. MATCHING JSON -> RVT por familia + proximidad
for apto in APTO_TARGETS:
    print("\n" + "=" * 50)
    print("CORRIGIENDO " + apto)
    print("=" * 50)
    
    expected = expected_by_apto[apto]
    used_rvt = set()
    corrected = 0
    skipped = 0
    errors = 0
    
    for exp in expected:
        fam_exp = exp.get('familia_revit', '')
        if not fam_exp: continue
        
        dxf_rot = exp.get('rotation', 0) % 360
        x_exp, y_exp = exp['x'], exp['y']
        
        # Determinar rotación objetivo según familia
        if fam_exp in ["M_Toma doble", "M_Comunicaciones"]:
            target_rot = (dxf_rot + 90) % 360
            rot_logic = "+90° (placa horizontal)"
        else:
            target_rot = dxf_rot
            rot_logic = "directo"
        
        # Buscar match en RVT
        best_j = None
        best_dist = float('inf')
        for j, rvt in enumerate(devices_rvt):
            if j in used_rvt: continue
            if rvt['family'] != fam_exp: continue
            d = dist_xy_ft(XYZ(x_exp, y_exp, 0), rvt['pt'])
            if d < best_dist and d < UMBRAL_MATCH_FT:
                best_dist = d
                best_j = j
        
        if best_j is None:
            print("  [NO MATCH] {} {} @ ({:.2f},{:.2f}) rot_dxf={}°".format(
                fam_exp, exp.get('tipo_revit',''), x_exp, y_exp, dxf_rot))
            skipped += 1
            continue
        
        used_rvt.add(best_j)
        rvt = devices_rvt[best_j]
        
        # Verificar si ya está correcto
        diff = abs((rvt['rot_actual'] - target_rot + 180) % 360 - 180)
        if diff <= 5:  # tolerancia 5°
            print("  [OK] {} {} Id={} rot_actual={}° target={}° ({})".format(
                fam_exp, exp.get('tipo_revit',''), rvt['id'], rvt['rot_actual'], target_rot, rot_logic))
            continue
        
        # Aplicar corrección
        try:
            inst = rvt['instance']
            loc = rvt['loc']
            if not isinstance(loc, LocationPoint):
                print("  [SKIP] {} Id={} no LocationPoint".format(fam_exp, rvt['id']))
                skipped += 1
                continue
            
            # Rotar alrededor del eje vertical del punto
            pt = loc.Point
            axis = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1))
            angle_rad = math.radians((target_rot - rvt['rot_actual']) % 360)
            # Usar rotación relativa
            loc.Rotate(axis, angle_rad)
            
            print("  [FIX] {} {} Id={} rot {}° -> {}° ({}) dXY={:.2f}ft".format(
                fam_exp, exp.get('tipo_revit',''), rvt['id'],
                rvt['rot_actual'], target_rot, rot_logic, best_dist))
            corrected += 1
            
        except Exception as e:
            print("  [ERR] {} Id={}: {}".format(fam_exp, rvt['id'], e))
            errors += 1
    
    print("\n  {} corregidos, {} sin cambio, {} sin match, {} errores".format(corrected, len(expected)-corrected-skipped-errors, skipped, errors))

print("\n" + "=" * 70)
print("CORRECCION COMPLETADA F01/F02")
print("=" * 70)