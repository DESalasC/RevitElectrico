# -*- coding: utf-8 -*-
# colocacion_F01_F02_v01.py | 2026-11-17
# Colocación masiva F01 y F02 desde plan_v01.csv usando API de Revit (pyRevit)
import io, json, math, datetime, csv, os, sys

VER = "01"
print("=" * 78)
print("COLOCACION F01/F02 v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 78)

try:
    _ = doc.Title
except:
    doc = __revit__.ActiveUIDocument.Document
print("Documento: " + doc.Title)

if "CENTRAL-V01" not in doc.Title:
    print("ABORTADO: documento activo no es CENTRAL-V01")
    exit(1)

try:
    from Autodesk.Revit.DB import *
    from Autodesk.Revit.DB.Structure import StructuralType
except:
    import clr
    clr.AddReference('RevitAPI')
    from Autodesk.Revit.DB import *
    from Autodesk.Revit.DB.Structure import StructuralType

FT = 0.3048
M2FT = 3.28084

def iid(e):
    if e is None: return -1
    try: return int(e.Value)
    except:
        try: return int(e.IntegerValue)
        except: return -1

def by_id(d, n):
    for e in FilteredElementCollector(d).WhereElementIsNotElementType().ToElements():
        if iid(e.Id) == n: return e
    return None

def clean(s):
    if not s: return s
    return s.replace("\ufeff", "").replace("\u200b", "").strip()

def get_type_name(fs):
    try:
        p = fs.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.HasValue: return clean(p.AsString())
    except: pass
    return None

# ============================================================================
# 1. CARGAR PLAN DESDE CSV
# ============================================================================
CSV_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\f01f02\plan_v01.csv"
print("\nCargando plan desde %s" % CSV_PATH)

plan = []
with io.open(CSV_PATH, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';')
    for row in reader:
        plan.append(row)

print("Dispositivos en plan: %d" % len(plan))

# ============================================================================
# 2. OBTENER ELEMENTOS BASE
# ============================================================================
LEVEL_NAME = "Piso 5"
level = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    if lvl.Name == LEVEL_NAME:
        level = lvl
        break

if not level:
    print("ERROR: Nivel '%s' no encontrado" % LEVEL_NAME)
    exit(1)

level_elev_m = level.Elevation * FT
print("Nivel objetivo: %s (elev=%.3f m)" % (level.Name, level_elev_m))

# Cielorrasos - RANGO AMPLIADO
ceilings = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType().ToElements()
cielorrasos = []
for c in ceilings:
    try:
        bb = c.get_BoundingBox(None)
        if bb:
            z_min = bb.Min.Z * FT
            if 14.0 <= z_min <= 16.5:
                cielorrasos.append({
                    "id": iid(c.Id),
                    "element": c,
                    "x_min": bb.Min.X * FT,
                    "y_min": bb.Min.Y * FT,
                    "x_max": bb.Max.X * FT,
                    "y_max": bb.Max.Y * FT,
                    "z": z_min
                })
    except:
        pass

print("Cielorrasos (Z 14.0-16.5 m): %d" % len(cielorrasos))

def encontrar_cielorraso_para_punto(x_m, y_m):
    candidatos = []
    for c in cielorrasos:
        if (c["x_min"] <= x_m <= c["x_max"] and c["y_min"] <= y_m <= c["y_max"]):
            area = (c["x_max"] - c["x_min"]) * (c["y_max"] - c["y_min"])
            candidatos.append((area, c))
    if candidatos:
        candidatos.sort()
        return candidatos[0][1]
    return None

# Muros del nivel
walls = []
for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements():
    try:
        p_level = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
        if p_level:
            lvl_id = p_level.AsElementId()
            if lvl_id and lvl_id.IntegerValue == level.Id.IntegerValue:
                walls.append(w)
    except:
        pass

print("Muros en nivel '%s': %d" % (LEVEL_NAME, len(walls)))

# Cache de familias
symbols = {}
for fs in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    fam = clean(fs.FamilyName) if hasattr(fs, 'FamilyName') else ""
    typ = get_type_name(fs)
    if fam and typ:
        symbols["{}|{}".format(fam, typ).lower()] = fs

print("FamilySymbols cacheados: %d" % len(symbols))

# ============================================================================
# 3. FUNCIONES AUXILIARES
# ============================================================================
def obtener_nivel_real_del_muro(wall):
    """Obtiene el nivel base REAL del muro"""
    try:
        for param_name in [BuiltInParameter.WALL_BASE_CONSTRAINT,
                          BuiltInParameter.FAMILY_LEVEL_PARAM,
                          BuiltInParameter.FAMILY_BASE_LEVEL_PARAM]:
            try:
                p_level = wall.get_Parameter(param_name)
                if p_level:
                    level_id = p_level.AsElementId()
                    if level_id and iid(level_id) > 0:
                        lvl_elem = doc.GetElement(level_id)
                        if lvl_elem:
                            return lvl_elem, lvl_elem.Elevation * FT
            except:
                pass
    except:
        pass
    return None, 0.0

def encontrar_muro_cercano(x_m, y_m, z_absoluta_m):
    """Encuentra el muro más cercano y calcula el punto de inserción correcto"""
    best_wall = None
    min_dist = float('inf')
    best_point_xyz = None
    best_wall_level_elev = 0.0
    opts = Options()
    opts.ComputeReferences = True

    for w in walls:
        wall_level, wall_level_elev = obtener_nivel_real_del_muro(w)
        if wall_level is None:
            wall_level_elev = 0.0

        elevation_m = z_absoluta_m - wall_level_elev
        z_para_proyeccion = (wall_level_elev + elevation_m) * M2FT

        placement_pt = XYZ(x_m * M2FT, y_m * M2FT, z_para_proyeccion)

        bb = w.get_BoundingBox(None)
        if not bb:
            continue

        if (placement_pt.X < bb.Min.X - 0.5 or placement_pt.X > bb.Max.X + 0.5 or
            placement_pt.Y < bb.Min.Y - 0.5 or placement_pt.Y > bb.Max.Y + 0.5 or
            placement_pt.Z < bb.Min.Z - 0.5 or placement_pt.Z > bb.Max.Z + 0.5):
            continue

        try:
            geo = w.get_Geometry(opts)
            if geo:
                for g in geo:
                    if isinstance(g, Solid):
                        for face in g.Faces:
                            if isinstance(face, PlanarFace) and abs(face.FaceNormal.Z) < 0.1:
                                try:
                                    it = face.Project(placement_pt)
                                    if it and face.IsInside(it.UVPoint) and it.Distance < min_dist:
                                        min_dist = it.Distance
                                        best_wall = w
                                        best_point_xyz = it.XYZPoint
                                        best_wall_level_elev = wall_level_elev
                                except:
                                    pass
        except:
            pass

    return best_wall, best_point_xyz, best_wall_level_elev

# ============================================================================
# 4. COLOCACIÓN
# ============================================================================
FAMILIAS_TECHO = {"M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"}
FAMILIAS_MURO = {"M_Toma doble", "M_Interruptores", "M_Comunicaciones",
                 "M_Climatizacion", "M_Timbre", "M_Pulsador - Interruptor"}

ALTURA_TECHO_M = 15.82
ALTURA_MURO_M = 14.32

# Delta de rotación por familia (desde RE_COLOCAR_DISPOSITIVOS_generico.py)
DELTA_ROT = {
    "M_Toma doble": 90.0,
    "M_Interruptores": 90.0,
    "M_Comunicaciones": 90.0,
    "M_Climatizacion": 90.0,
    "M_Timbre": 90.0,
    "M_Pulsador - Interruptor": 90.0,
    "M_ClimatizacionV": 0.0,
    "M_Iluminacion": 0.0,
    "Consolidation_Point": 0.0,
    "EA": 0.0,
}

creados = 0
errores = 0
detalle = []

t = Transaction(doc, "Colocacion masiva F01/F02")
t.Start()
try:
    for row in plan:
        unidad = row["unidad"]
        bloque = row["bloque"]
        fam = row["familia"]
        tipo = row["tipo"]
        x_mm = float(row["x_mm"])
        y_mm = float(row["y_mm"])
        z_mm = float(row["z_mm"])
        rot_dxf = float(row["rot_dxf"])
        delta_rot = float(row["delta_rot"])

        clave = "{}|{}".format(fam, tipo).lower()
        if clave not in symbols:
            detalle.append((unidad, bloque, fam, tipo, "SIN SIMBOLO"))
            errores += 1
            continue

        sym = symbols[clave]
        if not sym.IsActive:
            sym.Activate()

        es_techo = fam in FAMILIAS_TECHO
        z_absoluta_m = z_mm / 1000.0
        rot_aplicada = rot_dxf + DELTA_ROT.get(fam, 0.0)
        rad = math.radians(rot_aplicada)

        inst = None
        try:
            if es_techo:
                # Techo: buscar cielorraso que contenga el punto XY
                cielo = encontrar_cielorraso_para_punto(x_mm / 1000.0, y_mm / 1000.0)
                if cielo is None:
                    raise Exception("sin cielorraso en XY")
                ref_cielo = cielo["element"].GetReferenceByFaceDirection(XYZ.BasisZ)
                if ref_cielo is None:
                    # Fallback: referencia del techo completo
                    ref_cielo = Reference(cielo["element"])
                pt_ft = XYZ(x_mm / 304.8, y_mm / 304.8, z_absoluta_m / FT)
                inst = doc.Create.NewFamilyInstance(ref_cielo, pt_ft, XYZ.BasisZ, sym)
            else:
                # Muro: encontrar muro cercano y proyectar
                wall, pt_on_face, wall_level_elev = encontrar_muro_cercano(
                    x_mm / 1000.0, y_mm / 1000.0, z_absoluta_m)
                if wall is None:
                    raise Exception("sin muro cercano")
                inst = doc.Create.NewFamilyInstance(pt_on_face, sym, wall, level, StructuralType.NonStructural)

            # Rotar si necesario
            if abs(rad) > 1e-9 and inst:
                pt_inst = inst.Location.Point
                ElementTransformUtils.RotateElement(doc, inst.Id,
                    Line.CreateBound(pt_inst, pt_inst + XYZ.BasisZ), rad)

            detalle.append((unidad, bloque, fam, tipo, "CREADO", iid(inst.Id)))
            creados += 1

        except Exception as ex:
            detalle.append((unidad, bloque, fam, tipo, "ERROR: %s" % str(ex).split('\n')[0][:100]))
            errores += 1

    t.Commit()
except Exception as ex:
    t.RollBack()
    print("ERROR EN TRANSACCION: %s" % ex)
    exit(1)

# ============================================================================
# 5. REPORTE
# ============================================================================
print("\n" + "=" * 78)
print("RESULTADO: %d creados, %d errores" % (creados, errores))
print("=" * 78)

OUT_CSV = r"D:\Work\PROJECTS\RevitElectrico\data\f01f02\creados_pyrevit_v01.csv"
with io.open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f, delimiter=';')
    writer.writerow(["unidad", "bloque", "familia", "tipo", "estado", "id"])
    for d in detalle:
        writer.writerow(d)
print("Detalle guardado en: %s" % OUT_CSV)

# Validación rápida por id
if creados > 0:
    print("\nValidación por id (primeros 5):")
    for d in detalle[:5]:
        if d[4] == "CREADO":
            eid = d[5]
            e = by_id(doc, eid)
            if e:
                lp = e.Location.Point
                print("  id=%d pos=(%.0f, %.0f, %.0f) mm" % (eid, lp.X*304.8, lp.Y*304.8, lp.Z*304.8))

print("\nFIN")