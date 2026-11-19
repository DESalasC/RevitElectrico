# -*- coding: utf-8 -*-
"""
INVENTARIAR_TECHOS_GLOBAL_v01.py - IronPython 2.7 para pyRevit
Inventaria TODOS los techos del nivel Piso 5 con coordenadas GLOBALES reales
y los empareja con apartamentos del JSON maestro (dxf_master_global_all.json).
Genera CSV y JSON de mapeo apto -> ceiling_id.
"""

import json, os, math, clr, datetime, sys, csv
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    XYZ, UV, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Ceiling, Level, Options, Solid, Face, PlanarFace
)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

# ════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════

JSON_MAESTRO_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"
OUTPUT_CSV = r"D:\Work\PROJECTS\RevitElectrico\data\ceilings_inventory_global.csv"
OUTPUT_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\ceilings_mapping_apto.json"

TARGET_LEVEL_NAMES = ["PISO 5", "NIVEL 5", "LEVEL 5", "P5", "N5"]
TARGET_LEVEL_ELEV = 43.37  # ~13.22 m

# Techos ya confirmados (NO mover)
CONFIRMED = {
    "F01": 2764963,
    "F02": 2766313,
}

exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)

def m_a_ft(m): return m * 3.280839895
def ft_a_m(ft): return ft / 3.280839895
def log(msg): print(msg)
def elem_id(elem):
    if elem is None: return 0
    try:
        if hasattr(elem, 'Id'): eid_obj = elem.Id
        else: eid_obj = elem
        if hasattr(eid_obj, 'IntegerValue'): return int(eid_obj.IntegerValue)
        if hasattr(eid_obj, 'Value'): return int(eid_obj.Value)
        import re; m = re.search(r'(\d+)', str(eid_obj))
        return int(m.group(1)) if m else 0
    except: return 0
def eid(val): return ElementId(Int64(val))
def load_json(p):
    with open(p, 'r') as f: return json.load(f)

# ════════════════════════════════════════════════════════════════
# OBTENER CARA INFERIOR Y POSICIÓN GLOBAL REAL DEL TECHO
# ════════════════════════════════════════════════════════════════

def get_ceiling_global_data(doc, ceiling_id):
    """Obtiene cara inferior y bounds GLOBALES reales del techo."""
    ceil = doc.GetElement(eid(ceiling_id))
    if not ceil: return None
    opt = Options(); opt.ComputeReferences = True
    g = ceil.get_Geometry(opt)
    if not g: return None
    
    for obj in g:
        if isinstance(obj, Solid):
            bbox = obj.GetBoundingBox()
            if not bbox: continue
            
            # Buscar cara inferior (normal -Z)
            bottom_face = None
            for f in obj.Faces:
                if isinstance(f, PlanarFace) and f.FaceNormal.Z < -0.9:
                    bottom_face = f
                    break
            
            if bottom_face:
                # Evaluar 4 esquinas UV para bounds globales
                bb_uv = bottom_face.GetBoundingBox()
                corners_uv = [
                    UV(bb_uv.Min.U, bb_uv.Min.V),
                    UV(bb_uv.Min.U, bb_uv.Max.V),
                    UV(bb_uv.Max.U, bb_uv.Min.V),
                    UV(bb_uv.Max.U, bb_uv.Max.V),
                ]
                global_pts = [bottom_face.Evaluate(uv) for uv in corners_uv]
                xs = [p.X for p in global_pts]
                ys = [p.Y for p in global_pts]
                zs = [p.Z for p in global_pts]
                center = XYZ(sum(xs)/4, sum(ys)/4, sum(zs)/4)
                
                return {
                    "ceiling_id": ceiling_id,
                    "face": bottom_face,
                    "face_ref": bottom_face.Reference,
                    "face_z": sum(zs) / 4.0,
                    "global_bounds": {
                        "xmin": min(xs), "xmax": max(xs),
                        "ymin": min(ys), "ymax": max(ys),
                        "zmin": min(zs), "zmax": max(zs),
                    },
                    "center_global": center,
                    "area_ft2": (max(xs) - min(xs)) * (max(ys) - min(ys)),
                }
            else:
                # Sin cara plana, usar bbox del solid
                xs = [bbox.Min.X, bbox.Max.X]
                ys = [bbox.Min.Y, bbox.Max.Y]
                zs = [bbox.Min.Z, bbox.Max.Z]
                center = XYZ(sum(xs)/2, sum(ys)/2, sum(zs)/2)
                return {
                    "ceiling_id": ceiling_id,
                    "face": None,
                    "face_ref": None,
                    "face_z": max(zs),
                    "global_bounds": {
                        "xmin": min(xs), "xmax": max(xs),
                        "ymin": min(ys), "ymax": max(ys),
                        "zmin": min(zs), "zmax": max(zs),
                    },
                    "center_global": center,
                    "area_ft2": (max(xs) - min(xs)) * (max(ys) - min(ys)),
                }
    return None

