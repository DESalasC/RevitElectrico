# -*- coding: utf-8 -*-
"""
RE_CONTRASTAR_APTO_v01.py - 2026-11-19 - IronPython 2.7 para pyRevit
Valida UN apartamento específico contra JSON maestro global + V02-f
Uso: Cambiar APTO_TARGET = "E06" / "F01" / "F02" / etc.
"""

import json, math, clr, datetime, sys
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, BuiltInCategory, FilteredElementCollector, FamilyInstance, LocationPoint, Level, BuiltInParameter)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

# ════════════════════════════════════════════════════════════════
# CONFIG - LEER DESDE ARCHIVO EXTERNO
# ════════════════════════════════════════════════════════════════

CONFIG_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\apto_config.json"

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

cfg = load_config()
APTO_TARGET = cfg.get('apto_target', 'F01')
MODE = cfg.get('mode', 'validate')

JSON_MAESTRO_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"
V02F_DISPOSITIVOS_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\referencia\ruteo_F01_F02_v01\dispositivos.json"

METER_TO_FOOT = 3.280839895
FOOT_TO_METER = 1.0 / METER_TO_FOOT
NIVEL5_ELEV_FT = 43.37

ALTURAS_MM = {
    "M_Toma doble": 300, "M_Comunicaciones": 300,
    "M_Interruptores": 1100, "M_Pulsador - Interruptor": 1100,
    "M_Timbre": 2400, "EA": 1900,
    "M_ClimatizacionV": 2400, "M_Iluminacion": 2600, "Consolidation_Point": 2700,
}

UMBRAL_DXY_OK_M = 0.02
UMBRAL_DXY_WARN_M = 0.05
UMBRAL_DZ_OK_M = 0.02
UMBROT_DEG = 1.0

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
def dist_xy_m(p1, p2):
    dx = (p1.X - p2.X) * FOOT_TO_METER
    dy = (p1.Y - p2.Y) * FOOT_TO_METER
    return math.sqrt(dx*dx + dy*dy)
def rot_ok(rot_deg):
    for base in (0, 90, 180, 270):
        d = abs(((rot_deg - base + 180) % 360) - 180)
        if d <= UMBROT_DEG: return True
    return False
def round_deg(rot_deg):
    for base in (0, 90, 180, 270):
        d = abs(((rot_deg - base + 180) % 360) - 180)
        if d <= UMBROT_DEG: return base
    return round(rot_deg)

exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)

# ════════════════════════════════════════════════════════════════
# DOCUMENTO
# ═══════════════════════════════════════════════════════════════
doc = None
try: doc = __revit__.ActiveUIDocument.Document
except:
    try:
        from pyrevit import revit; doc = revit.doc
    except: pass
if not doc: print("[ERROR] No documento"); sys.exit()

print("=" * 70)
print("VALIDACIÓN APARTAMENTO: " + APTO_TARGET)
print("Ejecutado: " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 70)

# ════════════════════════════════════════════════════════════════
# CARGAR JSON MAESTRO - SOLO APTO_TARGET
# ═══════════════════════════════════════════════════════════════
maestro = load_json(JSON_MAESTRO_PATH)
apto_data = maestro.get('apartamentos', {}).get(APTO_TARGET, {})
devices = apto_data.get('devices', [])
panel = apto_data.get('panel_name', '?')

if not devices:
    print("[ERROR] No hay dispositivos para " + APTO_TARGET)
    sys.exit()

print("[JSON] " + APTO_TARGET + " (Panel: " + panel + ") - " + str(len(devices)) + " dispositivos")

expected = []
for d in devices:
    fam = d.get('familia_revit', '')
    if not fam: continue
    expected.append({
        "name": d.get('name', ''),
        "familia_revit": fam,
        "tipo_revit": d.get('tipo_revit', ''),
        "rotation": d.get('rotation', 0),
        "pt": XYZ(d['x'], d['y'], 0),
        "mark": d.get('mark', APTO_TARGET + "|" + panel),
    })
print("  Esperados (con familia): " + str(len(expected)))

# ════════════════════════════════════════════════════════════════
# CARGAR V02-f (solo F01/F02 tienen referencia)
# ════════════════════════════════════════════════════════════════
v02f_data = load_json(V02F_DISPOSITIVOS_PATH)
v02f_by_apto = {"F01": [], "F02": []}
for d in v02f_data:
    if d.get('unidad') == "F 01": v02f_by_apto["F01"].append(d)
    elif d.get('unidad') == "F 02": v02f_by_apto["F02"].append(d)

