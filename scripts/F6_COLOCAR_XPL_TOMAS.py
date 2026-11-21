"""
F6_COLOCAR_XPL_TOMAS.py - v04 (LineBased correcto)
Version: 04
Date: 2026-11-19
Time: 17:30
LineBased families -> Crear ModelLine en cara muro -> Usar línea como host
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import traceback
from System import Int64

APTO_OBJETIVO = 'TF 01a'
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURAS_MM = {
    'M_Toma doble': 1000,
    'M_Comunicaciones': 1000,
}

FAMILIAS_ROTAR_90 = {'M_Toma doble', 'M_Comunicaciones'}

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("="*60)
print("F6_COLOCAR_XPL_TOMAS v04 - LineBased con ModelLine host")
print("Date: 2026-11-19 17:30")
print("APTO_OBJETIVO:", APTO_OBJETIVO)
print("="*60)

print("Cargando JSON para {} (solo Tomas)...".format(APTO_OBJETIVO))
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

tomas = [d for d in data['dispositivos'] 
         if d['apto_asignado'] == APTO_OBJETIVO and d['familia_revit'] in ('M_Toma doble', 'M_Comunicaciones')]
print("Tomas en {}: {}".format(APTO_OBJETIVO, len(tomas)))

if not tomas:
    print("¡SIN TOMAS!")
    import sys
    sys.exit(0)

level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break

level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation
print("Nivel Piso 5: {} (Id={}, Elev={:.4f} ft)".format(level_piso5.Name, level_piso5_id, level_piso5_elev_ft))

# ─── SÍMBOLOS ─────────────────────────────────────────────
symbol_cache = {}
collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
for s in collector:
    if s.Family.Name in ('M_Toma doble', 'M_Comunicaciones'):
        fam_name = s.Family.Name
        if fam_name not in symbol_cache:
            symbol_cache[fam_name] = s

to_activate = [sym for sym in symbol_cache.values() if not sym.IsActive]
if to_activate:
    t_act = Transaction(doc, "Activar simbolos tomas")
    t_act.Start()
    for sym in to_activate:
        sym.Activate()
    t_act.Commit()
    print("  Activados {} simbolos".format(len(to_activate)))
else:
    print("  Simbolos ya activos")

# ─── MUROS: PlanarFace + Normal ──────────────────────────
print("Indexando muros Piso 5...")

walls_data = []
collector = FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType()
for w in collector:
    if w.LevelId == level_piso5_id:
        try:
            geom_opt = Options()
            geom_opt.ComputeReferences = True
            geom = w.get_Geometry(geom_opt)
            face_data = []
            for obj in geom:
                if isinstance(obj, Solid):
                    for face in obj.Faces:
                        if isinstance(face, PlanarFace):
                            normal = face.ComputeNormal(UV(0.5, 0.5))
                            if abs(normal.Z) < 0.1:  # vertical
                                face_data.append({'face': face, 'ref': face.Reference, 'normal': normal})
            if face_data:
                bbox = w.get_BoundingBox(None)
                if bbox:
                    walls_data.append({'wall': w, 'faces': face_data,
                        'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                        'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y})
        except:
            continue

print("  Muros con PlanarFace: {}".format(len(walls_data)))

# ─── SKETCH PLANE para ModelLines (vertical plane on wall) ───
def create_wall_sketch_plane(face, face_ref):
    """Create sketch plane on wall face for ModelLine"""
    return SketchPlane.Create(doc, face_ref)

def find_wall_face(x_ft, y_ft, z_ft, max_dist_ft=10.0):
    """Returns (face, ref, normal, sketch_plane)"""
    pt = XYZ(x_ft, y_ft, z_ft)
    best = None
    best_dist = float('inf')
    for wd in walls_data:
        if x_ft < wd['xmin'] - max_dist_ft or x_ft > wd['xmax'] + max_dist_ft: continue
        if y_ft < wd['ymin'] - max_dist_ft or y_ft > wd['ymax'] + max_dist_ft: continue
        for fd in wd['faces']:
            try:
                result = fd['face'].Project(pt)
                if result:
                    if hasattr(result, 'UVPoint'):
                        uv = result.UVPoint
                    else:
                        uv = result
                    pt_on_face = fd['face'].Evaluate(uv)
                    dist = ((pt_on_face.X - x_ft)**2 + (pt_on_face.Y - y_ft)**2)**0.5
                    if dist < best_dist and dist < max_dist_ft:
                        best_dist = dist
                        sketch_plane = SketchPlane.Create(doc, fd['ref'])
                        best = (fd['face'], fd['ref'], fd['normal'], sketch_plane, pt_on_face)
            except:
                continue
    return best

def generate_mark(d):
    x_int = int(round(d['x_mm']))
    y_int = int(round(d['y_mm']))
    fam_short = d['familia_revit'].replace('M_', '').replace(' ', '')[:8]
    typ_short = d['tipo_revit'].replace(' ', '')[:6]
    return "TOMA_{}_{}_{}".format(fam_short, typ_short, x_int, y_int)

# ─── TRANSACCIÓN ─────────────────────────────────────────
print("\n" + "="*60)
print("COLOCANDO TOMAS {} - LineBased con ModelLine host".format(APTO_OBJETIVO))
print("="*60)

t = Transaction(doc, "Colocar Tomas {}".format(APTO_OBJETIVO))
t.Start()

MM_TO_FT = 0.003280839895
placed = 0
warnings = []
created_lines = []  # track for cleanup if needed

for d in tomas:
    x_ft = d['x_mm'] * MM_TO_FT
    y_ft = d['y_mm'] * MM_TO_FT
    base_z_mm = ALTURAS_MM.get(d['familia_revit'], NIVEL_PISO5_ELEV_MM)
    device_z_ft = base_z_mm * MM_TO_FT
    
    symbol = symbol_cache.get(d['familia_revit'])
    if not symbol:
        warnings.append("Sin simbolo: {}".format(d['familia_revit']))
        continue
    
    rot_rad = math.radians(d['rotacion_grados'])
    if d['familia_revit'] in FAMILIAS_ROTAR_90:
        rot_rad += math.pi / 2
    
    inst = None
    try:
        result = find_wall_face(x_ft, y_ft, device_z_ft)
        if result:
            face, face_ref, wall_normal, sketch_plane, pt_on_face = result
            
            # CREAR MODEL LINE horizontal en la cara del muro
            # La línea va en dirección horizontal (perpendicular a normal del muro)
            # Usamos dirección horizontal arbitraria para la línea host
            line_dir = wall_normal.CrossProduct(XYZ(0, 0, 1)).Normalize()  # horizontal along wall
            if line_dir.GetLength() < 0.1:
                line_dir = XYZ(1, 0, 0)  # fallback
            
            # Línea de 100mm centrada en el punto
            half_len = 0.164  # ~50mm in feet
            line_start = pt_on_face - line_dir * half_len
            line_end = pt_on_face + line_dir * half_len
            
            # Crear ModelLine en el sketch plane del muro
            model_line = doc.Create.NewModelCurve(Line.CreateBound(line_start, line_end), sketch_plane)
            created_lines.append(model_line.Id)
            
            # Colocar familia LineBased en la ModelLine
            # NewFamilyInstance para LineBased: (Curve, FamilySymbol)
            inst = doc.Create.NewFamilyInstance(model_line.GeometryCurve, symbol)
            
            # Mover a Z correcto si es necesario
            loc = inst.Location
            if loc:
                actual_pt = loc.Point
                if abs(actual_pt.Z - device_z_ft) > 0.01:
                    move_vec = XYZ(0, 0, device_z_ft - actual_pt.Z)
                    ElementTransformUtils.MoveElement(doc, inst.Id, move_vec)
            
            # Rotación adicional si necesario
            if abs(rot_rad) > 0.01:
                try:
                    if hasattr(loc, 'Rotation'):
                        loc.Rotation = rot_rad
                except:
                    pass
            
            placed += 1
            print("  OK (LineBased+ModelLine): {} @ ({:.2f},{:.2f},{:.2f})".format(
                d['nombre_dxf'], x_ft, y_ft, device_z_ft))
        else:
            # Fallback level-based
            z_ft = level_piso5_elev_ft + device_z_ft
            pt = XYZ(x_ft, y_ft, z_ft)
            inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
            p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            if p_level: p_level.Set(level_piso5_id)
            warnings.append("Fallback level: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
            print("  FALLBACK: {} @ ({:.2f},{:.2f},{:.2f})".format(d['nombre_dxf'], x_ft, y_ft, z_ft))
            
            if abs(rot_rad) > 0.01:
                try:
                    loc = inst.Location
                    if hasattr(loc, 'Rotation'):
                        loc.Rotation = rot_rad
                except:
                    pass
        
        if inst:
            mark = generate_mark(d)
            p_mark = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mark:
                p_mark.Set(mark)
                
    except Exception as ex:
        tb = traceback.format_exc()
        warnings.append("Error {}: {} | {}".format(d['nombre_dxf'], str(ex), tb))
        print("  EXCEPTION for {}: {}".format(d['nombre_dxf'], str(ex)))

t.Commit()
print("Transacción completada.")

print("\n{} - RESUMEN TOMAS:".format(APTO_OBJETIVO))
print("  LineBased + ModelLine:  {}".format(placed))
print("  TOTAL:                    {}".format(placed))
print("  ModelLines creadas:       {}".format(len(created_lines)))
print("  Warnings:                 {}".format(len(warnings)))

for w in warnings:
    print("    WARN: {}".format(w))