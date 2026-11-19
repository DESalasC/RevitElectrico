# -*- coding: utf-8 -*-
"""COLOCAR_F01_F02_DESDE_DXF_JSON v2.38 - Fix Level + Mapeo familia + Debug"""

import json, os, math, clr, datetime
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    XYZ, Line, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
    Transaction, Level, Options, Solid, Face, Reference, LocationPoint,
    GeometryObject, PlanarFace, LocationCurve, ElementTransformUtils, UV, Parameter
)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)
print("=" * 60)
print("COLOCAR_F01_F02_DESDE_DXF_JSON v2.38 | Fix Level+Mapeo | " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S") + " (Bogotá GMT-5)")
print("=" * 60)

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
    print("[OK] " + doc.Title)

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_F01_F02_extraido.json"

def load_json(p):
    with open(p, 'r') as f:
        return json.load(f)

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

def elem_id(elem):
    if elem is None: return 0
    try:
        if hasattr(elem, 'Id'): eid_obj = elem.Id
        else: eid_obj = elem
        if hasattr(eid_obj, 'IntegerValue'): return int(eid_obj.IntegerValue)
        if hasattr(eid_obj, 'Value'): return int(eid_obj.Value)
        s = str(eid_obj)
        import re
        m = re.search(r'(\d+)', s)
        if m: return int(m.group(1))
        return int(s)
    except: return 0

def eid(val):
    return ElementId(Int64(val))

data = load_json(JSON_PATH)
f01_data = data.get('F01', {})
f02_data = data.get('F02', {})

f01_devices = [d for d in f01_data.get('devices', []) if 'familia_revit' in d]
f02_devices = [d for d in f02_data.get('devices', []) if 'familia_revit' in d]

print("F01: " + str(len(f01_devices)) + " dispositivos")
print("F02: " + str(len(f02_devices)) + " dispositivos")

# ──────────────────────────────────────────────────────────────
# 🔍 DEBUG MAPEO FAMILIA - Verificar equivalencias DXF → Revit
print("\n[DEBUG MAPEO] Verificando símbolos disponibles...")
all_symbols = {}
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol):
            fam = clean(elem.FamilyName)
            p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            typ = clean(p.AsString()) if p and p.HasValue else "SinNombre"
            all_symbols.setdefault(fam, set()).add(typ)
    except: pass

# Mostrar familias relevantes
for fam in ["M_Toma doble", "M_Comunicaciones", "M_Interruptores", "M_Pulsador - Interruptor", "M_Timbre", "M_ClimatizacionV", "M_Iluminacion", "EA"]:
    if fam in all_symbols:
        print("  " + fam + ": " + ", ".join(sorted(all_symbols[fam])))
    else:
        print("  " + fam + ": ❌ NO ENCONTRADA")

# ──────────────────────────────────────────────────────────────
# LEVEL PISO 5
PISO5_LEVEL = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    name = lvl.Name if hasattr(lvl, 'Name') else ""
    if any(kw in name.upper() for kw in ['PISO 5', 'NIVEL 5', 'LEVEL 5', 'P5', 'N5']):
        PISO5_LEVEL = lvl; break
if PISO5_LEVEL is None:
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if abs(lvl.Elevation - 43.37) < 0.5:
            PISO5_LEVEL = lvl; break
if PISO5_LEVEL is None:
    PISO5_LEVEL = list(FilteredElementCollector(doc).OfClass(Level).ToElements())[0]

NIVEL5_ELEV = PISO5_LEVEL.Elevation
PISO5_LEVEL_ID_INT = elem_id(PISO5_LEVEL)
NIVEL5_ELEV_M = NIVEL5_ELEV * 0.3048
print("\n[CONFIRMADO] Level: '" + PISO5_LEVEL.Name + "' Id=" + str(PISO5_LEVEL_ID_INT) + " Elev=" + str(round(NIVEL5_ELEV,2)) + "ft")

# ──────────────────────────────────────────────────────────────
# OFFSETS HARDCODEADOS PROBADOS
F01_OFF_X, F01_OFF_Y = 45.98, 26.28
F02_OFF_X, F02_OFF_Y = 45.98, 34.91
f01_off_x, f01_off_y = F01_OFF_X, F01_OFF_Y
f02_off_x, f02_off_y = F02_OFF_X, F02_OFF_Y

