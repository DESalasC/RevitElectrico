"""
F6_COLOCAR_XPL_TODOS_APTOS_TOMAS.py - v01
Version: 01
Date: 2026-11-21
Author: Basado en F6_COLOCAR_XPL_TOMAS_MANUAL_v08 (TF 01a) -> generalizado para multiples apartamentos

PROPOSITO:
  Colocar tomas de corriente (M_Toma doble, M_Comunicaciones) en TODOS los apartamentos
  del JSON XPL usando estrategia face-based wall-hosted con filtrado por nivel Piso 5.

ESTRATEGIA DE HOST (heredada de v08):
  1. Filtrar muros, suelos y cielorrasos por LevelId == Piso 5
  2. Buscar cara de muro vertical cerca en XY (ideal - rehosteable, vertical)
  3. Si no hay muro, buscar losa/suelo del Piso 5 (cara superior - rehosteable, horizontal)
  4. Si no hay suelo, buscar cielorraso del Piso 5 (cara inferior - rehosteable, horizontal)
  5. Ultimo recurso: Level-hosted (NO rehosteable, con aviso)

APARTAMENTOS EN JSON XPL:
  B15, B16, C14, D13, E05, E06, E07, E07a, E08, E08a,
  F01, F17, F17a, F18, F18a, TF 01a, TF 01b, TF 02, TF 02a, TF 02b

NOTA: F01 y F02 ya estan colocados (referencia intocable). Se pueden saltar.
      TF 01a ya fue procesado con v08. Se puede saltar o reprocesar.
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import traceback

# ============================================================
# CONFIGURACION
# ============================================================
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURAS_MM = {
    'M_Toma doble': 1000,
    'M_Comunicaciones': 1000,
}

# Tolerancias de busqueda
WALL_SEARCH_TOLERANCE_MM = 300.0
FLOOR_SEARCH_TOLERANCE_MM = 5000.0

# Familias objetivo
FAMILIAS_OBJETIVO = ('M_Toma doble', 'M_Comunicaciones')

# Apartamentos a procesar (comentar los que ya estan listos)
APTOS_A_PROCESAR = [
    'B15', 'B16', 'C14', 'D13',
    'E05', 'E06', 'E07', 'E07a', 'E08', 'E08a',
    'F17', 'F17a', 'F18', 'F18a',
    'TF 01b', 'TF 02', 'TF 02a', 'TF 02b',
]
# Saltar: 'F01', 'F02' (referencia intocable), 'TF 01a' (ya hecho con v08)

# ============================================================
# INIT
# ============================================================
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("=" * 70)
print("F6_COLOCAR_XPL_TODOS_APTOS_TOMAS v01 - MULTI-APTO FACE-BASED")
print("Apartamentos a procesar:", ", ".join(APTOS_A_PROCESAR))
print("MODO: Pared Piso5 -> Suelo Piso5 -> Techo Piso5 -> Level")
print("=" * 70)

# ============================================================
# CARGA JSON
# ============================================================
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

# Filtrar dispositivos de los apartamentos objetivo
dispositivos_por_apto = {}
for d in data['dispositivos']:
    apto = d['apto_asignado']
    if apto in APTOS_A_PROCESAR and d['familia_revit'] in FAMILIAS_OBJETIVO:
        dispositivos_por_apto.setdefault(apto, []).append(d)

for apto in APTOS_A_PROCESAR:
    count = len(dispositivos_por_apto.get(apto, []))
    print("  {}: {} tomas".format(apto, count))

total_tomas = sum(len(v) for v in dispositivos_por_apto.values())
print("\nTotal tomas a colocar:", total_tomas)

if total_tomas == 0:
    print("ERROR: No hay tomas para procesar")
    raise SystemExit(0)

# ============================================================
# NIVEL PISO 5
# ============================================================
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break

if not level_piso5:
    raise Exception("No se encontro el nivel Piso 5 (elev {} mm)".format(NIVEL_PISO5_ELEV_MM))

print("\nNivel: {} - elev: {:.1f} mm".format(level_piso5.Name, level_piso5.Elevation * 304.8))
level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation

# ============================================================
# SIMBOLOS DE FAMILIA
# ============================================================
symbols = {}
for fam_name in FAMILIAS_OBJETIVO:
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.Family.Name == fam_name:
            symbols[fam_name] = s
            if not s.IsActive:
                s.Activate()
            break

missing = [f for f in FAMILIAS_OBJETIVO if f not in symbols]
if missing:
    print("ADVERTENCIA: No se encontro el simbolo para:", missing)

print("\nSimbolos cargados:")
for fam_name_key, sym_obj in symbols.items():
    try:
        print("  - {} -> Id: {}".format(fam_name_key, str(sym_obj.Id)))
    except Exception:
        print("  - {} -> (no se pudo leer Id)".format(fam_name_key))

# ============================================================
# CONSTANTES Y HELPERS DE GEOMETRIA
# ============================================================
MM_TO_FT = 0.003280839895
TOLERANCE_FT = WALL_SEARCH_TOLERANCE_MM * MM_TO_FT
FLOOR_TOL_FT = FLOOR_SEARCH_TOLERANCE_MM * MM_TO_FT


def _distance_xy_to_curve(curve, target_x, target_y):
    """
    Distancia minima en XY (ignorando Z) desde un punto (x,y) a una curva de Revit.
    Revit curve.Project() mide distancia 3D - no nos sirve para muros en pisos altos.
    """
    if isinstance(curve, Line):
        sp = curve.GetEndPoint(0)
        ep = curve.GetEndPoint(1)
        x1, y1 = sp.X, sp.Y
        x2, y2 = ep.X, ep.Y
        dx, dy = x2 - x1, y2 - y1
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-12:
            return math.hypot(target_x - x1, target_y - y1)
        t = ((target_x - x1) * dx + (target_y - y1) * dy) / seg_len2
        t = max(0.0, min(1.0, t))
        cx = x1 + t * dx
        cy = y1 + t * dy
        return math.hypot(target_x - cx, target_y - cy)

    n = 24
    best = float('inf')
    for i in range(n + 1):
        u = float(i) / float(n)
        try:
            p = curve.Evaluate(u, False)
            d = math.hypot(target_x - p.X, target_y - p.Y)
            if d < best:
                best = d
        except Exception:
            continue
    return best


# ============================================================
# CACHE DE MUROS, SUELOS Y TECHOS DEL NIVEL PISO 5
# ============================================================
def _get_element_level_id(elem):
    """
    Obtiene el LevelId de un elemento (Wall, Floor, Ceiling).
    Para muros, el parametro LEVEL_PARAM (BuiltInParameter.LEVEL_PARAM)
    da el nivel base. Para Floor/Ceiling, la propiedad LevelId directa.
    """
    try:
        lid = elem.LevelId
        if lid is not None and lid != ElementId.InvalidElementId():
            return lid
    except Exception:
        pass

    try:
        p = elem.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if p is not None:
            return p.AsElementId()
    except Exception:
        pass

    try:
        p = elem.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
        if p is not None:
            return p.AsElementId()
    except Exception:
        pass

    try:
        p = elem.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if p is not None:
            return p.AsElementId()
    except Exception:
        pass

    return None


def _is_in_level(elem, target_level_id):
    """True si el elemento pertenece al nivel indicado."""
    if target_level_id is None:
        return True
    lid = _get_element_level_id(elem)
    if lid is None:
        return False
    return lid == target_level_id


print("\nCargando muros, suelos y cielorrasos del documento...")
all_walls_raw = list(FilteredElementCollector(doc).OfClass(Wall).ToElements())
print("Total muros (sin filtrar):", len(all_walls_raw))

clean_walls = []
for w in all_walls_raw:
    try:
        if w.WallType is None:
            continue
        if not _is_in_level(w, level_piso5_id):
            continue
        clean_walls.append(w)
    except Exception:
        pass
all_walls = clean_walls
print("Muros validos en Piso 5:", len(all_walls))

all_floors_raw = list(FilteredElementCollector(doc).OfClass(Floor).ToElements())
all_floors = []
for f in all_floors_raw:
    try:
        if not _is_in_level(f, level_piso5_id):
            continue
        all_floors.append(f)
    except Exception:
        pass
print("Total suelos (Floor): {} - en Piso 5: {}".format(len(all_floors_raw), len(all_floors)))

all_ceilings = []
all_ceilings_raw = []
try:
    all_ceilings_raw = list(FilteredElementCollector(doc).OfClass(Ceiling).ToElements())
    for c in all_ceilings_raw:
        try:
            if not _is_in_level(c, level_piso5_id):
                continue
            all_ceilings.append(c)
        except Exception:
            pass
    print("Total cielorrasos (Ceiling): {} - en Piso 5: {}".format(
        len(all_ceilings_raw), len(all_ceilings)))
except Exception:
    print("Ceiling class no disponible - se omitira el fallback de techo")

# Opciones de geometria (con referencias)
geom_opt = Options()
geom_opt.ComputeReferences = True
geom_opt.IncludeNonVisibleObjects = False
try:
    if doc.ActiveView and doc.ActiveView.IsValidObject:
        geom_opt.View = doc.ActiveView
except Exception:
    pass


# ============================================================
# BUSQUEDA DE HOST: PARED -> SUELO -> TECHO
# ============================================================
def find_wall_face_at_point(target_xyz):
    """
    Busca muro mas cercano y devuelve:
        (face_reference, face_normal, projected_point_on_face, wall_dir)
    Solo caras verticales con normal mirando al punto.
    """
    best_result = None
    best_distance = float('inf')

    target_x = target_xyz.X
    target_y = target_xyz.Y

    for wall in all_walls:
        loc = wall.Location
        if not isinstance(loc, LocationCurve):
            continue
        curve = loc.Curve
        if curve is None:
            continue

        try:
            distance_xy = _distance_xy_to_curve(curve, target_x, target_y)
        except Exception:
            continue
        if distance_xy > TOLERANCE_FT:
            continue

        try:
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
            wall_dir_v = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0)
            wlen = wall_dir_v.GetLength()
            if wlen < 1e-9:
                continue
            wall_dir = wall_dir_v.Normalize()
        except Exception:
            continue

        geom_elem = wall.get_Geometry(geom_opt)
        if geom_elem is None:
            continue

        for geom_obj in geom_elem:
            if not isinstance(geom_obj, Solid):
                continue
            try:
                if geom_obj.Faces.IsEmpty:
                    continue
            except Exception:
                continue

            for face in geom_obj.Faces:
                if not isinstance(face, PlanarFace):
                    continue

                face_normal = face.FaceNormal
                if abs(face_normal.Z) > 0.1:
                    continue  # Solo caras verticales

                try:
                    face_proj = face.Project(target_xyz)
                except Exception:
                    continue
                if face_proj is None:
                    continue

                proj_pt = face_proj.XYZPoint

                vec_to_point = target_xyz - proj_pt
                vlen = vec_to_point.GetLength()
                if vlen > 1e-6:
                    dot = face_normal.DotProduct(vec_to_point) / vlen
                    if dot < 0.5:
                        continue

                try:
                    bbox = face.GetBoundingBox()
                    if bbox is not None:
                        u = face_proj.UVPoint.U
                        v = face_proj.UVPoint.V
                        tol = 0.01
                        if not (bbox.Min.U - tol <= u <= bbox.Max.U + tol
                                and bbox.Min.V - tol <= v <= bbox.Max.V + tol):
                            continue
                except Exception:
                    pass

                if distance_xy < best_distance:
                    best_distance = distance_xy
                    best_result = (face.Reference, face_normal, proj_pt, wall_dir)

    return best_result


def find_horizontal_face_at_point(target_xyz, host_elements, want_top=True):
    """
    Busca una cara HORIZONTAL de un conjunto de elementos (Floor/Ceiling)
    en la posicion XY del target.

    want_top=True  -> busca cara con normal Z > 0 (cara SUPERIOR, mira hacia arriba)
    want_top=False -> busca cara con normal Z < 0 (cara INFERIOR, mira hacia abajo)

    Devuelve: (face_reference, face_normal, projected_point_on_face, None)
    """
    best_result = None
    best_distance = float('inf')

    target_x = target_xyz.X
    target_y = target_xyz.Y

    for elem in host_elements:
        try:
            bbox = elem.get_BoundingBox(None)
            if bbox is None:
                continue
            if (target_x < bbox.Min.X - FLOOR_TOL_FT
                    or target_x > bbox.Max.X + FLOOR_TOL_FT
                    or target_y < bbox.Min.Y - FLOOR_TOL_FT
                    or target_y > bbox.Max.Y + FLOOR_TOL_FT):
                continue
        except Exception:
            pass

        geom_elem = elem.get_Geometry(geom_opt)
        if geom_elem is None:
            continue

        for geom_obj in geom_elem:
            if not isinstance(geom_obj, Solid):
                continue
            try:
                if geom_obj.Faces.IsEmpty:
                    continue
            except Exception:
                continue

            for face in geom_obj.Faces:
                if not isinstance(face, PlanarFace):
                    continue

                face_normal = face.FaceNormal

                if abs(face_normal.Z) < 0.9:
                    continue

                if want_top and face_normal.Z < 0:
                    continue
                if (not want_top) and face_normal.Z > 0:
                    continue

                try:
                    face_proj = face.Project(target_xyz)
                except Exception:
                    continue
                if face_proj is None:
                    continue

                proj_pt = face_proj.XYZPoint

                d_xy = math.hypot(proj_pt.X - target_x, proj_pt.Y - target_y)
                if d_xy > FLOOR_TOL_FT:
                    continue

                try:
                    bbox_f = face.GetBoundingBox()
                    if bbox_f is not None:
                        u = face_proj.UVPoint.U
                        v = face_proj.UVPoint.V
                        tol = 0.01
                        if not (bbox_f.Min.U - tol <= u <= bbox_f.Max.U + tol
                                and bbox_f.Min.V - tol <= v <= bbox_f.Max.V + tol):
                            continue
                except Exception:
                    pass

                if d_xy < best_distance:
                    best_distance = d_xy
                    best_result = (face.Reference, face_normal, proj_pt, None)

    return best_result


# ============================================================
# PROCESAR CADA APARTAMENTO
# ============================================================
total_general = 0
total_failed_general = 0
total_wall_general = 0
total_floor_general = 0
total_ceiling_general = 0
total_level_general = 0
total_rot_ok_general = 0
total_rot_failed_general = 0

for APTO_OBJETIVO in APTOS_A_PROCESAR:
    tomas = dispositivos_por_apto.get(APTO_OBJETIVO, [])
    if not tomas:
        print("\n>>> {}: SIN TOMAS - saltando".format(APTO_OBJETIVO))
        continue

    print("\n" + "=" * 70)
    print("PROCESANDO: {} ({} tomas)".format(APTO_OBJETIVO, len(tomas)))
    print("=" * 70)

    placed_total = 0
    placed_on_wall = 0
    placed_on_floor = 0
    placed_on_ceiling = 0
    placed_level = 0
    failed = 0
    rot_ok = 0
    rot_failed = 0
    fallback_list = []
    all_method_list = []

    t = Transaction(doc, "Place Tomas {} - Face-based".format(APTO_OBJETIVO))
    t.Start()

    for d in tomas:
        try:
            x = d['x_mm'] * MM_TO_FT
            y = d['y_mm'] * MM_TO_FT
            fam = d['familia_revit']
            z_mm = ALTURAS_MM.get(fam, NIVEL_PISO5_ELEV_MM)
            z_ft = z_mm * MM_TO_FT

            symbol = symbols.get(fam)
            if not symbol:
                print("  SKIP: no symbol for {}".format(fam))
                failed += 1
                continue

            rot_dxf_deg = float(d['rotacion_grados'])
            rot_dxf_rad = math.radians(rot_dxf_deg)

            target_z = level_piso5_elev_ft + z_ft
            pt = XYZ(x, y, target_z)

            inst = None
            method = None
            face_normal = None
            face_pt = None

            # ----- INTENTO 1: PARED (vertical, ideal) -----
            wall_result = find_wall_face_at_point(pt)

            if wall_result is not None:
                face_ref, face_normal, face_pt, wall_dir = wall_result
                try:
                    direction = XYZ.BasisZ
                    try:
                        inst = doc.Create.NewFamilyInstance(
                            face_ref, face_pt, direction, symbol)
                    except Exception as e_amb:
                        if "Multiple targets" in str(e_amb):
                            inst = doc.Create.NewFamilyInstance(
                                face_ref, face_pt, direction, symbol,
                                ElementId.InvalidElementId())
                        else:
                            raise
                    method = "WALL-FACE"
                    placed_on_wall += 1
                except Exception as we:
                    print("    (wall placement failed): {}".format(str(we)[:80]))
                    inst = None

            # ----- INTENTO 2: SUELO/LOSA (cara superior) -----
            if inst is None and all_floors:
                floor_result = find_horizontal_face_at_point(
                    pt, all_floors, want_top=True)
                if floor_result is not None:
                    face_ref, face_normal, face_pt, _ = floor_result
                    try:
                        direction = XYZ.BasisX
                        try:
                            inst = doc.Create.NewFamilyInstance(
                                face_ref, face_pt, direction, symbol)
                        except Exception as e_amb:
                            if "Multiple targets" in str(e_amb):
                                inst = doc.Create.NewFamilyInstance(
                                    face_ref, face_pt, direction, symbol,
                                    ElementId.InvalidElementId())
                            else:
                                raise
                        method = "FLOOR-TOP"
                        placed_on_floor += 1
                    except Exception as fe:
                        print("    (floor placement failed): {}".format(str(fe)[:80]))
                        inst = None

            # ----- INTENTO 3: TECHO (cara inferior) -----
            if inst is None and all_ceilings:
                ceil_result = find_horizontal_face_at_point(
                    pt, all_ceilings, want_top=False)
                if ceil_result is not None:
                    face_ref, face_normal, face_pt, _ = ceil_result
                    try:
                        direction = XYZ.BasisX
                        try:
                            inst = doc.Create.NewFamilyInstance(
                                face_ref, face_pt, direction, symbol)
                        except Exception as e_amb:
                            if "Multiple targets" in str(e_amb):
                                inst = doc.Create.NewFamilyInstance(
                                    face_ref, face_pt, direction, symbol,
                                    ElementId.InvalidElementId())
                            else:
                                raise
                        method = "CEILING-BOTTOM"
                        placed_on_ceiling += 1
                    except Exception as ce:
                        print("    (ceiling placement failed): {}".format(str(ce)[:80]))
                        inst = None

            # ----- ROTACION (BEST-EFFORT) -----
            if inst is not None and method != "LEVEL-FALLBACK" and abs(rot_dxf_rad) > 1e-6:
                rot_applied = False

                if not rot_applied and face_normal is not None and face_pt is not None:
                    try:
                        axis = Line.CreateBound(
                            face_pt, face_pt + face_normal * 10.0)
                        ElementTransformUtils.RotateElement(
                            doc, inst.Id, axis, rot_dxf_rad)
                        rot_applied = True
                    except Exception:
                        pass

                if not rot_applied and face_pt is not None:
                    try:
                        axis = Line.CreateBound(
                            face_pt,
                            XYZ(face_pt.X, face_pt.Y, face_pt.Z + 10.0))
                        ElementTransformUtils.RotateElement(
                            doc, inst.Id, axis, rot_dxf_rad)
                        rot_applied = True
                    except Exception:
                        pass

                if not rot_applied and face_pt is not None:
                    try:
                        loc = inst.Location
                        if isinstance(loc, LocationPoint):
                            axis = Line.CreateBound(
                                face_pt,
                                XYZ(face_pt.X, face_pt.Y, face_pt.Z + 10.0))
                            loc.Rotate(axis, rot_dxf_rad)
                            rot_applied = True
                    except Exception:
                        pass

                if rot_applied:
                    rot_ok += 1
                else:
                    rot_failed += 1

            # ----- INTENTO 4: Level-hosted (ULTIMO RECURSO) -----
            if inst is None:
                inst = doc.Create.NewFamilyInstance(
                    pt, symbol, level_piso5,
                    Structure.StructuralType.NonStructural)

                p_level = inst.get_Parameter(
                    BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
                if p_level:
                    p_level.Set(level_piso5_id)

                if abs(rot_dxf_rad) > 1e-6:
                    try:
                        axis = Line.CreateBound(pt, pt + XYZ(0, 0, 10.0))
                        ElementTransformUtils.RotateElement(
                            doc, inst.Id, axis, rot_dxf_rad)
                        rot_ok += 1
                    except Exception:
                        rot_failed += 1

                placed_level += 1
                method = "LEVEL-FALLBACK"
                fallback_list.append((d.get('nombre_dxf', '?'),
                                      d['x_mm'], d['y_mm']))

                face_normal = None
                face_pt = None

            # Unique Mark
            mark = "{}_{}_{}_{}".format(
                fam.replace('M_', '').replace(' ', '')[:8],
                d['tipo_revit'].replace(' ', '')[:6],
                int(round(d['x_mm'])), int(round(d['y_mm']))
            )
            p_mark = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mark:
                p_mark.Set(mark)

            placed_total += 1
            all_method_list.append((d.get('nombre_dxf', '?'), method))

            print("  OK [{}]: {} @ ({:.2f},{:.2f},{:.2f}) rot={:.0f}deg mark={}".format(
                method, d['nombre_dxf'], float(x), float(y), float(target_z),
                float(rot_dxf_deg), mark))

        except Exception as e:
            failed += 1
            print("  FAIL: {} - {}".format(d.get('nombre_dxf', '?'), str(e)))

    t.Commit()

    # Resumen por apartamento
    print("\n--- RESUMEN {} ---".format(APTO_OBJETIVO))
    print("  Total colocados:                               ", placed_total)
    print("  En PARED (vertical, ideal):                    ", placed_on_wall)
    print("  En SUELO (horizontal, rehosteable):           ", placed_on_floor)
    print("  En TECHO (horizontal, rehosteable):           ", placed_on_ceiling)
    print("  Level-hosted fallback (NO rehosteable!):      ", placed_level)
    print("  Fallidos:                                     ", failed)
    print("  Rotacion aplicada OK:                         ", rot_ok)
    print("  Rotacion fallida (toma sin rotar, rehosteable):", rot_failed)

    rehosteable_total = placed_on_wall + placed_on_floor + placed_on_ceiling
    print("  >>> {} de {} tomas son REHOSTEABLES".format(rehosteable_total, placed_total))
    print("  >>> {} NO son rehosteables (level-hosted)".format(placed_level))

    if rot_failed > 0:
        print("  >>> AVISO: {} tomas con rotacion FALLIDA (sin rotar, pero colocadas)".format(rot_failed))

    # Acumular totales
    total_general += placed_total
    total_failed_general += failed
    total_wall_general += placed_on_wall
    total_floor_general += placed_on_floor
    total_ceiling_general += placed_on_ceiling
    total_level_general += placed_level
    total_rot_ok_general += rot_ok
    total_rot_failed_general += rot_failed


# ============================================================
# RESUMEN GENERAL
# ============================================================
print("\n" + "=" * 70)
print("RESUMEN GENERAL - TODOS LOS APARTAMENTOS")
print("=" * 70)
print("  Total colocados:                               ", total_general)
print("  En PARED  (vertical, ideal):                   ", total_wall_general)
print("  En SUELO  (horizontal, rehosteable):          ", total_floor_general)
print("  En TECHO  (horizontal, rehosteable):          ", total_ceiling_general)
print("  Level-hosted fallback (NO rehosteable!):       ", total_level_general)
print("  Fallidos:                                      ", total_failed_general)
print("  Rotacion aplicada OK:                          ", total_rot_ok_general)
print("  Rotacion fallida (sin rotar, rehosteable):     ", total_rot_failed_general)
print("=" * 70)

rehosteable_total = total_wall_general + total_floor_general + total_ceiling_general
print("\n  >>> {} de {} tomas son REHOSTEABLES (Pick Host funciona)".format(
    rehosteable_total, total_general))
print("  >>> {} NO son rehosteables (level-hosted)".format(total_level_general))

if total_wall_general > 0:
    print("\n>>> Dispositivos en PARED (objetivo principal cumplido):")
    print("    - Estan VERTICALES (placa paralela a la pared)")
    print("    - Son REHOSTEABLES (Pick Host activo)")
    print("    - Hosteados en muros del Piso 5 (filtrado por nivel)")

if total_floor_general > 0 or total_ceiling_general > 0:
    print("\n>>> Dispositivos en SUELO/TECHO (alternativa rehosteable):")
    print("    - Estan HORIZONTALES (placa acostada) - NO es la posicion final")
    print("    - Hosteados en losa/cielorraso del Piso 5 (filtrado por nivel)")
    print("    - PERO son REHOSTEABLES:")
    print("      1. Seleccionar la toma en Revit")
    print("      2. En panel Modify -> click 'Pick Host'")
    print("      3. Click en la cara del muro donde debe ir")
    print("      4. La toma se reubicara en la pared (quedara vertical)")

if total_rot_failed_general > 0:
    print("\n>>> AVISO: {} tomas con rotacion FALLIDA (sin rotar):".format(total_rot_failed_general))
    print("    Las tomas quedaron COLOCADAS y REHOSTEABLES pero sin rotacion.")
    print("    No fueron eliminadas - se pueden rotar manualmente.")

if total_level_general > 0:
    print("\n>>> ADVERTENCIA: {} dispositivos en Level-hosted fallback:".format(total_level_general))
    print("    Estos NO son rehosteables. Recomendacion: eliminarlos y recolocar manualmente.")

print("\n=== LISTO ===")