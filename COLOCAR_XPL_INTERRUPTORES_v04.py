"""
COLOCAR_XPL_INTERRUPTORES_v04.py - Limpieza + colocacion FACE-BASED
Version: 04 | Fecha: 2026-11-22

CAMBIOS vs v03 (que coloco 96 interruptores en el ORIGEN 0,0,1100):
  1. FASE 1 LIMPIEZA: borra M_Interruptores en (0,0) [basura v03 level-based]
     y timbres duplicados (mismo mark Pulsador_*, conserva el de menor Id).
  2. M_Interruptores ahora FACE-BASED sobre cara de muro:
     NewFamilyInstance(faceRef, pt, dir, symbol). El overload
     NewFamilyInstance(pt, symbol, level) manda familias wall-hosted a (0,0).
  3. Simbolo por tipo_revit (v03 usaba el primer simbolo = Conmutable para todos):
     ELEC-I-S-1-5A->Simple | ELEC-I-S-2-5A->Doble | ELEC-F-CONTROL->Simple conmutable
     ELEC-I-S-C1-5A->Triple conmutable | S3->Simple
  4. Dedup doble (solo familia M_Interruptores):
     a) por mark (coords JSON embebidas, tol 100mm) - protege re-ejecucion exacta
     b) por distancia a instancia (tol 120mm) - protege vs dispositivos piloto
        F01/F02 sin mark (pares distintos estan a >=152mm; offset cara-muro <=~75mm)
  5. Solo M_Interruptores: los 13 timbres ya estan colocados y validados.

Ejecutar en pyRevit Python Shell con la vista Piso 5 ACTIVA:
  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\COLOCAR_XPL_INTERRUPTORES_v04.py").read())
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import os
import datetime

print("Ejecucion: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

# ============================================================
# CONFIGURACION
# ============================================================
CONFIG_EQ_PATH = r"D:\Work\PROJECTS\RevitElectrico\config\equivalencias_apartamentos_piso5_v2.json"
CONFIG_APTOS_PATH = r"D:\Work\PROJECTS\RevitElectrico\config\apartamentos_a_procesar.json"
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURA_MM = 1100.0
WALL_SEARCH_TOLERANCE_MM = 300.0
DEDUP_MARK_MM = 100.0
DEDUP_DIST_MM = 120.0
ROT_OFFSET_GRADOS = 90.0   # placa horizontal vs orientacion DXF; si quedan giradas -> 0.0

FAMILIA = "M_Interruptores"
MM_TO_FT = 0.003280839895

# --- Lista de apartamentos (igual que v03) ---
with open(CONFIG_EQ_PATH, 'r') as f:
    EQ_CONFIG = json.load(f)
ALL_APTOS = list(EQ_CONFIG['apartamentos'].keys())

APTOS_A_PROCESAR = None
env_val = os.environ.get('APTOS_A_PROCESAR', '').strip()
if env_val:
    APTOS_A_PROCESAR = [a.strip() for a in env_val.split(',') if a.strip()]
    print("[CONFIG] Apartamentos desde variable de entorno APTOS_A_PROCESAR")
elif os.path.exists(CONFIG_APTOS_PATH):
    with open(CONFIG_APTOS_PATH, 'r') as f:
        cfg = json.load(f)
        APTOS_A_PROCESAR = cfg.get('apartamentos', [])
    print("[CONFIG] Apartamentos desde config/apartamentos_a_procesar.json")
else:
    APTOS_A_PROCESAR = [a for a in ALL_APTOS if a not in ('F01', 'F02')]
    print("[CONFIG] Apartamentos por defecto")

unknown = [a for a in APTOS_A_PROCESAR if a not in ALL_APTOS]
if unknown:
    print("[AVISO] Desconocidos ignorados: {}".format(', '.join(unknown)))
APTOS_A_PROCESAR = [a for a in APTOS_A_PROCESAR if a in ALL_APTOS]

print("=" * 60)
print("COLOCAR_XPL_INTERRUPTORES v04 - LIMPIEZA + FACE-BASED")
print("Apartamentos: {}".format(', '.join(APTOS_A_PROCESAR)))
print("ALTURA {}mm | ROTACION DXF+{} | DEDUP mark={}mm dist={}mm".format(
    ALTURA_MM, ROT_OFFSET_GRADOS, DEDUP_MARK_MM, DEDUP_DIST_MM))
print("=" * 60)

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document
try:
    print("Vista activa: {} (los muros deben ser visibles aqui)".format(doc.ActiveView.Name))
except:
    pass

# --- JSON fuente ---
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

dispositivos_por_apto = {}
for d in data['dispositivos']:
    apto = d['apto_asignado']
    if apto in APTOS_A_PROCESAR and d['familia_revit'] == FAMILIA:
        dispositivos_por_apto.setdefault(apto, []).append(d)

for apto in APTOS_A_PROCESAR:
    print("  {}: {} interruptores".format(apto, len(dispositivos_por_apto.get(apto, []))))
total = sum(len(v) for v in dispositivos_por_apto.values())
print("\nTotal a procesar: {}".format(total))
if total == 0:
    raise SystemExit(0)

# --- Nivel Piso 5 ---
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break
if not level_piso5:
    raise Exception("No se encontro nivel Piso 5")
level_piso5_id = level_piso5.Id
level_elev_ft = level_piso5.Elevation

# --- Simbolos por tipo (SYMBOL_NAME_PARAM; s.Name falla en IronPython) ---
symbols_por_tipo = {}
for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
    try:
        if s.Family.Name != FAMILIA:
            continue
    except:
        continue
    np_ = s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    tname = np_.AsString() if np_ else None
    if tname and tname not in symbols_por_tipo:
        symbols_por_tipo[tname] = s

print("\nSimbolos {} disponibles: {}".format(FAMILIA, ', '.join(sorted(symbols_por_tipo.keys()))))

# ============================================================
# FASE 1: LIMPIEZA
# ============================================================
print("\n" + "=" * 60)
print("FASE 1: LIMPIEZA (basura v03 en origen + timbres duplicados)")
print("=" * 60)

to_delete = []
n_origen = 0
pul_by_mark = {}

for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
    try:
        fam_name = e.Symbol.Family.Name
    except:
        continue
    loc = e.Location
    if not isinstance(loc, LocationPoint):
        continue
    if fam_name == FAMILIA:
        pt = loc.Point
        if abs(pt.X * 304.8) < 10 and abs(pt.Y * 304.8) < 10:
            to_delete.append(e.Id)
            n_origen += 1
    elif fam_name == "M_Pulsador - Interruptor":
        mp = e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        mark = mp.AsString() if mp else None
        if mark and mark.startswith("Pulsador_"):
            pul_by_mark.setdefault(mark, []).append(e.Id)

n_dup = 0
for mark in sorted(pul_by_mark.keys()):
    ids = pul_by_mark[mark]
    if len(ids) > 1:
        ids_sorted = sorted(ids, key=lambda i: int(str(i)))
        for eid in ids_sorted[1:]:
            to_delete.append(eid)
            n_dup += 1
        print("  TIMBRE DUP x{}: {} -> conservar Id={}".format(
            len(ids), mark, int(str(ids_sorted[0]))))

print("  M_Interruptores en origen (0,0): {}".format(n_origen))
print("  Timbres duplicados a eliminar: {}".format(n_dup))

if to_delete:
    t = Transaction(doc, "v04 F1: limpieza origen + timbres dup")
    t.Start()
    borrados = 0
    for eid in to_delete:
        try:
            doc.Delete(eid)
            borrados += 1
        except:
            pass
    t.Commit()
    print("  >>> Eliminados: {}".format(borrados))
else:
    print("  >>> Nada que eliminar")

# ============================================================
# FASE 2: COLOCACION FACE-BASED
# ============================================================
print("\n" + "=" * 60)
print("FASE 2: COLOCACION FACE-BASED (M_Interruptores)")
print("=" * 60)

TOLERANCE_FT = WALL_SEARCH_TOLERANCE_MM * MM_TO_FT
DEDUP_MARK_FT = DEDUP_MARK_MM * MM_TO_FT
DEDUP_DIST_FT = DEDUP_DIST_MM * MM_TO_FT


def _distance_xy_to_curve(curve, target_x, target_y):
    if isinstance(curve, Line):
        sp, ep = curve.GetEndPoint(0), curve.GetEndPoint(1)
        x1, y1, x2, y2 = sp.X, sp.Y, ep.X, ep.Y
        dx, dy = x2 - x1, y2 - y1
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-12:
            return math.hypot(target_x - x1, target_y - y1)
        tt = max(0.0, min(1.0, ((target_x - x1) * dx + (target_y - y1) * dy) / seg_len2))
        return math.hypot(target_x - (x1 + tt * dx), target_y - (y1 + tt * dy))
    n, best = 24, float('inf')
    for i in range(n + 1):
        try:
            p = curve.Evaluate(float(i) / n, False)
            dd = math.hypot(target_x - p.X, target_y - p.Y)
            if dd < best:
                best = dd
        except:
            pass
    return best


def _get_level_id(elem):
    try:
        lid = elem.LevelId
        if lid and lid != ElementId.InvalidElementId():
            return lid
    except:
        pass
    for bp in (BuiltInParameter.LEVEL_PARAM, BuiltInParameter.WALL_BASE_CONSTRAINT, BuiltInParameter.FAMILY_LEVEL_PARAM):
        try:
            p = elem.get_Parameter(bp)
            if p:
                return p.AsElementId()
        except:
            pass
    return None


def _is_in_level(elem, target_id):
    if not target_id:
        return True
    lid = _get_level_id(elem)
    return lid == target_id if lid else False


print("\nCargando muros Piso 5...")
all_walls = []
for w in FilteredElementCollector(doc).OfClass(Wall).ToElements():
    try:
        if w.WallType and _is_in_level(w, level_piso5_id):
            all_walls.append(w)
    except:
        pass
print("  Muros Piso 5: {}".format(len(all_walls)))

geom_opt = Options()
geom_opt.ComputeReferences = True
geom_opt.IncludeNonVisibleObjects = False
try:
    if doc.ActiveView and doc.ActiveView.IsValidObject:
        geom_opt.View = doc.ActiveView
except:
    pass


def find_wall_face(target_xyz):
    best, best_d = None, float('inf')
    tx, ty = target_xyz.X, target_xyz.Y
    for w in all_walls:
        loc = w.Location
        if not isinstance(loc, LocationCurve):
            continue
        c = loc.Curve
        if not c:
            continue
        try:
            dxy = _distance_xy_to_curve(c, tx, ty)
        except:
            continue
        if dxy > TOLERANCE_FT:
            continue
        try:
            p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
            wdir = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0).Normalize()
        except:
            continue
        geom = w.get_Geometry(geom_opt)
        if not geom:
            continue
        for obj in geom:
            if not isinstance(obj, Solid):
                continue
            try:
                if obj.Faces.IsEmpty:
                    continue
            except:
                continue
            for face in obj.Faces:
                if not isinstance(face, PlanarFace):
                    continue
                if abs(face.FaceNormal.Z) > 0.1:
                    continue
                try:
                    proj = face.Project(target_xyz)
                except:
                    continue
                if not proj:
                    continue
                pt_on = proj.XYZPoint
                vec = target_xyz - pt_on
                vlen = vec.GetLength()
                if vlen > 1e-6 and face.FaceNormal.DotProduct(vec) / vlen < 0.5:
                    continue
                try:
                    bbox = face.GetBoundingBox()
                    if bbox:
                        u, v = proj.UVPoint.U, proj.UVPoint.V
                        if not (bbox.Min.U - 0.01 <= u <= bbox.Max.U + 0.01 and bbox.Min.V - 0.01 <= v <= bbox.Max.V + 0.01):
                            continue
                except:
                    pass
                if dxy < best_d:
                    best_d, best = dxy, (face.Reference, face.FaceNormal, pt_on, wdir)
    return best


def _parse_mark_coords(mark):
    """'Interrup_<tipo>_<x>_<y>' -> (x_mm, y_mm) o None."""
    if not mark or not mark.startswith("Interrup_"):
        return None
    partes = mark.split("_")
    if len(partes) >= 4:
        try:
            return (int(partes[-2]), int(partes[-1]))
        except:
            return None
    return None


def _existe_cerca(target_x_ft, target_y_ft):
    """True si ya hay M_Interruptores en ese punto (por mark o por distancia)."""
    for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            if e.Symbol.Family.Name != FAMILIA:
                continue
        except:
            continue
        loc = e.Location
        if not isinstance(loc, LocationPoint):
            continue
        pt = loc.Point
        mp = e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        mark = mp.AsString() if mp else None
        mc = _parse_mark_coords(mark)
        if mc:
            mx = mc[0] * MM_TO_FT
            my = mc[1] * MM_TO_FT
            if math.hypot(mx - target_x_ft, my - target_y_ft) <= DEDUP_MARK_FT:
                return True, e.Id, "mark"
        if math.hypot(pt.X - target_x_ft, pt.Y - target_y_ft) <= DEDUP_DIST_FT:
            return True, e.Id, "dist"
    return False, None, None


totals = {'placed': 0, 'skipped': 0, 'failed': 0, 'rot_ok': 0, 'rot_fail': 0}

for APTO in APTOS_A_PROCESAR:
    disps = dispositivos_por_apto.get(APTO, [])
    if not disps:
        print("\n>>> {}: SIN INTERRUPTORES - saltando".format(APTO))
        continue

    print("\n" + "=" * 60)
    print("PROCESANDO: {} ({} interruptores)".format(APTO, len(disps)))
    print("=" * 60)

    placed = 0
    skipped = 0
    failed = 0
    rot_ok = 0
    rot_fail = 0

    t = Transaction(doc, "v04 interruptores {}".format(APTO))
    t.Start()
    for d in disps:
        try:
            x = d['x_mm'] * MM_TO_FT
            y = d['y_mm'] * MM_TO_FT
            pt = XYZ(x, y, level_elev_ft + ALTURA_MM * MM_TO_FT)

            existe, eid, motivo = _existe_cerca(x, y)
            if existe:
                skipped += 1
                print("  SKIP DUP[{}]: {} @ ({:.1f},{:.1f}) ya existe Id={}".format(
                    motivo, d['nombre_dxf'], x, y, int(str(eid))))
                continue

            tipo = d.get('tipo_revit') or 'Simple'
            symbol = symbols_por_tipo.get(tipo)
            if not symbol:
                failed += 1
                print("  FAIL [TIPO]: {} tipo_revit='{}' sin simbolo".format(d['nombre_dxf'], tipo))
                continue

            wr = find_wall_face(pt)
            if not wr:
                failed += 1
                print("  FAIL [SIN-MURO]: {} @ ({:.1f},{:.1f}) sin cara de muro a {}mm".format(
                    d['nombre_dxf'], x, y, WALL_SEARCH_TOLERANCE_MM))
                continue
            fref, fn, fpt, wdir = wr

            try:
                if not symbol.IsActive:
                    symbol.Activate()
                    doc.Regenerate()
            except:
                pass

            inst = None
            err_place = ""
            try:
                inst = doc.Create.NewFamilyInstance(fref, fpt, XYZ.BasisZ, symbol)
            except Exception as ex:
                err_place = str(ex)
                if "Multiple targets" in err_place:
                    try:
                        inst = doc.Create.NewFamilyInstance(fref, fpt, XYZ.BasisZ, symbol, ElementId.InvalidElementId())
                    except:
                        pass
            if not inst:
                failed += 1
                print("  FAIL [PLACE]: {} - {}".format(d['nombre_dxf'], err_place[:80]))
                continue

            rot_total = math.radians(float(d['rotacion_grados']) + ROT_OFFSET_GRADOS)
            if abs(rot_total) > 1e-6:
                ok = False
                try:
                    axis = Line.CreateBound(fpt, fpt + fn * 10)
                    ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_total)
                    ok = True
                except:
                    try:
                        axis2 = Line.CreateBound(fpt, XYZ(fpt.X, fpt.Y, fpt.Z + 10))
                        ElementTransformUtils.RotateElement(doc, inst.Id, axis2, rot_total)
                        ok = True
                    except:
                        pass
                if ok:
                    rot_ok += 1
                else:
                    rot_fail += 1

            mark = "Interrup_{}_{}_{}".format(
                tipo.replace(' ', '')[:8], int(round(d['x_mm'])), int(round(d['y_mm'])))
            pm = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if pm:
                pm.Set(mark)

            placed += 1
            print("  OK [WALL-FB]: {} tipo={} @ ({:.1f},{:.1f},{:.1f}) rot={}+{}".format(
                d['nombre_dxf'], tipo, fpt.X, fpt.Y, fpt.Z, d['rotacion_grados'], ROT_OFFSET_GRADOS))

        except Exception as e:
            failed += 1
            print("  FAIL: {} - {}".format(d.get('nombre_dxf', '?'), str(e)[:100]))
    t.Commit()

    totals['placed'] += placed
    totals['skipped'] += skipped
    totals['failed'] += failed
    totals['rot_ok'] += rot_ok
    totals['rot_fail'] += rot_fail
    print("  {}: PLACE={} SKIP={} FAIL={} ROT_OK={} ROT_FAIL={}".format(
        APTO, placed, skipped, failed, rot_ok, rot_fail))

# ============================================================
# RESUMEN
# ============================================================
print("\n" + "=" * 60)
print("RESUMEN TOTAL - INTERRUPTORES v04")
print("=" * 60)
print("  Colocados nuevos:      {}".format(totals['placed']))
print("  Saltados (dedup):      {}".format(totals['skipped']))
print("  Fallidos:              {}".format(totals['failed']))
print("  Rotacion OK:           {}".format(totals['rot_ok']))
print("  Rotacion fail:         {}".format(totals['rot_fail']))
print("=" * 60)