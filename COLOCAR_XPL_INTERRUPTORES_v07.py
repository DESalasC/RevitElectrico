"""
COLOCAR_XPL_INTERRUPTORES_v07.py - WALL-HOST + dedup corregido (pares espalda-espalda)
Version: 07 | Fecha: 2026-11-22

FIX vs v06: el dedup por DISTANCIA solo se aplica a instancias SIN mark
(colocadas a mano / piloto, que es lo que protege). Las instancias con mark
de script se comparan JSON-a-JSON via mark (exacto). Esto corrige los 2 falsos
positivos de v06: pares ELEC-I-S-C1-5A espalda-espalda en C14 (-95.8,8.1)ft y
D13 (-95.8,49.9)ft, cuyas proyecciones sobre el muro coinciden (116mm) pero son
dispositivos distintos (rot 90 vs 270, caras opuestas del muro).

Re-ejecutar v07 tras v06 es seguro e idempotente: esperado PLACE=2 (los pares
espalda-espalda), SKIP=94 (92 por mark + 2 piloto TF 02 por dist), FAIL=0.

Receta de colocacion (validada TEST v02-V2, ver v06):
  1. NewFamilyInstance(pt_json, sym, MURO, NonStructural) -> "dormida"
  2. RotateElement 0.5 en la proyeccion -> despierta en el muro
  3. MoveElement(delta = proyeccion_Z_objetivo - Location_real) -> Z a nivel+1100
  4. Verificacion real 60mm; si falla -> borrar + FAIL

Ejecutar en pyRevit Python Shell (vista Piso 5 activa):
  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\COLOCAR_XPL_INTERRUPTORES_v07.py").read())
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
DEDUP_DIST_MM = 120.0     # solo para instancias SIN mark (mano/piloto)
VERIF_TOL_MM = 60.0

FAMILIA = "M_Interruptores"
MM_TO_FT = 0.003280839895

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
print("COLOCAR_XPL_INTERRUPTORES v07 - WALL-HOST + DEDUP CORREGIDO")
print("Apartamentos: {}".format(', '.join(APTOS_A_PROCESAR)))
print("ALTURA {}mm | TOL muro {}mm | DEDUP mark={}mm (solo sin mark) dist={}mm | VERIF {}mm".format(
    ALTURA_MM, WALL_SEARCH_TOLERANCE_MM, DEDUP_MARK_MM, DEDUP_DIST_MM, VERIF_TOL_MM))
print("=" * 60)

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

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

level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break
if not level_piso5:
    raise Exception("No se encontro nivel Piso 5")
level_elev_ft = level_piso5.Elevation
target_z = level_elev_ft + ALTURA_MM * MM_TO_FT

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
# FASE 1: LIMPIEZA (idempotente)
# ============================================================
print("\n" + "=" * 60)
print("FASE 1: LIMPIEZA (basura en origen + timbres duplicados)")
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
    t = Transaction(doc, "v07 F1: limpieza origen + timbres dup")
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
# FASE 2: COLOCACION WALL-HOST (dedup corregido)
# ============================================================
print("\n" + "=" * 60)
print("FASE 2: COLOCACION WALL-HOST + WAKE + Z-FIX + VERIFICACION")
print("=" * 60)

TOLERANCE_FT = WALL_SEARCH_TOLERANCE_MM * MM_TO_FT
DEDUP_MARK_FT = DEDUP_MARK_MM * MM_TO_FT
DEDUP_DIST_FT = DEDUP_DIST_MM * MM_TO_FT
VERIF_TOL_FT = VERIF_TOL_MM * MM_TO_FT


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
        if w.WallType and _is_in_level(w, level_piso5.Id):
            all_walls.append(w)
    except:
        pass
print("  Muros Piso 5: {}".format(len(all_walls)))

wall_curves = []
for w in all_walls:
    try:
        loc = w.Location
        if not isinstance(loc, LocationCurve):
            continue
        c = loc.Curve
        if not c:
            continue
        p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
        wall_curves.append((w, p0.X, p0.Y, p1.X - p0.X, p1.Y - p0.Y))
    except:
        pass


def find_wall_and_projection(tx, ty):
    best = None
    best_d = float('inf')
    for (w, x0, y0, dx, dy) in wall_curves:
        L2 = dx * dx + dy * dy
        if L2 > 1e-12:
            tt = max(0.0, min(1.0, ((tx - x0) * dx + (ty - y0) * dy) / L2))
        else:
            tt = 0.0
        d = math.hypot(tx - (x0 + tt * dx), ty - (y0 + tt * dy))
        if d < best_d:
            best_d = d
            best = (w, x0 + tt * dx, y0 + tt * dy)
    return best, best_d


def _parse_mark_coords(mark):
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
    """Dedup v07: mark-exacto para instancias con mark; dist SOLO para sin mark."""
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
            # con mark: NO dist-check (pares espalda-espalda comparten proyeccion)
        else:
            if math.hypot(pt.X - target_x_ft, pt.Y - target_y_ft) <= DEDUP_DIST_FT:
                return True, e.Id, "dist"
    return False, None, None


totals = {'placed': 0, 'skipped': 0, 'failed': 0, 'deleted_bad': 0}

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
    deleted_bad = 0

    t = Transaction(doc, "v07 interruptores {} (wall-host)".format(APTO))
    t.Start()
    for d in disps:
        inst = None
        try:
            x = d['x_mm'] * MM_TO_FT
            y = d['y_mm'] * MM_TO_FT
            pt = XYZ(x, y, target_z)

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

            res, dist = find_wall_and_projection(x, y)
            if not res or dist > TOLERANCE_FT:
                failed += 1
                print("  FAIL [SIN-MURO]: {} @ ({:.1f},{:.1f}) sin muro a {}mm (dist={:.0f}mm)".format(
                    d['nombre_dxf'], x, y, WALL_SEARCH_TOLERANCE_MM, dist * 304.8))
                continue
            wall, px, py = res

            try:
                if not symbol.IsActive:
                    symbol.Activate()
                    doc.Regenerate()
            except:
                pass

            inst = doc.Create.NewFamilyInstance(pt, symbol, wall, Structure.StructuralType.NonStructural)

            eje = XYZ(px, py, target_z)
            ax = Line.CreateBound(eje, XYZ(eje.X, eje.Y, eje.Z + 1))
            ElementTransformUtils.RotateElement(doc, inst.Id, ax, math.radians(0.5))

            lp = inst.Location
            if isinstance(lp, LocationPoint):
                delta = XYZ(px, py, target_z) - lp.Point
                if delta.GetLength() > 0.001:
                    ElementTransformUtils.MoveElement(doc, inst.Id, delta)

            lp2 = inst.Location
            ok_pos = False
            real = (0.0, 0.0, 0.0)
            if isinstance(lp2, LocationPoint):
                q = lp2.Point
                real = (q.X * 304.8, q.Y * 304.8, q.Z * 304.8)
                if (abs(q.X - px) <= VERIF_TOL_FT and abs(q.Y - py) <= VERIF_TOL_FT
                        and abs(q.Z - target_z) <= VERIF_TOL_FT):
                    ok_pos = True
            if not ok_pos:
                try:
                    doc.Delete(inst.Id)
                except:
                    pass
                inst = None
                deleted_bad += 1
                failed += 1
                print("  FAIL [POS]: {} real=({:.0f},{:.0f},{:.0f}) esperado=({:.0f},{:.0f},{:.0f})".format(
                    d['nombre_dxf'], real[0], real[1], real[2], px * 304.8, py * 304.8, target_z * 304.8))
                continue

            mark = "Interrup_{}_{}_{}".format(
                tipo.replace(' ', '')[:8], int(round(d['x_mm'])), int(round(d['y_mm'])))
            pm = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if pm:
                pm.Set(mark)

            placed += 1
            print("  OK [WALL-HOST]: {} tipo={} real=({:.0f},{:.0f},{:.0f})mm".format(
                d['nombre_dxf'], tipo, real[0], real[1], real[2]))

        except Exception as e:
            if inst is not None:
                try:
                    doc.Delete(inst.Id)
                except:
                    pass
                deleted_bad += 1
            failed += 1
            print("  FAIL: {} - {}".format(d.get('nombre_dxf', '?'), str(e)[:100]))
    t.Commit()

    totals['placed'] += placed
    totals['skipped'] += skipped
    totals['failed'] += failed
    totals['deleted_bad'] += deleted_bad
    print("  {}: PLACE={} SKIP={} FAIL={} (borradas-mal-posicionadas={})".format(
        APTO, placed, skipped, failed, deleted_bad))

# ============================================================
# VERIFICACION FINAL GLOBAL
# ============================================================
print("\n" + "=" * 60)
print("VERIFICACION FINAL (conteo global real)")
print("=" * 60)
n_total = 0
n_origen_final = 0
for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
    try:
        if e.Symbol.Family.Name != FAMILIA:
            continue
    except:
        continue
    n_total += 1
    loc = e.Location
    if isinstance(loc, LocationPoint):
        p = loc.Point
        if abs(p.X * 304.8) < 10 and abs(p.Y * 304.8) < 10:
            n_origen_final += 1

print("  M_Interruptores totales: {}".format(n_total))
print("  En origen (debe ser 0):  {}".format(n_origen_final))
if n_origen_final > 0:
    print("  >>> AVISO: hay instancias en origen - revisar")

print("\n" + "=" * 60)
print("RESUMEN TOTAL - INTERRUPTORES v07")
print("=" * 60)
print("  Colocados nuevos:      {}".format(totals['placed']))
print("  Saltados (dedup):      {}".format(totals['skipped']))
print("  Fallidos:              {}".format(totals['failed']))
print("  Borradas (mal posic.): {}".format(totals['deleted_bad']))
print("=" * 60)