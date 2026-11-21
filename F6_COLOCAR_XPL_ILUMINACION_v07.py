"""
F6_COLOCAR_XPL_ILUMINACION.py - v07
Version: 07
Date: 2026-11-21
Fix: usar sobrecarga NewFamilyInstance(XYZ, FamilySymbol, Level)
     para que el Schedule Level quede en 'Piso 5' y no en 0.00.
Rotacion: ElementTransformUtils.RotateElement (Location.Rotation es read-only).
"""

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
ALTURA_ILUMINACION_MM = 2700

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("="*60)
print("F6_COLOCAR_XPL_ILUMINACION v07")
print("Date: 2026-11-21")
print("APTO_OBJETIVO:", APTO_OBJETIVO)
print("="*60)

print("Cargando JSON para {} (solo M_Iluminacion)...".format(APTO_OBJETIVO))
with open(JSON_PATH, 'r') as f:
    data = json.load(f)

iluminacion = [d for d in data['dispositivos']
               if d['apto_asignado'] == APTO_OBJETIVO and d['familia_revit'] == 'M_Iluminacion']
print("Luminarias en {}: {}".format(APTO_OBJETIVO, len(iluminacion)))

if not iluminacion:
    print("¡SIN LUMINARIAS!")
    import sys
    sys.exit(0)

# ─── NIVEL PISO 5 ────────────────────────────────────────
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break

if not level_piso5:
    print("¡ERROR: No se encontro el nivel 'Piso 5'!")
    import sys
    sys.exit(1)

level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation
print("Nivel Piso 5: {} (Id={}, Elev={:.4f} ft = {:.1f} mm)".format(
    level_piso5.Name, level_piso5_id, level_piso5_elev_ft,
    level_piso5_elev_ft * 304.8))

# ─── SIMBOLO ─────────────────────────────────────────────
symbol = None
collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
for s in collector:
    if s.Family.Name == 'M_Iluminacion':
        symbol = s
        break

if not symbol:
    print("¡ERROR: No hay M_Iluminacion!")
    import sys
    sys.exit(1)

if not symbol.IsActive:
    t_act = Transaction(doc, "Activar M_Iluminacion")
    t_act.Start()
    symbol.Activate()
    t_act.Commit()

fpt = symbol.Family.FamilyPlacementType
print("Simbolo: {} (FPT={}, Id={})".format(symbol.Family.Name, int(fpt), symbol.Id))
print("  FamilyPlacementType name: {}".format(str(fpt)))

# Validacion: esta sobrecarga funciona para familias OneLevelBased / FaceBased.
# Si la familia es CurveBased (LineBased) la sobrecarga XYZ+Level falla y hay
# que usar NewFamilyInstance(Curve, FamilySymbol). Lo reportamos y salimos.
if fpt == FamilyPlacementType.CurveBased:
    print("¡ERROR: La familia es CurveBased (LineBased)! Esta sobrecarga no aplica.")
    print("        Para CurveBased usar: doc.Create.NewFamilyInstance(Line, FamilySymbol)")
    import sys
    sys.exit(1)

# ─── TECHOS: obtener Z real ──────────────────────────────
print("Indexando techos Piso 5 (para Z real)...")

ceilings_data = []
collector = FilteredElementCollector(doc).OfClass(Ceiling).WhereElementIsNotElementType()
for c in collector:
    if c.LevelId == level_piso5_id:
        try:
            geom_opt = Options()
            geom_opt.ComputeReferences = True
            geom = c.get_Geometry(geom_opt)
            for obj in geom:
                if isinstance(obj, Solid):
                    for face in obj.Faces:
                        if isinstance(face, PlanarFace):
                            normal = face.ComputeNormal(UV(0.5, 0.5))
                            if normal.Z < -0.1:
                                bbox = c.get_BoundingBox(None)
                                if bbox:
                                    z = face.Evaluate(UV(0.5, 0.5)).Z
                                    ceilings_data.append({'ceiling': c, 'face': face,
                                        'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                                        'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y, 'z': z})
                                break
                    if ceilings_data and ceilings_data[-1]['ceiling'] == c:
                        break
        except:
            continue

print("  Techos con Z: {}".format(len(ceilings_data)))