print("[OFFSET F01] (+" + str(f01_off_x) + ", +" + str(f01_off_y) + ") ft")
print("[OFFSET F02] (+" + str(f02_off_x) + ", +" + str(f02_off_y) + ") ft")

# ──────────────────────────────────────────────────────────────
# TECHOS
F01_CEILING_ID = 2764963
F02_CEILING_ID = 2766313

def get_ceiling_bottom_face(doc, ceiling_id):
    ceil = doc.GetElement(eid(ceiling_id))
    if not ceil: return None, None, None
    try:
        opt = Options(); opt.ComputeReferences = True
        g = ceil.get_Geometry(opt)
        if not g: return None, None, None
        for o in g:
            if not isinstance(o, Solid): continue
            for f in o.Faces:
                if not isinstance(f, PlanarFace): continue
                if f.FaceNormal.Z < -0.95:
                    bb = f.GetBoundingBox()
                    u_mid = (bb.Min.U + bb.Max.U) / 2
                    v_mid = (bb.Min.V + bb.Max.V) / 2
                    uv_mid = UV(u_mid, v_mid)
                    pt_on_face = f.Evaluate(uv_mid)
                    return f, f.Reference, pt_on_face.Z
    except: pass
    return None, None, None

f01_face, f01_face_ref, f01_face_z = get_ceiling_bottom_face(doc, F01_CEILING_ID)
f02_face, f02_face_ref, f02_face_z = get_ceiling_bottom_face(doc, F02_CEILING_ID)

print("[F01 TECHO] Z=" + str(round(f01_face_z,2)) + "ft")
print("[F02 TECHO] Z=" + str(round(f02_face_z,2)) + "ft")

# ──────────────────────────────────────────────────────────────
# LIMPIEZA AGRESIVA - Borrar TODOS los dispositivos de corridas previas en área
print("\n[LIMPIEZA] Borrando TODOS los FamilyInstance en área F01/F02...")
to_delete_ids = []
f01_xmin, f01_xmax = 30, 50
f01_ymin, f01_ymax = 0, 30
f02_xmin, f02_xmax = 30, 50
f02_ymin, f02_ymax = 30, 60

for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
    try:
        loc = fi.Location
        if not loc or not hasattr(loc, "Point"): continue
        p = loc.Point
        in_f01 = f01_xmin <= p.X <= f01_xmax and f01_ymin <= p.Y <= f01_ymax
        in_f02 = f02_xmin <= p.X <= f02_xmax and f02_ymin <= p.Y <= f02_ymax
        if in_f01 or in_f02:
            to_delete_ids.append(fi.Id)
    except: pass

if to_delete_ids:
    from System.Collections.Generic import List
    tx_del = Transaction(doc, "Borrar TODOS previos F01/F02")
    tx_del.Start()
    try:
        doc.Delete(List[ElementId](to_delete_ids))
        tx_del.Commit()
        print("[LIMPIEZA] Borradas " + str(len(to_delete_ids)) + " instancias")
    except Exception as e:
        tx_del.RollBack()
        print("[LIMPIEZA ERROR] " + str(e))
else:
    print("[LIMPIEZA] Nada que borrar")

# ──────────────────────────────────────────────────────────────
# SÍMBOLOS
def syms(doc):
    d={}
    for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
        try:
            if isinstance(elem, FamilySymbol):
                fam = clean(elem.FamilyName)
                p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                typ = clean(p.AsString()) if p and p.HasValue else "SinNombre"
                d[(fam, typ)] = elem
        except: pass
    return d

def find_sym(d, fam, typ):
    fam = clean(fam); typ = clean(typ)
    if (fam, typ) in d: return d[(fam, typ)]
    # Búsqueda flexible
    for (f, t), s in d.items():
        if f == fam and (t == typ or typ in t or t in typ): return s
    for (f, t), s in d.items():
        if f == fam: return s
    return None

