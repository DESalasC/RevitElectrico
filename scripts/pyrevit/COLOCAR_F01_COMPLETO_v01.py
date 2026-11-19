# -*- coding: utf-8 -*-
# COLOCAR_F01_COMPLETO_v01.py - Face-based (tomas/comms/CP) + Level-based (interruptores) + FB-TECHO (ventilador/luces)
# Ejecutar en pyRevit

import clr, json, math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, HostObjectUtils, ShellLayerType, Transaction, Line, PlanarFace, Options, Solid)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"
FPM = 3.280839895
def m_a_ft(m): return m * FPM
def clean(s): return s.replace('\ufeff','').replace('\u200b','').strip() if s else s

doc = __revit__.ActiveUIDocument.Document

with open(JSON_PATH, 'r') as f:
    data = json.load(f)
devices = data['apartamentos']['F01']['devices']

# 1. RECOLECTAR MUROS + REFERENCES INTERIORES
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

# 2. RECOLECTAR TECHOS (para FB-TECHO)
ceilings = []
for c in FilteredElementCollector(doc).OfClass(Ceiling).WhereElementIsNotElementType().ToElements():
    if c.LevelId.Value == nivel5_id and c.Location:
        ceilings.append(c)
print("Techos Piso 5: {}".format(len(ceilings)))

def find_ceiling_face(pt_xy):
    """Encontrar techo más cercano y su cara inferior"""
    best = None
    best_d = float('inf')
    for c in ceilings:
        try:
            c_pt = c.Location.Point
            d = math.sqrt((c_pt.X - pt_xy.X)**2 + (c_pt.Y - pt_xy.Y)**2)
            if d < best_d:
                best_d = d
                best = c
        except: continue
    if best and best_d < 10.0:
        opt = Options(); opt.ComputeReferences = True
        geom = best.get_Geometry(opt)
        if geom:
            for obj in geom:
                if obj.GetType().Name == "Solid":
                    for f in obj.Faces:
                        if isinstance(f, PlanarFace) and f.FaceNormal.Z < -0.9:
                            return f
    return None

# 3. SÍMBOLOS
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

print("Símbolos totales: {}".format(len(S)))

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
    if fam in ["M_ClimatizacionV", "M_Iluminacion", "Consolidation_Point"]:
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
t = Transaction(doc, "Colocar F01 Completo"); t.Start()
ok_fb_wall = 0
ok_fb_ceil = 0
ok_lb = 0
skipped = 0
for dev in devices:
    fam = dev['familia_revit']; typ = dev['tipo_revit']
    s = find_sym(fam, typ)
    if not s:
        print("  SIN SÍMBOLO: {} | {}".format(fam, typ))
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
            z = nivel5_z + m_a_ft(2.70)  # CP a 2.70m
        else:
            z = nivel5_z + m_a_ft(0.30)
        
        pt = XYZ(x, y, z)
        
        if not s.IsActive: s.Activate()
        inst = doc.Create.NewFamilyInstance(ref, pt, XYZ.BasisZ, s)
        ok_fb_wall += 1
        
    elif placement == "FACE_CEILING":
        face = find_ceiling_face(pt_xy)
        if not face:
            print("  Sin techo para {} @ ({:.2f},{:.2f})".format(fam, x, y))
            skipped += 1
            continue
        
        normal = face.FaceNormal
        origin = face.Origin
        wall_dir = XYZ(-normal.Y, normal.X, 0)
        offset = (pt_xy.X - origin.X) * normal.X + (pt_xy.Y - origin.Y) * normal.Y
        pt_on = XYZ(pt_xy.X - offset * normal.X, pt_xy.Y - offset * normal.Y, 0)
        u = (pt_on.X - origin.X) * wall_dir.X + (pt_on.Y - origin.Y) * wall_dir.Y
        v = -origin.Z
        
        bb = face.GetBoundingBox()
        z = (bb.Min.V + bb.Max.V) / 2 + origin.Z
        
        pt = XYZ(x, y, z)
        
        if not s.IsActive: s.Activate()
        uv = UV(u, z - origin.Z)
        inst = doc.Create.NewFamilyInstance(face, uv, 0, s)
        ok_fb_ceil += 1
        
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
        
        # Spin Z
        face_normal_angle = math.atan2(normal.Y, normal.X)
        spin_rot = face_normal_angle
        if spin_rot != 0:
            axis = Line.CreateBound(pt, XYZ(x, y, z + 1))
            from Autodesk.Revit.DB import ElementTransformUtils
            ElementTransformUtils.RotateElement(doc, inst.Id, axis, spin_rot)
    
    # Mark único
    mark = "F01|TF 01"
    if 'id_bloque' in dev:
        mark = "F01|TF 01|{}".format(dev['id_bloque'])
    mark_param = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if mark_param: mark_param.Set(mark)

t.Commit()
print("F01 colocados: FB-Muro={}, FB-Techo={}, Level={}, Total={}, Skipped={}".format(
    ok_fb_wall, ok_fb_ceil, ok_lb, ok_fb_wall + ok_fb_ceil + ok_lb, skipped))