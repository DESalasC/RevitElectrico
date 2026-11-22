"""
F6_COLOCAR_XPL_TOMAS_FIX_CLUSTER.py - v12
Version: 12
Date: 2026-11-20
Fix: Tolerancia adaptativa por lado + aceptar ambas caras (dot >= -0.5)
     Log detallado para debugging clusters
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import traceback

APTO_OBJETIVO = 'B15'
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURAS_MM = {
    'M_Toma doble': 1000,
    'M_Comunicaciones': 1000,
}

# Tolerancias por lado (mm)
WALL_TOLERANCE = {
    'SOUTH': 300,   # muro perimetral sur
    'EAST': 300,    # muro perimetral este
    'WEST': 500,    # muro perimetral oeste + interiores
    'NORTH': 1200,  # interior: muros de habitaciones, mayor tolerancia
}

FAMILIAS_ROTAR_90 = {'M_Toma doble', 'M_Comunicaciones'}

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("="*60)
print("F6_COLOCAR_XPL_TOMAS_FIX_CLUSTER v12 - Tolerancia por lado")
print("APTO:", APTO_OBJETIVO)
print("="*60)

with open(JSON_PATH, 'r') as f:
    data = json.load(f)

tomas = [d for d in data['dispositivos'] 
         if d['apto_asignado'] == APTO_OBJETIVO and d['familia_revit'] in ('M_Toma doble', 'M_Comunicaciones')]
print("Tomas en {}: {}".format(APTO_OBJETIVO, len(tomas)))

# BBOX apartamento
xs = [d['x_mm'] for d in tomas]
ys = [d['y_mm'] for d in tomas]
apt_bbox_mm = {'xmin': min(xs), 'xmax': max(xs), 'ymin': min(ys), 'ymax': max(ys)}
apt_center_x = (apt_bbox_mm['xmin'] + apt_bbox_mm['xmax']) / 2.0
apt_center_y = (apt_bbox_mm['ymin'] + apt_bbox_mm['ymax']) / 2.0

# Level Piso 5
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break
level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation

# Symbols
symbols = {}
for fam_name in ('M_Toma doble', 'M_Comunicaciones'):
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.Family.Name == fam_name:
            symbols[fam_name] = s
            if not s.IsActive: s.Activate()
            break

# ===== FILTRO ROBUSTO DE NIVEL =====
def _get_element_level_id(elem):
    try:
        lid = elem.LevelId
        if lid is not None and lid != ElementId.InvalidElementId(): return lid
    except: pass
    try:
        p = elem.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if p is not None: return p.AsElementId()
    except: pass
    try:
        p = elem.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
        if p is not None: return p.AsElementId()
    except: pass
    try:
        p = elem.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if p is not None: return p.AsElementId()
    except: pass
    return None

def _is_in_level(elem, target_level_id):
    if target_level_id is None: return True
    lid = _get_element_level_id(elem)
    if lid is None: return False
    return lid == target_level_id

# ===== CARGAR MUROS PISO 5 =====
print("Cargando muros Piso 5...")
all_walls_raw = list(FilteredElementCollector(doc).OfClass(Wall).ToElements())
all_walls = []
for w in all_walls_raw:
    try:
        if w.WallType is None: continue
        if _is_in_level(w, level_piso5_id):
            all_walls.append(w)
    except: pass
print("Muros Piso 5: {}".format(len(all_walls)))

# Pre-calcular geometría
geom_opt = Options()
geom_opt.ComputeReferences = True

wall_faces = []
for wall in all_walls:
    loc = wall.Location
    if not isinstance(loc, LocationCurve): continue
    curve = loc.Curve
    if not curve: continue
    try:
        p0 = curve.GetEndPoint(0); p1 = curve.GetEndPoint(1)
        wall_dir_v = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0)
        wlen = wall_dir_v.GetLength()
        if wlen < 1e-9: continue
        wall_dir = wall_dir_v.Normalize()
        wall_cx = (p0.X + p1.X) / 2.0
        wall_cy = (p0.Y + p1.Y) / 2.0
    except: continue
    
    geom = wall.get_Geometry(geom_opt)
    if not geom: continue
    for obj in geom:
        if not isinstance(obj, Solid): continue
        for face in obj.Faces:
            if not isinstance(face, PlanarFace): continue
            n = face.FaceNormal
            if abs(n.Z) > 0.1: continue
            ref = face.Reference
            if not ref: continue
            try:
                fbox = face.GetBoundingBox()
                u_min, u_max = fbox.Min.U, fbox.Max.U
                v_min, v_max = fbox.Min.V, fbox.Max.V
            except: continue
            dx = wall_cx - (apt_center_x * 0.003280839895)
            dy = wall_cy - (apt_center_y * 0.003280839895)
            if abs(dx) > abs(dy):
                side = 'EAST' if dx > 0 else 'WEST'
            else:
                side = 'NORTH' if dy > 0 else 'SOUTH'
            wall_faces.append({
                'face': face, 'ref': ref, 'normal': n,
                'wall_dir': wall_dir, 'curve': curve,
                'u_min': u_min, 'u_max': u_max,
                'v_min': v_min, 'v_max': v_max,
                'side': side,
            })

print("Caras verticales: {}".format(len(wall_faces)))
for s in ('NORTH', 'SOUTH', 'EAST', 'WEST'):
    cnt = len([w for w in wall_faces if w['side'] == s])
    print("  {}: {} (tol={}mm)".format(s, cnt, WALL_TOLERANCE[s]))

MM_TO_FT = 0.003280839895
TOL_FT = {s: v * MM_TO_FT for s, v in WALL_TOLERANCE.items()}

def dist_xy_to_curve(curve, tx, ty):
    if isinstance(curve, Line):
        sp = curve.GetEndPoint(0); ep = curve.GetEndPoint(1)
        x1, y1 = sp.X, sp.Y; x2, y2 = ep.X, ep.Y
        dx, dy = x2 - x1, y2 - y1
        seg2 = dx*dx + dy*dy
        if seg2 < 1e-12: return math.hypot(tx-x1, ty-y1)
        t = ((tx-x1)*dx + (ty-y1)*dy) / seg2
        t = max(0.0, min(1.0, t))
        cx = x1 + t*dx; cy = y1 + t*dy
        return math.hypot(tx-cx, ty-cy)
    best = float('inf')
    for i in range(24):
        u = float(i)/24.0
        try:
            p = curve.Evaluate(u, False)
            d = math.hypot(tx-p.X, ty-p.Y)
            if d < best: best = d
        except: pass
    return best

def get_device_side(x_ft, y_ft):
    dx = x_ft - apt_center_x * MM_TO_FT
    dy = y_ft - apt_center_y * MM_TO_FT
    if abs(dx) > abs(dy):
        return 'EAST' if dx > 0 else 'WEST'
    else:
        return 'NORTH' if dy > 0 else 'SOUTH'

def find_wall_face_on_side(target_xyz, target_side, tolerance_ft):
    tx, ty, tz = target_xyz.X, target_xyz.Y, target_xyz.Z
    best = None; best_d = float('inf')
    for wf in wall_faces:
        if wf['side'] != target_side: continue
        d_xy = dist_xy_to_curve(wf['curve'], tx, ty)
        if d_xy > tolerance_ft: continue
        try:
            proj = wf['face'].Project(target_xyz)
            if not proj: continue
            pt_on_face = proj.XYZPoint
            uv = proj.UVPoint
            if not (wf['u_min']-0.01 <= uv.U <= wf['u_max']+0.01 and
                    wf['v_min']-0.01 <= uv.V <= wf['v_max']+0.01):
                continue
            # Aceptar ambas caras: normal hacia el punto O desde el punto (dot >= -0.5)
            vec = target_xyz - pt_on_face
            if vec.GetLength() > 1e-6:
                dot = wf['normal'].DotProduct(vec) / vec.GetLength()
                if dot < -0.5:  # solo rechazar si normal apunta MUY en contra
                    continue
            if d_xy < best_d:
                best_d = d_xy
                best = (wf['ref'], wf['normal'], pt_on_face, wf['wall_dir'], d_xy)
        except: pass
    return best

def generate_mark(d):
    return "{}_{}_{}_{}".format(
        d['familia_revit'].replace('M_','').replace(' ','')[:8],
        d['tipo_revit'].replace(' ','')[:6],
        int(round(d['x_mm'])), int(round(d['y_mm']))
    )

# ===== TRANSACCIÓN =====
t = Transaction(doc, "Place Tomas {} - Side Tol v12".format(APTO_OBJETIVO))
t.Start()

placed_wall = 0
placed_fallback = 0
warnings = []

for d in tomas:
    x = d['x_mm'] * MM_TO_FT
    y = d['y_mm'] * MM_TO_FT
    fam = d['familia_revit']
    z_mm = ALTURAS_MM.get(fam, NIVEL_PISO5_ELEV_MM)
    z_ft = z_mm * MM_TO_FT
    
    symbol = symbols.get(fam)
    if not symbol: continue
    
    rot = math.radians(d['rotacion_grados'])
    if fam in FAMILIAS_ROTAR_90:
        rot += math.pi / 2
    
    target_z = level_piso5_elev_ft + z_ft
    pt = XYZ(x, y, target_z)
    
    device_side = get_device_side(x, y)
    tol_ft = TOL_FT[device_side]
    
    inst = None
    method = None
    face_normal = None
    face_pt = None
    
    # Buscar en lado propio
    wall_result = find_wall_face_on_side(pt, device_side, tol_ft)
    
    # Fallback: lados adyacentes con su tolerancia
    if wall_result is None:
        adjacent = {
            'NORTH': [('WEST', TOL_FT['WEST']), ('EAST', TOL_FT['EAST'])],
            'SOUTH': [('WEST', TOL_FT['WEST']), ('EAST', TOL_FT['EAST'])],
            'EAST': [('NORTH', TOL_FT['NORTH']), ('SOUTH', TOL_FT['SOUTH'])],
            'WEST': [('NORTH', TOL_FT['NORTH']), ('SOUTH', TOL_FT['SOUTH'])]
        }
        for adj_side, adj_tol in adjacent.get(device_side, []):
            wall_result = find_wall_face_on_side(pt, adj_side, adj_tol)
            if wall_result:
                method = "WALL-FACE-ADJ-{}".format(adj_side)
                break
    
    if wall_result:
        face_ref, face_normal, face_pt, wall_dir, d_xy = wall_result
        try:
            direction = XYZ.BasisZ
            try:
                inst = doc.Create.NewFamilyInstance(face_ref, face_pt, direction, symbol)
            except Exception as e_amb:
                if "Multiple targets" in str(e_amb):
                    inst = doc.Create.NewFamilyInstance(face_ref, face_pt, direction, symbol, ElementId.InvalidElementId)
                else:
                    raise
            if method is None: method = "WALL-FACE-{}".format(device_side)
            placed_wall += 1
            # Debug: log cluster NORTE
            if device_side == 'NORTH' and fam == 'M_Comunicaciones':
                print("  DEBUG NORTE: {} d_xy={:.3f}ft face_normal=({:.2f},{:.2f},{:.2f})".format(
                    d['nombre_dxf'], d_xy, face_normal.X, face_normal.Y, face_normal.Z))
        except Exception as we:
            print("  (wall failed): {}".format(str(we)[:80]))
            inst = None
    
    if inst is None:
        pt_fb = XYZ(x, y, target_z)
        inst = doc.Create.NewFamilyInstance(pt_fb, symbol, level_piso5, Structure.StructuralType.NonStructural)
        p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
        if p_level: p_level.Set(level_piso5_id)
        placed_fallback += 1
        method = "LEVEL-FALLBACK"
        warnings.append("Fallback: {} @ ({:.0f},{:.0f}) side={} tol={}mm".format(
            d['nombre_dxf'], d['x_mm'], d['y_mm'], device_side, WALL_TOLERANCE[device_side]))
    
    # Rotación
    if abs(rot) > 1e-6 and face_normal is not None and face_pt is not None:
        try:
            axis = Line.CreateBound(face_pt, face_pt + face_normal * 10.0)
            ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot)
        except:
            try:
                axis = Line.CreateBound(face_pt, XYZ(face_pt.X, face_pt.Y, face_pt.Z + 10.0))
                ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot)
            except:
                pass
    
    # Mark
    mark = generate_mark(d)
    p_mark = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if p_mark: p_mark.Set(mark)
    
    print("  OK [{}]: {} @ ({:.2f},{:.2f},{:.2f}) side={}".format(
        method, d['nombre_dxf'], x, y, target_z, device_side))

t.Commit()

print("\nResumen:")
print("  Wall-hosted: {}".format(placed_wall))
print("  Level-fallback: {}".format(placed_fallback))
for w in warnings: print("  WARN:", w)