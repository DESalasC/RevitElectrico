"""
F6_COLOCAR_XPL_v02.py
=====================
Colocación dispositivos Piso 5 - VERSIÓN CORREGIDA
- Busca hosts (muros/techos) por PROXIMIDAD XY dinámicamente
- Usa FamilyPlacementType REAL para decidir método de colocación
- Nivel Piso 5 garantizado via parameter Level o Location.Point.Z
- Procesa en PARES para memoria

pyRevit IronPython 2.7 - usar __revit__ global
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
from System.Collections.Generic import List

# pyRevit globals
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

# ─── CONFIG ──────────────────────────────────────────────
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

# Apartamentos a procesar EN PARES
PAIRS = [
    ['F17', 'F18'],
    ['E06', 'E07'],
    ['B15', 'B16'],
    ['C14', 'D13'],
    ['TF 01', 'TF 02'],
    ['E05', 'E08'],
    ['F17a', 'F18a'],
    ['E07a', 'E08a'],
    ['TF 01a', 'TF 01b'],
    ['TF 02a', 'TF 02b'],
]

# Alturas (mm) - nivel Piso 5 = 43.37 ft = 13219 mm
NIVEL_PISO5_ELEV = 13219.0  # mm
ALTURAS = {
    'M_Toma doble': 1000,
    'M_Comunicaciones': 1000,
    'M_Interruptores': 1100,
    'M_Pulsador - Interruptor': 1100,
    'M_Timbre': 2400,
    'M_ClimatizacionV': 2700,
    'M_Iluminacion': 2700,
    'EA': 2400,
}

# Rotación norma COL: +90° para placas horizontales
FAMILIAS_ROTAR_90 = {'M_Toma doble', 'M_Comunicaciones', 'M_Interruptores', 'M_Pulsador - Interruptor'}

# ─── CARGAR DATOS ────────────────────────────────────────
print("Cargando JSON...")
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

dispositivos = data['dispositivos']
print("Total dispositivos en JSON:", len(dispositivos))

# ─── OBTENER NIVEL PISO 5 ────────────────────────────────
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV) < 10:
        level_piso5 = lvl
        break

if not level_piso5:
    best = None
    best_diff = float('inf')
    for lvl in FilteredElementCollector(doc).OfClass(Level):
        diff = abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV)
        if diff < best_diff:
            best_diff = diff
            best = lvl
    level_piso5 = best

level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation
print("Nivel Piso 5: {} (Id: {}, Elev: {:.2f} ft / {:.1f} mm)".format(
    level_piso5.Name, level_piso5_id, level_piso5_elev_ft, level_piso5_elev_ft * 304.8))

# ─── CACHÉ DE SÍMBOLOS + FamilyPlacementType (INT VALUE) ────────────
print("Cacheando simbolos y FamilyPlacementType...")
symbol_cache = {}  # fam_name -> {type_name: (symbol, fpt_int)}
collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
for s in collector:
    fam_name = s.Family.Name
    type_name = s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
    # FamilyPlacementType es enum, obtener valor entero
    fpt_int = int(s.Family.FamilyPlacementType)
    if fam_name not in symbol_cache:
        symbol_cache[fam_name] = {}
    symbol_cache[fam_name][type_name] = (s, fpt_int)

print("Familias cacheadas: {}".format(len(symbol_cache)))

# ─── PRE-ACTIVAR SÍMBOLOS ───────────────────────────────
print("Pre-activando simbolos...")
familias_usadas = set(d['familia_revit'] for d in dispositivos)
simbolos_a_activar = []
for fam in familias_usadas:
    if fam in symbol_cache:
        for typ, (sym, fpt_int) in symbol_cache[fam].items():
            if not sym.IsActive:
                simbolos_a_activar.append(sym)

if simbolos_a_activar:
    t_act = Transaction(doc, "Activar simbolos")
    t_act.Start()
    for sym in simbolos_a_activar:
        sym.Activate()
    t_act.Commit()
    print("  Activados {} simbolos".format(len(simbolos_a_activar)))
else:
    print("  Todos los simbolos ya activos")

# ─── FUNCIÓN: OBTENER SÍMBOLO ───────────────────────────
def get_symbol(fam_name, type_name):
    if fam_name in symbol_cache and type_name in symbol_cache[fam_name]:
        return symbol_cache[fam_name][type_name]
    if fam_name in symbol_cache and symbol_cache[fam_name]:
        return list(symbol_cache[fam_name].values())[0]
    return None

# FamilyPlacementType valores (int):
# FaceBased = 0, OneLevelBased = 1, TwoLevelsBased = 2, WorkPlaneBased = 3
FPT_FACE_BASED = 0
FPT_ONE_LEVEL = 1
FPT_TWO_LEVELS = 2
FPT_WORK_PLANE = 3

# ─── CACHÉ ESPACIAL: MUROS Y TECHOS PISO 5 ──────────────
print("Construyendo índice espacial muros/techos Piso 5...")

# Muros: filtrar por LevelId y almacenar (wall, bbox_min, bbox_max, faces_refs)
walls_data = []
collector = FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType()
for w in collector:
    if w.LevelId == level_piso5_id:
        try:
            geom_opt = Options()
            geom_opt.ComputeReferences = True
            geom = w.get_Geometry(geom_opt)
            faces = []
            for obj in geom:
                if isinstance(obj, Solid):
                    for face in obj.Faces:
                        normal = face.ComputeNormal(UV(0.5, 0.5))
                        if abs(normal.Z) < 0.1:  # vertical
                            faces.append(face)
            if faces:
                bbox = w.get_BoundingBox(None)
                if bbox:
                    walls_data.append({
                        'wall': w,
                        'faces': faces,
                        'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                        'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y
                    })
        except:
            continue

print("  Muros Piso 5 con geometría: {}".format(len(walls_data)))

# Techos: filtrar por LevelId (techos en Piso 5 = nivel superior del piso)
ceilings_data = []
collector = FilteredElementCollector(doc).OfClass(Ceiling).WhereElementIsNotElementType()
for c in collector:
    if c.LevelId == level_piso5_id:
        try:
            geom_opt = Options()
            geom_opt.ComputeReferences = True
            geom = c.get_Geometry(geom_opt)
            bottom_faces = []
            for obj in geom:
                if isinstance(obj, Solid):
                    for face in obj.Faces:
                        normal = face.ComputeNormal(UV(0.5, 0.5))
                        if normal.Z < -0.1:  # cara inferior
                            bottom_faces.append(face)
            if bottom_faces:
                bbox = c.get_BoundingBox(None)
                if bbox:
                    ceilings_data.append({
                        'ceiling': c,
                        'faces': bottom_faces,
                        'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                        'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y,
                        'z': bottom_faces[0].Evaluate(UV(0.5, 0.5)).Z
                    })
        except:
            continue

print("  Techos Piso 5 con geometría: {}".format(len(ceilings_data)))

# ─── FUNCIÓN: ENCONTRAR MURO MÁS CERCANO ─────────────────
def find_wall_host(x_ft, y_ft, z_ft, max_dist_ft=6.56):  # 2m = 6.56ft
    pt = XYZ(x_ft, y_ft, z_ft)
    best_ref = None
    best_dist = float('inf')
    for wd in walls_data:
        if x_ft < wd['xmin'] - max_dist_ft or x_ft > wd['xmax'] + max_dist_ft:
            continue
        if y_ft < wd['ymin'] - max_dist_ft or y_ft > wd['ymax'] + max_dist_ft:
            continue
        for face in wd['faces']:
            uv = face.Project(pt)
            if uv:
                pt_on_face = face.Evaluate(uv)
                dist = ((pt_on_face.X - x_ft)**2 + (pt_on_face.Y - y_ft)**2)**0.5
                if dist < best_dist and dist < max_dist_ft:
                    best_dist = dist
                    best_ref = face.Reference
    return best_ref

# ─── FUNCIÓN: ENCONTRAR TECHO MÁS CERCANO ───────────────
def find_ceiling_host(x_ft, y_ft, max_dist_ft=6.56):
    pt_xy = XYZ(x_ft, y_ft, 0)
    best_ref = None
    best_z = None
    best_dist = float('inf')
    for cd in ceilings_data:
        if x_ft < cd['xmin'] - max_dist_ft or x_ft > cd['xmax'] + max_dist_ft:
            continue
        if y_ft < cd['ymin'] - max_dist_ft or y_ft > cd['ymax'] + max_dist_ft:
            continue
        for face in cd['faces']:
            uv = face.Project(pt_xy)
            if uv:
                pt_on_face = face.Evaluate(uv)
                dist = ((pt_on_face.X - x_ft)**2 + (pt_on_face.Y - y_ft)**2)**0.5
                if dist < best_dist and dist < max_dist_ft:
                    best_dist = dist
                    best_ref = face.Reference
                    best_z = pt_on_face.Z
    return best_ref, best_z

# ─── FUNCIÓN: CLASIFICAR POR FamilyPlacementType (int) ────────
def get_placement_method(fam_name, type_name):
    """Determina método real basado en FamilyPlacementType int value"""
    sym_fpt = get_symbol(fam_name, type_name)
    if not sym_fpt:
        return 'LEVEL', None
    symbol, fpt_int = sym_fpt
    
    # Mapear FamilyPlacementType a método
    if fpt_int == FPT_FACE_BASED:  # FaceBased = 0
        if fam_name in ('M_Toma doble', 'M_Comunicaciones'):
            return 'FACE_WALL', symbol
        else:
            return 'FACE_CEILING', symbol
    elif fpt_int == FPT_ONE_LEVEL:  # OneLevelBased = 1
        return 'LEVEL', symbol
    elif fpt_int == FPT_TWO_LEVELS:  # TwoLevelsBased = 2
        return 'LEVEL', symbol
    elif fpt_int == FPT_WORK_PLANE:  # WorkPlaneBased = 3
        if fam_name in ('M_Toma doble', 'M_Comunicaciones'):
            return 'FACE_WALL', symbol
        elif fam_name in ('M_Iluminacion', 'M_ClimatizacionV'):
            return 'FACE_CEILING', symbol
        else:
            return 'LEVEL', symbol
    else:
        return 'LEVEL', symbol

# ─── FUNCIÓN: MARK ÚNICO ────────────────────────────────
def generate_mark(d):
    x_int = int(round(d['x_mm']))
    y_int = int(round(d['y_mm']))
    fam_short = d['familia_revit'].replace('M_', '').replace(' ', '')[:8]
    typ_short = d['tipo_revit'].replace(' ', '')[:6]
    return "{}_{}_{}_{}".format(fam_short, typ_short, x_int, y_int)

# ─── COLOCACIÓN PRINCIPAL ───────────────────────────────
def place_devices_for_apto(apto_name):
    apto_devices = [d for d in dispositivos if d['apto_asignado'] == apto_name]
    if not apto_devices:
        print("  {}: SIN dispositivos".format(apto_name))
        return 0, 0, 0
    
    print("  {}: {} dispositivos".format(apto_name, len(apto_devices)))
    
    placed_fb_wall = 0
    placed_fb_ceiling = 0
    placed_level = 0
    warnings = []
    
    MM_TO_FT = 0.003280839895
    
    for d in apto_devices:
        x_ft = d['x_mm'] * MM_TO_FT
        y_ft = d['y_mm'] * MM_TO_FT
        base_z_mm = ALTURAS.get(d['familia_revit'], NIVEL_PISO5_ELEV)
        z_ft = base_z_mm * MM_TO_FT
        
        symbol_data = get_symbol(d['familia_revit'], d['tipo_revit'])
        if not symbol_data:
            warnings.append("Sin simbolo: {} / {}".format(d['familia_revit'], d['tipo_revit']))
            continue
        
        method, symbol = get_placement_method(d['familia_revit'], d['tipo_revit'])
        
        rot_rad = math.radians(d['rotacion_grados'])
        if d['familia_revit'] in FAMILIAS_ROTAR_90:
            rot_rad += math.pi / 2
        
        inst = None
        try:
            if method == 'FACE_WALL':
                host_ref = find_wall_host(x_ft, y_ft, z_ft)
                if host_ref:
                    pt = XYZ(x_ft, y_ft, z_ft)
                    inst = doc.Create.NewFamilyInstance(host_ref, pt, symbol)
                    placed_fb_wall += 1
                else:
                    warnings.append("Sin host muro: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
                    
            elif method == 'FACE_CEILING':
                host_ref, ceiling_z = find_ceiling_host(x_ft, y_ft)
                if host_ref and ceiling_z:
                    pt = XYZ(x_ft, y_ft, ceiling_z)
                    inst = doc.Create.NewFamilyInstance(host_ref, pt, symbol)
                    placed_fb_ceiling += 1
                else:
                    warnings.append("Sin host techo: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
                    
            else:  # LEVEL
                pt = XYZ(x_ft, y_ft, level_piso5_elev_ft)
                inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
                # Forzar parámetro Level
                try:
                    p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                    if p_level:
                        p_level.Set(level_piso5_id)
                except:
                    pass
                placed_level += 1
            
            if inst:
                # Rotación post-creación
                if abs(rot_rad) > 0.01:
                    try:
                        loc = inst.Location
                        if hasattr(loc, 'Rotation'):
                            loc.Rotation = rot_rad
                    except:
                        pass
                
                # Mark único
                mark = generate_mark(d)
                try:
                    p_mark = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
                    if p_mark:
                        p_mark.Set(mark)
                except:
                    pass
                
        except Exception as ex:
            warnings.append("Error {} @ ({:.0f},{:.0f}): {}".format(
                d['nombre_dxf'], d['x_mm'], d['y_mm'], str(ex)))
    
    for w in warnings[:10]:
        print("    WARN: {}".format(w))
    if len(warnings) > 10:
        print("    ... y {} warnings mas".format(len(warnings) - 10))
    
    return placed_fb_wall, placed_fb_ceiling, placed_level

# ─── EJECUCIÓN ───────────────────────────────────────────
print("\n" + "="*60)
print("INICIANDO COLOCACION POR PARES (v02)")
print("="*60)

total_fb_wall = 0
total_fb_ceiling = 0
total_level = 0

for pair in PAIRS:
    print("\n--- PAIR: {} + {} ---".format(pair[0], pair[1]))
    
    t = Transaction(doc, "Colocar dispositivos {} + {}".format(pair[0], pair[1]))
    t.Start()
    try:
        for apto in pair:
            fb_w, fb_c, lev = place_devices_for_apto(apto)
            total_fb_wall += fb_w
            total_fb_ceiling += fb_c
            total_level += lev
        t.Commit()
        print("  Transaccion completada: FB-Wall={}, FB-Ceiling={}, Level={}".format(fb_w, fb_c, lev))
    except Exception as ex:
        print("  ERROR en par: {}".format(str(ex)))
        try:
            t.RollBack()
        except:
            pass

print("\n" + "="*60)
print("RESUMEN FINAL")
print("="*60)
print("Face-based Wall:   {}".format(total_fb_wall))
print("Face-based Ceiling: {}".format(total_fb_ceiling))
print("Level-based:        {}".format(total_level))
print("TOTAL:              {}".format(total_fb_wall + total_fb_ceiling + total_level))
print("\nCOLOCACION COMPLETADA!")