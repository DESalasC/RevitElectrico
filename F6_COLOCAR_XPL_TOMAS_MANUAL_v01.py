"""
F6_COLOCAR_XPL_TOMAS_MANUAL.py - v03
Version: 03
Date: 2026-11-21
Author: Correccion sobre v02

Fixes vs v02:
  1. Colocacion FACE-BASED en cara de muro (no level-hosted)
     -> Las tomas quedan VERTICALES (placa paralela a la pared)
  2. Las instancias son REHOSTEABLES: Pick Host funciona en UI
  3. Se elimina el +90 deg falso del v02 (era parche para level-based)
  4. La rotacion del DXF se aplica alrededor de la NORMAL de la cara
  5. Fallback a level-based SOLO si no se encuentra muro cercano
     (con aviso claro para revision manual)

RAIZ DEL PROBLEMA v02:
  doc.Create.NewFamilyInstance(pt, symbol, LEVEL, StructuralType)
  aloja la instancia al NIVEL. Para familias face-based esto:
    - deja el dispositivo HORIZONTAL (placa acostada sobre el nivel)
    - BLOQUEA el host: el comando "Pick Host" de la UI no funciona
      porque Revit no permite re-hostear instancias level-hosted.
  La rotacion +90 deg en Z era un parche inutil: rota en planta,
  no endereza el dispositivo.

SOLUCION v03:
  doc.Create.NewFamilyInstance(face_pt, symbol, face_REF, ref_dir)
  - face_pt  = punto proyectado sobre la cara del muro
  - face_REF = Reference a la cara (PlanarFace) del muro
  - ref_dir  = XYZ.BasisZ (vertical) -> placa vertical
  Resultado: dispositivo VERTICAL y rehosteable.
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

# Tolerancia para buscar muros cercanos (mm en XY).
# Las tomas suelen estar a unos pocos mm de la cara del muro en el DXF.
# 300 mm = 30 cm de holgura para compensar pequenos offsets de muro.
WALL_SEARCH_TOLERANCE_MM = 300.0

# Familias objetivo (face-based en el proyecto)
FAMILIAS_OBJETIVO = ('M_Toma doble', 'M_Comunicaciones')

# ============================================================
# INIT
# ============================================================
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("=" * 60)
print("F6_COLOCAR_XPL_TOMAS_MANUAL v03 - FACE-BASED")
print("APTO:", APTO_OBJETIVO)
print("MODO: Colocar en cara de muro (vertical + rehosteable)")
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

# NOTA IronPython 2.7: evitar dict comprehensions que acceden a propiedades
# .NET dentro del scope oculto de la comprehension (falla con AttributeError).
# Usar bucle normal con extraccion explicita a str de Python.
print("Simbolos cargados:")
for fam_name_key, sym_obj in symbols.items():
    try:
        sym_name = str(sym_obj.Name)
    except Exception:
        sym_name = "<sin nombre>"
    print("  -", fam_name_key, "->", sym_name)

# ============================================================
# CACHE DE MUROS DEL DOCUMENTO
# ============================================================
print("\nCargando muros del documento...")
all_walls = list(FilteredElementCollector(doc)
                 .OfClass(Wall)
                 .WhereElementIsNotGenericType()
                 .ToElements())
print("Total muros:", len(all_walls))

# Opciones de geometria (con referencias)
geom_opt = Options()
geom_opt.ComputeReferences = True
geom_opt.IncludeNonVisibleObjects = False
try:
    if doc.ActiveView and doc.ActiveView.IsValidObject:
        geom_opt.View = doc.ActiveView
except Exception:
    pass

MM_TO_FT = 0.003280839895
TOLERANCE_FT = WALL_SEARCH_TOLERANCE_MM * MM_TO_FT


def find_wall_face_at_point(target_xyz):
    """
    Busca el muro mas cercano al punto XY y devuelve una tupla:
        (face_reference, face_normal, projected_point_on_face, wall_dir)
    Solo considera caras verticales (PlanarFace con normal ~horizontal)
    que miren hacia el lado del punto (lado correcto del muro).

    Devuelve None si no encuentra ningun muro dentro de la tolerancia.
    """
    best_result = None
    best_distance = float('inf')

    target_2d = XYZ(target_xyz.X, target_xyz.Y, 0)

    for wall in all_walls:
        loc = wall.Location
        if not isinstance(loc, LocationCurve):
            continue

        curve = loc.Curve
        if curve is None:
            continue

        # Proyectar el punto XY sobre la curva del muro (ignorando Z)
        try:
            result = curve.Project(target_2d)
        except Exception:
            continue
        if result is None:
            continue

        distance_xy = result.Distance
        if distance_xy > TOLERANCE_FT:
            continue

        # Direccion tangente del muro en el parametro 0.5 (centro)
        try:
            derivs = curve.ComputeDerivatives(0.5)
            wall_dir = derivs.XYZVector.Normalize()
        except Exception:
            try:
                p0 = curve.GetEndPoint(0)
                p1 = curve.GetEndPoint(1)
                wall_dir = (p1 - p0).Normalize()
            except Exception:
                continue

        # Geometria del muro -> buscar caras planas verticales
        geom_elem = wall.get_Geometry(geom_opt)
        if geom_elem is None:
            continue

        for geom_obj in geom_elem:
            if not isinstance(geom_obj, Solid):
                continue
            if geom_obj.Faces.IsEmpty:
                continue

            for face in geom_obj.Faces:
                if not isinstance(face, PlanarFace):
                    continue

                face_normal = face.FaceNormal

                # Solo caras verticales (normal en plano XY)
                if abs(face_normal.Z) > 0.1:
                    continue  # Es cara horizontal (techo/piso) -> descartar

                # Proyectar el target sobre la cara
                try:
                    face_proj = face.Project(target_xyz)
                except Exception:
                    continue
                if face_proj is None:
                    continue

                proj_pt = face_proj.XYZPoint

                # La cara debe mirar hacia el punto (lado correcto)
                vec_to_point = target_xyz - proj_pt
                if vec_to_point.GetLength() > 1e-6:
                    dot = face_normal.DotProduct(vec_to_point.Normalize())
                    if dot < 0.5:
                        continue  # La cara no mira hacia el punto

                # Verificar que UV este dentro de los bounds de la cara
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

                # Tomar el mas cercano en XY
                if distance_xy < best_distance:
                    best_distance = distance_xy
                    best_result = (face.Reference, face_normal, proj_pt, wall_dir)

    return best_result


def compute_rotation_around_face_normal(rot_dxf_rad, face_normal, wall_dir):
    """
    Convierte la rotacion del DXF (alrededor de Z world) a una rotacion
    alrededor de la NORMAL de la cara del muro.

    Idea: la rotacion DXF define hacia donde apunta el dispositivo en planta.
    Cuando se coloca en la cara del muro, esa orientacion debe trasladarse
    al plano de la cara.

    Para simplificar y robustez: aplicamos directamente rot_dxf_rad
    alrededor del eje de la normal. Si la orientacion final no coincide
    con la del DXF, el usuario puede ajustar manualmente con el comando
    Rotar (que SI funciona, porque la instancia no esta bloqueada).
    """
    # Por ahora aplicamos directamente la rotacion DXF alrededor de la normal.
    # Senal: si hay un offset sistematico (mismo angulo en todas), se puede
    # corregir anadiendo un offset fijo aqui.
    return rot_dxf_rad


# ============================================================
# TRANSACTION
# ============================================================
t = Transaction(doc, "Place Tomas {} - Face-based v03".format(APTO_OBJETIVO))
t.Start()

placed_total = 0
placed_on_wall = 0
placed_level = 0
failed = 0
fallback_list = []  # Para reportar al final

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

        rot_dxf_deg = d['rotacion_grados']
        rot_dxf_rad = math.radians(rot_dxf_deg)

        # Z ABSOLUTO = elevacion nivel + altura dispositivo
        target_z = level_piso5_elev_ft + z_ft
        pt = XYZ(x, y, target_z)

        # Intentar colocacion FACE-BASED en muro
        wall_result = find_wall_face_at_point(pt)

        if wall_result is not None:
            face_ref, face_normal, face_pt, wall_dir = wall_result

            # Direccion de referencia = vertical (eje Z world)
            # -> la placa del dispositivo queda vertical, paralela a la pared
            ref_dir = XYZ.BasisZ

            # Colocar face-based en la cara del muro
            # Sobrecarga: NewFamilyInstance(XYZ, FamilySymbol, Reference, Line)
            inst = doc.Create.NewFamilyInstance(face_pt, symbol, face_ref, ref_dir)

            # Rotacion alrededor de la NORMAL de la cara (eje perpendicular a la pared)
            # Esto rota el dispositivo en el plano de la pared.
            rot_face = compute_rotation_around_face_normal(
                rot_dxf_rad, face_normal, wall_dir)
            if abs(rot_face) > 1e-6:
                try:
                    axis = Line.CreateBound(face_pt,
                                            face_pt + face_normal * 10.0)
                    ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_face)
                except Exception as re:
                    print("    (rot fallida - sin rotacion):", str(re)[:60])

            placed_on_wall += 1
            method = "WALL-FACE"
        else:
            # FALLBACK: Level-based (NO sera rehosteable facilmente)
            # Se mantiene como ultima opcion para que al menos queden colocados.
            # El usuario debera eliminarlos y recolocar manualmente.
            inst = doc.Create.NewFamilyInstance(
                pt, symbol, level_piso5,
                Structure.StructuralType.NonStructural)

            p_level = inst.get_Parameter(
                BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            if p_level:
                p_level.Set(level_piso5_id)

            # Rotacion Z (device quedara horizontal - no es ideal)
            if abs(rot_dxf_rad) > 1e-6:
                axis = Line.CreateBound(pt, pt + XYZ(0, 0, 10.0))
                ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_dxf_rad)

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
        print("  OK [{}]: {} @ ({:.2f},{:.2f},{:.2f}) rot={:.0f}deg mark={}".format(
            method, d['nombre_dxf'], x, y, target_z, rot_dxf_deg, mark))

    except Exception as e:
        failed += 1
        print("  FAIL: {} - {}".format(d.get('nombre_dxf', '?'), str(e)))
        # Descomentar para ver traza completa en debugging:
        # print(traceback.format_exc())

t.Commit()

# ============================================================
# RESUMEN
# ============================================================
print("\n" + "=" * 60)
print("RESUMEN:")
print("  Total colocados:                      ", placed_total)
print("  En cara de muro (VERTICAL+REHOSTEABLE):", placed_on_wall)
print("  Level-based fallback (revisar manual): ", placed_level)
print("  Fallidos:                              ", failed)
print("=" * 60)

if placed_on_wall > 0:
    print("\n>>> Dispositivos en cara de muro:")
    print("    - Estan VERTICALES (placa paralela a la pared)")
    print("    - Son REHOSTEABLES: seleccionar -> Modify -> Pick Host")
    print("      -> click en otra cara de muro (o en el mismo muro, otra cara)")
    print("    - La rotacion final puede requerir ajuste manual con Rotar.")

if placed_level > 0:
    print("\n>>> ADVERTENCIA: {} dispositivos en Level-based fallback:".format(placed_level))
    print("    Estos NO son facilmente rehosteables (quedan horizontal + bloqueados).")
    print("    Dispositivos afectados (nombre, x_mm, y_mm):")
    for n, x, y in fallback_list[:20]:  # Mostrar max 20
        print("      - {} @ ({:.0f}, {:.0f})".format(n, x, y))
    if len(fallback_list) > 20:
        print("      ... y {} mas".format(len(fallback_list) - 20))
    print("    Recomendacion: eliminarlos y recolocar manualmente sobre el muro,")
    print("    o ampliar WALL_SEARCH_TOLERANCE_MM y volver a ejecutar.")

print("\n>>> Verificacion en Revit:")
print("    1. Abrir vista 3D o seccion donde esten las tomas")
print("    2. Seleccionar una toma -> en el panel Modify debe estar activo 'Pick Host'")
print("    3. Si Pick Host esta activo: la instancia NO esta bloqueada (objetivo cumplido)")
print("    4. La placa debe verse vertical (paralela al muro), no acostada")