# ════════════════════════════════════════════════════════════════
# RECOLECTAR DISPOSITIVOS EN REVIT - FILTRAR POR ÁREA APTO_TARGET
# ════════════════════════════════════════════════════════════════
cats = [BuiltInCategory.OST_ElectricalEquipment, BuiltInCategory.OST_ElectricalFixtures,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_DataDevices,
        BuiltInCategory.OST_TelephoneDevices, BuiltInCategory.OST_CommunicationDevices]

# Bounds por apartamento (aproximados, en pies)
APTO_BOUNDS = {
    "F01": (25, 55, -5, 40), "F02": (25, 55, 25, 65),
    "F17": (-70, -40, -5, 40), "F18": (-70, -40, 25, 65),
    "E06": (-15, 15, 25, 65), "E07": (-150, -110, -5, 40), "E08": (-150, -110, 25, 65),
    "D13": (-110, -80, 25, 65), "C14": (-110, -80, -5, 40),
    "B15": (-180, -140, -5, 40), "B16": (-180, -140, 25, 65),
}

def in_bounds(pt, bounds):
    x_min, x_max, y_min, y_max = bounds
    return x_min <= pt.X <= x_max and y_min <= pt.Y <= y_max

bounds = APTO_BOUNDS.get(APTO_TARGET, (-200, 200, -200, 200))

placed = []
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
        if not in_bounds(pt, bounds): continue
        placed.append({"id": elem_id(fi), "unique_id": fi.UniqueId, "family": fam, "type": typ, "pt": pt, "level_id": elem_id(fi.LevelId)})

print("\n[REVIT] Dispositivos en área " + APTO_TARGET + ": " + str(len(placed)))

# ════════════════════════════════════════════════════════════════
# MATCHING ESPERADO vs COLOCADO
# ════════════════════════════════════════════════════════════════
matches = []
used = set()
for exp in expected:
    best = None; best_dist = float('inf')
    for i, pl in enumerate(placed):
        if i in used: continue
        if pl['family'] != exp['familia_revit']: continue
        d = dist_xy_m(exp['pt'], pl['pt'])
        if d < best_dist: best_dist = d; best = (i, pl)
    if best:
        used.add(best[0])
        matches.append({"expected": exp, "placed": best[1], "dxy_m": best_dist})

print("\n=== MATCHING " + APTO_TARGET + " ===")
print("Emparejados: " + str(len(matches)) + " / " + str(len(expected)))

# ════════════════════════════════════════════════════════════════
# VALIDAR DETALLADO
# ════════════════════════════════════════════════════════════════
print("\n=== DETALLE POR DISPOSITIVO ===")
dxy_ok = dxy_warn = dxy_fail = 0
dz_ok = dz_warn = dz_fail = 0
rot_ok_c = rot_fail = 0
mark_ok = mark_fail = 0

for m in matches:
    exp = m['expected']; pl = m['placed']
    dxy = m['dxy_m']
    
    # dXY
    if dxy <= UMBRAL_DXY_OK_M: dxy_ok += 1; dxy_s = "OK"
    elif dxy <= UMBRAL_DXY_WARN_M: dxy_warn += 1; dxy_s = "WARN"
    else: dxy_fail += 1; dxy_s = "FAIL"
    
    # dZ
    fam = exp['familia_revit']
    alt_mm = ALTURAS_MM.get(fam, 300)
    z_exp_ft = NIVEL5_ELEV_FT + (alt_mm/1000.0) * METER_TO_FOOT
    z_placed_ft = pl['pt'].Z
    dz_m = abs((z_placed_ft - z_exp_ft) * FOOT_TO_METER)
    if dz_m <= UMBRAL_DZ_OK_M: dz_ok += 1; dz_s = "OK"
    elif dz_m <= UMBRAL_DZ_OK_M * 5: dz_warn += 1; dz_s = "WARN"
    else: dz_fail += 1; dz_s = "FAIL"
    
    # Rotación
    exp_rot = exp['rotation'] % 360
    pl_rot = 0
    try:
        fi = doc.GetElement(pl['id'])
        if fi and fi.Location and isinstance(fi.Location, LocationPoint):
            pl_rot = round(fi.Location.Rotation * 180.0 / math.pi) % 360
    except: pass
    rot_match = (round_deg(exp_rot) == round_deg(pl_rot)) if rot_ok(exp_rot) and rot_ok(pl_rot) else (abs(((exp_rot - pl_rot + 180) % 360) - 180) <= UMBROT_DEG)
    if rot_match: rot_ok_c += 1; rot_s = "OK"
    else: rot_fail += 1; rot_s = "FAIL"
    
    # Mark (Identity Data)
    mark_exp = exp.get('mark', '')
    mark_act = ""
    try:
        fi = doc.GetElement(pl['id'])
        if fi:
            p = fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p and p.HasValue: mark_act = p.AsString() or ""
            else:
                for pp in fi.Parameters:
                    if pp.Definition.Name.lower() == "mark" and pp.HasValue:
                        mark_act = pp.AsString() or ""
                        break
    except: pass
    mark_match = (mark_act == mark_exp) if mark_exp else False
    if mark_match: mark_ok += 1; mark_s = "OK"
    else: mark_fail += 1; mark_s = "FAIL"
    
    # Print detalle
    status = "OK" if (dxy_s=="OK" and dz_s=="OK" and rot_s=="OK" and mark_s=="OK") else "REVISAR"
    print("  [{}] {} | {} {} | dXY={:.3f}m {} | dZ={:.3f}m {} | rot:exp={}° act={}° {} | Mark:exp='{}' act='{}' {}".format(
        status, exp['name'], exp['familia_revit'], exp['tipo_revit'],
        dxy, dxy_s, dz_m, dz_s, exp_rot, pl_rot, rot_s, mark_exp, mark_act, mark_s))