def find_ceiling_z(x_ft, y_ft, max_dist_ft=15.0):
    pt_xy = XYZ(x_ft, y_ft, 0)
    best_z = None
    best_dist = float('inf')
    for cd in ceilings_data:
        if x_ft < cd['xmin'] - max_dist_ft or x_ft > cd['xmax'] + max_dist_ft: continue
        if y_ft < cd['ymin'] - max_dist_ft or y_ft > cd['ymax'] + max_dist_ft: continue
        try:
            result = cd['face'].Project(pt_xy)
            if result:
                if hasattr(result, 'UVPoint'):
                    uv = result.UVPoint
                else:
                    uv = result
                pt_on_face = cd['face'].Evaluate(uv)
                dist = ((pt_on_face.X - x_ft)**2 + (pt_on_face.Y - y_ft)**2)**0.5
                if dist < best_dist and dist < max_dist_ft:
                    best_dist = dist
                    best_z = pt_on_face.Z
        except:
            continue
    return best_z

def generate_mark(d):
    x_int = int(round(d['x_mm']))
    y_int = int(round(d['y_mm']))
    typ_short = d['tipo_revit'].replace(' ', '')[:6]
    return "ILUM_{}_{}_{}".format(typ_short, x_int, y_int)

# ─── TRANSACCION: sobrecarga con Level ───────────────────
print("\n" + "="*60)
print("COLOCANDO ILUMINACION {} - NewFamilyInstance(XYZ, Symbol, Level)".format(APTO_OBJETIVO))
print("="*60)

t = Transaction(doc, "Colocar Iluminacion {}".format(APTO_OBJETIVO))
t.Start()

MM_TO_FT = 0.003280839895
placed = 0
warnings = []

for d in iluminacion:
    x_ft = d['x_mm'] * MM_TO_FT
    y_ft = d['y_mm'] * MM_TO_FT
    rot_rad = math.radians(d['rotacion_grados'])

    inst = None
    try:
        ceiling_z = find_ceiling_z(x_ft, y_ft)
        if ceiling_z is not None:
            target_z = ceiling_z
        else:
            target_z = level_piso5_elev_ft + (ALTURA_ILUMINACION_MM * MM_TO_FT)
            warnings.append("Sin techo Z, fallback: {} @ ({:.0f},{:.0f})".format(
                d['nombre_dxf'], d['x_mm'], d['y_mm']))

        # ===== CLAVE: sobrecarga con Level =====
        # NewFamilyInstance(XYZ location, FamilySymbol symbol, Level level)
        # Para familias OneLevelBased/FaceBased asocia la instancia al nivel
        # pasado y el Schedule Level queda correcto desde el principio.
        pt = XYZ(x_ft, y_ft, target_z)
        inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5)

        # Verificacion: Schedule Level debe ser Piso 5
        p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
        if p_level:
            sched_level_id = p_level.AsElementId()
            if sched_level_id != level_piso5_id:
                warnings.append("Schedule Level no es Piso 5: {} ({})".format(
                    d['nombre_dxf'], sched_level_id.IntegerValue))

        # Verificacion de Z real
        loc = inst.Location
        if loc:
            actual_pt = loc.Point
            delta_mm = (actual_pt.Z - target_z) * 304.8
            print("  OK: {} -> target Z={:.4f} ft, actual Z={:.4f} ft (delta={:+.1f} mm)".format(
                d['nombre_dxf'], target_z, actual_pt.Z, delta_mm))
            if abs(actual_pt.Z - target_z) > 0.01:
                warnings.append("Z mismatch: {} actual={:.2f} target={:.2f}".format(
                    d['nombre_dxf'], actual_pt.Z, target_z))

        placed += 1

        # Rotacion: Location.Rotation es read-only; usar ElementTransformUtils
        if abs(rot_rad) > 1e-6 and inst is not None:
            try:
                axis = Line.CreateBound(
                    XYZ(x_ft, y_ft, target_z),
                    XYZ(x_ft, y_ft, target_z + 10.0))
                ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_rad)
            except Exception as rex:
                warnings.append("Rotacion fallida {}: {}".format(d['nombre_dxf'], str(rex)))

        # Mark
        mark = generate_mark(d)
        p_mark = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if p_mark:
            p_mark.Set(mark)

    except Exception as ex:
        tb = traceback.format_exc()
        warnings.append("Error {}: {} | {}".format(d['nombre_dxf'], str(ex), tb))
        print("  EXCEPTION for {}: {}".format(d['nombre_dxf'], str(ex)))

t.Commit()
print("Transaccion completada.")

print("\n{} - RESUMEN:".format(APTO_OBJETIVO))
print("  Placed: {}".format(placed))
print("  Warnings: {}".format(len(warnings)))

for w in warnings:
    print("    WARN: {}".format(w))