S = syms(doc)
print("[DEBUG] Símbolos cargados: " + str(len(S)))

# ──────────────────────────────────────────────────────────────
# CLASIFICACIÓN Y ALTURAS
CEILING_BASED_TECHO = {"M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point", "M_Timbre"}
FACE_BASED_MURO_ONLY = {"M_Pulsador - Interruptor"}

ALTURAS_M = {
    "M_Toma doble": 0.30, "M_Comunicaciones": 0.30, "M_Interruptores": 1.10,
    "M_Pulsador - Interruptor": 1.10, "M_Timbre": 2.40, "EA": 1.90,
    "M_ClimatizacionV": 2.40, "M_Iluminacion": 2.60, "Consolidation_Point": 2.70,
}

FPM = 3.280839895
def m_a_ft(m): return m * FPM

# ──────────────────────────────────────────────────────────────
# MUROS
walls = []
all_walls = list(FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements())
for w in all_walls:
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id_int = elem_id(bp.AsElementId()) if bp and bp.HasValue else 0
    lvl_id_int = elem_id(w.LevelId)
    if bp_id_int == PISO5_LEVEL_ID_INT or lvl_id_int == PISO5_LEVEL_ID_INT:
        if w.Location: walls.append(w)
print("[DEBUG] Muros Piso 5: " + str(len(walls)))

# ──────────────────────────────────────────────────────────────
# DUPLICADOS - Umbral más estricto
def existe_instancia_cercana(doc, px_ft, py_ft, umbral_ft):
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            loc = fi.Location
            if not loc or not hasattr(loc, "Point"): continue
            p = loc.Point
            if math.hypot(p.X - px_ft, p.Y - py_ft) < umbral_ft:
                return True
        except: continue
    return False

UMBRAL_DUP_FT = m_a_ft(0.05)  # 5cm en lugar de 10cm

# ──────────────────────────────────────────────────────────────
# PROYECCIÓN TECHO ROBUSTA
def project_on_ceiling_face_robust(doc, ceiling_id, face, face_ref, face_z, x, y):
    if not face or not face_ref: return None, None, False
    try:
        bb = face.GetBoundingBox()
        pt_above = XYZ(x, y, face_z + 10)
        res = face.Project(pt_above)
        if res:
            uv = res.UVPoint
            u_clamped = max(bb.Min.U, min(bb.Max.U, uv.U))
            v_clamped = max(bb.Min.V, min(bb.Max.V, uv.V))
            uv_clamped = UV(u_clamped, v_clamped)
            pt_on_face = face.Evaluate(uv_clamped)
            return pt_on_face, uv_clamped, True
    except: pass
    try:
        ceil = doc.GetElement(eid(ceiling_id))
        if ceil:
            opt = Options()
            g = ceil.get_Geometry(opt)
            if g:
                for o in g:
                    if isinstance(o, Solid):
                        bbox3d = o.GetBoundingBox()
                        if bbox3d:
                            u_range = bb.Max.U - bb.Min.U
                            v_range = bb.Max.V - bb.Min.V
                            x_range = bbox3d.Max.X - bbox3d.Min.X
                            y_range = bbox3d.Max.Y - bbox3d.Min.Y
                            if x_range > 0 and y_range > 0:
                                u_frac = (x - bbox3d.Min.X) / x_range
                                v_frac = (y - bbox3d.Min.Y) / y_range
                                u_mapped = bb.Min.U + u_frac * u_range
                                v_mapped = bb.Min.V + v_frac * v_range
                                u_clamped = max(bb.Min.U, min(bb.Max.U, u_mapped))
                                v_clamped = max(bb.Min.V, min(bb.Max.V, v_mapped))
                                uv_clamped = UV(u_clamped, v_clamped)
                                pt_on_face = face.Evaluate(uv_clamped)
                                return pt_on_face, uv_clamped, True
    except: pass
    try:
        u_center = (bb.Min.U + bb.Max.U) / 2
        v_center = (bb.Min.V + bb.Max.V) / 2
        uv_center = UV(u_center, v_center)
        pt_on_face = face.Evaluate(uv_center)
        return pt_on_face, uv_center, True
    except: pass
    return None, None, False

