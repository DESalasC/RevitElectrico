"""
F6_COLOCAR_XPL_ILUMINACION.py - v12
Version: 12
Date: 2026-11-21
Fix v12: Si no se puede leer el nombre del tipo (IronPython bug 'Name'),
         asignar TODAS las luminarias al primer simbolo de M_Iluminacion
         (usuario cambiara a mano los tipos 22W y 13W despues).
         El usuario prefiere esto antes que adivinar el orden por Id.
Fix v11: Helper get_element_name() con varias estrategias (Name, Element.Name,
         SYMBOL_NAME_PARAM, ALL_MODEL_TYPE_NAME).
Fix v10: Seleccionar el FamilySymbol CORRECTO por tipo_revit.
Fix v09: INSTANCE_SCHEDULE_LEVEL_PARAM no existe en esta API.
Fix v08: La familia M_Iluminacion es WorkPlaneBased (no Level-Based).
         Sobrecarga correcta: NewFamilyInstance(Reference, XYZ, XYZ, FamilySymbol)
         hosteando en la cara inferior (Reference) del techo de Piso 5.
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
print("F6_COLOCAR_XPL_ILUMINACION v12")
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
    """Obtiene el nombre de un Element (Family o FamilySymbol) probando varias estrategias.
    En IronPython, s.Name puede lanzar excepcion 'Name' en algunos casos."""
    # Estrategia 1: propiedad Name directa
    try:
        n = el.Name
        if n is not None:
            return str(n)
    except Exception as ex:
        pass
    # Estrategia 2: Element.Name getter estatico
    try:
        n = Element.Name[el]
        if n is not None:
            return str(n)
    except Exception:
        pass
    # Estrategia 3: ALL_MODEL_TYPE_NAME (para tipos)
    try:
        p = el.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p:
            n = p.AsString()
            if n:
                return str(n)
    except Exception:
        pass
    # Estrategia 4: SYMBOL_NAME_PARAM (para FamilySymbol)
    try:
        p = el.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p:
            n = p.AsString()
            if n:
                return str(n)
    except Exception:
        pass
    # Estrategia 5: Title (algunos elementos)
    try:
        n = el.Title
        if n is not None:
            return str(n)
    except Exception:
        pass
    return None


# ─── SIMBOLOS: indexar TODOS los tipos de M_Iluminacion por nombre ─
print("Indexando tipos (FamilySymbol) de M_Iluminacion...")
symbols_by_type = {}  # {tipo_revit: FamilySymbol}
first_symbol = None
illum_symbols_unnamed = []  # simbolos de M_Iluminacion cuyo Name no se pudo leer

collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
n_total = 0
n_illum = 0
n_errors = 0
for s in collector:
    n_total += 1
    # Obtener nombre de familia
    fam_name = None
    try:
        fam = s.Family
        if fam is not None:
            fam_name = get_element_name(fam)
    except Exception as ex:
        if n_errors < 3:
            print("  ERR al leer .Family Id={}: {}: {}".format(
                s.Id, type(ex).__name__, str(ex)))
        n_errors += 1
        continue
    if fam_name != 'M_Iluminacion':
        continue
    # Es un simbolo de M_Iluminacion. Obtener su nombre (tipo)
    n_illum += 1
    sym_name = get_element_name(s)
    if sym_name:
        symbols_by_type[sym_name] = s
    else:
        # No se pudo leer el nombre, pero si sabemos que es de M_Iluminacion
        illum_symbols_unnamed.append(s)
    if first_symbol is None:
        first_symbol = s

print("  Total FamilySymbols iterados: {}".format(n_total))
print("  M_Iluminacion encontrados: {} (con nombre: {}, sin nombre: {})".format(
    n_illum, len(symbols_by_type), len(illum_symbols_unnamed)))
if n_errors:
    print("  Errores al iterar (no M_Iluminacion): {}".format(n_errors))

# Fallback: si no se pudieron leer los nombres de los tipos, pero si se
# encontro la familia, asignar TODAS las luminarias al primer simbolo
# disponible. El usuario cambiara a mano las que no sean del tipo correcto.
if not symbols_by_type and illum_symbols_unnamed:
    print("  FALLBACK (v12): no se pudo leer el nombre de los tipos.")
    print("  Asignando TODAS las luminarias al primer simbolo de M_Iluminacion.")
    print("  -> El usuario debera cambiar a mano los tipos 22W y 13W despues.")
    # Nota: no usar int(s.Id) -> falla en IronPython con algunos ElementId.
    # Como key usamos str(s.Id) que siempre es comparable.
    fallback_symbol = sorted(illum_symbols_unnamed, key=lambda s: str(s.Id))[0]
    print("  Simbolo elegido como fallback: Id={}".format(fallback_symbol.Id))
    tipos_en_json = sorted(set(d['tipo_revit'] for d in iluminacion))
    for tipo in tipos_en_json:
        symbols_by_type[tipo] = fallback_symbol
    print("  {} tipos en JSON mapeados al simbolo Id={}".format(
        len(tipos_en_json), fallback_symbol.Id))

if not symbols_by_type:
    print("¡ERROR: No hay tipos en M_Iluminacion accesibles!")
    print("  Diagnostico: se iteraron {} FamilySymbols.".format(n_total))
    print("  Lista de familias encontradas (primeras 20):")
    seen = set()
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        fn = get_element_name(s.Family) if s.Family else None
        if fn and fn not in seen:
            seen.add(fn)
            if len(seen) <= 20:
                print("       - '{}'".format(fn))
    import sys
    sys.exit(1)

print("  Tipos mapeados: {}".format(len(symbols_by_type)))
for name, s in sorted(symbols_by_type.items()):
    print("    - '{}' -> Id={}".format(name, s.Id))

fpt = first_symbol.Family.FamilyPlacementType
print("FamilyPlacementType: {} (FPT={})".format(str(fpt), int(fpt)))

# Validacion de tipo de colocacion
if fpt == FamilyPlacementType.CurveBased:
    print("¡ERROR: La familia es CurveBased! Esta sobrecarga no aplica.")
    import sys
    sys.exit(1)

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
                            # normal.Z < -0.1 => cara inferior del techo (apunta hacia abajo)
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

# Verificar que todas las entradas tengan Reference valida
ceilings_data = [cd for cd in ceilings_data if cd['reference'] is not None]
print("  Techos con Reference valida: {}".format(len(ceilings_data)))


def find_ceiling_face(x_ft, y_ft, max_dist_ft=15.0):
    """Devuelve el dict de ceilings_data cuya cara inferior contiene (x,y)
    o esta mas cerca, dentro de max_dist_ft."""
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


# ─── TRANSACCION: sobrecarga con Reference para WorkPlaneBased ──
print("\n" + "="*60)
print("COLOCANDO ILUMINACION {} - NewFamilyInstance(Reference, XYZ, XYZ, Symbol) [v12]".format(APTO_OBJETIVO))
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
        cd = find_ceiling_face(x_ft, y_ft)
        if cd is not None:
            # Proyectar (x, y) sobre la cara inferior del techo
            pt_xy = XYZ(x_ft, y_ft, 0)
            result = cd['face'].Project(pt_xy)
            if result and hasattr(result, 'UVPoint'):
                uv = result.UVPoint
            else:
                uv = result
            pt_on_face = cd['face'].Evaluate(uv)
            target_z = pt_on_face.Z
            host_ref = cd['reference']
            host_info = "techo Id={} Z={:.4f}ft".format(cd['ceiling'].Id, target_z)
        else:
            # Sin techo: colocamos en Z=fallback pero sin host (sin Reference).
            # WorkPlaneBased requiere host -> advertir y saltar.
            target_z = level_piso5_elev_ft + (ALTURA_ILUMINACION_MM * MM_TO_FT)
            host_ref = None
            warnings.append("Sin techo alrededor de ({:.0f},{:.0f}) - LUMINARIA NO COLOCADA: {}".format(
                d['x_mm'], d['y_mm'], d['nombre_dxf']))
            print("  SKIP (sin host): {} @ ({:.0f},{:.0f})".format(
                d['nombre_dxf'], d['x_mm'], d['y_mm']))
            continue

        # ===== Buscar el FamilySymbol correcto para ESTA luminaria =====
        tipo_revit = d.get('tipo_revit', '')
        symbol = symbols_by_type.get(tipo_revit)
        if symbol is None:
            # Buscar match parcial (case-insensitive, sin espacios extra)
            tipo_norm = tipo_revit.strip().lower()
            for k, s in symbols_by_type.items():
                if k.strip().lower() == tipo_norm:
                    symbol = s
                    break
        if symbol is None:
            warnings.append("Tipo no encontrado en familia M_Iluminacion: '{}' para {}".format(
                tipo_revit, d['nombre_dxf']))
            print("  SKIP (tipo no encontrado): '{}' para {}".format(
                tipo_revit, d['nombre_dxf']))
            continue

        # ===== CLAVE: sobrecarga con Reference para WorkPlaneBased =====
        # NewFamilyInstance(Reference reference, XYZ location,
        #                   XYZ referenceDirection, FamilySymbol symbol)
        # El host es la cara del techo (Piso 5) -> Schedule Level heredado del host.
        loc_pt = XYZ(x_ft, y_ft, target_z)
        ref_dir = XYZ.BasisX  # cualquier vector en el plano de la cara
        inst = doc.Create.NewFamilyInstance(host_ref, loc_pt, ref_dir, symbol)

        # Verificacion NO FATAL de Schedule Level
        # Para WorkPlaneBased hosted en techo, Revit crea automaticamente
        # el parametro 'Schedule Level' / 'Nivel de planificacion' que apunta
        # al nivel del host. No hay BuiltInParameter para el; buscar por nombre.
        sched_ok = False
        sched_param_name = None
        sched_level_id_str = "(no param)"
        # 1) Probar BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM (existe siempre)
        p_level_ref = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
        # 2) Buscar por nombre en todos los parametros de la instancia
        p_level_named = None
        nombres_nivel = ['Schedule Level', 'Nivel de planificacion',
                         'Nivel de referencia', 'Reference Level',
                         'Nivel', 'Level']
        for p in inst.Parameters:
            try:
                pname = p.Definition.Name
                if pname in nombres_nivel and p.StorageType == StorageType.ElementId:
                    p_level_named = p
                    sched_param_name = pname
                    break
            except:
                continue
        # 3) Elegir cual param usar para verificar
        p_level = p_level_ref if p_level_ref else p_level_named
        if p_level:
            # No usar int(p_level.AsElementId()) -> falla en IronPython.
            # Para el mensaje solo indicamos si coincide o no con Piso 5.
            if p_level.AsElementId() == level_piso5_id:
                sched_ok = True
                sched_level_id_str = "=Piso5"
            else:
                sched_level_id_str = "!=Piso5"
            if sched_param_name is None and p_level.Definition is not None:
                sched_param_name = p_level.Definition.Name
        # Nota: NO intentamos forzar p_level.Set() porque para instancias
        # hosted en un techo, el nivel lo determina el host. Si el techo es
        # de Piso 5, el Schedule Level quedo Piso 5 y no se puede cambiar aqui.
        if not sched_ok:
            warnings.append("Schedule Level pendiente verificar: {} (param={}, val={})".format(
                d['nombre_dxf'], sched_param_name, sched_level_id_str))

        # Verificacion de Z real
        loc = inst.Location
        actual_z = None
        if loc:
            actual_pt = loc.Point
            actual_z = actual_pt.Z
            delta_mm = (actual_z - target_z) * 304.8
            # Marcar con asterisco si el simbolo usado NO coincide con el tipo del JSON
            # (cuando se uso el fallback). El usuario debera cambiarlo a mano.
            tipo_marker = ""
            try:
                sym_used_name = get_element_name(symbol)
            except Exception:
                sym_used_name = "(Id={})".format(symbol.Id)
            if sym_used_name and sym_used_name != tipo_revit:
                tipo_marker = " [REVISAR: tipo JSON='{}' pero simbolo='{}' Id={}]".format(
                    tipo_revit, sym_used_name, symbol.Id)
            print("  OK: {} -> host={} tipo_JSON='{}' simbolo_Id={} Z={:.4f}ft actual Z={:.4f}ft (delta={:+.1f}mm) sched={}{}".format(
                d['nombre_dxf'], host_info, tipo_revit, symbol.Id, target_z, actual_z,
                delta_mm, "OK" if sched_ok else "FAIL", tipo_marker))
            if abs(actual_z - target_z) > 0.01:
                warnings.append("Z mismatch: {} actual={:.2f} target={:.2f}".format(
                    d['nombre_dxf'], actual_z, target_z))

        placed += 1

        # Rotacion: eje vertical en (x, y, z)
        if abs(rot_rad) > 1e-6 and inst is not None:
            try:
                z_axis = actual_z if actual_z is not None else target_z
                axis = Line.CreateBound(
                    XYZ(x_ft, y_ft, z_axis),
                    XYZ(x_ft, y_ft, z_axis + 10.0))
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
