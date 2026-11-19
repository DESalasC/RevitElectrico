# -*- coding: utf-8 -*-
"""
COLOCAR_DISPOSITIVOS_DESDE_DXF v3.12.1 - JSON MAESTRO GLOBAL DIRECTO (FIXED)
- Fix: IronPython 2.7 enum access (BuiltInParameter string names)
- Fix: Limpieza expandida para atrapar runs previos
- Fix: Clasificación correcta (solo M_Pulsador-Interruptor -> FB-MURO)
- Fix: Rotación segura solo para familias que la necesitan
- Coordenadas globales directas del JSON maestro (SIN offsets manuales)
"""

import json, os, math, clr, datetime, sys, csv
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    XYZ, Line, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
    Transaction, Level, Options, Solid, Face, Reference,
    PlanarFace, UV, ElementTransformUtils
)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

# ════════════════════════════════════════════════════════════════
# CONFIG - JSON MAESTRO CON COORDENADAS GLOBALES
# ════════════════════════════════════════════════════════════════

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global.json"

CEILING_IDS = {
    "F01": 2764963,
    "F02": 2766313,
}

# LIMPIEZA EXPANDIDA - atrapar dispositivos de runs previos
CLEANUP_BOUNDS = {
    "F01": {"xmin": 25, "xmax": 55, "ymin": -5, "ymax": 40},
    "F02": {"xmin": 25, "xmax": 55, "ymin": 25, "ymax": 65},
}

TARGET_LEVEL_NAMES = ["PISO 5", "NIVEL 5", "LEVEL 5", "P5", "N5"]
TARGET_LEVEL_ELEV = 43.37

# ════════════════════════════════════════════════════════════════
# CLASIFICACIÓN CORRECTA
# ════════════════════════════════════════════════════════════════

# Solo este va face-based a muro
FACE_BASED_MURO = {"M_Pulsador - Interruptor"}

# Ceiling-based obligatorio (luces, CP)
CEILING_BASED_TECHO = {"M_Iluminacion", "Consolidation_Point"}

# Ceiling-based con offset -0.65ft (campana, climatizacion)
CEILING_WITH_OFFSET = {"M_ClimatizacionV", "M_Timbre"}

# Level-based Z absoluto - TODO LO DEMÁS
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

CEILING_OFFSET_FT = {
    "M_ClimatizacionV": -0.65,
    "M_Timbre": -0.65,
}

# Solo estas familias necesitan rotación +90° (modeladas vertical, placa horizontal)
ROTATE_FAMILIES = {"M_Toma doble", "M_Comunicaciones"}

# ════════════════════════════════════════════════════════════════
# CONSTANTES
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
# TECHO: Obtener cara inferior + bounds GLOBALES reales
# ════════════════════════════════════════════════════════════════

def get_ceiling_bottom_face_data(doc, ceiling_id):
    """Obtiene cara inferior del techo y sus bounds GLOBALES evaluando esquinas UV"""
    ceil = doc.GetElement(eid(ceiling_id))
    if not ceil: return None
    opt = Options(); opt.ComputeReferences = True
    g = ceil.get_Geometry(opt)
    if not g: return None
    for o in g:
        if isinstance(o, Solid):
            for f in o.Faces:
                if isinstance(f, PlanarFace) and f.FaceNormal.Z < -0.95:
                    bb_uv = f.GetBoundingBox()
                    corners_uv = [
                        UV(bb_uv.Min.U, bb_uv.Min.V),
                        UV(bb_uv.Min.U, bb_uv.Max.V),
                        UV(bb_uv.Max.U, bb_uv.Min.V),
                        UV(bb_uv.Max.U, bb_uv.Max.V),
                    ]
                    global_pts = [f.Evaluate(uv) for uv in corners_uv]
                    xs = [p.X for p in global_pts]
                    ys = [p.Y for p in global_pts]
                    zs = [p.Z for p in global_pts]
                    return {
                        "ceiling_id": ceiling_id,
                        "face": f,
                        "face_ref": f.Reference,
                        "face_z": sum(zs) / 4.0,
                        "uv_bbox": bb_uv,
                        "global_bounds": {
                            "xmin": min(xs), "xmax": max(xs),
                            "ymin": min(ys), "ymax": max(ys),
                            "zmin": min(zs), "zmax": max(zs),
                        },
                        "center_global": XYZ(sum(xs)/4, sum(ys)/4, sum(zs)/4)
                    }
    return None

