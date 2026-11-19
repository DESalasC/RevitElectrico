# -*- coding: utf-8 -*-
"""
COLOCAR_APTO_INDIVIDUAL_v01.py - 2026-11-19 - IronPython 2.7 para pyRevit
Coloca UN apartamento del JSON maestro global con LOG DETALLADO por dispositivo.
Uso: Cambiar APTO_TARGET = "F01" / "F02" / "E07" / etc.
"""

import json, os, math, clr, datetime, sys
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    XYZ, UV, Line, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
    Transaction, Level, Options, Solid, Face, Reference,
    PlanarFace, ElementTransformUtils
)
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
MODE = cfg.get('mode', 'place')

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"

# TECHOS POR APARTAMENTO (del inventario global 2026-11-18)
CEILING_IDS = {
    "F01": 2764963, "F02": 2766313,
    "F17": 5094834, "F18": 3103282,
    "E06": 2766255, "E07": 3170680, "E08": 3171021,
    "D13": 3101674, "C14": 5094752,
    "B15": 2281234, "B16": 2281303,
}

TARGET_LEVEL_NAMES = ["PISO 5", "NIVEL 5", "LEVEL 5", "P5", "N5"]
TARGET_LEVEL_ELEV = 43.37

# ════════════════════════════════════════════════════════════════
# CLASIFICACIÓN
# ════════════════════════════════════════════════════════════════
FACE_BASED_MURO = {"M_Pulsador - Interruptor"}
CEILING_BASED_TECHO = {"M_Iluminacion", "Consolidation_Point"}
CEILING_WITH_OFFSET = {"M_ClimatizacionV", "M_Timbre"}
LB_Z_ABS_ONLY = {"M_Toma doble", "M_Comunicaciones", "M_Interruptores", "EA"}

ALTURAS_MONTAJE_M = {
    "M_Toma doble": 0.30, "M_Comunicaciones": 0.30,
    "M_Interruptores": 1.10, "M_Pulsador - Interruptor": 1.10,
    "M_Timbre": 2.40, "EA": 1.90,
    "M_ClimatizacionV": 2.40, "M_Iluminacion": 2.60, "Consolidation_Point": 2.70,
}

Z_CORRECTION_M = {
    "M_Toma doble": +0.025, "M_Comunicaciones": +0.025,
    "M_Interruptores": 0.0, "M_Pulsador - Interruptor": 0.0,
    "M_Timbre": 0.0, "M_ClimatizacionV": 0.0, "EA": 0.0,
    "M_Iluminacion": 0.0, "Consolidation_Point": 0.0,
}

CEILING_OFFSET_FT = {"M_ClimatizacionV": -0.65, "M_Timbre": -0.65}
ROTATE_FAMILIES = {"M_Toma doble", "M_Comunicaciones"}

# ════════════════════════════════════════════════════════════════
HORIZONTAL_DIR = XYZ(1, 0, 0)
exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)
FPM = 3.280839895
def m_a_ft(m): return m * FPM
def log(msg): print(msg)
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
def eid(val): return ElementId(Int64(val))
def load_json(p):
    with open(p, 'r') as f: return json.load(f)

# ════════════════════════════════════════════════════════════════
# TECHO: Cara inferior + bounds globales
# ════════════════════════════════════════════════════════════════
def get_ceiling_bottom_face_data(doc, ceiling_id):
    ceil = doc.GetElement(eid(ceiling_id))
    if not ceil: return None
    opt = Options(); opt.ComputeReferences = True
    g = ceil.get_Geometry(opt)
    if not g: return None
    for obj in g:
        if isinstance(obj, Solid):
            bottom_face = None
            for f in obj.Faces:
                if isinstance(f, PlanarFace) and f.FaceNormal.Z < -0.9:
                    bottom_face = f; break
            if bottom_face:
                bb_uv = bottom_face.GetBoundingBox()
                corners_uv = [UV(bb_uv.Min.U, bb_uv.Min.V), UV(bb_uv.Min.U, bb_uv.Max.V),
                              UV(bb_uv.Max.U, bb_uv.Min.V), UV(bb_uv.Max.U, bb_uv.Max.V)]
                global_pts = [bottom_face.Evaluate(uv) for uv in corners_uv]
                xs = [p.X for p in global_pts]; ys = [p.Y for p in global_pts]; zs = [p.Z for p in global_pts]
                return {"ceiling_id": ceiling_id, "face": bottom_face, "face_ref": bottom_face.Reference,
                        "face_z": sum(zs)/4.0,
                        "global_bounds": {"xmin": min(xs), "xmax": max(xs), "ymin": min(ys), "ymax": max(ys),
                                          "zmin": min(zs), "zmax": max(zs)},
                        "center_global": XYZ(sum(xs)/4, sum(ys)/4, sum(zs)/4)}
    return None

