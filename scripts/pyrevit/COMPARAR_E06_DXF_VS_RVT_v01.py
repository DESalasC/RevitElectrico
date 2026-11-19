# -*- coding: utf-8 -*-
"""
COMPARAR_E06_DXF_VS_RVT_v01.py - IronPython 2.7 para pyRevit
Compara dispositivo por dispositivo: JSON maestro (DXF) vs Revit real
"""

import json, math, clr, datetime, sys
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, BuiltInCategory, FilteredElementCollector, FamilyInstance, LocationPoint, Level, BuiltInParameter)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"
APTO_TARGET = "E06"

METER_TO_FOOT = 3.280839895
FOOT_TO_METER = 1.0 / METER_TO_FOOT
NIVEL5_ELEV_FT = 43.37

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

exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)

doc = None
try: doc = __revit__.ActiveUIDocument.Document
except:
    try:
        from pyrevit import revit; doc = revit.doc
    except: pass
if not doc: print("[ERROR] No documento"); sys.exit()

print("=" * 90)
print("COMPARACION E06: DXF (JSON maestro) vs RVT (CENTRAL-V01)")
print("Ejecutado: " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 90)

# 1. CARGAR JSON MAESTRO - E06
maestro = load_json(JSON_PATH)
apto_data = maestro.get('apartamentos', {}).get(APTO_TARGET, {})
devices_dxf = apto_data.get('devices', [])
panel_name = apto_data.get('panel_name', 'TE 06')
base_x = apto_data.get('base_x_ft', 0)
base_y = apto_data.get('base_y_ft', 0)

print("\n[DXF] E06 - Panel: {} | Base apartamento: ({:.2f}, {:.2f}) ft".format(panel_name, base_x, base_y))
print("       {} dispositivos en JSON".format(len(devices_dxf)))

print("\n--- DISPOSITIVOS DXF (JSON MAESTRO) ---")
for i, d in enumerate(devices_dxf, 1):
    mark = d.get('mark', 'E06|TE 06')
    name = d.get('name','')[:24]
    fam = d.get('familia_revit','')[:21]
    typ = d.get('tipo_revit','')[:11]
    x = d['x']; y = d['y']; rot = d.get('rotation', 0)
    # Usar str() para rot para evitar problemas de formato
    print("#{:<3} {:<25} {:<22} {:<12} X={:>9.3f} Y={:>9.3f} Rot={:>6} Mark={}".format(i, name, fam, typ, x, y, str(rot), mark))

# 2. RECOLECTAR RVT - AREA E06
cats = [BuiltInCategory.OST_ElectricalEquipment, BuiltInCategory.OST_ElectricalFixtures,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_DataDevices,
        BuiltInCategory.OST_TelephoneDevices, BuiltInCategory.OST_CommunicationDevices]

E06_X_MIN, E06_X_MAX = -20.0, 30.0
E06_Y_MIN, E06_Y_MAX = 20.0, 70.0

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
        if not (E06_X_MIN <= pt.X <= E06_X_MAX and E06_Y_MIN <= pt.Y <= E06_Y_MAX): continue
        
        mark = ""
        try:
            p = fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p and p.HasValue: mark = p.AsString() or ""
            else:
                for pp in fi.Parameters:
                    if pp.Definition.Name.lower() == "mark" and pp.HasValue:
                        mark = pp.AsString() or ""
                        break
        except: pass
        
        rot = 0
        try:
            if isinstance(loc, LocationPoint):
                rot = int(round(loc.Rotation * 180.0 / math.pi)) % 360
        except: pass
        
        devices_rvt.append({
            "id": elem_id(fi),
            "family": fam,
            "type": typ,
            "pt": pt,
            "rot": rot,
            "mark": mark,
        })

print("\n--- DISPOSITIVOS RVT (EN AREA E06) ---")
print("Total encontrados: {}".format(len(devices_rvt)))
for i, d in enumerate(devices_rvt, 1):
    fam = d['family'][:29]
    typ = d['type'][:14]
    x = d['pt'].X; y = d['pt'].Y; z = d['pt'].Z
    rot = d['rot']; eid = d['id']; mk = d['mark'][:19]
    print("#{:<3} {:<30} {:<15} X={:>9.3f} Y={:>9.3f} Z={:>8.3f} Rot={:>3} Id={:<10} Mark={}".format(i, fam, typ, x, y, z, rot, eid, mk))

# 3. MATCHING
used_rvt = set()
matches = []
unmatched_dxf = []

for dxf in devices_dxf:
    fam_dxf = dxf.get('familia_revit', '')
    if not fam_dxf: continue
    best_j = None; best_dist = float('inf')
    for j, rvt in enumerate(devices_rvt):
        if j in used_rvt: continue
        if rvt['family'] != fam_dxf: continue
        d = dist_xy_m(XYZ(dxf['x'], dxf['y'], 0), rvt['pt'])
        if d < best_dist:
            best_dist = d; best_j = j
    if best_j is not None:
        used_rvt.add(best_j)
        matches.append({"dxf": dxf, "rvt": devices_rvt[best_j], "dxy_m": best_dist})
    else:
        unmatched_dxf.append(dxf)

