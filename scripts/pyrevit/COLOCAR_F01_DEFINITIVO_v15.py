# -*- coding: utf-8 -*-
# COLOCAR_F01_DEFINITIVO_v15.py - v15.13-fix2: XYZ.CrossProduct correcto
# Ejecutar en pyRevit Python Shell

import clr, json, math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, UV, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, HostObjectUtils, ShellLayerType, Transaction, Line, PlanarFace, Options, Solid, Level, FamilyPlacementType)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

JSON_DEVICES = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"
JSON_CEILINGS = r"D:\Work\PROJECTS\RevitElectrico\data\ceilings_mapping_apto.json"
FPM = 3.280839895
def m_a_ft(m): return m * FPM
def clean(s): return s.replace('\ufeff','').replace('\u200b','').strip() if s else s

doc = __revit__.ActiveUIDocument.Document

with open(JSON_DEVICES, 'r') as f:
    data = json.load(f)
with open(JSON_CEILINGS, 'r') as f:
    ceilings_map = json.load(f)

devices = data['apartamentos']['F01']['devices']
f01_info = ceilings_map.get('mapping', {}).get('F01', {})

f01_ceiling_id = f01_info.get('ceiling_id')
f01_ceiling_z = f01_info.get('ceiling_face_z_ft')
bounds = f01_info.get('ceiling_bounds_ft', {})
xmin, xmax = bounds.get('xmin'), bounds.get('xmax')
ymin, ymax = bounds.get('ymin'), bounds.get('ymax')

APTO_OFFSET_X = 0.0
APTO_OFFSET_Y = 11.95

print("=== v15.13-fix2: Orientación en colocación, XYZ.CrossProduct ===")
print("Techo F01: ID={}, Z={:.2f}ft".format(f01_ceiling_id, f01_ceiling_z))

# 0. LIMPIAR
print("\n=== LIMPIANDO F01 ===")
to_delete = []
elec_cats = [
    BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_TelephoneDevices, BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_MechanicalEquipment,
    BuiltInCategory.OST_FireAlarmDevices, BuiltInCategory.OST_ElectricalEquipment,
]
for cat in elec_cats:
    for elem in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
        mark_p = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if mark_p and mark_p.HasValue:
            mark_val = mark_p.AsString()
            if mark_val and mark_val.startswith("F01|TF 01"):
                to_delete.append(elem.Id)

t_clean = Transaction(doc, "Limpiar F01"); t_clean.Start()
for eid in to_delete:
    try: doc.Delete(eid)
    except: pass
t_clean.Commit()
print("Eliminados: {}".format(len(to_delete)))

# 1. MUROS - Reference interior + normal
nivel5_id = 192512
nivel5_z = 43.37
level5_elem = doc.GetElement(ElementId(Int64(nivel5_id)))

walls = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id = int(bp.AsElementId().Value) if bp and bp.HasValue else 0
    lvl_id = int(w.LevelId.Value)
    if not ((bp_id == nivel5_id or lvl_id == nivel5_id) and w.Location):
        continue
    curve = w.Location.Curve
    if not curve: continue
    
    interior_ref = None
    normal = None
    try:
        int_refs = HostObjectUtils.GetSideFaces(w, ShellLayerType.Interior)
        for ref in int_refs:
            f = w.GetGeometryObjectFromReference(ref)
            if f and abs(f.FaceNormal.Z) < 0.1:
                interior_ref = ref
                normal = f.FaceNormal
                break
    except: continue
    
    if interior_ref:
        # wall_dir = vector horizontal ALONG el muro (XYZ.CrossProduct)
        wall_dir = XYZ.CrossProduct(normal, XYZ.BasisZ)
        walls.append((w.Id, curve, interior_ref, normal, wall_dir))

print("Muros con Reference interior: {}".format(len(walls)))

# 2. TECHO F01
f01_ceiling = doc.GetElement(ElementId(Int64(f01_ceiling_id)))
if not f01_ceiling:
    print("ERROR: Techo ID {} no encontrado".format(f01_ceiling_id))
    raise SystemExit(1)

