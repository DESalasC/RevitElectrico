"""
F6_COLOCAR_XPL_LINEBASED.py - FIXED API
Version: FINAL-FIXED
Date: 2026-11-19
LineBased -> ModelLine on face -> NewFamilyInstance(curve, symbol, StructuralType)
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
    'M_Iluminacion': 2700,
}

FAMILIAS_ROTAR_90 = {'M_Toma doble', 'M_Comunicaciones'}
TIPOS_OBJETIVO = ['M_Toma doble', 'M_Comunicaciones', 'M_Iluminacion']

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("="*60)
print("F6_COLOCAR_XPL_LINEBASED - FIXED")
print("APTO:", APTO_OBJETIVO)
print("="*60)

with open(JSON_PATH, 'r') as f:
    data = json.load(f)

dispositivos = [d for d in data['dispositivos'] 
                if d['apto_asignado'] == APTO_OBJETIVO and d['familia_revit'] in TIPOS_OBJETIVO]
print("Dispositivos: {}".format(len(dispositivos)))

# Level
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break
level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation

# Symbols
symbols = {}
for fam_name in TIPOS_OBJETIVO:
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.Family.Name == fam_name:
            symbols[fam_name] = s
            if not s.IsActive: s.Activate()
            break

# Walls + Ceilings: PlanarFace + Reference
print("Indexing walls/ceilings...")

walls_data = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType():
    if w.LevelId != level_piso5_id: continue
    try:
        geom_opt = Options(); geom_opt.ComputeReferences = True
        faces = []
        for obj in w.get_Geometry(geom_opt):
            if isinstance(obj, Solid):
                for face in obj.Faces:
                    if isinstance(face, PlanarFace):
                        n = face.ComputeNormal(UV(0.5, 0.5))
                        if abs(n.Z) < 0.1:
                            faces.append((face, face.Reference, n))
        if faces:
            bbox = w.get_BoundingBox(None)
            if bbox:
                walls_data.append({'faces': faces, 
                    'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                    'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y})
    except: pass

ceilings_data = []
for c in FilteredElementCollector(doc).OfClass(Ceiling).WhereElementIsNotElementType():
    if c.LevelId != level_piso5_id: continue
    try:
        geom_opt = Options(); geom_opt.ComputeReferences = True
        faces = []
        for obj in c.get_Geometry(geom_opt):
            if isinstance(obj, Solid):
                for face in obj.Faces:
                    if isinstance(face, PlanarFace):
                        n = face.ComputeNormal(UV(0.5, 0.5))
                        if n.Z < -0.1:
                            faces.append((face, face.Reference, n))
        if faces:
            bbox = c.get_BoundingBox(None)
            if bbox:
                ceilings_data.append({'faces': faces,
                    'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                    'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y})
    except: pass

print("  Walls: {}, Ceilings: {}".format(len(walls_data), len(ceilings_data)))

# Debug: print first device coords
if dispositivos:
    d = dispositivos[0]
    print("  First device: x={:.2f}ft, y={:.2f}ft".format(d['x_mm']*0.003280839895, d['y_mm']*0.003280839895))

def find_host_face(x, y, z, max_d, data_list, is_wall):
    pt = XYZ(x, y, z) if is_wall else XYZ(x, y, 0)
    best = None; best_dist = float('inf')
    for item in data_list:
        if x < item['xmin']-max_d or x > item['xmax']+max_d: continue
        if y < item['ymin']-max_d or y > item['ymax']+max_d: continue
        for face, ref, normal in item['faces']:
            try:
                res = face.Project(pt)
                if res:
                    uv = res.UVPoint if hasattr(res, 'UVPoint') else res
                    p = face.Evaluate(uv)
                    d = ((p.X-x)**2 + (p.Y-y)**2)**0.5
                    if d < best_dist and d < max_d:
                        best_dist = d; best = (face, ref, normal, p)
            except: pass
    return best

def generate_mark(d):
    return "{}_{}_{}_{}".format(
        d['familia_revit'].replace('M_','').replace(' ','')[:8],
        d['tipo_revit'].replace(' ','')[:6],
        int(round(d['x_mm'])), int(round(d['y_mm']))
    )

# MAIN
t = Transaction(doc, "Place LineBased {}".format(APTO_OBJETIVO))
t.Start()

MM_TO_FT = 0.003280839895
placed = 0
fallback = 0
warnings = []

for d in dispositivos:
    x = d['x_mm'] * MM_TO_FT
    y = d['y_mm'] * MM_TO_FT
    fam = d['familia_revit']
    z_mm = ALTURAS_MM.get(fam, NIVEL_PISO5_ELEV_MM)
    z = z_mm * MM_TO_FT
    
    symbol = symbols.get(fam)
    if not symbol:
        warnings.append("No symbol: {}".format(fam))
        continue
    
    rot = math.radians(d['rotacion_grados'])
    if fam in FAMILIAS_ROTAR_90: rot += math.pi / 2
    
    inst = None
    try:
        host_line = None
        sketch_plane = None
        place_z = z
        
        if fam in ('M_Toma doble', 'M_Comunicaciones'):  # WALL
            res = find_host_face(x, y, z, 10.0, walls_data, True)
            if res:
                face, ref, normal, pt_on_face = res
                place_z = pt_on_face.Z
                sketch_plane = SketchPlane.Create(doc, ref)
                line_dir = normal.CrossProduct(XYZ(0,0,1)).Normalize()
                if line_dir.GetLength() < 0.1: line_dir = XYZ(1,0,0)
                half = 0.164
                line = Line.CreateBound(pt_on_face - line_dir*half, pt_on_face + line_dir*half)
                host_line = doc.Create.NewModelCurve(line, sketch_plane)
        
        elif fam == 'M_Iluminacion':  # CEILING
            res = find_host_face(x, y, 0, 15.0, ceilings_data, False)
            if res:
                face, ref, normal, pt_on_face = res
                place_z = pt_on_face.Z
                sketch_plane = SketchPlane.Create(doc, ref)
                line_dir = normal.CrossProduct(XYZ(1,0,0)).Normalize()
                if line_dir.GetLength() < 0.1: line_dir = normal.CrossProduct(XYZ(0,1,0)).Normalize()
                half = 0.164
                line = Line.CreateBound(pt_on_face - line_dir*half, pt_on_face + line_dir*half)
                host_line = doc.Create.NewModelCurve(line, sketch_plane)
        
        if host_line:
            # CORRECT API: NewFamilyInstance(Curve, FamilySymbol, StructuralType)
            inst = doc.Create.NewFamilyInstance(host_line.GeometryCurve, symbol, Structure.StructuralType.NonStructural)
            # Move to exact Z
            loc = inst.Location
            if loc:
                pt = loc.Point
                if abs(pt.Z - place_z) > 0.01:
                    ElementTransformUtils.MoveElement(doc, inst.Id, XYZ(0,0,place_z - pt.Z))
            placed += 1
            print("  OK LineBased: {} @ ({:.2f},{:.2f},{:.2f})".format(d['nombre_dxf'], x, y, place_z))
        else:
            # FALLBACK: level-based at correct Z
            pt = XYZ(x, y, level_piso5_elev_ft + z)
            inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
            p = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            if p: p.Set(level_piso5_id)
            fallback += 1
            warnings.append("Fallback: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
            print("  FALLBACK: {} @ ({:.2f},{:.2f},{:.2f})".format(d['nombre_dxf'], x, y, level_piso5_elev_ft + z))
        
        if inst:
            if abs(rot) > 0.01:
                try:
                    loc = inst.Location
                    if hasattr(loc, 'Rotation'): loc.Rotation = rot
                except: pass
            m = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if m: m.Set(generate_mark(d))
    
    except Exception as ex:
        warnings.append("{}: {}".format(d['nombre_dxf'], str(ex)))

t.Commit()
print("\nLineBased placed: {}, Fallback: {}, Warnings: {}".format(placed, fallback, len(warnings)))
for w in warnings[:10]: print("  WARN:", w)