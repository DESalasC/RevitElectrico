"""
F6_COLOCAR_XPL_APTO.py - WorkPlaneBased CORREGIDO
SketchPlane.Create necesita PlanarFace, no Reference genérico.
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import sys
import json
import math
from System import Int64

APTO_OBJETIVO = 'F17'
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURAS_MM = {
    'M_Toma doble': 1000,
    'M_Comunicaciones': 1000,
    'M_Interruptores': 1100,
    'M_Pulsador - Interruptor': 1100,
    'M_Timbre': 2400,
    'M_ClimatizacionV': 2700,
    'M_Iluminacion': 2700,
    'EA': 2400,
}

FAMILIAS_ROTAR_90 = {'M_Toma doble', 'M_Comunicaciones', 'M_Interruptores', 'M_Pulsador - Interruptor'}

def classify_device(fam_name):
    if fam_name in ('M_Toma doble', 'M_Comunicaciones'):
        return 'WORK_PLANE_WALL'
    if fam_name in ('M_Iluminacion', 'M_ClimatizacionV'):
        return 'WORK_PLANE_CEILING'
    if 'Interruptor' in fam_name or fam_name in ('M_Pulsador - Interruptor', 'M_Timbre', 'EA'):
        return 'LEVEL'
    return 'LEVEL'

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("Cargando JSON para {}...".format(APTO_OBJETIVO))
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

dispositivos = [d for d in data['dispositivos'] if d['apto_asignado'] == APTO_OBJETIVO]
print("Dispositivos en {}: {}".format(APTO_OBJETIVO, len(dispositivos)))

level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break

level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation

# ─── CACHÉ SÍMBOLOS ──────────────────────────────────────
print("Cacheando simbolos...")
symbol_cache = {}
collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
for s in collector:
    fam_name = s.Family.Name
    type_name = s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
    fpt = int(s.Family.FamilyPlacementType)
    if fam_name not in symbol_cache:
        symbol_cache[fam_name] = {}
    symbol_cache[fam_name][type_name] = (s, fpt)

for fam in set(d['familia_revit'] for d in dispositivos):
    if fam in symbol_cache:
        for typ, (sym, fpt) in symbol_cache[fam].items():
            if not sym.IsActive:
                sym.Activate()

def get_symbol(fam_name, type_name):
    if fam_name in symbol_cache and type_name in symbol_cache[fam_name]:
        return symbol_cache[fam_name][type_name]
    if fam_name in symbol_cache and symbol_cache[fam_name]:
        return list(symbol_cache[fam_name].values())[0]
    return None

# ─── CACHÉ ESPACIAL: guardar PLANARFACE y Reference ──────
print("Indexando muros y techos Piso 5...")

walls_data = []  # each: {'wall', 'faces': [(face, ref)], bbox}
collector = FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType()
for w in collector:
    if w.LevelId == level_piso5_id:
        try:
            geom_opt = Options()
            geom_opt.ComputeReferences = True
            geom = w.get_Geometry(geom_opt)
            face_refs = []
            for obj in geom:
                if isinstance(obj, Solid):
                    for face in obj.Faces:
                        if isinstance(face, PlanarFace):
                            normal = face.ComputeNormal(UV(0.5, 0.5))
                            if abs(normal.Z) < 0.1:  # vertical wall
                                face_refs.append((face, face.Reference))
            if face_refs:
                bbox = w.get_BoundingBox(None)
                if bbox:
                    walls_data.append({'wall': w, 'faces': face_refs,
                        'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                        'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y})
        except:
            continue

ceilings_data = []  # each: {'ceiling', 'faces': [(face, ref)], bbox, z}
collector = FilteredElementCollector(doc).OfClass(Ceiling).WhereElementIsNotElementType()
for c in collector:
    if c.LevelId == level_piso5_id:
        try:
            geom_opt = Options()
            geom_opt.ComputeReferences = True
            geom = c.get_Geometry(geom_opt)
            face_refs = []
            for obj in geom:
                if isinstance(obj, Solid):
                    for face in obj.Faces:
                        if isinstance(face, PlanarFace):
                            normal = face.ComputeNormal(UV(0.5, 0.5))
                            if normal.Z < -0.1:  # bottom face
                                face_refs.append((face, face.Reference))
            if face_refs:
                bbox = c.get_BoundingBox(None)
                if bbox:
                    z = face_refs[0][0].Evaluate(UV(0.5, 0.5)).Z
                    ceilings_data.append({'ceiling': c, 'faces': face_refs,
                        'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                        'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y, 'z': z})
        except:
            continue

print("  Muros (con PlanarFace): {}, Techos: {}".format(len(walls_data), len(ceilings_data)))

def find_wall_plane(x_ft, y_ft, z_ft, max_dist_ft=10.0):
    """Returns (PlanarFace, Reference) for SketchPlane"""
    pt = XYZ(x_ft, y_ft, z_ft)
    best_face = None
    best_ref = None
    best_dist = float('inf')
    for wd in walls_data:
        if x_ft < wd['xmin'] - max_dist_ft or x_ft > wd['xmax'] + max_dist_ft: continue
        if y_ft < wd['ymin'] - max_dist_ft or y_ft > wd['ymax'] + max_dist_ft: continue
        for face, ref in wd['faces']:
            try:
                result = face.Project(pt)
                if result:
                    if hasattr(result, 'UVPoint'):
                        uv = result.UVPoint
                    else:
                        uv = result
                    pt_on_face = face.Evaluate(uv)
                    dist = ((pt_on_face.X - x_ft)**2 + (pt_on_face.Y - y_ft)**2)**0.5
                    if dist < best_dist and dist < max_dist_ft:
                        best_dist = dist
                        best_face = face
                        best_ref = ref
            except:
                continue
    return best_face, best_ref

def find_ceiling_plane(x_ft, y_ft, max_dist_ft=10.0):
    """Returns (PlanarFace, Reference, ceiling_z) for SketchPlane"""
    pt_xy = XYZ(x_ft, y_ft, 0)
    best_face = None
    best_ref = None
    best_z = None
    best_dist = float('inf')
    for cd in ceilings_data:
        if x_ft < cd['xmin'] - max_dist_ft or x_ft > cd['xmax'] + max_dist_ft: continue
        if y_ft < cd['ymin'] - max_dist_ft or y_ft > cd['ymax'] + max_dist_ft: continue
        for face, ref in cd['faces']:
            try:
                result = face.Project(pt_xy)
                if result:
                    if hasattr(result, 'UVPoint'):
                        uv = result.UVPoint
                    else:
                        uv = result
                    pt_on_face = face.Evaluate(uv)
                    dist = ((pt_on_face.X - x_ft)**2 + (pt_on_face.Y - y_ft)**2)**0.5
                    if dist < best_dist and dist < max_dist_ft:
                        best_dist = dist
                        best_face = face
                        best_ref = ref
                        best_z = pt_on_face.Z
            except:
                continue
    return best_face, best_ref, best_z

def generate_mark(d):
    x_int = int(round(d['x_mm']))
    y_int = int(round(d['y_mm']))
    fam_short = d['familia_revit'].replace('M_', '').replace(' ', '')[:8]
    typ_short = d['tipo_revit'].replace(' ', '')[:6]
    return "{}_{}_{}_{}".format(fam_short, typ_short, x_int, y_int)

# ─── TRANSACCIÓN ─────────────────────────────────────────
print("\n" + "="*60)
print("COLOCANDO {} - WorkPlaneBased con PlanarFace".format(APTO_OBJETIVO))
print("="*60)

t = Transaction(doc, "Colocar dispositivos {}".format(APTO_OBJETIVO))
t.Start()

MM_TO_FT = 0.003280839895
placed_wp_wall = 0
placed_wp_ceiling = 0
placed_level = 0
warnings = []

for d in dispositivos:
    x_ft = d['x_mm'] * MM_TO_FT
    y_ft = d['y_mm'] * MM_TO_FT
    base_z_mm = ALTURAS_MM.get(d['familia_revit'], NIVEL_PISO5_ELEV_MM)
    device_z_ft = base_z_mm * MM_TO_FT
    
    symbol_data = get_symbol(d['familia_revit'], d['tipo_revit'])
    if not symbol_data:
        warnings.append("Sin simbolo: {} / {}".format(d['familia_revit'], d['tipo_revit']))
        continue
    
    symbol, fpt_int = symbol_data
    classification = classify_device(d['familia_revit'])
    
    rot_rad = math.radians(d['rotacion_grados'])
    if d['familia_revit'] in FAMILIAS_ROTAR_90:
        rot_rad += math.pi / 2
    
    inst = None
    try:
        if classification == 'WORK_PLANE_WALL':
            face, face_ref = find_wall_plane(x_ft, y_ft, device_z_ft)
            if face and face_ref:
                pt = XYZ(x_ft, y_ft, device_z_ft)
                # Create SketchPlane from PlanarFace
                sketch_plane = SketchPlane.Create(doc, face_ref)
                inst = doc.Create.NewFamilyInstance(pt, symbol, sketch_plane)
                placed_wp_wall += 1
                print("  OK: WP-Wall {} @ ({:.2f},{:.2f},{:.2f})".format(d['nombre_dxf'], x_ft, y_ft, device_z_ft))
            else:
                # Fallback level-based
                z_ft = level_piso5_elev_ft + device_z_ft
                pt = XYZ(x_ft, y_ft, z_ft)
                inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
                p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                if p_level: p_level.Set(level_piso5_id)
                placed_level += 1
                warnings.append("WP-Wall fallback level: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
                
        elif classification == 'WORK_PLANE_CEILING':
            face, face_ref, ceiling_z = find_ceiling_plane(x_ft, y_ft)
            if face and face_ref and ceiling_z:
                pt = XYZ(x_ft, y_ft, ceiling_z)
                sketch_plane = SketchPlane.Create(doc, face_ref)
                inst = doc.Create.NewFamilyInstance(pt, symbol, sketch_plane)
                placed_wp_ceiling += 1
                print("  OK: WP-Ceiling {} @ ({:.2f},{:.2f},{:.2f})".format(d['nombre_dxf'], x_ft, y_ft, ceiling_z))
            else:
                z_ft = level_piso5_elev_ft + device_z_ft
                pt = XYZ(x_ft, y_ft, z_ft)
                inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
                p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                if p_level: p_level.Set(level_piso5_id)
                placed_level += 1
                warnings.append("WP-Ceiling fallback level: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
                
        else:  # LEVEL
            z_ft = level_piso5_elev_ft + device_z_ft
            pt = XYZ(x_ft, y_ft, z_ft)
            inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
            p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            if p_level: p_level.Set(level_piso5_id)
            placed_level += 1
            print("  OK: LEVEL {} @ ({:.2f},{:.2f},{:.2f})".format(d['nombre_dxf'], x_ft, y_ft, z_ft))
        
        if inst:
            if abs(rot_rad) > 0.01:
                try:
                    loc = inst.Location
                    if hasattr(loc, 'Rotation'):
                        loc.Rotation = rot_rad
                except:
                    pass
            
            mark = generate_mark(d)
            p_mark = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mark:
                p_mark.Set(mark)
                
    except Exception as ex:
        warnings.append("Error {}: {}".format(d['nombre_dxf'], str(ex)))

t.Commit()
print("Transacción completada.")

print("\n{} - RESUMEN:".format(APTO_OBJETIVO))
print("  WorkPlane Wall:   {}".format(placed_wp_wall))
print("  WorkPlane Ceiling: {}".format(placed_wp_ceiling))
print("  Level-based:        {}".format(placed_level))
print("  TOTAL:              {}".format(placed_wp_wall + placed_wp_ceiling + placed_level))
print("  Warnings:           {}".format(len(warnings)))

for w in warnings:
    print("    WARN: {}".format(w))