def project_on_ceiling_clamped(doc, face_data, x, y, z_above=10.0):
    face = face_data["face"]; face_ref = face_data["face_ref"]; gb = face_data["global_bounds"]
    margin = 0.01
    x_clamped = max(gb["xmin"]+margin, min(gb["xmax"]-margin, x))
    y_clamped = max(gb["ymin"]+margin, min(gb["ymax"]-margin, y))
    clamped = (x_clamped != x or y_clamped != y)
    if clamped: log("    [CLAMP] ({:.2f},{:.2f}) -> ({:.2f},{:.2f}) Y[{:.2f},{:.2f}]".format(x, y, x_clamped, y_clamped, gb["ymin"], gb["ymax"]))
    pt_above = XYZ(x_clamped, y_clamped, face_data["face_z"] + z_above)
    proj = face.Project(pt_above)
    if proj:
        uv = proj.UVPoint; bb = face.GetBoundingBox()
        u_clamped = max(bb.Min.U, min(bb.Max.U, uv.U))
        v_clamped = max(bb.Min.V, min(bb.Max.V, uv.V))
        pt_on_face = face.Evaluate(UV(u_clamped, v_clamped))
        return pt_on_face, UV(u_clamped, v_clamped), True, "PROJECT+CLAMP" if clamped else "PROJECT"
    bb = face.GetBoundingBox()
    pt_on_face = face.Evaluate(UV((bb.Min.U+bb.Max.U)/2, (bb.Min.V+bb.Max.V)/2))
    return pt_on_face, UV((bb.Min.U+bb.Max.U)/2, (bb.Min.V+bb.Max.V)/2), True, "CENTER_FALLBACK"

# ════════════════════════════════════════════════════════════════
# FB-MURO: Buscar cara de muro
# ════════════════════════════════════════════════════════════════
def compute_wall_direction(face_normal, rotation_deg):
    nx, ny = face_normal.X, face_normal.Y
    base_dir = XYZ(-ny, nx, 0)
    ang = math.radians(rotation_deg)
    cos_a = math.cos(ang); sin_a = math.sin(ang)
    dir_x = base_dir.X * cos_a - base_dir.Y * sin_a
    dir_y = base_dir.X * sin_a + base_dir.Y * cos_a
    return XYZ(dir_x, dir_y, 0)

def find_wall_face_for_pulsador(doc, walls, target_x, target_y, target_z_ft):
    target_pt = XYZ(target_x, target_y, target_z_ft)
    best = None; best_dist = float('inf'); best_strat = ""
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
                    try:
                        proj = face.Project(target_pt)
                        if proj:
                            uv = proj.UVPoint; bb = face.GetBoundingBox()
                            if bb.Min.U <= uv.U <= bb.Max.U and bb.Min.V <= uv.V <= bb.Max.V:
                                pt_on_face = face.Evaluate(uv)
                                d = target_pt.DistanceTo(pt_on_face)
                                if d < best_dist:
                                    best_dist = d; best = (face, w, pt_on_face, face.FaceNormal); best_strat = "DIRECT_PROJECT"
                    except: pass
        except: continue
    if best: return best[0], best[1], best[2], best[3], best_strat
    return None, None, None, None, "NOT_FOUND"