f01_ceiling_face = None
opt = Options(); opt.ComputeReferences = True
geom = f01_ceiling.get_Geometry(opt)
if geom:
    for obj in geom:
        if obj.GetType().Name == "Solid":
            for f in obj.Faces:
                if isinstance(f, PlanarFace) and f.FaceNormal.Z < -0.9:
                    f01_ceiling_face = f
                    break

ceiling_normal = f01_ceiling_face.FaceNormal if f01_ceiling_face else XYZ(0,0,-1)
ceiling_wall_dir = XYZ.CrossProduct(ceiling_normal, XYZ.BasisZ)

print("Techo F01: {} | Cara: {}".format(f01_ceiling.Name, f01_ceiling_face is not None))

# 3. SÍMBOLOS
S = {}
PLACEMENT_TYPE = {}
cats = [
    BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_MechanicalEquipment, BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_FireAlarmDevices, BuiltInCategory.OST_ElectricalEquipment,
]
for cat in cats:
    for elem in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsElementType().ToElements():
        try:
            if isinstance(elem, FamilySymbol):
                fam = clean(elem.FamilyName)
                p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                typ = clean(p.AsString()) if p and p.HasValue else "SinNombre"
                S[(fam, typ)] = elem
                if fam not in PLACEMENT_TYPE:
                    PLACEMENT_TYPE[fam] = elem.Family.FamilyPlacementType
        except: pass

print("\nSimbolos: {}".format(len(S)))
for fam, fpt in PLACEMENT_TYPE.items():
    print("  {}: {}".format(fam, fpt))

# 4. MAPEO
FAMILY_MAP = {
    ("M_Toma doble", "GFCI"): ("M_Toma doble", "GFCI"),
    ("M_Toma doble", "Normal"): ("M_Toma doble", "Normal"),
    ("M_Toma doble", "Intemperie"): ("M_Toma doble", "Intemperie"),
    ("M_Toma-Rango", "Unica"): ("M_Toma-Rango", "Unica"),
    ("M_Toma - 220V", "220V"): ("M_Toma - 220V", "220V"),
    ("M_Comunicaciones", "Datos"): ("M_Comunicaciones", "Datos"),
    ("M_Comunicaciones", "Telefono"): ("M_Comunicaciones", "Telefono"),
    ("M_Interruptores", "Simple"): ("M_Interruptores", "Simple"),
    ("M_Interruptores", "Doble"): ("M_Interruptores", "Doble"),
    ("M_Interruptores", "Triple"): ("M_Interruptores", "Triple"),
    ("M_Interruptores", "Conmutable"): ("M_Interruptores", "Conmutable"),
    ("M_Interruptores", "Simple conmutable"): ("M_Interruptores", "Simple conmutable"),
    ("M_Interruptores", "Doble conmutable"): ("M_Interruptores", "Doble conmutable"),
    ("M_Interruptores", "Triple conmutable"): ("M_Interruptores", "Triple conmutable"),
    ("M_Interruptores", "Control"): ("M_Interruptores", "Conmutable"),
    ("M_Pulsador - Interruptor", "Timbre"): ("M_Pulsador - Interruptor", "Timbre"),
    ("M_Timbre", "Campana"): ("M_Timbre", "Campana"),
    ("EA", "Extintor"): ("EA", "Extractor"),
    ("EA", "Extractor"): ("EA", "Extractor"),
    ("M_ClimatizacionV", "Ventilador"): ("M_ClimatizacionV", "Ventilador"),
    ("M_Climatizacion", "Interruptor Ventilador"): ("M_Climatizacion", "Interruptor Ventilador"),
    ("M_Iluminacion", "SONO FLEX 10 trim"): ("M_Iluminacion", "SONO FLEX 10 trim"),
    ("M_Iluminacion", "SONO FLEX 13 trim"): ("M_Iluminacion", "SONO FLEX 13 trim"),
    ("M_Iluminacion", "SONO FLEX 22 trim"): ("M_Iluminacion", "SONO FLEX 22 trim"),
}

def find_sym(fam, typ):
    fam = clean(fam); typ = clean(typ)
    if (fam, typ) in FAMILY_MAP:
        target = FAMILY_MAP[(fam, typ)]
        if target in S: return S[target]
    if (fam, typ) in S: return S[(fam, typ)]
    for (f, t), s in S.items():
        if f == fam and (t == typ or typ in t or t in typ): return s
    for (f, t), s in S.items():
        if f == fam: return s
    return None