# ════════════════════════════════════════════════════════════════
# MATCHING: Techos -> Apartamentos por proximidad del centro
# ════════════════════════════════════════════════════════════════

def dist_xy(p1, p2):
    dx = p1.X - p2.X
    dy = p1.Y - p2.Y
    return math.sqrt(dx*dx + dy*dy)

def match_ceilings_to_apartments(ceilings_data, apartamentos):
    """Empareja cada apartamento con su techo más cercano por centro global."""
    matches = {}
    used_ceilings = set()
    
    for apto_key, apto_data in sorted(apartamentos.items()):
        # Centro del apartamento = promedio de dispositivos
        devices = apto_data.get('devices', [])
        if not devices:
            continue
        x_avg = sum(d['x'] for d in devices) / len(devices)
        y_avg = sum(d['y'] for d in devices) / len(devices)
        apto_center = XYZ(x_avg, y_avg, 0)
        
        best_cid = None
        best_dist = float('inf')
        best_ceil = None
        
        for cd in ceilings_data:
            cid = cd['ceiling_id']
            if cid in used_ceilings:
                continue
            c_center = cd['center_global']
            d = dist_xy(apto_center, c_center)
            if d < best_dist:
                best_dist = d
                best_cid = cid
                best_ceil = cd
        
        if best_cid:
            used_ceilings.add(best_cid)
            matches[apto_key] = {
                "apto_key": apto_key,
                "panel_name": apto_data.get('panel_name', ''),
                "apto_center_ft": {"x": x_avg, "y": y_avg},
                "ceiling_id": best_cid,
                "ceiling_center_ft": {"x": best_ceil['center_global'].X, "y": best_ceil['center_global'].Y, "z": best_ceil['center_global'].Z},
                "ceiling_bounds_ft": best_ceil['global_bounds'],
                "ceiling_face_z_ft": best_ceil['face_z'],
                "distance_ft": best_dist,
                "confirmed": best_cid in CONFIRMED.values(),
            }
            log("MATCH {} (Panel: {}) -> Ceiling {} | dist={:.2f}ft Centro=({:.2f},{:.2f}) Bounds Y=[{:.2f},{:.2f}]".format(
                apto_key, apto_data.get('panel_name',''), best_cid, best_dist,
                best_ceil['center_global'].X, best_ceil['center_global'].Y,
                best_ceil['global_bounds']['ymin'], best_ceil['global_bounds']['ymax']))
        else:
            log("NO MATCH for {}".format(apto_key))
            matches[apto_key] = {
                "apto_key": apto_key,
                "panel_name": apto_data.get('panel_name', ''),
                "apto_center_ft": {"x": x_avg, "y": y_avg},
                "ceiling_id": None,
            }
    
    return matches

# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