def project_on_ceiling_clamped(doc, face_data, x, y, z_above=10.0):
    """Proyecta (x,y) sobre la cara; clampea a bounds globales reales si está fuera"""
    face = face_data["face"]
    face_ref = face_data["face_ref"]
    gb = face_data["global_bounds"]
    
    margin = 0.01
    x_clamped = max(gb["xmin"] + margin, min(gb["xmax"] - margin, x))
    y_clamped = max(gb["ymin"] + margin, min(gb["ymax"] - margin, y))
    
    clamped = (x_clamped != x or y_clamped != y)
    if clamped:
        log("    [CLAMP] ({:.2f},{:.2f}) -> ({:.2f},{:.2f}) Y bounds [{:.2f},{:.2f}]".format(
            x, y, x_clamped, y_clamped, gb["ymin"], gb["ymax"]))
    
    pt_above = XYZ(x_clamped, y_clamped, face_data["face_z"] + z_above)
    proj = face.Project(pt_above)
    
    if proj:
        uv = proj.UVPoint
        bb = face.GetBoundingBox()
        u_clamped = max(bb.Min.U, min(bb.Max.U, uv.U))
        v_clamped = max(bb.Min.V, min(bb.Max.V, uv.V))
        pt_on_face = face.Evaluate(UV(u_clamped, v_clamped))
        strategy = "PROJECT+CLAMP" if clamped else "PROJECT"
        return pt_on_face, UV(u_clamped, v_clamped), True, strategy
    
    bb = face.GetBoundingBox()
    u_center = (bb.Min.U + bb.Max.U) / 2
    v_center = (bb.Min.V + bb.Max.V) / 2
    pt_on_face = face.Evaluate(UV(u_center, v_center))
    return pt_on_face, UV(u_center, v_center), True, "CENTER_FALLBACK"

# ════════════════════════════════════════════════════════════════
# INVENTARIO TECHOS
# ════════════════════════════════════════════════════════════════

def inventory_ceilings(doc, level_elev, level_name):
    log("\n[INVENTARIO TECHOS] Nivel " + level_name + "...")
    ceilings_data = []
    for c in FilteredElementCollector(doc).OfClass(Ceiling).WhereElementIsNotElementType().ToElements():
        try:
            lvl = doc.GetElement(c.LevelId)
            if not lvl or abs(lvl.Elevation - level_elev) > 0.5: continue
            opt = Options(); opt.ComputeReferences = True
            g = c.get_Geometry(opt)
            if not g: continue
            for o in g:
                if isinstance(o, Solid):
                    bbox = o.GetBoundingBox()
                    if bbox:
                        typ = doc.GetElement(c.GetTypeId())
                        type_name = typ.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() if typ else "?"
                        ceilings_data.append({
                            "id": elem_id(c.Id), "type": type_name,
                            "xmin": round(bbox.Min.X,2), "xmax": round(bbox.Max.X,2),
                            "ymin": round(bbox.Min.Y,2), "ymax": round(bbox.Max.Y,2),
                            "zmin": round(bbox.Min.Z,2), "zmax": round(bbox.Max.Z,2),
                            "area_ft2": round((bbox.Max.X - bbox.Min.X) * (bbox.Max.Y - bbox.Min.Y), 1)
                        })
        except: pass
    log("[INVENTARIO] " + str(len(ceilings_data)) + " techos en " + level_name)
    for cd in ceilings_data:
        log("  Id={id} Type={type} X[{xmin},{xmax}] Y[{ymin},{ymax}] Z[{zmin},{zmax}] Area={area_ft2}ft2".format(**cd))
    return ceilings_data

