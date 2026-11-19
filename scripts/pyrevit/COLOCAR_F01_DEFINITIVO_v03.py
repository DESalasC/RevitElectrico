# -*- coding: utf-8 -*-
# COLOCAR_F01_DEFINITIVO_v03.py - Usar JSON de techos (ceilings_mapping_apto.json)
# Ejecutar en pyRevit

import clr, json, math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, UV, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, HostObjectUtils, ShellLayerType, Transaction, Line, PlanarFace, Options, Solid)
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
f01_ceiling_id = ceilings_map.get('F01')
if not f01_ceiling_id:
    print("ERROR: F01 no esta en ceilings_mapping_apto.json")
else:
    print("Techo F01 desde JSON: {}".format(f01_ceiling_id))

# 1. MUROS + REFERENCES INTERIORES
nivel5_id = 192512
nivel5_z = 43.37
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

# 2. TECHO F01 DESDE JSON
f01_ceiling = doc.GetElement(ElementId(Int64(f01_ceiling_id)))
if not f01_ceiling:
    print("ERROR: Techo F01 no encontrado en Revit")
else:
    print("Techo F01 encontrado: {}".format(int(f01_ceiling.Id.Value)))

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

if not f01_ceiling_face:
    print("ERROR: No se encontro cara inferior del techo F01")

# Pre-calcular datos del techo
ceiling_normal = f01_ceiling_face.FaceNormal
ceiling_origin = f01_ceiling_face.Origin
ceiling_wall_dir = XYZ(-ceiling_normal.Y, ceiling_normal.X, 0)
bb = f01_ceiling_face.GetBoundingBox()
ceiling_z = (bb.Min.V + bb.Max.V) / 2 + f01_ceiling_face.Origin.Z

print("Techo Z={:.2f} Bounds U=[{:.1f},{:.1f}] V=[{:.1f},{:.1f}]".format(
    ceiling_z, bb.Min.U, bb.Max.U, bb.Min.V, bb.Max.V))

# 3. SIMBOLOS
S = {}
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
        except: pass

print("Simbolos totales: {}".format(len(S)))

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
    ("EA", "Extintor"): ("EA", "EA 1010"),
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

def get_placement(fam):
    if fam in ["M_Toma doble", "M_Toma-Rango", "M_Toma - 220V", "M_Comunicaciones", "Consolidation_Point"]:
        return "FACE_WALL"
    if fam in ["M_ClimatizacionV", "M_Iluminacion"]:
        return "FACE_CEILING"
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
                best = (ref, normal, wall_dir)
        except: continue
    return best

# 5. COLOCAR
t = Transaction(doc, "Colocar F01 DEFINITIVO v3"); t.Start()
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
    pt_xy = XYZ(x, y, 0)
    
    placement = get_placement(fam)
    
    if placement == "FACE_WALL":
        result = find_wall_ref(pt_xy)
        if not result:
            print("  Sin muro para {} @ ({:.2f},{:.2f})".format(fam, x, y))
            skipped += 1
            continue
        ref, normal, wall_dir = result
        
        if fam in ["M_Toma doble", "M_Toma-Rango", "M_Toma - 220V", "M_Comunicaciones"]:
            z = nivel5_z + m_a_ft(0.30)
        elif fam == "Consolidation_Point":
            z = nivel5_z + m_a_ft(2.70)
        else:
            z = nivel5_z + m_a_ft(0.30)
        
        pt = XYZ(x, y, z)
        
        if not s.IsActive: s.Activate()
        inst = doc.Create.NewFamilyInstance(ref, pt, XYZ.BasisZ, s)
        ok_fb_wall += 1
        
    elif placement == "FACE_CEILING":
        face = f01_ceiling_face
        if not face:
            print("  ERROR: Sin cara de techo F01")
            skipped += 1
            continue
        
        # UV en el techo para el punto (x,y)
        offset = (pt_xy.X - ceiling_origin.X) * ceiling_normal.X + (pt_xy.Y - ceiling_origin.Y) * ceiling_normal.Y
        pt_on = XYZ(pt_xy.X - offset * ceiling_normal.X, pt_xy.Y - offset * ceiling_normal.Y, 0)
        
        u = (pt_on.X - ceiling_origin.X) * ceiling_wall_dir.X + (pt_on.Y - ceiling_origin.Y) * ceiling_wall_dir.Y
        v = -ceiling_origin.Z
        
        bb = f01_ceiling_face.GetBoundingBox()
        if bb.Min.U - 1.0 <= u <= bb.Max.U + 1.0 and bb.Min.V - 1.0 <= v <= bb.Max.V + 1.0:
            pt = XYZ(x, y, ceiling_z)
            
            if not s.IsActive: s.Activate()
            inst = doc.Create.NewFamilyInstance(f01_ceiling_face, XYZ(x, y, ceiling_z), ceiling_wall_dir, s)
            ok_fb_ceil += 1
        else:
            print("  Punto fuera de techo para {} @ ({:.2f},{:.2f}) UV=({:.1f},{:.1f})".format(fam, x, y, u, v))
            skipped += 1
        
    else:  # LEVEL
        result = find_wall_ref(pt_xy)
        if not result:
            print("  Sin muro para {} @ ({:.2f},{:.2f})".format(fam, x, y))
            skipped += 1
            continue
        ref, normal, wall_dir = result
        
        if fam in ["M_Interruptores", "M_Pulsador - Interruptor", "M_Timbre"]:
            z = nivel5_z + m_a_ft(1.10)
        elif fam == "EA":
            z = nivel5_z + m_a_ft(1.90)
        else:
            z = nivel5_z + m_a_ft(0.30)
        
        pt = XYZ(x, y, z)
        
        if not s.IsActive: s.Activate()
        inst = doc.Create.NewFamilyInstance(pt, s, StructuralType.NonStructural)
        ok_lb += 1
        
        face_normal_angle = math.atan2(normal.Y, normal.X)
        spin_rot = face_normal_angle
        if spin_rot != 0:
            axis = Line.CreateBound(pt, XYZ(x, y, z + 1))
            from Autodesk.Revit.DB import ElementTransformUtils
            ElementTransformUtils.RotateElement(doc, inst.Id, axis, spin_rot)
    
    # Mark unico
    mark = "F01|TF 01"
    if 'id_bloque' in dev:
        mark = "F01|TF 01|{}".format(dev['id_bloque'])
    mark_param = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if mark_param: mark_param.Set(mark)

t.Commit()
print("F01 colocados: FB-Muro={}, FB-Techo={}, Level={}, Total={}, Skipped={}".format(
    ok_fb_wall, ok_fb_ceil, ok_lb, ok_fb_wall + ok_fb_ceil + ok_lb, skipped))