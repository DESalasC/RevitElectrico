# -*- coding: utf-8 -*-
"""COLOCAR_F01_F02_DESDE_DXF_JSON.py v1.3 - 2026-11-18 - IronPython 2.7 compatible (sin encoding)"""

import json, os, math, clr, datetime
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    XYZ, Line, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
    Transaction, Level, Options, Solid, Reference, LocationPoint, UV,
    Element
)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

# ──────────────────────────────────────────────────────────────
exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)
print("=" * 60)
print("COLOCAR_F01_F02_DESDE_DXF_JSON v1.3 | Ejecución: {} (Bogotá GMT-5)".format(exec_bogota.strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 60)

# ──────────────────────────────────────────────────────────────
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
    print("[ERROR] No documento")
else:
    print("[OK] {}".format(doc.Title))

# ──────────────────────────────────────────────────────────────
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_F01_F02_extraido.json"

def load_json(p):
    with open(p, 'r') as f:  # IronPython 2.7: SIN encoding=
        return json.load(f)

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

def elem_id(elem):
    if elem is None: return 0
    try:
        eid = elem.Id if hasattr(elem, 'Id') else elem
        if hasattr(eid, 'IntegerValue'): return eid.IntegerValue
        return int(eid)
    except: return 0

# ──────────────────────────────────────────────────────────────
# CARGAR JSON EXTRAÍDO
data = load_json(JSON_PATH)
f01_data = data.get('F01', {})
f02_data = data.get('F02', {})

f01_devices = [d for d in f01_data.get('devices', []) if 'familia_revit' in d]
f02_devices = [d for d in f02_data.get('devices', []) if 'familia_revit' in d]

f01_panels = f01_data.get('panels', {})
f02_panels = f02_data.get('panels', {})

print("F01: {} dispositivos, paneles: {}".format(len(f01_devices), list(f01_panels.keys())))
print("F02: {} dispositivos, paneles: {}".format(len(f02_devices), list(f02_panels.keys())))

# ──────────────────────────────────────────────────────────────
def syms(doc):
    d={}
    collector = FilteredElementCollector(doc).WhereElementIsElementType()
    for elem in collector.ToElements():
        try:
            if isinstance(elem, FamilySymbol):
                fam = clean(elem.FamilyName)
                p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                typ = clean(p.AsString()) if p and p.HasValue else "SinNombre"
                d[(fam, typ)] = elem
        except: pass
    print("[DEBUG] Símbolos cargados: {}".format(len(d)))
    return d

def panels(doc):
    d={}
    for fi in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType().ToElements():
        if not isinstance(fi,FamilyInstance): continue
        loc=fi.Location
        if not isinstance(loc,LocationPoint): continue
        pn=""
        p=fi.LookupParameter("Panel Name")
        if p and p.HasValue: pn=clean(p.AsString()) or ""
        if pn: 
            lvl_id = find_level_by_elevation(doc, 13.22)
            d[pn]={"id":elem_id(fi),"pt":loc.Point,"levelId":lvl_id}
    return d

def find_level_by_elevation(doc, target_elev, tol=0.01):
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if abs(lvl.Elevation - target_elev) < tol:
            return elem_id(lvl)
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        return elem_id(lvl)
    return 0

def ceilings(doc):
    return list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType().ToElements())

def find_sym(d,fam,typ):
    fam = clean(fam); typ = clean(typ)
    if (fam,typ) in d: return d[(fam,typ)]
    for (f,t),s in d.items():
        if f == fam and (t == typ or typ in t or t in typ):
            return s
    for (f,t),s in d.items():
        if f == fam: return s
    return None

# ──────────────────────────────────────────────────────────────
# ALTURAS POR FAMILIA
ALTURAS = {
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

CEIL_FAM = {"M_Iluminacion","M_ClimatizacionV","Consolidation_Point"}
NIVEL5_ELEV = 13.22

def place_level(doc, s, x, y, alt_mm, lvl_id, rot):
    if not s.IsActive: s.Activate()
    lv = doc.GetElement(ElementId(Int64(lvl_id)))
    if not lv: return {"status":"error","error":"No level"}
    z_abs = lv.Elevation + alt_mm / 304.8
    pt = XYZ(x, y, z_abs)
    try: inst = doc.Create.NewFamilyInstance(pt, s, lv, StructuralType.NonStructural)
    except Exception as e: return {"status":"error","error":"Level: "+str(e)}
    ang = (rot + 90) % 360
    if abs(ang) > 0.1:
        try:
            ax = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z+1))
            inst.Location.Rotate(ax, math.radians(ang))
        except: pass
    if alt_mm > 0:
        try:
            for p in inst.Parameters:
                if p.Definition.Name in ("Elevation","Offset") and not p.IsReadOnly:
                    p.Set(alt_mm/304.8); break
        except: pass
    return {"status":"ok","id":elem_id(inst)}

