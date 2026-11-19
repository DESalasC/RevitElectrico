# -*- coding: utf-8 -*-
"""
RE_CONTRASTAR_JSON_MAESTRO_V02F_v01.py - 2026-11-19 - IronPython 2.7 para pyRevit

Compara la colocación actual en CENTRAL-V01 contra:
1. JSON maestro global (dxf_master_global.json) - posiciones esperadas del DXF
2. Datos V02-f de referencia (data/referencia/ruteo_F01_F02_v01/) - estándar validado

Umbrales CLAUDE.md:
  - dXY <= 0.02 m (aceptación) / 0.05 m (aviso)
  - dZ <= 0.02 m
  - rotación en {0, 90, 180, 270} +/- 1 deg

USO: Copiar/pegar en pyRevit Python Shell con CENTRAL-V01.rvt abierto.
"""

import json
import math
import clr
import datetime
import sys
import os

clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    XYZ, BuiltInCategory, FilteredElementCollector, FamilyInstance,
    LocationPoint, Level, BuiltInParameter
)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

# ════════════════════════════════════════════════════════════════
# CONSTANTES
# ════════════════════════════════════════════════════════════════

METER_TO_FOOT = 3.280839895
FOOT_TO_METER = 1.0 / METER_TO_FOOT
NIVEL5_ELEV_FT = 43.37  # ~13.22 m

JSON_MAESTRO_PATH = r"D:\\Work\\PROJECTS\\RevitElectrico\\data\\dxf_master_global_all.json"
V02F_DISPOSITIVOS_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\referencia\ruteo_F01_F02_v01\dispositivos.json"

ALTURAS_MM = {
    "M_Toma doble": 300,
    "M_Comunicaciones": 300,
    "M_Interruptores": 1100,
    "M_Pulsador - Interruptor": 1100,
    "M_Timbre": 2400,
    "EA": 1900,
    "M_ClimatizacionV": 2400,
    "M_Iluminacion": 2600,
    "Consolidation_Point": 2700,
}

UMBRAL_DXY_OK_M = 0.02
UMBRAL_DXY_WARN_M = 0.05
UMBRAL_DZ_OK_M = 0.02
UMBROT_DEG = 1.0

# Mapeo familia DXF -> familia Revit (del JSON maestro)
FAMILIA_DXF_A_REVIT = {
    "ELEC-T-GFCI-t-15A": "M_Toma doble",
    "ELEC-T-D-t-15A": "M_Toma doble",
    "ELEC-TEL": "M_Comunicaciones",
    "ELEC-NET-PAU": "M_Comunicaciones",
    "ELEC-I-S-2-5A": "M_Interruptores",
    "ELEC-I-S-1-5A": "M_Interruptores",
    "ELEC-F-CONTROL": "M_Interruptores",
    "ELEC-TIMBRE": "M_Pulsador - Interruptor",
    "ELEC-CAMPANA": "M_Timbre",
    "ELEC-F-VENT": "M_ClimatizacionV",
    "ELEC-EXT": "EA",
    "Bala Stil Led 10W": "M_Iluminacion",
    "Bala Stil Led 13W": "M_Iluminacion",
    "Bala Stil Led 22W": "M_Iluminacion",
}

# ════════════════════════════════════════════════════════════════
# UTILIDADES
# ════════════════════════════════════════════════════════════════

def clean(s):
    if not s:
        return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

def elem_id_int(elem):
    if elem is None:
        return 0
    try:
        eid = elem.Id if hasattr(elem, 'Id') else elem
        if hasattr(eid, 'IntegerValue'):
            return int(eid.IntegerValue)
        if hasattr(eid, 'Value'):
            return int(eid.Value)
        return int(str(eid))
    except Exception:
        return 0

def load_json(path):
    with open(path, 'r') as f:  # IronPython 2.7: SIN encoding=
        return json.load(f)

def dist_xy_m(p1, p2):
    dx = (p1.X - p2.X) * FOOT_TO_METER
    dy = (p1.Y - p2.Y) * FOOT_TO_METER
    return math.sqrt(dx * dx + dy * dy)