log("=" * 70)
log("INVENTARIAR_TECHOS_GLOBAL_v01")
log("Ejecutado: " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S") + " (Bogotá GMT-5)")
log("=" * 70)

doc = None
try: doc = __revit__.ActiveUIDocument.Document
except:
    try:
        from pyrevit import revit; doc = revit.doc
    except: pass
if not doc: log("[ERROR] No documento"); sys.exit()
log("[OK] " + doc.Title)

# 1. CARGAR JSON MAESTRO PARA POSICIONES DE APARTAMENTOS
maestro = load_json(JSON_MAESTRO_PATH)
apartamentos = maestro.get('apartamentos', {})
log("\n[JSON MAESTRO] {} apartamentos cargados".format(len(apartamentos)))

# 2. NIVEL PISO 5
PISO5_LEVEL = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    name = lvl.Name if hasattr(lvl, 'Name') else ""
    if any(kw in name.upper() for kw in TARGET_LEVEL_NAMES):
        PISO5_LEVEL = lvl; break
if not PISO5_LEVEL:
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if abs(lvl.Elevation - TARGET_LEVEL_ELEV) < 0.5:
            PISO5_LEVEL = lvl; break
NIVEL5_ELEV = PISO5_LEVEL.Elevation
PISO5_LEVEL_ID_INT = elem_id(PISO5_LEVEL)
log("[LEVEL] '{}' Id={} Elev={:.4f}ft".format(PISO5_LEVEL.Name, PISO5_LEVEL_ID_INT, NIVEL5_ELEV))

# 3. RECOLECTAR TODOS LOS TECHOS DEL NIVEL
log("\n[RECOLECTANDO] Techos en nivel Piso 5...")
all_ceilings_data = []
for c in FilteredElementCollector(doc).OfClass(Ceiling).WhereElementIsNotElementType().ToElements():
    try:
        lvl = doc.GetElement(c.LevelId)
        if not lvl or abs(lvl.Elevation - NIVEL5_ELEV) > 0.5: continue
        
        cd = get_ceiling_global_data(doc, elem_id(c.Id))
        if cd:
            typ = doc.GetElement(c.GetTypeId())
            type_name = "?"
            if typ:
                p = typ.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                if p and p.HasValue:
                    type_name = p.AsString()
            cd['type_name'] = type_name
            cd['level_elev'] = NIVEL5_ELEV
            all_ceilings_data.append(cd)
    except Exception as e:
        log("[WARN] Error techo {}: {}".format(elem_id(c.Id), e))

log("[RECOLECTADOS] {} techos con geometría válida".format(len(all_ceilings_data)))

# 4. MATCHING TECHOS -> APARTAMENTOS
log("\n[MATCHING] Techos -> Apartamentos por centro global...")
matches = match_ceilings_to_apartments(all_ceilings_data, apartamentos)

# 5. EXPORTAR CSV
log("\n[EXPORT] CSV -> " + OUTPUT_CSV)
with open(OUTPUT_CSV, 'wb') as f:
    w = csv.writer(f)
    w.writerow([
        "apto_key", "panel_name", "ceiling_id", "ceiling_type",
        "apto_center_x_ft", "apto_center_y_ft",
        "ceiling_center_x_ft", "ceiling_center_y_ft", "ceiling_center_z_ft",
        "ceiling_face_z_ft",
        "bounds_xmin_ft", "bounds_xmax_ft", "bounds_ymin_ft", "bounds_ymax_ft", "bounds_zmin_ft", "bounds_zmax_ft",
        "area_ft2", "distance_ft", "confirmed"
    ])
    for apto_key in sorted(matches.keys()):
        m = matches[apto_key]
        apto_data = apartamentos.get(apto_key, {})
        cid = m.get('ceiling_id')
        if cid:
            # Encontrar type_name
            type_name = ""
            for cd in all_ceilings_data:
                if cd['ceiling_id'] == cid:
                    type_name = cd.get('type_name', '')
                    break
            w.writerow([
                apto_key, apto_data.get('panel_name',''), cid, type_name,
                m['apto_center_ft']['x'], m['apto_center_ft']['y'],
                m['ceiling_center_ft']['x'], m['ceiling_center_ft']['y'], m['ceiling_center_ft']['z'],
                m['ceiling_face_z_ft'],
                m['ceiling_bounds_ft']['xmin'], m['ceiling_bounds_ft']['xmax'],
                m['ceiling_bounds_ft']['ymin'], m['ceiling_bounds_ft']['ymax'],
                m['ceiling_bounds_ft']['zmin'], m['ceiling_bounds_ft']['zmax'],
                (m['ceiling_bounds_ft']['xmax'] - m['ceiling_bounds_ft']['xmin']) * (m['ceiling_bounds_ft']['ymax'] - m['ceiling_bounds_ft']['ymin']),
                m['distance_ft'], m.get('confirmed', False)
            ])
        else:
            w.writerow([apto_key, apto_data.get('panel_name',''), "", "", 
                       m['apto_center_ft']['x'], m['apto_center_ft']['y'],
                       "", "", "", "", "", "", "", "", "", "", "", "", ""])

# 6. EXPORTAR JSON MAPEO
mapping = {}
for apto_key in sorted(matches.keys()):
    m = matches[apto_key]
    if m.get('ceiling_id'):
        mapping[apto_key] = {
            "ceiling_id": m['ceiling_id'],
            "panel_name": m['panel_name'],
            "ceiling_center_ft": m['ceiling_center_ft'],
            "ceiling_face_z_ft": m['ceiling_face_z_ft'],
            "ceiling_bounds_ft": m['ceiling_bounds_ft'],
            "confirmed": m.get('confirmed', False),
        }

with open(OUTPUT_JSON, 'w') as f:
    json.dump({"mapping": mapping, "generated": exec_bogota.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=2)

log("[EXPORT] JSON -> " + OUTPUT_JSON)

# 7. RESUMEN
log("\n" + "=" * 70)
log("RESUMEN MAPEO APARTAMENTO -> TECHO")
log("=" * 70)
for apto_key in sorted(mapping.keys()):
    m = mapping[apto_key]
    c = m['ceiling_center_ft']
    log("  {} (Panel: {}) -> Ceiling {} | Centro=({:.2f},{:.2f},{:.2f}) FaceZ={:.2f} BoundsY=[{:.2f},{:.2f}] {}".format(
        apto_key, m['panel_name'], m['ceiling_id'],
        c['x'], c['y'], c['z'], m['ceiling_face_z_ft'],
        m['ceiling_bounds_ft']['ymin'], m['ceiling_bounds_ft']['ymax'],
        "[CONFIRMADO]" if m['confirmed'] else ""))
    
missing = [k for k in sorted(apartamentos.keys()) if k not in mapping]
if missing:
    log("\nSIN TECHO ASIGNADO: " + ", ".join(missing))

log("\nActualiza COLOCAR_TODOS_APARTAMENTOS_v01.py CEILING_IDS con estos IDs.")
log("=" * 70)