# ════════════════════════════════════════════════════════════════
# ROTACIÓN FB-MURO
# ════════════════════════════════════════════════════════════════

def compute_wall_direction(face_normal, rotation_deg):
    nx, ny = face_normal.X, face_normal.Y
    base_dir = XYZ(-ny, nx, 0)
    ang = math.radians(rotation_deg)
    cos_a = math.cos(ang)
    sin_a = math.sin(ang)
    dir_x = base_dir.X * cos_a - base_dir.Y * sin_a
    dir_y = base_dir.X * sin_a + base_dir.Y * cos_a
    return XYZ(dir_x, dir_y, 0)

# ════════════════════════════════════════════════════════════════
# BUSCAR PARÁMETRO OFFSET - FIX IRONPYTHON ENUM ACCESS
# ════════════════════════════════════════════════════════════════

def find_and_set_offset_parameter(inst, offset_ft):
    """IronPython 2.7 compatible: usa nombres de string para BuiltInParameter"""
    if offset_ft == 0: return True, "none", 0
    # Nombres de string - evita error 'type' object has no attribute
    builtin_names = [
        "INSTANCE_FREE_HOST_OFFSET_PARAM",
        "INSTANCE_HEAD_OFFSET_PARAM", 
        "INSTANCE_BASE_OFFSET_PARAM",
        "LEVEL_OFFSET",
        "ROOF_BASE_OFFSET_PARAM",
        "CEILING_HEIGHTABOVELEVEL_PARAM",
    ]
    for bp_name in builtin_names:
        try:
            bp = getattr(BuiltInParameter, bp_name)
            p = inst.get_Parameter(bp)
            if p and not p.IsReadOnly and p.StorageType == 0:  # StorageType.Double = 0
                p.Set(offset_ft)
                return True, bp_name, offset_ft
        except: pass
    # Búsqueda por nombre del parámetro
    keywords = ["offset", "desplaz", "altura", "height", "elevation", "base", "head", "host"]
    for p in inst.Parameters:
        try:
            if p.IsReadOnly: continue
            if p.StorageType != 0: continue
            name_lower = p.Definition.Name.lower() if p.Definition else ""
            for kw in keywords:
                if kw in name_lower:
                    p.Set(offset_ft)
                    return True, p.Definition.Name, offset_ft
        except: pass
    return False, "NOT_FOUND", 0

# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