# ════════════════════════════════════════════════════════════════
# Parámetro OFFSET + MARK
# ════════════════════════════════════════════════════════════════
def find_and_set_offset_parameter(inst, offset_ft):
    if offset_ft == 0: return True, "none", 0
    builtin_names = ["INSTANCE_FREE_HOST_OFFSET_PARAM", "INSTANCE_HEAD_OFFSET_PARAM",
                     "INSTANCE_BASE_OFFSET_PARAM", "LEVEL_OFFSET",
                     "ROOF_BASE_OFFSET_PARAM", "CEILING_HEIGHTABOVELEVEL_PARAM"]
    for bp_name in builtin_names:
        try:
            bp = getattr(BuiltInParameter, bp_name)
            p = inst.get_Parameter(bp)
            if p and not p.IsReadOnly and p.StorageType == 0:
                p.Set(offset_ft); return True, bp_name, offset_ft
        except: pass
    keywords = ["offset", "desplaz", "altura", "height", "elevation", "base", "head", "host"]
    for p in inst.Parameters:
        try:
            if p.IsReadOnly: continue
            if p.StorageType != 0: continue
            name_lower = p.Definition.Name.lower() if p.Definition else ""
            for kw in keywords:
                if kw in name_lower:
                    p.Set(offset_ft); return True, p.Definition.Name, offset_ft
        except: pass
    return False, "NOT_FOUND", 0

def set_mark_parameter(inst, mark_value):
    try:
        p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if p and not p.IsReadOnly:
            p.Set(mark_value); return True, "ALL_MODEL_MARK"
    except: pass
    for p in inst.Parameters:
        try:
            if p.IsReadOnly: continue
            if p.Definition.Name.lower() == "mark":
                p.Set(mark_value); return True, p.Definition.Name
        except: pass
    return False, "NOT_FOUND"

def set_level_parameter(inst, level):
    for bp in [BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
               BuiltInParameter.LEVEL_PARAM, BuiltInParameter.FAMILY_LEVEL_PARAM]:
        try:
            p = inst.get_Parameter(bp)
            if p and not p.IsReadOnly: p.Set(level.Id); return True, bp.ToString()
        except: pass
    return False, "FAILED"

# ════════════════════════════════════════════════════════════════
# MAIN - SOLO APTO_TARGET
# ════════════════════════════════════════════════════════════════
log("=" * 70)
log("COLOCAR_APTO_INDIVIDUAL_v01 - " + APTO_TARGET)
log("Ejecutado: " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S"))
log("=" * 70)

doc = None
try: doc = __revit__.ActiveUIDocument.Document
except:
    try:
        from pyrevit import revit; doc = revit.doc
    except: pass
if not doc: log("[ERROR] No documento"); sys.exit()
log("[OK] " + doc.Title)

# 1. CARGAR JSON
data = load_json(JSON_PATH)
apto_data = data.get('apartamentos', {}).get(APTO_TARGET, {})
devices = apto_data.get('devices', [])
panel = apto_data.get('panel_name', '')

if not devices:
    log("[ERROR] " + APTO_TARGET + " sin dispositivos"); sys.exit()

log("\n[JSON] " + APTO_TARGET + " (Panel: " + panel + ") - " + str(len(devices)) + " dispositivos")

# 2. LEVEL
PISO5_LEVEL = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    name = lvl.Name if hasattr(lvl, 'Name') else ""
    if any(kw in name.upper() for kw in TARGET_LEVEL_NAMES): PISO5_LEVEL = lvl; break
if not PISO5_LEVEL:
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if abs(lvl.Elevation - TARGET_LEVEL_ELEV) < 0.5: PISO5_LEVEL = lvl; break
NIVEL5_ELEV = PISO5_LEVEL.Elevation
PISO5_LEVEL_ID_INT = elem_id(PISO5_LEVEL)
log("[LEVEL] '" + PISO5_LEVEL.Name + "' Id=" + str(PISO5_LEVEL_ID_INT) + " Elev=" + str(round(NIVEL5_ELEV,4)) + "ft")

# 3. TECHO
cid = CEILING_IDS.get(APTO_TARGET, 0)
if cid == 0:
    log("[ERROR] " + APTO_TARGET + " SIN TECHO ID"); sys.exit()
fd = get_ceiling_bottom_face_data(doc, cid)
if not fd:
    log("[ERROR] " + APTO_TARGET + " techo " + str(cid) + " sin cara inferior"); sys.exit()
gb = fd["global_bounds"]; c = fd["center_global"]
log("[TECHO " + APTO_TARGET + " Id=" + str(cid) + "] Centro=({:.2f},{:.2f},{:.2f}) Bounds Y=[{:.2f},{:.2f}] Z={:.2f}".format(
    c.X, c.Y, c.Z, gb["ymin"], gb["ymax"], fd["face_z"]))

# 4. MUROS
walls = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id_int = elem_id(bp.AsElementId()) if bp and bp.HasValue else 0
    lvl_id_int = elem_id(w.LevelId)
    if (bp_id_int == PISO5_LEVEL_ID_INT or lvl_id_int == PISO5_LEVEL_ID_INT) and w.Location:
        walls.append(w)
log("[MUROS] Piso 5: " + str(len(walls)))

# 5. SÍMBOLOS
S = {}
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol):
            fam = clean(elem.FamilyName)
            p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            typ = clean(p.AsString()) if p and p.HasValue else "SinNombre"
            S[(fam, typ)] = elem
    except: pass
