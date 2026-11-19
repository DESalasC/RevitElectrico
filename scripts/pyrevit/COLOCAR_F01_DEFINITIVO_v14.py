# -*- coding: utf-8 -*-
# COLOCAR_F01_DEFINITIVO_v14.py - FIX: EA=Extractor + FamilyPlacementType verificado
# Ejecutar en pyRevit

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

# CARGAR JSONs
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

print("Offset apartamento F01: X={:.2f}ft, Y={:.2f}ft".format(APTO_OFFSET_X, APTO_OFFSET_Y))

# 0. LIMPIAR
print("=== LIMPIANDO F01 EXISTENTE ===")
to_delete = []
for elem in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
    mark_p = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if mark_p and mark_p.HasValue:
        mark_val = mark_p.AsString()
        if mark_val and mark_val.startswith("F01|TF 01"):
            to_delete.append(elem.Id)

t_clean = Transaction(doc, "Limpiar F01"); t_clean.Start()
deleted = 0
for eid in to_delete:
    try:
        doc.Delete(eid)
        deleted += 1
    except: pass
t_clean.Commit()
print("Eliminados: {}".format(deleted))

# 1. MUROS
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
        wall_dir = XYZ(-normal.Y, normal.X, 0)
        walls.append((w.Id, curve, interior_ref, normal, wall_dir))

print("Muros con Reference interior: {}".format(len(walls)))

# 2. TECHO
f01_ceiling = doc.GetElement(ElementId(Int64(f01_ceiling_id)))
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
ceiling_wall_dir = XYZ(-ceiling_normal.Y, ceiling_normal.X, 0)

# 3. SIMBOLOS + VERIFICAR FamilyPlacementType
S = {}
PLACEMENT_TYPE = {}
cats = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_MechanicalEquipment,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_FireAlarmDevices,
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

print("Simbolos totales: {}".format(len(S)))
print("FamilyPlacementType detectados:")
for fam, fpt in PLACEMENT_TYPE.items():
    print("  {}: {}".format(fam, fpt))

# 4. MAPEO - CORREGIDO: EA = Extractor (no Extintor)
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
    ("EA", "Extractor"): ("EA", "Extractor"),  # CORREGIDO: Extractor
    ("M_ClimatizacionV", "Ventilador"): ("M_ClimatizacionV", "Ventilador"),
    ("M_Climatizacion", "Interruptor Ventilador"): ("M_Climatizacion", "Interruptor Ventilador"),
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

def get_placement(fam, sym):
    """Decidir placement basado en FamilyPlacementType real"""
    fpt = PLACEMENT_TYPE.get(fam)
    if fpt == FamilyPlacementType.WorkPlaneBased:
        if fam in ["M_ClimatizacionV", "M_Iluminacion"]:
            return "FACE_CEILING"
        return "FACE_WALL"
    elif fpt == FamilyPlacementType.CeilingBased:
        return "FACE_CEILING"
    else:
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
                best = (ref, normal, wall_dir, d)
        except: continue
    return best

def point_in_ceiling(x, y):
    return xmin <= x <= xmax and ymin <= y <= ymax

# ALTURAS CORRECTAS (norma COL) - Z absoluto en pies
ALTURAS = {
    "M_Toma doble": nivel5_z + m_a_ft(0.30),      # 30cm
    "M_Toma-Rango": nivel5_z + m_a_ft(0.30),
    "M_Toma - 220V": nivel5_z + m_a_ft(0.30),
    "M_Comunicaciones": nivel5_z + m_a_ft(0.30),
    "Consolidation_Point": nivel5_z + m_a_ft(2.70),
    "M_Pulsador - Interruptor": nivel5_z + m_a_ft(1.10),  # Timbre pulsador
    "M_Timbre": nivel5_z + m_a_ft(2.40),                  # Campana
    "M_Interruptores": nivel5_z + m_a_ft(1.10),
    "EA": nivel5_z + m_a_ft(2.40),        # Extractor a 2.40m (techo) - verificar
    "M_ClimatizacionV": "techo",
    "M_Iluminacion": "techo",
}

