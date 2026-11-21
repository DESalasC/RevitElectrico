"""
F6_COLOCAR_XPL_ILUMINACION.py - v13
Version: 13
Date: 2026-11-21
Estrategia: volver al enfoque v08/v09 (que SI colocaba las 11 luminarias)
pero con la seleccion de tipo correcta (v10+) y verificacion no-fatal (v12).

v08/v09 colocaba todas las luminarias pero con el mismo simbolo (el primero
que encontraba de M_Iluminacion). El usuario veia 11 luminarias creadas.

v10-v12 intentaron discriminar por tipo, pero introdujeron regresiones:
- v12 SKIPea luminarias si find_ceiling_face devuelve None (y por alguna razon
  en este modelo devuelve None para 9 de 11 aunque v09 encontraba techo para 11)
- v12 no mueve la Z a la cara del techo correctamente

v13 simplifica:
1. Si find_ceiling_face encuentra techo -> host en techo, Z = cara inferior
2. Si NO encuentra techo -> colocar en Z=fallback (nivel + 2700mm) usando
   NewFamilyInstance(XYZ, Symbol, StructuralType) como v06/v07. Aunque esto
   deje el Schedule Level en 0.00, al menos la luminaria EXISTE en el modelo
   y el usuario la puede re-hostear a mano.

IMPORTANTE: el usuario ya entiende que las luminarias pueden quedar en Z=0
o con Schedule Level mal, y las corrige a mano. Lo importante es que se
CREEN las 11 luminarias con el tipo correcto.
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
print("F6_COLOCAR_XPL_ILUMINACION v13")
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


# ─── HELPERS: obtener nombre de Element de forma robusta ─
def get_element_name(el):
    """Obtiene el nombre de un Element (Family o FamilySymbol) probando varias estrategias."""
    try:
        n = el.Name
        if n is not None:
            return str(n)
    except Exception:
        pass
    try:
        n = Element.Name[el]
        if n is not None:
            return str(n)
    except Exception:
        pass
    try:
        p = el.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p:
            n = p.AsString()
            if n:
                return str(n)
    except Exception:
        pass
    try:
        p = el.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p:
            n = p.AsString()
            if n:
                return str(n)
    except Exception:
        pass
    try:
        n = el.Title
        if n is not None:
            return str(n)
    except Exception:
        pass
    return None


# ─── SIMBOLOS: indexar TODOS los tipos de M_Iluminacion por nombre ─
print("Indexando tipos (FamilySymbol) de M_Iluminacion...")
symbols_by_type = {}
first_symbol = None
illum_symbols_unnamed = []

n_total = 0
n_illum = 0
for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
    n_total += 1
    fam_name = None
    try:
        fam = s.Family
        if fam is not None:
            fam_name = get_element_name(fam)
    except Exception:
        continue
    if fam_name != 'M_Iluminacion':
        continue
    n_illum += 1
    sym_name = get_element_name(s)
    if sym_name:
        symbols_by_type[sym_name] = s
    else:
        illum_symbols_unnamed.append(s)
    if first_symbol is None:
        first_symbol = s

print("  Total FamilySymbols iterados: {}".format(n_total))
print("  M_Iluminacion encontrados: {} (con nombre: {}, sin nombre: {})".format(
    n_illum, len(symbols_by_type), len(illum_symbols_unnamed)))

# Fallback: si no se pudieron leer los nombres, asignar al primer simbolo
if not symbols_by_type and illum_symbols_unnamed:
    print("  FALLBACK: asignando todos los tipos al primer simbolo (sin nombre legible)")
    fallback_symbol = sorted(illum_symbols_unnamed, key=lambda s: str(s.Id))[0]
    tipos_en_json = sorted(set(d['tipo_revit'] for d in iluminacion))
    for tipo in tipos_en_json:
        symbols_by_type[tipo] = fallback_symbol

if not symbols_by_type:
    print("¡ERROR: No hay tipos en M_Iluminacion accesibles!")
    import sys
    sys.exit(1)

print("  Tipos mapeados: {}".format(len(symbols_by_type)))
for name, s in sorted(symbols_by_type.items()):
    print("    - '{}' -> Id={}".format(name, s.Id))

fpt = first_symbol.Family.FamilyPlacementType
print("FamilyPlacementType: {} (FPT={})".format(str(fpt), int(fpt)))

# Activar TODOS los simbolos en una sola transaccion
inactive = [s for s in symbols_by_type.values() if not s.IsActive]
if inactive:
    t_act = Transaction(doc, "Activar tipos M_Iluminacion")
    t_act.Start()
    for s in inactive:
        s.Activate()
    t_act.Commit()
    print("Simbolos activados: {}".format(len(inactive)))


# ─── TECHOS: obtener Z real + Reference de cara inferior ──
print("Indexando techos Piso 5 (para Z real y Reference)...")

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
                                    ref = face.Reference
                                    ceilings_data.append({
                                        'ceiling': c,
                                        'face': face,
                                        'reference': ref,
                                        'xmin': bbox.Min.X, 'xmax': bbox.Max.X,
                                        'ymin': bbox.Min.Y, 'ymax': bbox.Max.Y,
                                        'z': z
                                    })
                                break
                    if ceilings_data and ceilings_data[-1]['ceiling'] == c:
                        break
        except:
            continue

print("  Techos con cara inferior + Reference: {}".format(len(ceilings_data)))
ceilings_data = [cd for cd in ceilings_data if cd['reference'] is not None]
print("  Techos con Reference valida: {}".format(len(ceilings_data)))


def find_ceiling_face(x_ft, y_ft, max_dist_ft=15.0):
    """Devuelve el dict de ceilings_data cuya cara inferior contiene (x,y)."""
    pt_xy = XYZ(x_ft, y_ft, 0)
    best_cd = None
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
                    best_cd = cd
        except:
            continue
    return best_cd


def generate_mark(d):
    x_int = int(round(d['x_mm']))
    y_int = int(round(d['y_mm']))
    typ_short = d['tipo_revit'].replace(' ', '')[:6]
    return "ILUM_{}_{}_{}".format(typ_short, x_int, y_int)


# ─── TRANSACCION ─────────────────────────────────────────
print("\n" + "="*60)
print("COLOCANDO ILUMINACION {} [v13]".format(APTO_OBJETIVO))
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
        # ===== Buscar el FamilySymbol correcto para ESTA luminaria =====
        tipo_revit = d.get('tipo_revit', '')
        symbol = symbols_by_type.get(tipo_revit)
        if symbol is None:
            # Match parcial (case-insensitive)
            tipo_norm = tipo_revit.strip().lower()
            for k, s in symbols_by_type.items():
                if k.strip().lower() == tipo_norm:
                    symbol = s
                    break
        if symbol is None:
            warnings.append("Tipo no encontrado: '{}' para {}".format(tipo_revit, d['nombre_dxf']))
            print("  SKIP (tipo no encontrado): '{}' para {}".format(tipo_revit, d['nombre_dxf']))
            continue

        # ===== Buscar techo cercano =====
        cd = find_ceiling_face(x_ft, y_ft)
        target_z = None
        host_ref = None

        if cd is not None:
            # Proyectar (x, y) sobre la cara inferior del techo
            pt_xy = XYZ(x_ft, y_ft, 0)
            result = cd['face'].Project(pt_xy)
            if result:
                if hasattr(result, 'UVPoint'):
                    uv = result.UVPoint
                else:
                    uv = result
                pt_on_face = cd['face'].Evaluate(uv)
                target_z = pt_on_face.Z
                host_ref = cd['reference']
                host_info = "techo Id={} Z={:.4f}ft".format(cd['ceiling'].Id, target_z)
            else:
                target_z = cd['z']
                host_ref = cd['reference']
                host_info = "techo Id={} Z={:.4f}ft (bbox center)".format(cd['ceiling'].Id, target_z)

        if target_z is None:
            # SIN techo: usar Z = nivel Piso 5 + altura iluminacion (fallback)
            target_z = level_piso5_elev_ft + (ALTURA_ILUMINACION_MM * MM_TO_FT)
            host_info = "fallback Z={:.4f}ft (sin techo, sin host)".format(target_z)

        loc_pt = XYZ(x_ft, y_ft, target_z)

        # ===== INTENTO 1: host en cara del techo (WorkPlaneBased) =====
        if host_ref is not None:
            try:
                ref_dir = XYZ.BasisX
                inst = doc.Create.NewFamilyInstance(host_ref, loc_pt, ref_dir, symbol)
            except Exception as ex_host:
                # Si falla el host, caemos al Intento 2
                inst = None
                warnings.append("Host fallido {}: {}".format(d['nombre_dxf'], str(ex_host)))

        # ===== INTENTO 2: sin host, usando XYZ + StructuralType (como v06/v07) =====
        if inst is None:
            try:
                inst = doc.Create.NewFamilyInstance(
                    loc_pt, symbol, Structure.StructuralType.NonStructural)
            except Exception as ex_no_host:
                warnings.append("Colocacion fallida {}: {}".format(d['nombre_dxf'], str(ex_no_host)))
                print("  FAIL: {} no se pudo colocar".format(d['nombre_dxf']))
                continue

        # ===== Verificacion NO FATAL de Z y Schedule Level =====
        loc = inst.Location
        actual_z = None
        if loc and hasattr(loc, 'Point'):
            actual_pt = loc.Point
            actual_z = actual_pt.Z
            delta_mm = (actual_z - target_z) * 304.8
        else:
            delta_mm = 0.0

        # Intentar mover la instancia a la Z correcta si quedo en Z=0 o muy lejos
        if actual_z is not None and abs(actual_z - target_z) > 0.5:
            # delta > 0.5 ft (15 cm) -> mover con ElementTransformUtils
            try:
                translation = XYZ(0, 0, target_z - actual_z)
                ElementTransformUtils.MoveElement(doc, inst.Id, translation)
                # Volver a leer Z
                loc2 = inst.Location
                if loc2 and hasattr(loc2, 'Point'):
                    new_z = loc2.Point.Z
                    delta_mm = (new_z - target_z) * 304.8
                    actual_z = new_z
            except Exception as ex_move:
                warnings.append("No se pudo mover Z: {} ({})".format(
                    d['nombre_dxf'], str(ex_move)))

        # Verificar Schedule Level (no fatal)
        sched_ok = False
        try:
            p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
            if p_level and p_level.AsElementId() == level_piso5_id:
                sched_ok = True
        except Exception:
            pass

        placed += 1
        print("  OK #{}: {} -> tipo={} simbolo_Id={} | {} | Z real={:.4f}ft (delta={:+.1f}mm) | sched={}".format(
            placed, d['nombre_dxf'], tipo_revit, symbol.Id, host_info,
            actual_z if actual_z is not None else 0.0, delta_mm,
            "OK" if sched_ok else "FAIL"))

        # Rotacion (no fatal)
        if abs(rot_rad) > 1e-6:
            try:
                z_axis = actual_z if actual_z is not None else target_z
                axis = Line.CreateBound(
                    XYZ(x_ft, y_ft, z_axis),
                    XYZ(x_ft, y_ft, z_axis + 10.0))
                ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_rad)
            except Exception as rex:
                warnings.append("Rotacion fallida {}: {}".format(d['nombre_dxf'], str(rex)))

        # Mark
        try:
            mark = generate_mark(d)
            p_mark = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mark:
                p_mark.Set(mark)
        except Exception as ex_mark:
            warnings.append("Mark fallido {}: {}".format(d['nombre_dxf'], str(ex_mark)))

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