log("[SÍMBOLOS] " + str(len(S)))

def find_sym(fam, typ):
    fam = clean(fam); typ = clean(typ)
    if (fam, typ) in S: return S[(fam, typ)]
    for (f, t), s in S.items():
        if f == fam and (t == typ or typ in t or t in typ): return s
    for (f, t), s in S.items():
        if f == fam: return s
    return None

# 6. LIMPIEZA SOLO ÁREA APTO_TARGET (bounds específicos)
APTO_BOUNDS = {
    "F01": {"xmin":25,"xmax":55,"ymin":-5,"ymax":40}, "F02": {"xmin":25,"xmax":55,"ymin":25,"ymax":65},
    "F17": {"xmin":-70,"xmax":-40,"ymin":-5,"ymax":40}, "F18": {"xmin":-70,"xmax":-40,"ymin":25,"ymax":65},
    "E06": {"xmin":-15,"xmax":15,"ymin":25,"ymax":65}, "E07": {"xmin":-150,"xmax":-110,"ymin":-5,"ymax":40},
    "E08": {"xmin":-150,"xmax":-110,"ymin":25,"ymax":65}, "D13": {"xmin":-110,"xmax":-80,"ymin":25,"ymax":65},
    "C14": {"xmin":-110,"xmax":-80,"ymin":-5,"ymax":40}, "B15": {"xmin":-180,"xmax":-140,"ymin":-5,"ymax":40},
    "B16": {"xmin":-180,"xmax":-140,"ymin":25,"ymax":65},
}
bounds = APTO_BOUNDS.get(APTO_TARGET, {"xmin":-200,"xmax":200,"ymin":-200,"ymax":200})

log("\n[LIMPIEZA] " + APTO_TARGET + " bounds X[{},{}] Y[{},{}]".format(bounds["xmin"],bounds["xmax"],bounds["ymin"],bounds["ymax"]))
to_delete = []
for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
    try:
        loc = fi.Location
        if not loc or not hasattr(loc, "Point"): continue
        p = loc.Point
        if bounds["xmin"] <= p.X <= bounds["xmax"] and bounds["ymin"] <= p.Y <= bounds["ymax"]:
            to_delete.append(fi.Id)
    except: pass
if to_delete:
    from System.Collections.Generic import List
    tx_del = Transaction(doc, "Limpiar " + APTO_TARGET); tx_del.Start()
    try: doc.Delete(List[ElementId](to_delete)); tx_del.Commit(); log("[LIMPIEZA] " + str(len(to_delete)) + " borradas")
    except Exception as e: tx_del.RollBack(); log("[LIMPIEZA ERR] " + str(e))
else: log("[LIMPIEZA] Nada")

# 7. DUPLICADOS
def existe_cercano(doc, px, py, umbral):
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            loc = fi.Location
            if not loc or not hasattr(loc, "Point"): continue
            p = loc.Point
            if math.hypot(p.X - px, p.Y - py) < umbral: return True
        except: continue
    return False