# 5. COLOCAR
t = Transaction(doc, "Colocar F01 DEFINITIVO v14"); t.Start()
ok_fb_wall = 0
ok_fb_ceil = 0
ok_lb = 0
skipped = 0
for dev in devices:
    fam = dev['familia_revit']; typ = dev['tipo_revit']
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
    placement = get_placement(fam, s)
    z = ALTURAS.get(fam, nivel5_z + m_a_ft(0.30))
    pt = XYZ(x, y, z)
    
    try:
        if not s.IsActive: s.Activate()
        
        if placement == "FACE_WALL":
            result = find_wall_ref(pt_xy)
            if not result:
                print("  Sin muro para {} @ ({:.2f},{:.2f})".format(fam, x, y))
                skipped += 1
                continue
            ref, normal, wall_dir, dist = result
            inst = doc.Create.NewFamilyInstance(ref, pt, XYZ.BasisZ, s)
            ok_fb_wall += 1
            print("    FB-MURO: {} @ ({:.2f},{:.2f},{:.2f}) muro_dist={:.2f}ft".format(fam, x, y, z, dist))
            
            # Spin Z para interruptores, timbre pulsador, extractor
            if fam in ["M_Interruptores", "M_Pulsador - Interruptor", "EA"]:
                face_normal_angle = math.atan2(normal.Y, normal.X)
                spin_rot = face_normal_angle
                if spin_rot != 0:
                    axis = Line.CreateBound(pt, XYZ(x, y, z + 1))
                    from Autodesk.Revit.DB import ElementTransformUtils
                    ElementTransformUtils.RotateElement(doc, inst.Id, axis, spin_rot)
        
        elif placement == "FACE_CEILING":
            face = f01_ceiling_face
            if not face:
                print("  ERROR: Sin cara de techo F01")
                skipped += 1
                continue
            if not point_in_ceiling(x, y):
                print("  Punto fuera de techo para {} @ ({:.2f},{:.2f})".format(fam, x, y))
                skipped += 1
                continue
            inst = doc.Create.NewFamilyInstance(f01_ceiling_face, pt, ceiling_wall_dir, s)
            ok_fb_ceil += 1
            print("    FB-TECHO: {} @ ({:.2f},{:.2f},{:.2f})".format(fam, x, y, f01_ceiling_z))
        
        else:  # LEVEL
            inst = doc.Create.NewFamilyInstance(pt, s, level5_elem, StructuralType.NonStructural)
            ok_lb += 1
            print("    LEVEL: {} @ ({:.2f},{:.2f},{:.2f})".format(fam, x, y, z))
            
            # Spin Z para campana también
            result = find_wall_ref(pt_xy)
            if result:
                ref, normal, wall_dir, dist = result
                face_normal_angle = math.atan2(normal.Y, normal.X)
                spin_rot = face_normal_angle
                if spin_rot != 0:
                    axis = Line.CreateBound(pt, XYZ(x, y, z + 1))
                    from Autodesk.Revit.DB import ElementTransformUtils
                    ElementTransformUtils.RotateElement(doc, inst.Id, axis, spin_rot)
    
    except Exception as e:
        print("  ERROR colocando {}: {}".format(fam, e))
        skipped += 1
        continue
    
    # Mark
    mark = "F01|TF 01"
    if 'id_bloque' in dev:
        mark = "F01|TF 01|{}".format(dev['id_bloque'])
    mark_param = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if mark_param: mark_param.Set(mark)

t.Commit()
print("=== RESUMEN ===")
print("FB-Muro: {}".format(ok_fb_wall))
print("FB-Techo: {}".format(ok_fb_ceil))
print("Level: {}".format(ok_lb))
print("Total: {}".format(ok_fb_wall + ok_fb_ceil + ok_lb))
print("Skipped: {}".format(skipped))