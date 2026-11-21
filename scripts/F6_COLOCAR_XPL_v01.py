"""
F6_COLOCAR_XPL_v01.py
=====================
Colocación dispositivos Piso 5 usando DXF EXPLOTADO (coordenadas ABSOLUTAS mm).
Fuente: dxf_electricos_xpl_absolutos.json (899 dispositivos).

CONVENCIÓN: DXF origen (0,0) = Revit Internal Origin (0,0).
Coordenadas del JSON están en mm. Solo conversión: /1000 → metros.
SIN OFFSETS. El JSON YA tiene coordenadas globales Revit.

Clasificación:
  FACE_WALL: M_Toma doble, M_Comunicaciones
  FACE_CEILING: M_Iluminacion, M_ClimatizacionV
  LEVEL: Interruptores, Timbre, Campana, EA

Procesar en PARES para evitar crash de memoria:
  1. F17 + F18
  2. E06 + E07
  3. B15 + B16
  4. C14 + D13
  5. TF 01 + TF 02
  6. E05 + E08
  7. F17a + F18a
  8. E07a + E08a
  9. TF 01a + TF 01b
  10. TF 02a + TF 02b

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

# pyRevit globals
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

# ─── CONFIG ──────────────────────────────────────────────
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"
CEILING_MAP_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\ceilings_mapping_apto.json"

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

with open(CEILING_MAP_PATH, 'r') as f:
    ceilings_map = json.load(f)
ceilings_mapping = ceilings_map.get('mapping', ceilings_map)

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
print("Nivel Piso 5: {} (Id: {}, Elev: {:.2f} mm)".format(
    level_piso5.Name, level_piso5_id, level_piso5.Elevation * 304.8))

# ─── CACHÉ DE SÍMBOLOS ───────────────────────────────────
print("Cacheando simbolos de familia...")
symbol_cache = {}
collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
for s in collector:
    fam_name = s.Family.Name
    type_name = s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
    if fam_name not in symbol_cache:
        symbol_cache[fam_name] = {}
    symbol_cache[fam_name][type_name] = s

print("Familias disponibles:", list(symbol_cache.keys()))

# ─── PRE-ACTIVAR TODOS LOS SÍMBOLOS NECESARIOS ───────────
print("Pre-activando simbolos...")
familias_usadas = set(d['familia_revit'] for d in dispositivos)
simbolos_a_activar = []
for fam in familias_usadas:
    if fam in symbol_cache:
        for typ, sym in symbol_cache[fam].items():
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

# ─── FUNCIÓN: OBTENER TECHO ─────────────────────────────
def get_ceiling_for_apto(apto):
    if apto in ceilings_mapping:
        info = ceilings_mapping[apto]
        return ElementId(Int64(info['ceiling_id'])), float(info['ceiling_face_z_ft']) * 304.8
    return None, None

# ─── FUNCIÓN: PROYECTAR EN TECHO ────────────────────────
def project_to_ceiling_face(xyz_pt, ceiling_id):
    ceiling = doc.GetElement(ceiling_id)
    if not ceiling:
        return xyz_pt
    try:
        geom_opt = Options()
        geom_opt.ComputeReferences = True
        geom_opt.IncludeNonVisibleObjects = True
        geom = ceiling.get_Geometry(geom_opt)
        if not geom:
            return xyz_pt
        for obj in geom:
            if isinstance(obj, Solid):
                for face in obj.Faces:
                    normal = face.ComputeNormal(UV(0.5, 0.5))
                    if normal.Z < -0.1:
                        uv = face.Project(xyz_pt)
                        if uv:
                            pt_on_face = face.Evaluate(uv)
                            return XYZ(xyz_pt.X, xyz_pt.Y, pt_on_face.Z)
    except:
        pass
    return xyz_pt

# ─── FUNCIÓN: REFERENCIA TECHO ──────────────────────────
def get_ceiling_face_reference(xyz_pt, ceiling_id):
    ceiling = doc.GetElement(ceiling_id)
    if not ceiling:
        return None
    try:
        geom_opt = Options()
        geom_opt.ComputeReferences = True
        geom_opt.IncludeNonVisibleObjects = True
        geom = ceiling.get_Geometry(geom_opt)
        for obj in geom:
            if isinstance(obj, Solid):
                for face in obj.Faces:
                    normal = face.ComputeNormal(UV(0.5, 0.5))
                    if normal.Z < -0.1:
                        uv = face.Project(xyz_pt)
                        if uv:
                            return face.Reference
    except:
        pass
    return None

# ─── CACHÉ DE MUROS PISO 5 (una sola vez, fuera del loop) ───────────────
print("Cacheando muros Piso 5...")
walls_piso5 = []
collector = FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType()
for w in collector:
    if w.LevelId == level_piso5_id:
        walls_piso5.append(w)
print("  Muros Piso 5: {}".format(len(walls_piso5)))

# ─── FUNCIÓN: REFERENCIA MURO (usa caché pre-filtrado) ─────────────────
def get_wall_face_reference(xyz_pt):
    best_ref = None
    best_dist = float('inf')
    for wall in walls_piso5:
        try:
            geom_opt = Options()
            geom_opt.ComputeReferences = True
            geom = wall.get_Geometry(geom_opt)
            for obj in geom:
                if isinstance(obj, Solid):
                    for face in obj.Faces:
                        normal = face.ComputeNormal(UV(0.5, 0.5))
                        if abs(normal.Z) < 0.1:  # muro vertical
                            uv = face.Project(xyz_pt)
                            if uv:
                                pt_on_face = face.Evaluate(uv)
                                dist = ((pt_on_face.X - xyz_pt.X)**2 + (pt_on_face.Y - xyz_pt.Y)**2)**0.5
                                if dist < best_dist and dist < 2000:  # 2m threshold
                                    best_dist = dist
                                    best_ref = face.Reference
        except:
            continue
    return best_ref

# ─── FUNCIÓN: CLASIFICAR ────────────────────────────────
def classify_device(d):
    fam = d['familia_revit']
    if fam == 'M_Toma doble' or fam == 'M_Comunicaciones':
        return 'FACE_WALL'
    if fam == 'M_Iluminacion' or fam == 'M_ClimatizacionV':
        return 'FACE_CEILING'
    if 'Interruptor' in fam or fam == 'M_Pulsador - Interruptor' or fam == 'M_Timbre' or fam == 'EA':
        return 'LEVEL'
    return 'LEVEL'

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
    
    ceiling_id, ceiling_z_mm = get_ceiling_for_apto(apto_name)
    cid_str = str(ceiling_id) if ceiling_id else "None"
    if ceiling_z_mm is not None:
        z_str = "{:.1f}".format(ceiling_z_mm)
    else:
        z_str = "N/A"
    print("  {}: {} dispositivos, techo_id={}, techo_z={}mm".format(
        apto_name, len(apto_devices), cid_str, z_str))
    
    placed_fb_wall = 0
    placed_fb_ceiling = 0
    placed_level = 0
    warnings = []
    
    MM_TO_FT = 0.003280839895
    
    for d in apto_devices:
        classification = classify_device(d)
        
        x_ft = d['x_mm'] * MM_TO_FT
        y_ft = d['y_mm'] * MM_TO_FT
        
        base_z_mm = ALTURAS.get(d['familia_revit'], NIVEL_PISO5_ELEV)
        
        symbol = get_symbol(d['familia_revit'], d['tipo_revit'])
        if not symbol:
            warnings.append("Sin simbolo: {} / {}".format(d['familia_revit'], d['tipo_revit']))
            continue
        
        rot_rad = math.radians(d['rotacion_grados'])
        if d['familia_revit'] in FAMILIAS_ROTAR_90:
            rot_rad += math.pi / 2
        
        try:
            if classification == 'FACE_WALL':
                z_ft = base_z_mm * MM_TO_FT
                pt = XYZ(x_ft, y_ft, z_ft)
                host_ref = get_wall_face_reference(pt)
                if host_ref:
                    inst = doc.Create.NewFamilyInstance(host_ref, pt, symbol)
                    placed_fb_wall += 1
                else:
                    warnings.append("Sin host muro: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
                    
            elif classification == 'FACE_CEILING':
                if ceiling_id:
                    pt_xy = XYZ(x_ft, y_ft, 0)
                    pt_on_ceiling = project_to_ceiling_face(pt_xy, ceiling_id)
                    host_ref = get_ceiling_face_reference(pt_on_ceiling, ceiling_id)
                    if host_ref:
                        inst = doc.Create.NewFamilyInstance(host_ref, pt_on_ceiling, symbol)
                        placed_fb_ceiling += 1
                    else:
                        warnings.append("Sin host techo: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
                else:
                    warnings.append("Sin techo mapeado: {} @ ({:.0f},{:.0f})".format(d['nombre_dxf'], d['x_mm'], d['y_mm']))
                    
            else:  # LEVEL
                z_ft = base_z_mm * MM_TO_FT
                pt = XYZ(x_ft, y_ft, z_ft)
                inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
                placed_level += 1
            
            # Rotación post-creación (level-based)
            if classification == 'LEVEL' and abs(rot_rad) > 0.01:
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
print("INICIANDO COLOCACION POR PARES")
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
        print("  Transaccion completada para par.")
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