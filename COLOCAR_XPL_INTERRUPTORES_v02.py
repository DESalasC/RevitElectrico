"""
COLOCAR_XPL_INTERRUPTORES_v02.py - Interruptores multi-apto (M_Interruptores + M_Pulsador-Interruptor)
Version: 02 | Date: 2026-11-22
Fix: M_Interruptores = LEVEL-based (OneLevelBasedHosted), M_Pulsador = face-based wall-hosted (WorkPlaneBased)
Basado en validación runtime v16.2

Uso:
  $env:APTOS_A_PROCESAR = "TF_01a,F17a,F18a,TF_01b,TF_02a,TF_02b,E07a,E08a,B15,B16,C14,D13"
  exec(open(r"D:\Work\PROJECTS\RevitElectrico\COLOCAR_XPL_INTERRUPTORES_v02.py").read())

  # O usa config/apartamentos_a_procesar.json
  # O default: todos menos F01,F02
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import os
import traceback

# ============================================================
# CONFIGURACION
# ============================================================
CONFIG_EQ_PATH = r"D:\Work\PROJECTS\RevitElectrico\config\equivalencias_apartamentos_piso5_v2.json"
CONFIG_APTOS_PATH = r"D:\Work\PROJECTS\RevitElectrico\config\apartamentos_a_procesar.json"
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURAS_MM = {'M_Interruptores': 1100, 'M_Pulsador - Interruptor': 1100}
WALL_SEARCH_TOLERANCE_MM = 300.0
FLOOR_SEARCH_TOLERANCE_MM = 5000.0

# CLASIFICACION POR FAMILIA (validada runtime v16.2)
# M_Pulsador - Interruptor (Timbre) -> WorkPlaneBased -> FACE-BASED wall-hosted
# M_Interruptores (Simple, Doble, Control, Conmutable) -> OneLevelBasedHosted -> LEVEL-BASED + set Host param
FAMILIAS_FACE_BASED = ('M_Pulsador - Interruptor',)
FAMILIAS_LEVEL_BASED = ('M_Interruptores',)
FAMILIAS_OBJETIVO = FAMILIAS_FACE_BASED + FAMILIAS_LEVEL_BASED

# Cargar equivalencias
with open(CONFIG_EQ_PATH, 'r') as f:
    EQ_CONFIG = json.load(f)

ALL_APTOS = list(EQ_CONFIG['apartamentos'].keys())
INTOCABLES = set(EQ_CONFIG.get('apartamentos_intocables', ['F01', 'F02']))
YA_PROCESADOS = set(EQ_CONFIG.get('apartamentos_ya_procesados', []))
DEFAULT_APTOS = [a for a in EQ_CONFIG.get('orden_ejecucion_sugerido', ALL_APTOS)
                 if a not in INTOCABLES and a not in YA_PROCESADOS]

# Resolver lista
APTOS_A_PROCESAR = None
env_val = os.environ.get('APTOS_A_PROCESAR', '').strip()
if env_val:
    APTOS_A_PROCESAR = [a.strip() for a in env_val.split(',') if a.strip()]
    print("[CONFIG] Apartamentos desde variable de entorno APTOS_A_PROCESAR")
elif os.path.exists(CONFIG_APTOS_PATH):
    with open(CONFIG_APTOS_PATH, 'r') as f:
        cfg = json.load(f)
        APTOS_A_PROCESAR = cfg.get('apartamentos', DEFAULT_APTOS)
    print("[CONFIG] Apartamentos desde config/apartamentos_a_procesar.json")
else:
    APTOS_A_PROCESAR = DEFAULT_APTOS
    print("[CONFIG] Apartamentos por defecto")

APTOS_A_PROCESAR = [a for a in APTOS_A_PROCESAR if a in ALL_APTOS]
unknown = [a for a in APTOS_A_PROCESAR if a not in ALL_APTOS]
if unknown: print("[AVISO] Desconocidos ignorados:", unknown)

print("=" * 60)
print("COLOCAR_XPL_INTERRUPTORES v02 - MULTI-APTO")
print("Apartamentos:", ", ".join(APTOS_A_PROCESAR))
print("ALTURA: 1100mm | ROTACION: DXF + 90° (placa horizontal)")
print("ESTRATEGIA: M_Pulsador=Face-based | M_Interruptores=Level-based + Host param")
print("=" * 60)

# ============================================================
# INIT REVIT
# ============================================================
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

# ============================================================
# CARGA JSON
# ============================================================
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

dispositivos_por_apto = {}
for d in data['dispositivos']:
    apto = d['apto_asignado']
    if apto in APTOS_A_PROCESAR and d['familia_revit'] in FAMILIAS_OBJETIVO:
        dispositivos_por_apto.setdefault(apto, []).append(d)

for apto in APTOS_A_PROCESAR:
    count = len(dispositivos_por_apto.get(apto, []))
    print("  {}: {} interruptores/pulsadores".format(apto, count))

total = sum(len(v) for v in dispositivos_por_apto.values())
print("\nTotal a colocar:", total)
if total == 0: raise SystemExit(0)

# ============================================================
# NIVEL PISO 5
# ============================================================
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl; break
if not level_piso5:
    raise Exception("No se encontro nivel Piso 5")
level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation

# ============================================================
# SIMBOLOS
# ============================================================
symbols = {}
for fam_name in FAMILIAS_OBJETIVO:
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.Family.Name == fam_name:
            symbols[fam_name] = s
            if not s.IsActive: s.Activate()
            break
missing = [f for f in FAMILIAS_OBJETIVO if f not in symbols]
if missing: print("ADVERTENCIA: Sin simbolo:", missing)

# ============================================================
# CONSTANTES GEOMETRIA
# ============================================================
MM_TO_FT = 0.003280839895
TOLERANCE_FT = WALL_SEARCH_TOLERANCE_MM * MM_TO_FT
FLOOR_TOL_FT = FLOOR_SEARCH_TOLERANCE_MM * MM_TO_FT

def _distance_xy_to_curve(curve, target_x, target_y):
    if isinstance(curve, Line):
        sp, ep = curve.GetEndPoint(0), curve.GetEndPoint(1)
        x1, y1, x2, y2 = sp.X, sp.Y, ep.X, ep.Y
        dx, dy = x2 - x1, y2 - y1
        seg_len2 = dx*dx + dy*dy
        if seg_len2 < 1e-12: return math.hypot(target_x - x1, target_y - y1)
        t = max(0.0, min(1.0, ((target_x - x1)*dx + (target_y - y1)*dy) / seg_len2))
        return math.hypot(target_x - (x1 + t*dx), target_y - (y1 + t*dy))
    n, best = 24, float('inf')
    for i in range(n + 1):
        try:
            p = curve.Evaluate(float(i)/n, False)
            d = math.hypot(target_x - p.X, target_y - p.Y)
            if d < best: best = d
        except: pass
    return best

# ============================================================
# CACHE HOSTS PISO 5 (para face-based: M_Pulsador)
# ============================================================
def _get_level_id(elem):
    try:
        lid = elem.LevelId
        if lid and lid != ElementId.InvalidElementId(): return lid
    except: pass
    for bp in (BuiltInParameter.LEVEL_PARAM, BuiltInParameter.WALL_BASE_CONSTRAINT, BuiltInParameter.FAMILY_LEVEL_PARAM):
        try:
            p = elem.get_Parameter(bp)
            if p: return p.AsElementId()
        except: pass
    return None

def _is_in_level(elem, target_id):
    if not target_id: return True
    lid = _get_level_id(elem)
    return lid == target_id if lid else False

print("\nCargando hosts Piso 5...")
all_walls_raw = list(FilteredElementCollector(doc).OfClass(Wall).ToElements())
all_walls = [w for w in all_walls_raw if w.WallType and _is_in_level(w, level_piso5_id)]
print("  Muros Piso 5:", len(all_walls))

all_floors_raw = list(FilteredElementCollector(doc).OfClass(Floor).ToElements())
all_floors = [f for f in all_floors_raw if _is_in_level(f, level_piso5_id)]
print("  Suelos Piso 5:", len(all_floors))

all_ceilings = []
try:
    all_ceilings_raw = list(FilteredElementCollector(doc).OfClass(Ceiling).ToElements())
    all_ceilings = [c for c in all_ceilings_raw if _is_in_level(c, level_piso5_id)]
    print("  Cielorrasos Piso 5:", len(all_ceilings))
except: print("  Ceiling no disponible")

geom_opt = Options(); geom_opt.ComputeReferences = True; geom_opt.IncludeNonVisibleObjects = False
try:
    if doc.ActiveView and doc.ActiveView.IsValidObject: geom_opt.View = doc.ActiveView
except: pass

# ============================================================
# BUSQUEDA HOST (solo para face-based: M_Pulsador)
# ============================================================
def find_wall_face(target_xyz):
    best, best_d = None, float('inf')
    tx, ty = target_xyz.X, target_xyz.Y
    for w in all_walls:
        loc = w.Location
        if not isinstance(loc, LocationCurve): continue
        c = loc.Curve
        if not c: continue
        try:
            dxy = _distance_xy_to_curve(c, tx, ty)
        except: continue
        if dxy > TOLERANCE_FT: continue
        try:
            p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
            wdir = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0).Normalize()
        except: continue
        geom = w.get_Geometry(geom_opt)
        if not geom: continue
        for obj in geom:
            if not isinstance(obj, Solid): continue
            try:
                if obj.Faces.IsEmpty: continue
            except: continue
            for face in obj.Faces:
                if not isinstance(face, PlanarFace): continue
                if abs(face.FaceNormal.Z) > 0.1: continue
                try:
                    proj = face.Project(target_xyz)
                except: continue
                if not proj: continue
                pt_on = proj.XYZPoint
                vec = target_xyz - pt_on
                vlen = vec.GetLength()
                if vlen > 1e-6 and face.FaceNormal.DotProduct(vec)/vlen < 0.5: continue
                try:
                    bbox = face.GetBoundingBox()
                    if bbox:
                        u, v = proj.UVPoint.U, proj.UVPoint.V
                        if not (bbox.Min.U - 0.01 <= u <= bbox.Max.U + 0.01 and bbox.Min.V - 0.01 <= v <= bbox.Max.V + 0.01):
                            continue
                except: pass
                if dxy < best_d:
                    best_d, best = dxy, (face.Reference, face.FaceNormal, pt_on, wdir)
    return best

def find_horizontal_face(target_xyz, hosts, want_top=True):
    best, best_d = None, float('inf')
    tx, ty = target_xyz.X, target_xyz.Y
    for elem in hosts:
        try:
            bbox = elem.get_BoundingBox(None)
            if not bbox: continue
            if (tx < bbox.Min.X - FLOOR_TOL_FT or tx > bbox.Max.X + FLOOR_TOL_FT or
                ty < bbox.Min.Y - FLOOR_TOL_FT or ty > bbox.Max.Y + FLOOR_TOL_FT):
                continue
        except: pass
        geom = elem.get_Geometry(geom_opt)
        if not geom: continue
        for obj in geom:
            if not isinstance(obj, Solid): continue
            try:
                if obj.Faces.IsEmpty: continue
            except: continue
            for face in obj.Faces:
                if not isinstance(face, PlanarFace): continue
                fn = face.FaceNormal
                if abs(fn.Z) < 0.9: continue
                if want_top and fn.Z < 0: continue
                if not want_top and fn.Z > 0: continue
                try:
                    proj = face.Project(target_xyz)
                except: continue
                if not proj: continue
                pt_on = proj.XYZPoint
                dxy = math.hypot(pt_on.X - tx, pt_on.Y - ty)
                if dxy > FLOOR_TOL_FT: continue
                try:
                    bbox_f = face.GetBoundingBox()
                    if bbox_f:
                        u, v = proj.UVPoint.U, proj.UVPoint.V
                        if not (bbox_f.Min.U - 0.01 <= u <= bbox_f.Max.U + 0.01 and bbox_f.Min.V - 0.01 <= v <= bbox_f.Max.V + 0.01):
                            continue
                except: pass
                if dxy < best_d:
                    best_d, best = dxy, (face.Reference, fn, pt_on, None)
    return best

# ============================================================
# PROCESAR
# ============================================================
totals = {'wall_fb':0, 'level_based':0, 'placed':0, 'failed':0, 'rot_ok':0, 'rot_fail':0}

for APTO in APTOS_A_PROCESAR:
    disps = dispositivos_por_apto.get(APTO, [])
    if not disps:
        print("\n>>> {}: SIN INTERRUPTORES - saltando".format(APTO))
        continue

    print("\n" + "=" * 60)
    print("PROCESANDO: {} ({} interruptores)".format(APTO, len(disps)))
    print("=" * 60)

    placed = 0; failed = 0; rot_ok = 0; rot_fail = 0
    methods = {'wall_fb':0, 'level_based':0}

    t = Transaction(doc, "Interruptores {} - v02".format(APTO))
    t.Start()
    for d in disps:
        try:
            x = d['x_mm'] * MM_TO_FT
            y = d['y_mm'] * MM_TO_FT
            fam = d['familia_revit']
            z_ft = ALTURAS_MM[fam] * MM_TO_FT
            symbol = symbols.get(fam)
            if not symbol:
                failed += 1; continue

            rot_dxf_rad = math.radians(float(d['rotacion_grados']))
            rot_total_rad = rot_dxf_rad + math.radians(90.0)  # +90° placa horizontal
            target_z = level_piso5_elev_ft + z_ft
            pt = XYZ(x, y, target_z)

            inst = None
            method = None

            # --------------------------------------------------
            # M_Pulsador - Interruptor -> FACE-BASED (WorkPlaneBased)
            # --------------------------------------------------
            if fam in FAMILIAS_FACE_BASED:
                wr = find_wall_face(pt)
                if wr:
                    fref, fn, fpt, _ = wr
                    try:
                        inst = doc.Create.NewFamilyInstance(fref, fpt, XYZ.BasisZ, symbol)
                    except Exception as e:
                        if "Multiple targets" in str(e):
                            inst = doc.Create.NewFamilyInstance(fref, fpt, XYZ.BasisZ, symbol, ElementId.InvalidElementId())
                        else: raise
                    method = "WALL-FB"
                    methods['wall_fb'] += 1
                # Fallback: si no hay muro, level-based
                if not inst:
                    inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
                    p = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                    if p: p.Set(level_piso5_id)
                    method = "LEVEL-FB-FALLBACK"
                    methods['level_based'] += 1

                # Rotación best-effort
                if abs(rot_total_rad) > 1e-6:
                    applied = False
                    if method == "WALL-FB" and 'fn' in locals() and fn and fpt:
                        try:
                            axis = Line.CreateBound(fpt, fpt + fn * 10)
                            ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_total_rad)
                            applied = True
                        except: pass
                    if not applied and fpt:
                        try:
                            axis = Line.CreateBound(fpt, XYZ(fpt.X, fpt.Y, fpt.Z + 10))
                            ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_total_rad)
                            applied = True
                        except: pass
                    if applied: rot_ok += 1
                    else: rot_fail += 1

            # --------------------------------------------------
            # M_Interruptores -> LEVEL-BASED (OneLevelBasedHosted) + set Host param
            # --------------------------------------------------
            elif fam in FAMILIAS_LEVEL_BASED:
                inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
                p = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                if p: p.Set(level_piso5_id)
                method = "LEVEL"
                methods['level_based'] += 1

                # Intentar asociar a muro cercano via parámetro HOST (post-placement)
                # Buscar muro más cercano en XY
                best_wall = None
                best_d = float('inf')
                for w in all_walls:
                    loc = w.Location
                    if not isinstance(loc, LocationCurve): continue
                    c = loc.Curve
                    if not c: continue
                    try:
                        dxy = _distance_xy_to_curve(c, x, y)
                    except: continue
                    if dxy < best_d:
                        best_d, best_wall = dxy, w
                if best_wall and best_d < TOLERANCE_FT:
                    try:
                        # Parámetro HOST_ID_PARAM o similar
                        p_host = inst.get_Parameter(BuiltInParameter.HOST_ID_PARAM)
                        if not p_host:
                            p_host = inst.get_Parameter(BuiltInParameter.INSTANCE_HOST_ID_PARAM)
                        if p_host and best_wall.Id != ElementId.InvalidElementId():
                            p_host.Set(best_wall.Id)
                    except:
                        pass

                # Rotación best-effort (eje vertical en punto de inserción)
                if abs(rot_total_rad) > 1e-6:
                    try:
                        axis = Line.CreateBound(pt, pt + XYZ(0, 0, 10))
                        ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_total_rad)
                        rot_ok += 1
                    except:
                        rot_fail += 1

            # Mark
            mark = "{}_{}_{}_{}".format(fam.replace('M_','').replace(' ','')[:8], d['tipo_revit'].replace(' ','')[:6], int(round(d['x_mm'])), int(round(d['y_mm'])))
            pm = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if pm: pm.Set(mark)

            placed += 1
            print("  OK [{}]: {} @ ({:.1f},{:.1f},{:.1f}) rot_dxf={:.0f}° (+90)".format(method, d['nombre_dxf'], x, y, target_z, float(d['rotacion_grados'])))

        except Exception as e:
            failed += 1
            print("  FAIL: {} - {}".format(d.get('nombre_dxf','?'), str(e)[:100]))
    t.Commit()

    for k in methods: totals[k] += methods[k]
    totals['placed'] += placed; totals['failed'] += failed; totals['rot_ok'] += rot_ok; totals['rot_fail'] += rot_fail

    print("  {}: WALL-FB={} LEVEL={} FAIL={} ROT_OK={} ROT_FAIL={}".format(
        APTO, methods['wall_fb'], methods['level_based'], failed, rot_ok, rot_fail))

# ============================================================
# RESUMEN
# ============================================================
print("\n" + "=" * 60)
print("RESUMEN TOTAL - INTERRUPTORES v02")
print("=" * 60)
print("  Colocados:              {}".format(totals['placed']))
print("  Face-based (M_Pulsador): {}".format(totals['wall_fb']))
print("  Level-based (M_Int):     {}".format(totals['level_based']))
print("  Fallidos:               {}".format(totals['failed']))
print("  Rotacion OK:            {}".format(totals['rot_ok']))
print("  Rotacion fail:          {} (rotar manual DXF+90°)".format(totals['rot_fail']))
print("=" * 60)