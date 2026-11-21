# F6_COLOCAR_XPL_TOMAS_FINAL.py - WorkPlaneBased en MURO
# Versión correcta basada en v09 que SÍ funciona

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import traceback

APTO_OBJETIVO = 'TF 01a'
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURAS_MM = {
    'M_Toma doble': 1000,
    'M_Comunicaciones': 1000,
}

FAMILIAS_ROTAR_90 = {'M_Toma doble', 'M_Comunicaciones'}
TIPOS_OBJETIVO = ['M_Toma doble', 'M_Comunicaciones']

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("="*60)
print("F6_COLOCAR_XPL_TOMAS_FINAL - WorkPlaneBased en Muro")
print("APTO:", APTO_OBJETIVO)
print("="*60)

# Load data
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

tomas = [d for d in data['dispositivos'] 
         if d['apto_asignado'] == APTO_OBJETIVO and d['familia_revit'] in TIPOS_OBJETIVO]
print("Tomas en {}: {}".format(APTO_OBJETIVO, len(tomas)))

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

# WALLS: vertical PlanarFace + Reference
print("Indexing walls Piso 5...")

walls_data = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType():
    if w.LevelId != level_piso5_id: continue
    try:
        geom_opt = Options(); geom_opt.ComputeReferences = True
        for obj in w.get_Geometry(geom_opt):
            if isinstance(obj, Solid):
                for face in obj.Faces:
                    if isinstance(face, PlanarFace):
                        n = face.ComputeNormal(UV(0.5, 0.5))
                        if abs(n.Z) < 0.1:  # vertical wall
                            ref = face.Reference
                            if ref:
                                bbox = w.get_BoundingBox(None)
                                if bbox:
                                    walls_data.append({
                                        'face': face, 'reference': ref, 'normal': n,
                                        'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                                        'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y
                                    })
    except: pass

print("  Walls with vertical face + Reference: {}".format(len(walls_data)))

def find_wall_face(x, y, z, max_d=10.0):
    pt = XYZ(x, y, z)
    best = None; best_dist = float('inf')
    for wd in walls_data:
        if x < wd['xmin']-max_d or x > wd['xmax']+max_d: continue
        if y < wd['ymin']-max_d or y > wd['ymax']+max_d: continue
        try:
            res = wd['face'].Project(pt)
            if res:
                uv = res.UVPoint if hasattr(res, 'UVPoint') else res
                p = wd['face'].Evaluate(uv)
                d = ((p.X-x)**2 + (p.Y-y)**2)**0.5
                if d < best_dist and d < max_d:
                    best_dist = d; best = (wd['face'], wd['reference'], wd['normal'], p)
        except: pass
    return best

def generate_mark(d):
    return "TOMA_{}_{}_{}".format(
        d['familia_revit'].replace('M_','').replace(' ','')[:8],
        d['tipo_revit'].replace(' ','')[:6],
        int(round(d['x_mm'])), int(round(d['y_mm']))
    )

# MAIN
t = Transaction(doc, "Place Tomas {}".format(APTO_OBJETIVO))
t.Start()

MM_TO_FT = 0.003280839895
placed = 0
warnings = []

for d in tomas:
    x = d['x_mm'] * MM_TO_FT
    y = d['y_mm'] * MM_TO_FT
    fam = d['familia_revit']
    z_mm = ALTURAS_MM.get(fam, NIVEL_PISO5_ELEV_MM)
    z = z_mm * MM_TO_FT
    
    symbol = symbols.get(fam)
    if not symbol: continue
    
    rot = math.radians(d['rotacion_grados'])
    if fam in FAMILIAS_ROTAR_90: rot += math.pi / 2
    
    inst = None
    try:
        res = find_wall_face(x, y, z)
        if res:
            face, host_ref, wall_normal, pt_on_face = res
            target_z = pt_on_face.Z
            host_info = "muro face Z={:.4f}".format(target_z)
            
            # WORKPLANEBASED: NewFamilyInstance(Reference, XYZ, XYZ, FamilySymbol)
            loc_pt = XYZ(x, y, target_z)
            ref_dir = wall_normal.CrossProduct(XYZ(0,0,1)).Normalize()  # horizontal along wall
            if ref_dir.GetLength() < 0.1: ref_dir = XYZ(1,0,0)
            
            inst = doc.Create.NewFamilyInstance(host_ref, loc_pt, ref_dir, symbol)
            
            # Rotation: vertical axis
            if abs(rot) > 1e-6:
                axis = Line.CreateBound(loc_pt, loc_pt + XYZ(0,0,10))
                ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot)
            
            # Mark
            m = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if m: m.Set(generate_mark(d))
            
            placed += 1
            print("  OK: {} @ ({:.2f},{:.2f},{:.2f}) host=wall".format(d['nombre_dxf'], x, y, target_z))
        else:
            # Fallback level-based
            pt = XYZ(x, y, level_piso5_elev_ft + z)
            inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
            p = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            if p: p.Set(level_piso5_id)
            if abs(rot) > 1e-6:
                loc = inst.Location
                if hasattr(loc, 'Rotation'): loc.Rotation = rot
            warnings.append("Fallback: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
            print("  FALLBACK: {} @ ({:.2f},{:.2f},{:.2f})".format(d['nombre_dxf'], x, y, level_piso5_elev_ft + z))
    
    except Exception as ex:
        warnings.append("{}: {}".format(d['nombre_dxf'], str(ex)))

t.Commit()
print("\nPlaced on wall: {}, Fallback: {}, Warnings: {}".format(placed, len([w for w in warnings if 'Fallback' in w]), len(warnings)))
for w in warnings[:10]: print("  WARN:", w)