# ──────────────────────────────────────────────────────────────
# BUSCAR CARA MURO
def find_wall_face_at_z(doc, walls, target_x, target_y, target_z_ft):
    best = None; best_dist = float('inf')
    target_pt = XYZ(target_x, target_y, target_z_ft)
    for w in walls:
        try:
            opt = Options(); opt.ComputeReferences = True
            geom = w.get_Geometry(opt)
            if not geom: continue
            for obj in geom:
                if not isinstance(obj, Solid): continue
                for face in obj.Faces:
                    if not isinstance(face, PlanarFace): continue
                    if abs(face.FaceNormal.Z) > 0.1: continue
                    proj = face.Project(target_pt)
                    if not proj: continue
                    uv = proj.UVPoint
                    bb = face.GetBoundingBox()
                    if bb.Min.U <= uv.U <= bb.Max.U and bb.Min.V <= uv.V <= bb.Max.V:
                        pt_on_face = face.Evaluate(uv)
                        d = target_pt.DistanceTo(pt_on_face)
                        if d < best_dist:
                            best_dist = d; best = (face, w, pt_on_face, face.FaceNormal)
        except: continue
    return best

# ──────────────────────────────────────────────────────────────
# 🔑 SET LEVEL - VERSIÓN ROBUSTA
def set_level_parameter(inst, level):
    """Intenta múltiples parámetros de level"""
    param_names = [
        BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
        BuiltInParameter.LEVEL_PARAM,
        BuiltInParameter.FAMILY_LEVEL_PARAM
    ]
    for bp in param_names:
        try:
            p = inst.get_Parameter(bp)
            if p and not p.IsReadOnly:
                p.Set(level.Id)
                return True, bp.ToString()
        except: pass
    return False, "FAILED"

HORIZONTAL_DIR = XYZ(1, 0, 0)

# ──────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL CON DEBUG MAPEO
def place_device(doc, dev, s, x_abs, y_abs, rot, h_m, target_z_ft, apto_name, ceiling_id, face, face_ref, face_z, walls):
    fam = dev['familia_revit']
    dxf_name = dev.get('name', '')
    dxf_handle = dev.get('handle', '')
    
    # ─── CEILING-BASED: FB-TECHO
    if fam in CEILING_BASED_TECHO and face and face_ref and face_z:
        pt_on_face, uv, success = project_on_ceiling_face_robust(doc, ceiling_id, face, face_ref, face_z, x_abs, y_abs)
        if success and pt_on_face:
            if not s.IsActive: s.Activate()
            try:
                inst = doc.Create.NewFamilyInstance(face_ref, pt_on_face, HORIZONTAL_DIR, s)
                level_ok, param_used = set_level_parameter(inst, PISO5_LEVEL)
                host_id = elem_id(inst.Host.Id) if inst.Host else -1
                host_ok = "✅" if host_id == ceiling_id else "⚠️ Host=" + str(host_id)
                print("  [FB-TECHO] " + dxf_name + "(" + dxf_handle + ") " + fam + " -> Techo " + str(ceiling_id) + " " + host_ok + " Z=" + str(round(pt_on_face.Z,2)) + " Level=" + ("OK(" + param_used + ")" if level_ok else "FAIL"))
                return inst, "FB-TECHO-" + apto_name, pt_on_face.Z
            except Exception as e:
                print("  [FB-TECHO ERR] " + dxf_name + ": " + str(e))
    
    # ─── FB-MURO: Solo Pulsador/Timbre
    if fam in FACE_BASED_MURO_ONLY and walls:
        res = find_wall_face_at_z(doc, walls, x_abs, y_abs, target_z_ft)
        if res:
            face_w, wall, pt_on_face, normal = res
            if not s.IsActive: s.Activate()
            try:
                inst = doc.Create.NewFamilyInstance(face_w.Reference, pt_on_face, HORIZONTAL_DIR, s)
                level_ok, param_used = set_level_parameter(inst, PISO5_LEVEL)
                print("  [FB-MURO] " + dxf_name + "(" + dxf_handle + ") " + fam + " -> Muro Z=" + str(round(pt_on_face.Z,2)) + " Level=" + ("OK(" + param_used + ")" if level_ok else "FAIL"))
                return inst, "FB-MURO", pt_on_face.Z
            except Exception as e:
                print("  [FB-MURO ERR] " + dxf_name + ": " + str(e))
    
    # ─── LB-Z-ABS: Todo lo demás
    pt = XYZ(x_abs, y_abs, target_z_ft)
    if not s.IsActive: s.Activate()
    try:
        inst = doc.Create.NewFamilyInstance(pt, s, StructuralType.NonStructural)
        level_ok, param_used = set_level_parameter(inst, PISO5_LEVEL)
        
        rotation = rot
        ang = (rotation + 90) % 360
        if abs(ang) > 0.1:
            try:
                ax = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z+1))
                inst.Location.Rotate(ax, math.radians(ang))
            except: pass
        
        print("  [LB-Z-ABS] " + dxf_name + "(" + dxf_handle + ") " + fam + "/" + dev['tipo_revit'] + " Z=" + str(round(target_z_ft,2)) + " Level=" + ("OK(" + param_used + ")" if level_ok else "FAIL"))
        return inst, "LB-Z-ABS", target_z_ft
    except Exception as e:
        return None, "ERR: " + str(e), 0