def get_placement_type(fam):
    fpt = PLACEMENT_TYPE.get(fam)
    fpt_str = str(fpt) if fpt else ""
    if fpt_str == "WorkPlaneBased":
        if fam in ["M_ClimatizacionV", "M_Iluminacion"]:
            return "FACE_CEILING"
        return "FACE_WALL"
    return "LEVEL"

def find_wall_ref(pt_xy, max_dist=5.0):
    best = None
    best_d = float('inf')
    pt_at_z = XYZ(pt_xy.X, pt_xy.Y, nivel5_z)
    for w_id, curve, ref, normal, wall_dir in walls:
        try:
            d = curve.Distance(pt_at_z)
            if d < best_d and d < max_dist:
                best_d = d
                best = (w_id, ref, normal, wall_dir, d)
        except: continue
    return best

def point_in_ceiling_bounds(x, y):
    return xmin <= x <= xmax and ymin <= y <= ymax

ALTURAS = {
    "M_Toma doble": nivel5_z + m_a_ft(0.30),
    "M_Toma-Rango": nivel5_z + m_a_ft(0.30),
    "M_Toma - 220V": nivel5_z + m_a_ft(0.30),
    "M_Comunicaciones": nivel5_z + m_a_ft(0.30),
    "Consolidation_Point": nivel5_z + m_a_ft(2.70),
    "M_Pulsador - Interruptor": nivel5_z + m_a_ft(1.10),
    "M_Timbre": nivel5_z + m_a_ft(2.40),
    "M_Interruptores": nivel5_z + m_a_ft(1.10),
    "EA": nivel5_z + m_a_ft(2.40),
}

def calc_place_dir(normal, rot_json):
    """Calcula vector de orientación (3er parámetro NewFamilyInstance) según rotación JSON.
    rot_json: 0=up (vertical), 90=along (horizontal along wall), 180=down, 270=-along"""
    up_vec = XYZ.BasisZ
    along_vec = XYZ.CrossProduct(normal, up_vec)  # horizontal along wall face
    
    rot = rot_json % 360
    if rot <= 45 or rot >= 315:      # 0°
        return up_vec
    elif rot <= 135:                 # 90°
        return along_vec
    elif rot <= 225:                 # 180°
        return XYZ(-up_vec.X, -up_vec.Y, -up_vec.Z)
    else:                            # 270°
        return XYZ(-along_vec.X, -along_vec.Y, -along_vec.Z)

# 5. COLOCAR
t = Transaction(doc, "Colocar F01 v15.13-fix2"); t.Start()
ok_fb_wall = ok_fb_ceil = ok_lb = skipped = 0