def place_ceiling(doc, s, x, y, z, cs):
    if not s.IsActive: s.Activate()
    best, best_a = None, float('inf')
    opt = Options(); opt.ComputeReferences = False
    for c in cs:
        try:
            g = c.get_Geometry(opt)
            if not g: continue
            for o in g:
                if not isinstance(o, Solid): continue
                for f in o.Faces:
                    try:
                        r = f.Project(XYZ(x, y, 0))
                        if not r: continue
                        uv = r.UVPoint
                        bb = f.GetBoundingBox()
                        if bb.Min.U <= uv.U <= bb.Max.U and bb.Min.V <= uv.V <= bb.Max.V:
                            a = f.Area
                            if a and a < best_a: best_a, best = a, c
                    except: continue
        except: pass
    if not best: return {"status":"error","error":"No ceiling"}
    pt = XYZ(x, y, z)
    try: inst = doc.Create.NewFamilyInstance(pt, s, best, StructuralType.NonStructural)
    except:
        try: inst = doc.Create.NewFamilyInstance(pt, s, StructuralType.NonStructural)
        except Exception as e: return {"status":"error","error":"Ceiling: "+str(e)}
    return {"status":"ok","id":elem_id(inst)}

# ──────────────────────────────────────────────────────────────
# MATCHAR PANELES DXF -> RVT
pn = panels(doc)
print("\nPaneles RVT:")
for n, p in pn.items():
    print("  {} @ ({:.2f},{:.2f})".format(n, p['pt'].X, p['pt'].Y))

# Asociar: F01 -> "TF 01", F02 -> "TF 02" (nombres reales en RVT)
f01_panel_rvt = "TF 01"
f02_panel_rvt = "TF 02"

for apto_name, devices, panel_rvt_name in [("F01", f01_devices, f01_panel_rvt), ("F02", f02_devices, f02_panel_rvt)]:
    if not devices:
        print("\n{} sin dispositivos".format(apto_name))
        continue
    
    panel_data = pn.get(panel_rvt_name)
    if not panel_data:
        print("[ERROR] Panel RVT {} no existe".format(panel_rvt_name))
        continue
    
    lvl_id = panel_data['levelId']
    panel_pt = panel_data['pt']
    print("\n===== {} =====".format(apto_name))
    print("Panel RVT: {} @ ({:.2f},{:.2f}) LevelId: {}".format(panel_rvt_name, panel_pt.X, panel_pt.Y, lvl_id))
    print("Dispositivos desde DXF: {}".format(len(devices)))
    
    S = syms(doc)
    C = ceilings(doc)
    
    ok = er = 0
    tx = Transaction(doc, "Colocar {} desde DXF".format(apto_name))
    tx.Start()
    try:
        for i, dev in enumerate(devices, 1):
            fam = dev['familia_revit']
            typ = dev['tipo_revit']
            s = find_sym(S, fam, typ)
            if not s:
                print("[{}/{}] {}/{} -> NO SYM".format(i, len(devices), fam, typ))
                er += 1
                continue
            
            # COORDENADAS EXACTAS DEL DXF (metros)
            x = dev['x']
            y = dev['y']
            rot = dev.get('rotation', 0)
            alt = ALTURAS.get(fam, 300)
            
            if fam in CEIL_FAM:
                z = NIVEL5_ELEV + alt / 1000.0
                r = place_ceiling(doc, s, x, y, z, C)
            else:
                r = place_level(doc, s, x, y, alt, lvl_id, rot)
            
            if r["status"] == "ok":
                print("[{}/{}] {} @ ({:.2f},{:.2f}) -> OK id={}".format(i, len(devices), dev['name'], x, y, r["id"]))
                ok += 1
            else:
                print("[{}/{}] {} -> ERR {}".format(i, len(devices), dev['name'], r.get("error")))
                er += 1
        tx.Commit()
    except Exception as e:
        tx.RollBack(); print("[TXN ERR]", e)
    print("{} -> OK:{} ERR:{}".format(apto_name, ok, er))

print("\n=== LISTO ===")