def rot_ok(rot_deg):
    """Devuelve True si rotación está en {0,90,180,270} +/- UMBROT_DEG."""
    for base in (0, 90, 180, 270):
        d = abs(((rot_deg - base + 180) % 360) - 180)
        if d <= UMBROT_DEG:
            return True
    return False

def round_deg(rot_deg):
    """Redondea rotación al múltiplo de 90 más cercano."""
    for base in (0, 90, 180, 270):
        d = abs(((rot_deg - base + 180) % 360) - 180)
        if d <= UMBROT_DEG:
            return base
    return round(rot_deg)

# ════════════════════════════════════════════════════════════════
# DOCUMENTO
# ════════════════════════════════════════════════════════════════

doc = None
try:
    doc = __revit__.ActiveUIDocument.Document
except Exception:
    try:
        from pyrevit import revit
        doc = revit.doc
    except Exception:
        pass

if not doc:
    print("[ERROR] No se pudo resolver el documento Revit. Ejecuta dentro de pyRevit.")
    raise SystemExit(1)

print("[OK] {}".format(doc.Title))
print("=" * 70)
print("VALIDACIÓN CONTRA JSON MAESTRO GLOBAL + V02-f")
print("Ejecutado: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 70)

# ════════════════════════════════════════════════════════════════
# CARGAR JSON MAESTRO (fuente de verdad DXF)
# ════════════════════════════════════════════════════════════════

maestro = load_json(JSON_MAESTRO_PATH)
f01_expected = maestro.get('apartamentos', {}).get('F01', {}).get('devices', [])
f02_expected = maestro.get('apartamentos', {}).get('F02', {}).get('devices', [])

print("\n[JSON MAESTRO] F01: {} dispositivos, F02: {} dispositivos".format(len(f01_expected), len(f02_expected)))

# Convertir a formato unificado con XYZ
expected_devices = []
for apto_name, devices in [("F01", f01_expected), ("F02", f02_expected)]:
    for d in devices:
        fam_revit = d.get('familia_revit', '')
        if not fam_revit:
            continue
        expected_devices.append({
            "apto": apto_name,
            "name": d.get('name', ''),
            "familia_revit": fam_revit,
            "tipo_revit": d.get('tipo_revit', ''),
            "rotation": d.get('rotation', 0),
            "pt": XYZ(d['x'], d['y'], 0),  # Z se valida aparte
        })

print("Total esperados (con familia): {}".format(len(expected_devices)))

# ════════════════════════════════════════════════════════════════
# CARGAR V02-f REFERENCIA (estándar validado)
# ════════════════════════════════════════════════════════════════

v02f_data = load_json(V02F_DISPOSITIVOS_PATH)
print("[V02-f] {} dispositivos de referencia".format(len(v02f_data)))

# Agrupar V02-f por apartamento
v02f_by_apto = {"F01": [], "F02": []}
for d in v02f_data:
    unidad = d.get('unidad', '')
    if unidad == "F 01":
        v02f_by_apto["F01"].append(d)
    elif unidad == "F 02":
        v02f_by_apto["F02"].append(d)

print("  F01: {} | F02: {}".format(len(v02f_by_apto["F01"]), len(v02f_by_apto["F02"])))

# ════════════════════════════════════════════════════════════════
# RECOLECTAR DISPOSITIVOS COLOCADOS EN REVIT
# ════════════════════════════════════════════════════════════════

def collect_placed_devices(doc):
    """Recopila FamilyInstances por Mark F01|TF 01 o F02|TF 01 - exactos de esta sesión."""
    cats = [
        BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_ElectricalFixtures,
        BuiltInCategory.OST_LightingFixtures,
        BuiltInCategory.OST_DataDevices,
        BuiltInCategory.OST_TelephoneDevices,
        BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_MechanicalEquipment,
        BuiltInCategory.OST_FireAlarmDevices,
    ]
    placed = []
    for cat in cats:
        for fi in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
            if not isinstance(fi, FamilyInstance):
                continue
            mark_p = fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if not (mark_p and mark_p.HasValue):
                continue
            mark_val = mark_p.AsString()
            if not mark_val or not (mark_val.startswith("F01|TF 01") or mark_val.startswith("F02|TF 01")):
                continue
            
            loc = fi.Location
            fam = clean(fi.Symbol.FamilyName)
            sym = fi.Symbol
            typ = ""
            try:
                p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                if p and p.HasValue:
                    typ = clean(p.AsString()) or ""
            except Exception:
                pass
            
            # BoundingBox para Z real
            pt = None
            try:
                bb = fi.get_BoundingBox(None)
                if bb is not None:
                    pt = XYZ(
                        (bb.Min.X + bb.Max.X) / 2.0,
                        (bb.Min.Y + bb.Max.Y) / 2.0,
                        (bb.Min.Z + bb.Max.Z) / 2.0,
                    )
            except Exception:
                pass
            if pt is None and isinstance(loc, LocationPoint):
                pt = loc.Point
            if pt is None:
                continue
            
            apto = "F01" if mark_val.startswith("F01") else "F02"
            
            placed.append({
                "id": elem_id_int(fi),
                "unique_id": fi.UniqueId,
                "family": fam,
                "type": typ,
                "pt": pt,
                "level_id": elem_id_int(fi.LevelId),
                "mark": mark_val,
                "apto": apto,
            })
    return placed

placed = collect_placed_devices(doc)
print("\nDispositivos con mark F01|TF 01 o F02|TF 01: {}".format(len(placed)))

f01_placed = [d for d in placed if d['apto'] == "F01"]
f02_placed = [d for d in placed if d['apto'] == "F02"]
our_placed = f01_placed + f02_placed

print("Dispositivos F01 (por mark): {}".format(len(f01_placed)))
print("Dispositivos F02 (por mark): {}".format(len(f02_placed)))
print("Total dispositivos de esta sesión: {}".format(len(our_placed)))

# ════════════════════════════════════════════════════════════════
# MATCHING: Esperado (JSON maestro) <-> Colocado (Revit)
# ════════════════════════════════════════════════════════════════

def match_devices(expected, placed, apto_name):
    """Empareja por familia base + proximidad XY.
    Familia base: 'M_Interruptores' matchea 'M_Interruptores Simple', 'M_Interruptores Doble', etc."""
    matches = []
    used = set()
    for exp in expected:
        if exp['apto'] != apto_name:
            continue
        best = None
        best_dist = float('inf')
        exp_fam_base = exp['familia_revit']
        for i, pl in enumerate(placed):
            if i in used:
                continue
            pl_fam = pl['family']
            # Match flexible: familia base exacta o familia base + espacio + sufijo
            if not (pl_fam == exp_fam_base or pl_fam.startswith(exp_fam_base + " ")):
                continue
            d = dist_xy_m(exp['pt'], pl['pt'])
            if d < best_dist:
                best_dist = d
                best = (i, pl)
        if best:
            used.add(best[0])
            matches.append({
                "expected": exp,
                "placed": best[1],
                "dxy_m": best_dist,
            })
    return matches

f01_matches = match_devices(expected_devices, f01_placed, "F01")
f02_matches = match_devices(expected_devices, f02_placed, "F02")
all_matches = f01_matches + f02_matches

print("\n=== MATCHING ESPERADO vs COLOCADO ===")
print("F01 emparejados: {}/{}".format(len(f01_matches), len([e for e in expected_devices if e['apto']=='F01'])))
print("F02 emparejados: {}/{}".format(len(f02_matches), len([e for e in expected_devices if e['apto']=='F02'])))

# ════════════════════════════════════════════════════════════════
# VALIDAR dXY, dZ, ROTACIÓN
# ════════════════════════════════════════════════════════════════

print("\n=== VALIDACIÓN POR INSTANCIA ===")
dxy_ok = dxy_warn = dxy_fail = 0
dz_ok = dz_warn = dz_fail = 0
rot_ok_count = rot_fail = 0

for m in all_matches:
    exp = m['expected']
    pl = m['placed']
    dxy = m['dxy_m']
    
    # dXY
    if dxy <= UMBRAL_DXY_OK_M:
        dxy_ok += 1
        dxy_status = "OK"
    elif dxy <= UMBRAL_DXY_WARN_M:
        dxy_warn += 1
        dxy_status = "WARN"
    else:
        dxy_fail += 1
        dxy_status = "FAIL"
    
    # dZ
    fam = exp['familia_revit']
    alt_mm = ALTURAS_MM.get(fam, 300)
    z_exp_ft = NIVEL5_ELEV_FT + (alt_mm / 1000.0) * METER_TO_FOOT
    z_placed_ft = pl['pt'].Z
    dz_m = abs((z_placed_ft - z_exp_ft) * FOOT_TO_METER)
    
    # Debug: mostrar Z esperado vs colocado si dZ > 0.1m
    if dz_m > 0.1:
        print("  [DEBUG dZ] {} exp_Z={:.2f}ft placed_Z={:.2f}ft dz={:.3f}m".format(fam, z_exp_ft, z_placed_ft, dz_m))
    
    if dz_m <= UMBRAL_DZ_OK_M:
        dz_ok += 1
        dz_status = "OK"
    elif dz_m <= UMBRAL_DZ_OK_M * 5:  # 0.1m aviso
        dz_warn += 1
        dz_status = "WARN"
    else:
        dz_fail += 1
        dz_status = "FAIL"
    
    # Rotación
    exp_rot = exp['rotation'] % 360
    pl_rot = 0
    try:
        loc = doc.GetElement(pl['id']).Location
        if isinstance(loc, LocationPoint):
            pl_rot = round(loc.Rotation * 180.0 / math.pi) % 360
    except:
        pass
    
    if rot_ok(exp_rot) and rot_ok(pl_rot):
        rot_match = round_deg(exp_rot) == round_deg(pl_rot)
    else:
        rot_match = abs(((exp_rot - pl_rot + 180) % 360) - 180) <= UMBROT_DEG
    
    if rot_match:
        rot_ok_count += 1
        rot_status = "OK"
    else:
        rot_fail += 1
        rot_status = "FAIL"
    
    if dxy_status != "OK" or dz_status != "OK" or rot_status != "OK":
        print("  [{} {}] {} | dXY={:.3f}m {} | dZ={:.3f}m {} | rot:exp={}° pl={}° {}".format(
            exp['apto'], exp['name'], exp['familia_revit'],
            dxy, dxy_status, dz_m, dz_status, exp_rot, pl_rot, rot_status))

print("\nResumen dXY: OK={} WARN={} FAIL={}".format(dxy_ok, dxy_warn, dxy_fail))
print("Resumen dZ:  OK={} WARN={} FAIL={}".format(dz_ok, dz_warn, dz_fail))
print("Resumen rot: OK={} FAIL={}".format(rot_ok_count, rot_fail))

# ════════════════════════════════════════════════════════════════
# VALIDAR CONTRA V02-f (estándar de ruteo validado)
# ════════════════════════════════════════════════════════════════

print("\n=== VALIDACIÓN CONTRA V02-f (REFERENCIA) ===")

def match_to_v02f(placed, v02f_list):
    """Empareja colocados con V02-f por familia+tipo+proximidad."""
    matches = []
    used = set()
    for pl in placed:
        best = None
        best_dist = float('inf')
        for i, v02f in enumerate(v02f_list):
            if i in used:
                continue
            if v02f['fam'] != pl['family']:
                continue
            # Tipo compatible
            if pl['type'] and v02f['tipo'] and pl['type'] != v02f['tipo']:
                continue
            v_pt = XYZ(v02f['x'] / 304.8, v02f['y'] / 304.8, v02f['z'] / 304.8)
            d = dist_xy_m(pl['pt'], v_pt)
            if d < best_dist:
                best_dist = d
                best = (i, v02f)
        if best:
            used.add(best[0])
            matches.append({
                "placed": pl,
                "v02f": best[1],
                "dxy_m": best_dist,
            })
    return matches

f01_v02f = match_to_v02f(f01_placed, v02f_by_apto["F01"])
f02_v02f = match_to_v02f(f02_placed, v02f_by_apto["F02"])
all_v02f = f01_v02f + f02_v02f

v02f_dxy_ok = v02f_dxy_warn = v02f_dxy_fail = 0
for m in all_v02f:
    dxy = m['dxy_m']
    if dxy <= UMBRAL_DXY_OK_M:
        v02f_dxy_ok += 1
    elif dxy <= UMBRAL_DXY_WARN_M:
        v02f_dxy_warn += 1
    else:
        v02f_dxy_fail += 1

print("Emparejados con V02-f: F01={} F02={} Total={}".format(len(f01_v02f), len(f02_v02f), len(all_v02f)))
print("dXY vs V02-f: OK={} WARN={} FAIL={}".format(v02f_dxy_ok, v02f_dxy_warn, v02f_dxy_fail))

# Mostrar discrepancias > 0.05m vs V02-f
for m in all_v02f:
    if m['dxy_m'] > UMBRAL_DXY_WARN_M:
        pl = m['placed']
        v02f = m['v02f']
        print("  [DXY>{}m] {} {} @ ({:.1f},{:.1f}) vs V02-f ({:.1f},{:.1f}) d={:.3f}m".format(
            UMBRAL_DXY_WARN_M, pl['family'], pl['type'],
            pl['pt'].X, pl['pt'].Y, v02f['x']/304.8, v02f['y']/304.8, m['dxy_m']))

# ════════════════════════════════════════════════════════════════
# CONTEOS POR FAMILIA/TIPO
# ════════════════════════════════════════════════════════════════

def count_by_family_type(devices):
    d = {}
    for dev in devices:
        key = (dev.get('familia_revit', dev.get('family', '')), dev.get('tipo_revit', dev.get('type', '')))
        d[key] = d.get(key, 0) + 1
    return d

expected_counts = count_by_family_type(expected_devices)
placed_counts = count_by_family_type(our_placed)
v02f_counts = count_by_family_type(v02f_data)

print("\n=== CONTEOS POR FAMILIA/TIPO ===")
all_keys = sorted(set(list(expected_counts.keys()) + list(placed_counts.keys()) + list(v02f_counts.keys())))
for key in all_keys:
    exp_n = expected_counts.get(key, 0)
    pl_n = placed_counts.get(key, 0)
    v02f_n = v02f_counts.get(key, 0)
    status = "OK" if exp_n == pl_n else "DISCREPANCIA"
    print("  {:<30} | {:<20} | Exp={} Pl={} V02f={} [{}]".format(key[0], key[1], exp_n, pl_n, v02f_n, status))

# ════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("RESUMEN DE VALIDACIÓN")
print("=" * 70)
print("Dispositivos en JSON maestro: {}".format(len(expected_devices)))
print("Dispositivos en V02-f:        {}".format(len(v02f_data)))
print("Dispositivos en Revit (F01+F02): {}".format(len(our_placed)))
print("")
print("vs JSON maestro:")
print("  dXY OK (<=0.02m):     {}".format(dxy_ok))
print("  dXY WARN (0.02-0.05m): {}".format(dxy_warn))
print("  dXY FAIL (>0.05m):     {}".format(dxy_fail))
print("  dZ OK (<=0.02m):       {}".format(dz_ok))
print("  dZ WARN:               {}".format(dz_warn))
print("  dZ FAIL:               {}".format(dz_fail))
print("  Rotación OK:           {}".format(rot_ok_count))
print("")
print("vs V02-f:")
print("  dXY OK:     {}".format(v02f_dxy_ok))
print("  dXY WARN:   {}".format(v02f_dxy_warn))
print("  dXY FAIL:   {}".format(v02f_dxy_fail))
print("")
if dxy_fail == 0 and dz_fail == 0 and rot_fail == 0 and v02f_dxy_fail == 0:
    print(">>> VALIDACIÓN EXITOSA <<<")
else:
    print(">>> VALIDACIÓN CON DISCREPANCIAS - REVISAR <<<")
print("=" * 70)