"""
F6_COLOCAR_XPL_TOMAS_MANUAL.py - v06
Version: 06
Date: 2026-11-21
Author: Correccion sobre v05

RAIZ DEL PROBLEMA v05 (error "expected Curve, got XYZ"):
  Yo usaba: doc.Create.NewFamilyInstance(face_pt, symbol, face_ref, ref_dir_line)
  - Orden equivocado de argumentos
  - Line como 4to argumento => IronPython eligia otra sobrecarga => rechazo

SOLUCION (hallada en sesion con Qwen 2026-11-14, problema v69 F01):
  Sobrecarga correcta:
      doc.Create.NewFamilyInstance(face_ref, placement_pt, direction, symbol)
  - Primer arg: face_ref (Reference a la cara del muro/suelo/techo)
  - Segundo arg: placement_pt (XYZ donde se coloca)
  - Tercer arg: direction (XYZ, NO Line) - perpendicular a la normal de la cara
    * Para muro vertical (normal horizontal): direction = XYZ.BasisZ (hacia arriba)
    * Para suelo/techo (normal vertical Z):  direction = XYZ.BasisX (horizontal)
  - Cuarto arg: symbol (FamilySymbol)

ROTACION:
  Aplicar DESPUES de la colocacion con LocationPoint.Rotate() sobre un eje
  vertical (Z) que pasa por el punto de insercion.
  NO usar ElementTransformUtils.RotateElement con la normal de la cara.

ESTRATEGIA EN CASCADA:
  1. PARED  (ideal, vertical)
  2. SUELO  (cara superior, horizontal pero rehosteable)
  3. TECHO  (cara inferior, horizontal pero rehosteable)
  4. Level-hosted (ULTIMO RECURSO, NO rehosteable)
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
APTO_OBJETIVO = 'TF 01a'  # <- cambiar aqui
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURAS_MM = {
    'M_Toma doble': 1000,
    'M_Comunicaciones': 1000,
}

# Tolerancia para buscar muros cercanos (mm en XY)
WALL_SEARCH_TOLERANCE_MM = 300.0

# Tolerancia para buscar suelo/techo cercanos (mm en XY)
# Mayor porque losas/suelos cubren todo el piso del apartamento
FLOOR_SEARCH_TOLERANCE_MM = 5000.0

# Familias objetivo
FAMILIAS_OBJETIVO = ('M_Toma doble', 'M_Comunicaciones')

# ============================================================
# INIT
# ============================================================
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("=" * 60)
print("F6_COLOCAR_XPL_TOMAS_MANUAL v06 - FACE-BASED HOSTED")
print("APTO:", APTO_OBJETIVO)
print("MODO: Pared -> Suelo -> Techo -> Level (ultimo recurso)")
print("=" * 60)

# ============================================================
# CARGA JSON
# ============================================================
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

tomas = [d for d in data['dispositivos']
         if d['apto_asignado'] == APTO_OBJETIVO
         and d['familia_revit'] in FAMILIAS_OBJETIVO]
print("Tomas en {}: {}".format(APTO_OBJETIVO, len(tomas)))

if not tomas:
    print("ERROR: No hay tomas para el apartamento", APTO_OBJETIVO)
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

print("Nivel:", level_piso5.Name, "- elev:", level_piso5.Elevation * 304.8, "mm")
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

print("Simbolos cargados:")
for fam_name_key, sym_obj in symbols.items():
    try:
        print("  -", fam_name_key, "-> Id:", str(sym_obj.Id))
    except Exception:
        print("  -", fam_name_key, "-> (no se pudo leer Id)")

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


def _distance_xy_to_point(px, py, target_x, target_y):
    """Distancia en plano XY entre dos puntos."""
    return math.hypot(px - target_x, py - target_y)


# ============================================================
# CACHE DE MUROS Y SUELOS DEL DOCUMENTO
# ============================================================
print("\nCargando muros y suelos del documento...")
all_walls = list(FilteredElementCollector(doc).OfClass(Wall).ToElements())
print("Total muros (sin filtrar):", len(all_walls))

# Filtrar manualmente (donde WallType exista)
clean_walls = []
for w in all_walls:
    try:
        if w.WallType is not None:
            clean_walls.append(w)
    except Exception:
        pass
all_walls = clean_walls
print("Muros validos (con WallType):", len(all_walls))

# Cargar Floors (suelos/losas) y Ceilings (cielorrasos)
all_floors = list(FilteredElementCollector(doc).OfClass(Floor).ToElements())
print("Total suelos (Floor):", len(all_floors))

all_ceilings = []
try:
    all_ceilings = list(FilteredElementCollector(doc).OfClass(Ceiling).ToElements())
    print("Total cielorrasos (Ceiling):", len(all_ceilings))
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
# DIAGNOSTICO PREVIO
# ============================================================
if all_walls and tomas:
    print("\nDiagnostico de coordenadas:")
    print("  Muestra de muros (XYZ de LocationCurve, en pies):")
    sample_count = 0
    for w in all_walls:
        try:
            loc = w.Location
            if not isinstance(loc, LocationCurve):
                continue
            c = loc.Curve
            sp = c.GetEndPoint(0)
            ep = c.GetEndPoint(1)
            print("    wall: ({:.2f},{:.2f},{:.2f}) -> ({:.2f},{:.2f},{:.2f})".format(
                float(sp.X), float(sp.Y), float(sp.Z),
                float(ep.X), float(ep.Y), float(ep.Z)))
            sample_count += 1
            if sample_count >= 3:
                break
        except Exception:
            continue

    t0 = tomas[0]
    tx_ft = t0['x_mm'] * MM_TO_FT
    ty_ft = t0['y_mm'] * MM_TO_FT
    print("  Primera toma del apto (en pies):")
    print("    toma: ({:.2f},{:.2f})".format(float(tx_ft), float(ty_ft)))

    best_d = float('inf')
    for w in all_walls:
        try:
            loc = w.Location
            if not isinstance(loc, LocationCurve):
                continue
            c = loc.Curve
            d = _distance_xy_to_curve(c, tx_ft, ty_ft)
            if d < best_d:
                best_d = d
        except Exception:
            continue
    print("  Muro mas cercano a primera toma:")
    print("    distancia XY = {:.2f} ft = {:.1f} mm".format(
        float(best_d), float(best_d) / MM_TO_FT))
    print("    TOLERANCE_FT = {:.2f} ft = {:.1f} mm".format(
        float(TOLERANCE_FT), float(WALL_SEARCH_TOLERANCE_MM)))
    print("")


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
        # Para Floor/Ceiling, usar la bbox o el punto central como filtro rapido
        try:
            bbox = elem.get_BoundingBox(None)
            if bbox is None:
                continue
            # Verificar que el XY del target este dentro de la bbox (con holgura)
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

                # Solo caras horizontales
                if abs(face_normal.Z) < 0.9:
                    continue

                # Filtrar por direccion de la normal
                if want_top and face_normal.Z < 0:
                    continue
                if (not want_top) and face_normal.Z > 0:
                    continue

                # Proyectar el target (a la altura del nivel) sobre la cara
                try:
                    face_proj = face.Project(target_xyz)
                except Exception:
                    continue
                if face_proj is None:
                    continue

                proj_pt = face_proj.XYZPoint

                # Distancia XY desde el target hasta el punto proyectado
                d_xy = math.hypot(proj_pt.X - target_x, proj_pt.Y - target_y)
                if d_xy > FLOOR_TOL_FT:
                    continue

                # Verificar que UV este dentro de los bounds
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
# TRANSACTION
# ============================================================
t = Transaction(doc, "Place Tomas {} - Face-based v06".format(APTO_OBJETIVO))
t.Start()

placed_total = 0
placed_on_wall = 0
placed_on_floor = 0
placed_on_ceiling = 0
placed_level = 0
failed = 0
fallback_list = []  # Level-hosted
all_method_list = []  # Todos los colocados con su metodo

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
        # SOLUCION (sesion con Qwen 2026-11-14, problema v69):
        # Sobrecarga correcta: NewFamilyInstance(face_ref, placement_pt, direction, sym)
        # - direction = XYZ.BasisZ (perpendicular a la normal del muro vertical)
        # - NO usar Line como 4to argumento (sobrecarga distinta -> "expected Curve, got XYZ")
        # - Rotacion posterior con LocationPoint.Rotate() sobre eje vertical Z
        wall_result = find_wall_face_at_point(pt)

        if wall_result is not None:
            face_ref, face_normal, face_pt, wall_dir = wall_result
            try:
                direction = XYZ.BasisZ  # perpendicular a normal del muro vertical
                inst = doc.Create.NewFamilyInstance(
                    face_ref, face_pt, direction, symbol)
                method = "WALL-FACE"

                # Rotacion: aplicar sobre un eje vertical que pasa por el punto
                # de insercion (NO sobre la normal de la cara). El eje Z local.
                if abs(rot_dxf_rad) > 1e-6:
                    try:
                        loc = inst.Location
                        if isinstance(loc, LocationPoint):
                            axis = Line.CreateBound(
                                face_pt,
                                XYZ(face_pt.X, face_pt.Y, face_pt.Z + 1.0))
                            loc.Rotate(axis, rot_dxf_rad)
                        else:
                            # Fallback: ElementTransformUtils
                            axis = Line.CreateBound(
                                face_pt,
                                XYZ(face_pt.X, face_pt.Y, face_pt.Z + 1.0))
                            ElementTransformUtils.RotateElement(
                                doc, inst.Id, axis, rot_dxf_rad)
                    except Exception as re:
                        print("    (rot fallida - sin rotacion):", str(re)[:60])

                placed_on_wall += 1
            except Exception as we:
                print("    (wall placement failed):", str(we)[:80])
                inst = None

        # ----- INTENTO 2: SUELO/LOSA (cara superior) -----
        # Para caras horizontales, direction debe ser perpendicular a Z:
        # BasisX o BasisY. Esto define la orientacion "horizontal" del dispositivo.
        if inst is None and all_floors:
            floor_result = find_horizontal_face_at_point(
                pt, all_floors, want_top=True)
            if floor_result is not None:
                face_ref, face_normal, face_pt, _ = floor_result
                try:
                    direction = XYZ.BasisX  # perpendicular a la normal Z
                    inst = doc.Create.NewFamilyInstance(
                        face_ref, face_pt, direction, symbol)
                    method = "FLOOR-TOP"
                    placed_on_floor += 1
                except Exception as fe:
                    print("    (floor placement failed):", str(fe)[:80])
                    inst = None

        # ----- INTENTO 3: TECHO (cara inferior) -----
        if inst is None and all_ceilings:
            ceil_result = find_horizontal_face_at_point(
                pt, all_ceilings, want_top=False)
            if ceil_result is not None:
                face_ref, face_normal, face_pt, _ = ceil_result
                try:
                    direction = XYZ.BasisX
                    inst = doc.Create.NewFamilyInstance(
                        face_ref, face_pt, direction, symbol)
                    method = "CEILING-BOTTOM"
                    placed_on_ceiling += 1
                except Exception as ce:
                    print("    (ceiling placement failed):", str(ce)[:80])
                    inst = None

        # ----- INTENTO 4: Level-hosted (ULTIMO RECURSO, NO rehosteable) -----
        if inst is None:
            inst = doc.Create.NewFamilyInstance(
                pt, symbol, level_piso5,
                Structure.StructuralType.NonStructural)

            p_level = inst.get_Parameter(
                BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            if p_level:
                p_level.Set(level_piso5_id)

            if abs(rot_dxf_rad) > 1e-6:
                axis = Line.CreateBound(pt, pt + XYZ(0, 0, 10.0))
                ElementTransformUtils.RotateElement(
                    doc, inst.Id, axis, rot_dxf_rad)

            placed_level += 1
            method = "LEVEL-FALLBACK"
            fallback_list.append((d.get('nombre_dxf', '?'),
                                  d['x_mm'], d['y_mm']))

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

# ============================================================
# RESUMEN
# ============================================================
print("\n" + "=" * 60)
print("RESUMEN:")
print("  Total colocados:                              ", placed_total)
print("  En PARED  (vertical, ideal):                  ", placed_on_wall)
print("  En SUELO  (horizontal, rehosteable):         ", placed_on_floor)
print("  En TECHO  (horizontal, rehosteable):         ", placed_on_ceiling)
print("  Level-hosted fallback (NO rehosteable!):      ", placed_level)
print("  Fallidos:                                     ", failed)
print("=" * 60)

rehosteable_total = placed_on_wall + placed_on_floor + placed_on_ceiling
print("\n  >>> {} de {} tomas son REHOSTEABLES (Pick Host funciona)".format(
    rehosteable_total, placed_total))
print("  >>> {} NO son rehosteables (level-hosted)".format(placed_level))

if placed_on_wall > 0:
    print("\n>>> Dispositivos en PARED (objetivo principal cumplido):")
    print("    - Estan VERTICALES (placa paralela a la pared)")
    print("    - Son REHOSTEABLES")
    print("    - Listos para uso o ajuste fino de rotacion con Rotar.")

if placed_on_floor > 0 or placed_on_ceiling > 0:
    print("\n>>> Dispositivos en SUELO/TECHO (alternativa rehosteable):")
    print("    - Estan HORIZONTALES (placa acostada) - NO es la posicion final")
    print("    - PERO son REHOSTEABLES:")
    print("      1. Seleccionar la toma en Revit")
    print("      2. En panel Modify -> click 'Pick Host'")
    print("      3. Click en la cara del muro donde debe ir")
    print("      4. La toma se reubicara en la pared (quedara vertical)")
    print("    - Repetir para cada toma horizontal.")

if placed_level > 0:
    print("\n>>> ADVERTENCIA: {} dispositivos en Level-hosted fallback:".format(placed_level))
    print("    Estos NO son rehosteables. Dispositivos afectados:")
    for n, x, y in fallback_list[:20]:
        print("      - {} @ ({:.0f}, {:.0f})".format(n, float(x), float(y)))
    if len(fallback_list) > 20:
        print("      ... y {} mas".format(len(fallback_list) - 20))
    print("    Recomendacion: eliminarlos y recolocar manualmente.")

print("\n>>> Detalle por dispositivo:")
for n, m in all_method_list:
    print("    [{}] {}".format(m, n))