# Dispositivos esperados SIN match
for exp in expected:
    found = False
    for m in matches:
        if m['expected']['name'] == exp['name'] and m['expected']['familia_revit'] == exp['familia_revit']:
            found = True; break
    if not found:
        print("  [FALTANTE] {} {} {} -> NO ENCONTRADO EN REVIT".format(exp['name'], exp['familia_revit'], exp['tipo_revit']))

# Dispositivos en Revit SIN match (extras)
for i, pl in enumerate(placed):
    if i not in used:
        print("  [EXTRA] {} {} @ ({:.2f},{:.2f}) -> NO EN JSON MAESTRO".format(pl['family'], pl['type'], pl['pt'].X, pl['pt'].Y))

# ════════════════════════════════════════════════════════════════
# VS V02-f (solo F01/F02)
# ════════════════════════════════════════════════════════════════
if APTO_TARGET in v02f_by_apto:
    v02f_list = v02f_by_apto[APTO_TARGET]
    print("\n=== VS V02-f ({}) ===".format(APTO_TARGET))
    v02f_matches = []
    used_v = set()
    for pl in placed:
        best = None; best_dist = float('inf')
        for i, v02f in enumerate(v02f_list):
            if i in used_v: continue
            if v02f['fam'] != pl['family']: continue
            if pl['type'] and v02f['tipo'] and pl['type'] != v02f['tipo']: continue
            vpt = XYZ(v02f['x']/304.8, v02f['y']/304.8, v02f['z']/304.8)
            d = dist_xy_m(pl['pt'], vpt)
            if d < best_dist: best_dist = d; best = (i, v02f)
        if best:
            used_v.add(best[0])
            v02f_matches.append({"placed": pl, "v02f": best[1], "dxy_m": best_dist})
    for m in v02f_matches:
        dxy = m['dxy_m']
        s = "OK" if dxy <= UMBRAL_DXY_OK_M else ("WARN" if dxy <= UMBRAL_DXY_WARN_M else "FAIL")
        pl = m['placed']; v02f = m['v02f']
        print("  [{}] {} {} dXY={:.3f}m vs V02-f ({:.2f},{:.2f})".format(s, pl['family'], pl['type'], dxy, v02f['x']/304.8, v02f['y']/304.8))

# ════════════════════════════════════════════════════════════════
# RESUMEN
# ════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("RESUMEN " + APTO_TARGET)
print("=" * 70)
print("Esperados (JSON):     " + str(len(expected)))
print("En Revit (área):      " + str(len(placed)))
print("Emparejados:          " + str(len(matches)))
print("Faltantes:            " + str(len(expected) - len(matches)))
print("Extras en Revit:      " + str(len(placed) - len(matches)))
print("")
print("dXY  OK:{} WARN:{} FAIL:{}".format(dxy_ok, dxy_warn, dxy_fail))
print("dZ   OK:{} WARN:{} FAIL:{}".format(dz_ok, dz_warn, dz_fail))
print("ROT  OK:{} FAIL:{}".format(rot_ok_c, rot_fail))
print("MARK OK:{} FAIL:{}".format(mark_ok, mark_fail))
print("")
if dxy_fail==0 and dz_fail==0 and rot_fail==0 and mark_fail==0 and len(matches)==len(expected):
    print(">>> " + APTO_TARGET + " VALIDACIÓN EXITOSA <<<")
else:
    print(">>> " + APTO_TARGET + " CON DISCREPANCIAS - REVISAR <<<")
print("=" * 70)