log("=" * 70)
log("COLOCAR_DISPOSITIVOS_DESDE_DXF v3.12.1 - JSON MAESTRO GLOBAL DIRECTO (FIXED)")
log("Ejecutado: " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S") + " (Bogotá GMT-5)")
log("=" * 70)

doc = None
try: doc = __revit__.ActiveUIDocument.Document
except:
    try:
        from pyrevit import revit; doc = revit.doc
    except: pass
if not doc: log("[ERROR] No documento"); sys.exit()
log("[OK] " + doc.Title)

# 1. INVENTARIO
inventory_ceilings(doc, TARGET_LEVEL_ELEV, "Piso_5")

# Cargar JSON MAESTRO (coordenadas globales directas)
data = load_json(JSON_PATH)
f01_devices = data.get('apartamentos',{}).get('F01',{}).get('devices',[])
f02_devices = data.get('apartamentos',{}).get('F02',{}).get('devices',[])

log("[JSON] F01: {} dispositivos, F02: {} dispositivos".format(len(f01_devices), len(f02_devices)))

# Level
PISO5_LEVEL = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    name = lvl.Name if hasattr(lvl, 'Name') else ""
    if any(kw in name.upper() for kw in TARGET_LEVEL_NAMES):
        PISO5_LEVEL = lvl; break
if not PISO5_LEVEL:
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if abs(lvl.Elevation - TARGET_LEVEL_ELEV) < 0.5:
            PISO5_LEVEL = lvl; break
if not PISO5_LEVEL:
    PISO5_LEVEL = list(FilteredElementCollector(doc).OfClass(Level).ToElements())[0]

NIVEL5_ELEV = PISO5_LEVEL.Elevation
PISO5_LEVEL_ID_INT = elem_id(PISO5_LEVEL)
log("[LEVEL] '" + PISO5_LEVEL.Name + "' Id=" + str(PISO5_LEVEL_ID_INT) + " Elev=" + str(round(NIVEL5_ELEV,4)) + "ft")

# 2. TECHOS POR APTO
ceiling_data = {}
for apto in ["F01", "F02"]:
    cid = CEILING_IDS[apto]
    fd = get_ceiling_bottom_face_data(doc, cid)
    if fd:
        gb = fd["global_bounds"]
        c = fd["center_global"]
        ceiling_data[apto] = fd
        log("[TECHO " + apto + " Id=" + str(cid) + "] Centro=({:.2f},{:.2f},{:.2f}) Bounds Y=[{:.2f},{:.2f}] Z={:.2f}".format(
            c.X, c.Y, c.Z, gb["ymin"], gb["ymax"], fd["face_z"]))
    else:
        log("[TECHO " + apto + " Id=" + str(cid) + "] ERROR: No se obtuvo cara inferior")
        ceiling_data[apto] = None

# Muros Piso 5
walls = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id_int = elem_id(bp.AsElementId()) if bp and bp.HasValue else 0
    lvl_id_int = elem_id(w.LevelId)
    if (bp_id_int == PISO5_LEVEL_ID_INT or lvl_id_int == PISO5_LEVEL_ID_INT) and w.Location:
        walls.append(w)
log("[MUROS] Piso 5: " + str(len(walls)) + " muros")

# Símbolos
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

# Limpieza EXPANDIDA
log("\n[LIMPIEZA] Borrando previos (bounds expandidos)...")
to_delete = []
for apto, bounds in CLEANUP_BOUNDS.items():
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
    tx_del = Transaction(doc, "Limpiar previos"); tx_del.Start()
    try: doc.Delete(List[ElementId](to_delete)); tx_del.Commit(); log("[LIMPIEZA] " + str(len(to_delete)) + " borradas")
    except Exception as e: tx_del.RollBack(); log("[LIMPIEZA ERR] " + str(e))
else: log("[LIMPIEZA] Nada")

# Duplicados
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

def set_level_parameter(inst, level):
    for bp in [BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM, BuiltInParameter.LEVEL_PARAM, BuiltInParameter.FAMILY_LEVEL_PARAM]:
        try:
            p = inst.get_Parameter(bp)
            if p and not p.IsReadOnly: p.Set(level.Id); return True, bp.ToString()
        except: pass
    return False, "FAILED"

# FB-MURO Pulsador
def find_wall_face_for_pulsador(doc, walls, target_x, target_y, target_z_ft):
    target_pt = XYZ(target_x, target_y, target_z_ft)
    best = None; best_dist = float('inf'); best_strategy = ""
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
                            uv = proj.UVPoint
                            bb = face.GetBoundingBox()
                            if bb.Min.U <= uv.U <= bb.Max.U and bb.Min.V <= uv.V <= bb.Max.V:
                                pt_on_face = face.Evaluate(uv)
                                d = target_pt.DistanceTo(pt_on_face)
                                if d < best_dist:
                                    best_dist = d; best = (face, w, pt_on_face, face.FaceNormal); best_strategy = "DIRECT_PROJECT"
                    except: pass
        except: continue
    if best: return best[0], best[1], best[2], best[3], best_strategy
    return None, None, None, None, "NOT_FOUND"

# ════════════════════════════════════════════════════════════════
# COLOCAR - COORDENADAS GLOBALES DIRECTAS DEL JSON
# ════════════════════════════════════════════════════════════════

def place_apartment(apto_name, devices, fd):
    if not devices: return 0,0,0
    if not fd:
        log("⚠️ " + apto_name + ": Sin datos de techo")
        return 0,0,0
    log("\n===== " + apto_name + " (Techo " + str(fd["ceiling_id"]) + ") =====")
    ok = er = saltados = 0
    tx = Transaction(doc, "Colocar " + apto_name); tx.Start()
    try:
        for i, dev in enumerate(devices, 1):
            fam = dev['familia_revit']; typ = dev['tipo_revit']
            s = find_sym(fam, typ)
            if not s: log("[" + str(i) + "] " + fam + "/" + typ + " -> NO SYM"); er += 1; continue
            
            # COORDENADAS GLOBALES DIRECTAS DEL JSON (ya en pies)
            x_abs = dev['x']
            y_abs = dev['y']
            rot = dev.get('rotation', 0)
            
            h_montaje_m = ALTURAS_MONTAJE_M.get(fam, 0.30)
            z_corr_m = Z_CORRECTION_M.get(fam, 0.0)
            h_effective_m = h_montaje_m + z_corr_m
            
            if existe_cercano(doc, x_abs, y_abs, UMBRAL_DUP):
                log("  [DUP] " + dev.get('name','') + " -> SALTADO"); saltados += 1; continue
            
            target_z_ft = NIVEL5_ELEV + m_a_ft(h_effective_m)
            dxf_name = dev.get('name', ''); dxf_handle = dev.get('handle', '')
            log("  [PLACE] " + dxf_name + " " + fam + " @ XY=(" + str(round(x_abs,2)) + "," + str(round(y_abs,2)) + ") GLOBAL")
            if z_corr_m != 0:
                log("    [Z_CORRECTION] montaje=" + str(h_montaje_m) + "m corr=" + str(z_corr_m) + "m -> effective=" + str(round(h_effective_m,4)) + "m")
            
            placed = False; z_final = target_z_ft; method = ""; inst = None
            
            # 1. FB-MURO: SOLO M_Pulsador - Interruptor
            if fam in FACE_BASED_MURO and walls:
                face_w, wall, pt_on_face, face_normal, strategy = find_wall_face_for_pulsador(doc, walls, x_abs, y_abs, target_z_ft)
                if face_w and pt_on_face:
                    if not s.IsActive: s.Activate()
                    try:
                        direction = compute_wall_direction(face_normal, rot)
                        inst = doc.Create.NewFamilyInstance(face_w.Reference, pt_on_face, direction, s)
                        set_level_parameter(inst, PISO5_LEVEL)
                        z_final = pt_on_face.Z
                        method = "FB-MURO-" + apto_name + "/" + strategy
                        log("    [FB-MURO/" + strategy + "] " + dxf_name + " -> Muro " + str(elem_id(wall.Id)) + " Z=" + str(round(z_final,4)) + " rot=" + str(rot) + "°")
                        placed = True
                    except Exception as e: log("    [FB-MURO ERR] " + str(e))
                else: log("    [FB-MURO FALLÓ] " + dxf_name)
            
            # 2. FB-TECHO: Luces + CP (host obligatorio)
            if not placed and fam in CEILING_BASED_TECHO:
                pt_on_face, uv, success, strategy = project_on_ceiling_clamped(doc, fd, x_abs, y_abs)
                if success and pt_on_face:
                    if not s.IsActive: s.Activate()
                    try:
                        inst = doc.Create.NewFamilyInstance(fd["face_ref"], pt_on_face, HORIZONTAL_DIR, s)
                        set_level_parameter(inst, PISO5_LEVEL)
                        host_id = elem_id(inst.Host.Id) if inst.Host else -1
                        host_ok = "✅" if host_id == fd["ceiling_id"] else "⚠️"
                        z_final = pt_on_face.Z
                        method = "FB-TECHO-" + apto_name + "/" + strategy
                        log("    [FB-TECHO/" + strategy + "] " + dxf_name + " -> Techo " + str(fd["ceiling_id"]) + " " + host_ok + " Z=" + str(round(z_final,4)))
                        placed = True
                    except Exception as e: log("    [FB-TECHO ERR] " + str(e))
                else: log("    [FB-TECHO FALLÓ] " + dxf_name + " " + strategy)
            
            # 3. CEILING_WITH_OFFSET: ClimatizacionV + Timbre (host + offset -0.65ft)
            if not placed and fam in CEILING_WITH_OFFSET:
                pt_on_face, uv, success, strategy = project_on_ceiling_clamped(doc, fd, x_abs, y_abs)
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
                                log("    [OFFSET PARAM] " + param_name + " = " + str(val) + "ft -> Z_real=" + str(round(z_final,4)) + "ft")
                            else:
                                log("    [MOVE ELEMENT FALLBACK] " + dxf_name)
                                vec = XYZ(0, 0, offset_ft)
                                ElementTransformUtils.MoveElement(doc, inst.Id, vec)
                                z_final = pt_on_face.Z + offset_ft
                                log("    [MOVE] Z_techo=" + str(round(pt_on_face.Z,4)) + " -> Z_real=" + str(round(z_final,4)) + "ft")
                        else:
                            z_final = pt_on_face.Z
                        method = "FB-TECHO-OFFSET-" + apto_name + "/" + strategy
                        log("    [FB-TECHO/" + strategy + "] " + dxf_name + " -> Techo " + str(fd["ceiling_id"]) + " Z=" + str(round(z_final,4)))
                        placed = True
                    except Exception as e: log("    [FB-TECHO-OFFSET ERR] " + str(e))
                else: log("    [FB-TECHO-OFFSET FALLÓ] " + dxf_name + " " + strategy)
            
            # 4. LB-Z-ABS: Tomas, Comm, Interruptores, EA
            if not placed:
                pt = XYZ(x_abs, y_abs, target_z_ft)
                if not s.IsActive: s.Activate()
                try:
                    inst = doc.Create.NewFamilyInstance(pt, s, StructuralType.NonStructural)
                    set_level_parameter(inst, PISO5_LEVEL)
                    
                    # ROTACIÓN SEGURA: solo familias modeladas en vertical
                    if fam in ROTATE_FAMILIES:
                        rotation = rot
                        ang = (rotation + 90) % 360
                        if abs(ang) > 0.1:
                            try:
                                ax = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1))
                                inst.Location.Rotate(ax, math.radians(ang))
                            except Exception as e_rot:
                                log("    [ROT WARN] " + dxf_name + " rot=" + str(ang) + "° falló: " + str(e_rot))
                    
                    z_final = target_z_ft
                    method = "LB-Z-ABS"
                    log("    [LB-Z-ABS] " + dxf_name + " Z=" + str(round(z_final,4)) + " (target=" + str(round(target_z_ft,4)) + ")")
                    placed = True
                except Exception as e:
                    log("[" + str(i) + "] " + dxf_name + " -> ERR: " + str(e)); er += 1; continue
            
            if placed and inst:
                uid = inst.UniqueId
                log("[" + str(i) + "] " + dxf_name + " @ XY=(" + str(round(x_abs,2)) + "," + str(round(y_abs,2)) + ") GLOBAL ft Z=" + str(round(z_final,4)) + "ft -> OK id=" + str(elem_id(inst)) + " " + method + " UID=" + uid[:8])
                ok += 1
            elif not placed:
                log("[" + str(i) + "] " + dxf_name + " -> NO PLACED"); er += 1
        tx.Commit()
    except Exception as e: tx.RollBack(); log("[TXN ERR] " + str(e))
    return ok, er, saltados

# EJECUTAR - Sin offsets, coordenadas directas del JSON
for apto in ["F01", "F02"]:
    devices = f01_devices if apto == "F01" else f02_devices
    fd = ceiling_data[apto]
    o, e, s = place_apartment(apto, devices, fd)
    log(apto + " -> OK:" + str(o) + " ERR:" + str(e) + " SALT:" + str(s))

log("\n" + "=" * 70)
log("v3.12.1 COMPLETADO - JSON MAESTRO GLOBAL DIRECTO (FIXED)")
log("Techos: 2764963 (F01), 2766313 (F02) — sin mover")
log("Fix: IronPython enum access, limpieza expandida, rotación segura")
log("=" * 70)