# ──────────────────────────────────────────────────────────────
for apto_name, devices, off_x, off_y, ceiling_id, face, face_ref, face_z in [
    ("F01", f01_devices, f01_off_x, f01_off_y, F01_CEILING_ID, f01_face, f01_face_ref, f01_face_z),
    ("F02", f02_devices, f02_off_x, f02_off_y, F02_CEILING_ID, f02_face, f02_face_ref, f02_face_z),
]:
    if not devices: continue
    
    if not face_z:
        print("⚠️ " + apto_name + ": Sin cara techo válida")
    
    print("\n===== " + apto_name + " (Techo Id=" + str(ceiling_id) + ", Cara Z=" + str(round(face_z,2) if face_z else 0) + "ft) =====")
    ok = er = saltados = 0
    tx = Transaction(doc, "Colocar " + apto_name + " v2.38")
    tx.Start()
    try:
        for i, dev in enumerate(devices, 1):
            fam = dev['familia_revit']; typ = dev['tipo_revit']
            s = find_sym(S, fam, typ)
            if not s:
                print("[" + str(i) + "] " + fam + "/" + typ + " -> NO SYM"); er += 1; continue
            
            x_abs = dev['x'] * FPM + off_x
            y_abs = dev['y'] * FPM + off_y
            rot = dev.get('rotation', 0)
            
            h_m = ALTURAS_M.get(fam, 0.30)
            
            if existe_instancia_cercana(doc, x_abs, y_abs, UMBRAL_DUP_FT):
                print("  [DUP] " + dev['name'] + "(" + dev.get('handle','') + ") -> SALTADO"); saltados += 1; continue
            
            target_z_ft = NIVEL5_ELEV + m_a_ft(h_m)
            
            inst, method, z_final = place_device(doc, dev, s, x_abs, y_abs, rot, h_m, target_z_ft, apto_name, ceiling_id, face, face_ref, face_z, walls)
            
            if inst:
                uid = inst.UniqueId
                print("[" + str(i) + "] " + dev['name'] + "(" + dev.get('handle','') + ") @ XY=(" + str(round(x_abs,2)) + "," + str(round(y_abs,2)) + ") ft Z=" + str(round(z_final,2)) + "ft -> OK id=" + str(elem_id(inst)) + " " + method + " UID=" + uid[:8])
                ok += 1
            else:
                print("[" + str(i) + "] " + dev['name'] + " -> " + method); er += 1
        tx.Commit()
    except Exception as e:
        tx.RollBack(); print("[TXN ERR] " + str(e))
    print(apto_name + " -> OK:" + str(ok) + " SALTADOS:" + str(saltados) + " ERR:" + str(er))

print("\n=== LISTO v2.38 ===")
print("Fixes: SetLevel robusto (3 params), Umbral DUP 5cm, Debug mapeo familia, Limpieza agresiva")