UMBRAL_DUP = m_a_ft(0.05)

# ════════════════════════════════════════════════════════════════
# COLOCAR DISPOSITIVOS CON LOG DETALLADO
# ════════════════════════════════════════════════════════════════
ok = er = saltados = 0
tx = Transaction(doc, "Colocar " + APTO_TARGET); tx.Start()
try:
    for i, dev in enumerate(devices, 1):
        fam = dev['familia_revit']; typ = dev['tipo_revit']
        s = find_sym(fam, typ)
        if not s:
            log("[" + str(i) + "/" + str(len(devices)) + "] " + fam + "/" + typ + " -> NO SYMBOL"); er += 1; continue
        
        x_abs = dev['x']; y_abs = dev['y']; rot = dev.get('rotation', 0)
        mark_value = dev.get('mark', APTO_TARGET + "|" + panel)
        dxf_name = dev.get('name', '')
        
        h_montaje_m = ALTURAS_MONTAJE_M.get(fam, 0.30)
        z_corr_m = Z_CORRECTION_M.get(fam, 0.0)
        h_effective_m = h_montaje_m + z_corr_m
        
        if existe_cercano(doc, x_abs, y_abs, UMBRAL_DUP):
            log("[" + str(i) + "] " + dxf_name + " -> DUPLICADO (saltado)"); saltados += 1; continue
        
        target_z_ft = NIVEL5_ELEV + m_a_ft(h_effective_m)
        
        log("[" + str(i) + "/" + str(len(devices)) + "] " + dxf_name)
        log("  Familia: " + fam + " / Tipo: " + typ + " | Mark: " + mark_value)
        log("  XY Global: ({:.3f}, {:.3f}) ft | Rot DXF: {}°".format(x_abs, y_abs, rot))
        if z_corr_m != 0: log("  Z_corr: montaje={:.3f}m corr={:.3f}m -> effective={:.4f}m".format(h_montaje_m, z_corr_m, h_effective_m))
        
        placed = False; z_final = target_z_ft; method = ""; inst = None
        
        # 1. FB-MURO
        if fam in FACE_BASED_MURO and walls:
            face_w, wall, pt_on_face, face_normal, strat = find_wall_face_for_pulsador(doc, walls, x_abs, y_abs, target_z_ft)
            if face_w and pt_on_face:
                if not s.IsActive: s.Activate()
                try:
                    direction = compute_wall_direction(face_normal, rot)
                    inst = doc.Create.NewFamilyInstance(face_w.Reference, pt_on_face, direction, s)
                    set_level_parameter(inst, PISO5_LEVEL)
                    z_final = pt_on_face.Z
                    method = "FB-MURO-" + APTO_TARGET + "/" + strat
                    log("  [FB-MURO/" + strat + "] Muro " + str(elem_id(wall.Id)) + " Z={:.4f} rot={}°".format(z_final, rot))
                    placed = True
                except Exception as e: log("  [FB-MURO ERR] " + str(e))
            else: log("  [FB-MURO FALLÓ] " + strat)
        
        # 2. FB-TECHO (luces, CP)
        if not placed and fam in CEILING_BASED_TECHO:
            pt_on_face, uv, success, strat = project_on_ceiling_clamped(doc, fd, x_abs, y_abs)
            if success and pt_on_face:
                if not s.IsActive: s.Activate()
                try:
                    inst = doc.Create.NewFamilyInstance(fd["face_ref"], pt_on_face, HORIZONTAL_DIR, s)
                    set_level_parameter(inst, PISO5_LEVEL)
                    host_id = elem_id(inst.Host.Id) if inst.Host else -1
                    host_ok = "OK" if host_id == fd["ceiling_id"] else "WRONG_HOST"
                    z_final = pt_on_face.Z
                    method = "FB-TECHO-" + APTO_TARGET + "/" + strat
                    log("  [FB-TECHO/" + strat + "] Techo " + str(fd["ceiling_id"]) + " " + host_ok + " Z={:.4f}".format(z_final))
                    placed = True
                except Exception as e: log("  [FB-TECHO ERR] " + str(e))
            else: log("  [FB-TECHO FALLÓ] " + strat)
        
        # 3. FB-TECHO OFFSET (ClimatizacionV, Timbre)
        if not placed and fam in CEILING_WITH_OFFSET:
            pt_on_face, uv, success, strat = project_on_ceiling_clamped(doc, fd, x_abs, y_abs)
            if success and pt_on_face:
                if not s.IsActive: s.Activate()
                try:
                    inst = doc.Create.NewFamilyInstance(fd["face_ref"], pt_on_face, HORIZONTAL_DIR, s)
                    set_level_parameter(inst, PISO5_LEVEL)
                    offset_ft = CEILING_OFFSET_FT.get(fam, 0)
                    if offset_ft != 0:
                        found, param_name, val = find_and_set_offset_parameter(inst, offset_ft)
                        if found:
                            z_final = pt_on_face.Z + offset_ft
                            log("  [OFFSET PARAM] " + param_name + " = {:.3f}ft -> Z_real={:.4f}ft".format(val, z_final))
                        else:
                            log("  [MOVE ELEMENT FALLBACK]")
                            ElementTransformUtils.MoveElement(doc, inst.Id, XYZ(0, 0, offset_ft))
                            z_final = pt_on_face.Z + offset_ft
                            log("  [MOVE] Z_techo={:.4f} -> Z_real={:.4f}ft".format(pt_on_face.Z, z_final))
                    else: z_final = pt_on_face.Z
                    method = "FB-TECHO-OFFSET-" + APTO_TARGET + "/" + strat
                    log("  [FB-TECHO/" + strat + "] Techo " + str(fd["ceiling_id"]) + " Z={:.4f}".format(z_final))
                    placed = True
                except Exception as e: log("  [FB-TECHO-OFFSET ERR] " + str(e))
            else: log("  [FB-TECHO-OFFSET FALLÓ] " + strat)
        
        # 4. LB-Z-ABS
        if not placed:
            pt = XYZ(x_abs, y_abs, target_z_ft)
            if not s.IsActive: s.Activate()
            try:
                inst = doc.Create.NewFamilyInstance(pt, s, StructuralType.NonStructural)
                set_level_parameter(inst, PISO5_LEVEL)
                
                if fam in ROTATE_FAMILIES:
                    ang = (rot + 90) % 360
                    if abs(ang) > 0.1:
                        try:
                            ax = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1))
                            inst.Location.Rotate(ax, math.radians(ang))
                            log("  [ROT +90°] applied: {}°".format(ang))
                        except Exception as e_rot: log("  [ROT WARN] rot={}° falló: {}".format(ang, e_rot))
                
                z_final = target_z_ft
                method = "LB-Z-ABS"
                log("  [LB-Z-ABS] Z={:.4f} (target={:.4f})".format(z_final, target_z_ft))
                placed = True
            except Exception as e:
                log("[" + str(i) + "] " + dxf_name + " -> ERR: " + str(e)); er += 1; continue
        
        # MARK
        if placed and inst:
            mark_ok, mark_param = set_mark_parameter(inst, mark_value)
            if mark_ok: log("  [MARK] " + mark_param + " = " + mark_value)
            else: log("  [MARK WARN] No seteado: " + mark_value)
            
            uid = inst.UniqueId
            log("  -> OK id=" + str(elem_id(inst)) + " " + method + " UID=" + uid[:8] + " MARK=" + mark_value)
            ok += 1
        elif not placed:
            log("[" + str(i) + "] " + dxf_name + " -> NO PLACED"); er += 1
    
    tx.Commit()
except Exception as e:
    tx.RollBack()
    log("[TXN ERR] " + str(e))
    import traceback; traceback.print_exc()

log("\n" + "=" * 70)
log(APTO_TARGET + " COMPLETADO")
log("OK: " + str(ok) + " | ERR: " + str(er) + " | SALT: " + str(saltados) + " / " + str(len(devices)))
log("Mark seteado: Apto|Panel = " + APTO_TARGET + "|" + panel)
log("=" * 70)