unmatched_rvt = [devices_rvt[j] for j in range(len(devices_rvt)) if j not in used_rvt]

# 4. TABLA COMPARATIVA
print("\n" + "=" * 90)
print("TABLA COMPARATIVA: DXF vs RVT")
print("=" * 90)
for idx, m in enumerate(matches, 1):
    dxf = m['dxf']; rvt = m['rvt']
    dxy = m['dxy_m']
    mark_dxf = dxf.get('mark', 'E06|TE 06')
    mark_rvt = rvt['mark']
    if dxy <= 0.02: flag = "OK"
    elif dxy <= 0.05: flag = "WARN"
    else: flag = "FAIL"
    print("#{:<3} {:<22} {:<8} | DXF: X={:>9.3f} Y={:>9.3f} Rot={:>5} | RVT: X={:>9.3f} Y={:>9.3f} Z={:>8.3f} Rot={:>3} Id={:<6} | dXY={} {:.3f}m | Mark DXF={} RVT={}".format(
        idx, dxf.get('familia_revit','')[:21], dxf.get('tipo_revit','')[:7],
        dxf['x'], dxf['y'], str(dxf.get('rotation', 0)),
        rvt['pt'].X, rvt['pt'].Y, rvt['pt'].Z, rvt['rot'], rvt['id'],
        flag, dxy, mark_dxf[:9], mark_rvt[:9]))

for dxf in unmatched_dxf:
    print("! {:<22} {:<8} | DXF: X={:>9.3f} Y={:>9.3f} Rot={:>5} | NO MATCH EN RVT".format(
        dxf.get('familia_revit','')[:21], dxf.get('tipo_revit','')[:7],
        dxf['x'], dxf['y'], str(dxf.get('rotation', 0))))

for rvt in unmatched_rvt:
    print("+ {:<22} {:<8} | RVT: X={:>9.3f} Y={:>9.3f} Z={:>8.3f} Rot={:>3} Id={:<6} | EXTRA EN RVT | Mark={}".format(
        "(EXTRA)", rvt['type'][:7],
        rvt['pt'].X, rvt['pt'].Y, rvt['pt'].Z, rvt['rot'], rvt['id'], rvt['mark'][:9]))

# 5. PANEL
print("\n" + "=" * 90)
print("PANEL / TABLERO TE 06")
print("=" * 90)
panel_rvt = None
for fi in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType().ToElements():
    if isinstance(fi, FamilyInstance):
        name = clean(fi.Symbol.FamilyName)
        typ = ""
        p = fi.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.HasValue: typ = clean(p.AsString()) or ""
        full = name + " " + typ
        if "TE" in full.upper() or "TABLERO" in full.upper() or "PANEL" in full.upper():
            loc = fi.Location
            if isinstance(loc, LocationPoint):
                pt = loc.Point
                if E06_X_MIN <= pt.X <= E06_X_MAX and E06_Y_MIN <= pt.Y <= E06_Y_MAX:
                    panel_rvt = {"pt": pt, "name": full, "id": elem_id(fi)}
                    break

print("Panel en JSON (base apartamento): X={:.3f} Y={:.3f}".format(base_x, base_y))
if panel_rvt:
    print("Panel en RVT: {} @ X={:.3f} Y={:.3f} Z={:.3f} Id={}".format(
        panel_rvt['name'], panel_rvt['pt'].X, panel_rvt['pt'].Y, panel_rvt['pt'].Z, panel_rvt['id']))
    d_panel = dist_xy_m(XYZ(base_x, base_y, 0), panel_rvt['pt'])
    print("Diferencia panel: {:.3f}m = {:.2f}ft".format(d_panel, d_panel * METER_TO_FOOT))
else:
    print("Panel NO encontrado en RVT en area E06")

# RESUMEN
print("\n" + "=" * 90)
print("RESUMEN")
print("=" * 90)
print("DXF (JSON):     {} dispositivos".format(len(devices_dxf)))
print("RVT (area):     {} dispositivos".format(len(devices_rvt)))
print("Emparejados:    {}".format(len(matches)))
print("Solo en DXF:    {}".format(len(unmatched_dxf)))
print("Solo en RVT:    {}".format(len(unmatched_rvt)))

dxy_ok = sum(1 for m in matches if m['dxy_m'] <= 0.02)
dxy_warn = sum(1 for m in matches if 0.02 < m['dxy_m'] <= 0.05)
dxy_fail = sum(1 for m in matches if m['dxy_m'] > 0.05)
print("\ndXY <= 0.02m:   {}".format(dxy_ok))
print("dXY 0.02-0.05m: {}".format(dxy_warn))
print("dXY > 0.05m:    {}".format(dxy_fail))

familias_dxf = set(d['familia_revit'] for d in devices_dxf if d.get('familia_revit'))
familias_rvt = set(d['family'] for d in devices_rvt)
print("\nFamilias en DXF: {}".format(sorted(familias_dxf)))
print("Familias en RVT: {}".format(sorted(familias_rvt)))
print("En DXF no en RVT: {}".format(sorted(familias_dxf - familias_rvt)))
print("En RVT no en DXF: {}".format(sorted(familias_rvt - familias_dxf)))
print("=" * 90)