for dev in devices:
    fam = dev['familia_revit']; typ = dev['tipo_revit']
    rot_json = dev.get('rotation', 0) % 360
    
    s = find_sym(fam, typ)
    if not s:
        print("  SIN SIMBOLO: {} | {}".format(fam, typ))
        skipped += 1
        continue

    x, y = dev['x'], dev['y']
    if fam == "Consolidation_Point":
        x += APTO_OFFSET_X
        y += APTO_OFFSET_Y
        print("  CP CORREGIDO: ({:.2f}, {:.2f})".format(x, y))

    pt_xy = XYZ(x, y, 0)
    placement = get_placement_type(fam)

    if placement == "FACE_CEILING":
        z = f01_ceiling_z
    else:
        z = ALTURAS.get(fam, nivel5_z + m_a_ft(0.30))
    pt = XYZ(x, y, z)

    try:
        if not s.IsActive: s.Activate()
        inst = None

        if placement == "FACE_WALL":
            result = find_wall_ref(pt_xy)
            if not result:
                print("  Sin muro para {} @ ({:.2f},{:.2f})".format(fam, x, y))
                skipped += 1
                continue
            w_id, ref, normal, wall_dir, dist = result
            
            # Calcular place_dir según rotación JSON
            place_dir = calc_place_dir(normal, rot_json)
            
            # Colocar CON orientación correcta (sin spin post)
            inst = doc.Create.NewFamilyInstance(ref, pt, place_dir, s)
            ok_fb_wall += 1
            print("    FB-MURO: {} @ ({:.2f},{:.2f},{:.2f}) rot={}° place_dir=({:.0f},{:.0f},{:.0f}) d={:.2f}ft".format(
                fam, x, y, z, rot_json, place_dir.X, place_dir.Y, place_dir.Z, dist))
            # NO spin post-placement

        elif placement == "FACE_CEILING":
            if not f01_ceiling_face or not point_in_ceiling_bounds(x, y):
                print("  Fuera de techo para {} @ ({:.2f},{:.2f})".format(fam, x, y))
                skipped += 1
                continue
            z_ceiling = f01_ceiling_z
            if fam == "M_ClimatizacionV":
                z_ceiling -= 0.65
            pt_ceiling = XYZ(x, y, z_ceiling)
            
            # Orientación en techo: rotar ceiling_wall_dir según rot_json
            place_dir = ceiling_wall_dir
            if rot_json != 0:
                angle = rot_json * math.pi / 180.0
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                nx = ceiling_wall_dir.X * cos_a - ceiling_wall_dir.Y * sin_a
                ny = ceiling_wall_dir.X * sin_a + ceiling_wall_dir.Y * cos_a
                place_dir = XYZ(nx, ny, 0)
            
            inst = doc.Create.NewFamilyInstance(f01_ceiling_face, pt_ceiling, place_dir, s)
            ok_fb_ceil += 1
            print("    FB-TECHO: {} @ ({:.2f},{:.2f},{:.2f}) rot={}° offset={:.2f}ft".format(
                fam, x, y, z_ceiling, rot_json, z_ceiling - f01_ceiling_z))

        else:  # LEVEL
            pt_level = XYZ(x, y, 0)
            inst = doc.Create.NewFamilyInstance(pt_level, s, level5_elem, StructuralType.NonStructural)
            ok_lb += 1
            print("    LEVEL: {} @ ({:.2f},{:.2f}) target_Z={:.2f}ft rot={}°".format(fam, x, y, z, rot_json))
            
            # Host para OneLevelBasedHosted
            fpt = PLACEMENT_TYPE.get(fam)
            fpt_str = str(fpt) if fpt else ""
            if fpt_str == "OneLevelBasedHosted" and fam in ["M_Interruptores", "EA", "M_Toma-Rango", "M_Toma - 220V"]:
                try:
                    result = find_wall_ref(pt_xy)
                    if result:
                        w_id, ref, normal, wall_dir, dist = result
                        host_param = inst.get_Parameter(BuiltInParameter.HOST_ID_PARAM)
                        if host_param and not host_param.IsReadOnly:
                            host_param.Set(w_id)
                            print("      HOST set: {} -> muro {}".format(fam, w_id))
                except: pass
            
            # Rotación JSON SOLO para LEVEL (funciona en Z global)
            if rot_json != 0:
                try:
                    rot_rad = rot_json * math.pi / 180.0
                    axis = Line.CreateBound(XYZ(x, y, nivel5_z), XYZ(x, y, nivel5_z + 10))
                    from Autodesk.Revit.DB import ElementTransformUtils
                    ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_rad)
                    print("      ROT Z JSON: {}°".format(rot_json))
                except: pass

    except Exception as e:
        print("  ERROR {}: {}".format(fam, e))
        skipped += 1
        continue

    # Mark único
    mark = "F01|TF 01"
    if 'id_bloque' in dev and dev['id_bloque']:
        mark = "F01|TF 01|{}".format(dev['id_bloque'])
    else:
        mark = "F01|TF 01|{}_{:.3f}_{:.3f}_{}".format(
            fam.replace(' ', '_').replace('-', ''), dev['x'], dev['y'], typ[:8].replace(' ', ''))
    if inst:
        mp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if mp: mp.Set(mark)

t.Commit()
print("\n=== RESUMEN v15.13-fix2 ===")
print("FB-Muro: {} | FB-Techo: {} | Level: {} | Total: {} | Skipped: {}".format(
    ok_fb_wall, ok_fb_ceil, ok_lb, ok_fb_wall+ok_fb_ceil+ok_lb, skipped))