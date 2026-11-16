# -*- coding: utf-8 -*-
# colocacion_masiva_F01_v66.py | v66.0 | 2026-11-14
# Colocación masiva del F01 con correcciones preventivas
import io, json, math, datetime

VER = "66.0"
print("=" * 78)
print("COLOCACION MASIVA F01 v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 78)

try:
    _ = doc.Title
except:
    doc = __revit__.ActiveUIDocument.Document
print("Documento: " + doc.Title)

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
# 1. CONFIGURACIÓN DEL F01
# ============================================================================
APTO_NAME = "F 01"
PANEL_ID = 5501141
LEVEL_NAME = "Piso 5"
ORIG_X = 14.060755
ORIG_Y = 8.007905

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\plan_F01_v01.json"

# MAPEO EXPLÍCITO: Qué familias van en TECHO vs MURO
FAMILIAS_TECHO = ["M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"]
FAMILIAS_MURO = ["M_Toma doble", "M_Interruptores", "M_Comunicaciones", 
                 "M_Climatizacion", "M_Timbre", "M_Pulsador - Interruptor"]

# Alturas absolutas objetivo
ALTURA_TECHO_M = 15.82  # 2.60 m sobre Piso 5
ALTURA_MURO_M = 14.32   # 1.10 m sobre Piso 5

print("\nConfiguracion:")
print("  Apartamento: %s" % APTO_NAME)
print("  Panel ID: %d" % PANEL_ID)
print("  ORIG_X: %.6f" % ORIG_X)
print("  ORIG_Y: %.6f" % ORIG_Y)
print("  Altura techo: %.2f m" % ALTURA_TECHO_M)
print("  Altura muro: %.2f m" % ALTURA_MURO_M)

# ============================================================================
# 2. CARGAR PLAN
# ============================================================================
print("\nCargando plan de colocación...")
with io.open(JSON_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

plan = data['plan']
print("Dispositivos a colocar: %d" % len(plan))

# ============================================================================
# 3. OBTENER ELEMENTOS BASE
# ============================================================================
panel = by_id(doc, PANEL_ID)
if not panel:
    print("ERROR: Panel Id=%d no encontrado" % PANEL_ID)
    exit(1)

level = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    if lvl.Name == LEVEL_NAME:
        level = lvl
        break

if not level:
    print("ERROR: Nivel '%s' no encontrado" % LEVEL_NAME)
    exit(1)

level_elev_m = level.Elevation * FT
print("Nivel: %s (Id=%d, elevacion=%.3f m)" % (level.Name, iid(level.Id), level_elev_m))

# Buscar cielorrasos del Piso 5
print("\nBuscando cielorrasos del Piso 5...")
ceilings = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType().ToElements()

cielorrasos_piso5 = []
for c in ceilings:
    try:
        bb = c.get_BoundingBox(None)
        if bb:
            z_min = bb.Min.Z * FT
            if 15.5 <= z_min <= 16.0:
                cielorrasos_piso5.append({
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

print("Cielorrasos del Piso 5: %d" % len(cielorrasos_piso5))

def encontrar_cielorraso_para_punto(x_m, y_m):
    candidatos = []
    for c in cielorrasos_piso5:
        if (c["x_min"] <= x_m <= c["x_max"] and c["y_min"] <= y_m <= c["y_max"]):
            area = (c["x_max"] - c["x_min"]) * (c["y_max"] - c["y_min"])
            candidatos.append((area, c))
    if candidatos:
        candidatos.sort()
        return candidatos[0][1]
    return None

# Obtener todos los muros
walls = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
print("Muros encontrados: %d" % len(walls))

# ============================================================================
# 4. CACHE DE FAMILIAS
# ============================================================================
print("\nConstruyendo cache de familias...")
symbols = {}
for fs in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    fam = clean(fs.FamilyName) if hasattr(fs, 'FamilyName') else ""
    typ = get_type_name(fs)
    if fam and typ:
        symbols["{}|{}".format(fam, typ).lower()] = fs

print("Familias en cache: %d" % len(symbols))

# ============================================================================
# 5. FUNCIONES AUXILIARES
# ============================================================================
def encontrar_muro_cercano(x_m, y_m, z_m):
    """Encuentra el muro más cercano a un punto y proyecta el punto sobre la cara"""
    best_wall = None
    min_dist = float('inf')
    best_projection = None
    opts = Options()
    opts.ComputeReferences = True
    
    placement_pt = XYZ(x_m * M2FT, y_m * M2FT, z_m * M2FT)
    
    for w in walls:
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
                                        best_projection = it
                                except:
                                    pass
        except:
            pass
    
    return best_wall, min_dist, best_projection

def calcular_rotacion_muro(wall, x_m, y_m, z_m):
    """Calcula la rotación basada en la normal del muro (solo ángulos rectos)"""
    opts = Options()
    opts.ComputeReferences = True
    
    placement_pt = XYZ(x_m * M2FT, y_m * M2FT, z_m * M2FT)
    
    try:
        geo = wall.get_Geometry(opts)
        if geo:
            for g in geo:
                if isinstance(g, Solid):
                    for face in g.Faces:
                        if isinstance(face, PlanarFace) and abs(face.FaceNormal.Z) < 0.1:
                            try:
                                it = face.Project(placement_pt)
                                if it and face.IsInside(it.UVPoint):
                                    normal = face.FaceNormal
                                    angulo_rad = math.atan2(normal.Y, normal.X)
                                    angulo_deg = math.degrees(angulo_rad)
                                    
                                    # Normalizar a [0, 360)
                                    angulo_deg = angulo_deg % 360
                                    if angulo_deg < 0:
                                        angulo_deg += 360
                                    
                                    # Redondear al ángulo recto más cercano
                                    angulos_rectos = [0, 90, 180, 270]
                                    angulo_cercano = min(angulos_rectos, key=lambda a: abs((angulo_deg - a + 180) % 360 - 180))
                                    
                                    return angulo_cercano
                            except:
                                pass
    except:
        pass
    
    return 0

def obtener_nivel_del_muro(wall):
    """Obtiene el nivel base del muro"""
    try:
        p_level = wall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
        if p_level:
            level_id = p_level.AsElementId()
            if level_id and iid(level_id) > 0:
                lvl_elem = doc.GetElement(level_id)
                if lvl_elem:
                    return lvl_elem, lvl_elem.Elevation * FT
    except:
        pass
    return None, 0.0

# ============================================================================
# 6. COLOCACIÓN MASIVA
# ============================================================================
print("\n" + "=" * 78)
print("INICIANDO COLOCACION MASIVA")
print("=" * 78)

results = []
stats = {"ok": 0, "error": 0}

for idx, dev in enumerate(plan):
    handle = dev.get('handle', '?')
    nombre = dev['nombre']
    fam_name = dev['familia_revit']
    type_name = dev['tipo_revit']
    
    print("\n[%d/%d] %s (Handle: %s)" % (idx + 1, len(plan), nombre, handle))
    
    # Transformación
    x_m = dev['x_dxf'] + ORIG_X
    y_m = dev['y_dxf'] + ORIG_Y
    
    # Determinar host y altura
    if fam_name in FAMILIAS_TECHO:
        host_type = "TECHO"
        z_absoluta_m = ALTURA_TECHO_M
    else:
        host_type = "MURO"
        z_absoluta_m = ALTURA_MURO_M
    
    # Buscar símbolo
    key = "{}|{}".format(fam_name, type_name).lower()
    sym = symbols.get(key)
    
    if not sym:
        for k, fs in symbols.items():
            if fam_name.lower() in k:
                sym = fs
                break
    
    if not sym:
        print("  ERROR: Familia no encontrada (%s / %s)" % (fam_name, type_name))
        stats["error"] += 1
        continue
    
    t = Transaction(doc, "Colocar %s" % handle)
    t.Start()
    
    try:
        if not sym.IsActive:
            sym.Activate()
            doc.Regenerate()
        
        new_inst = None
        
        if host_type == "TECHO":
            # Buscar cielorraso
            ceiling_info = encontrar_cielorraso_para_punto(x_m, y_m)
            
            if not ceiling_info:
                print("  ERROR: No se encontró cielorraso en (%.2f, %.2f)" % (x_m, y_m))
                t.RollBack()
                stats["error"] += 1
                continue
            
            ceiling = ceiling_info["element"]
            opts = Options()
            opts.ComputeReferences = True
            geo = ceiling.get_Geometry(opts)
            host_face_ref = None
            
            placement_pt = XYZ(x_m * M2FT, y_m * M2FT, z_absoluta_m * M2FT)
            
            for g in geo:
                if isinstance(g, Solid):
                    for face in g.Faces:
                        if isinstance(face, PlanarFace) and face.FaceNormal.Z < -0.9:
                            try:
                                it = face.Project(placement_pt)
                                if it and face.IsInside(it.UVPoint):
                                    host_face_ref = face.Reference
                                    break
                            except: pass
                if host_face_ref: break
            
            if not host_face_ref:
                print("  ERROR: Cara de techo no encontrada")
                t.RollBack()
                stats["error"] += 1
                continue
            
            new_inst = doc.Create.NewFamilyInstance(host_face_ref, placement_pt, XYZ.BasisX, sym)
            
            # Asignar nivel
            try:
                p_sl = new_inst.get_Parameter(BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM)
                if p_sl and not p_sl.IsReadOnly:
                    p_sl.Set(level.Id)
            except: pass
            
        else:  # MURO
            # Encontrar muro cercano y proyectar punto
            wall, dist, projection = encontrar_muro_cercano(x_m, y_m, z_absoluta_m)
            
            if not wall or dist > 0.5:
                print("  ERROR: Muro no encontrado (dist=%.3f)" % dist)
                t.RollBack()
                stats["error"] += 1
                continue
            
            print("  Muro: Id=%d (dist=%.3f m)" % (iid(wall.Id), dist))
            
            # Obtener nivel del muro
            wall_level, wall_level_elev_m = obtener_nivel_del_muro(wall)
            if wall_level:
                print("  Nivel del muro: %s (elev=%.2f m)" % (wall_level.Name, wall_level_elev_m))
            else:
                print("  WARNING: No se pudo obtener nivel del muro, asumiendo Piso 5")
                wall_level_elev_m = level_elev_m
            
            # Calcular elevation sobre el nivel del muro
            elevation_m = z_absoluta_m - wall_level_elev_m
            print("  Elevation calculada: %.3f m" % elevation_m)
            
            # Usar el punto proyectado sobre la cara del muro
            if projection:
                placement_pt = projection
            else:
                placement_pt = XYZ(x_m * M2FT, y_m * M2FT, z_absoluta_m * M2FT)
            
            # Crear elemento
            new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, wall, StructuralType.NonStructural)
            
            # Ajustar elevation inmediatamente
            try:
                p_elev = new_inst.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM)
                if p_elev and not p_elev.IsReadOnly:
                    p_elev.Set(elevation_m * M2FT)
                    print("  ✓ Elevation ajustado a %.3f m" % elevation_m)
            except Exception as e:
                print("  WARNING: No se pudo ajustar elevation: %s" % str(e))
            
            # Asignar nivel
            try:
                p_lv = new_inst.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
                if p_lv and not p_lv.IsReadOnly:
                    p_lv.Set(level.Id)
            except: pass
            
            # Calcular y aplicar rotación basada en la normal del muro
            rot_deg = calcular_rotacion_muro(wall, x_m, y_m, z_absoluta_m)
            print("  Rotación (normal del muro): %.1f°" % rot_deg)
            
            if abs(rot_deg) > 0.1:
                loc = new_inst.Location
                if isinstance(loc, LocationPoint):
                    rot_actual = loc.Rotation
                    rot_objetivo = math.radians(rot_deg)
                    delta_rad = rot_objetivo - rot_actual
                    if abs(delta_rad) > 0.001:
                        axis = Line.CreateBound(placement_pt, XYZ(placement_pt.X, placement_pt.Y, placement_pt.Z + 1))
                        loc.Rotate(axis, delta_rad)
        
        # Asignar Mark
        try:
            p_mk = new_inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mk and not p_mk.IsReadOnly:
                p_mk.Set("%s|%s|%s" % (APTO_NAME, handle, nombre[:10]))
        except: pass
        
        t.Commit()
        
        # Verificación post-colocación
        loc = new_inst.Location
        if isinstance(loc, LocationPoint):
            z_final_m = loc.Point.Z * FT
            host = new_inst.Host
            host_status = "con host" if host else "SIN HOST"
            print("  OK - Id=%d | Z=%.2f m | %s | Rot=%.1f°" % (
                iid(new_inst.Id), z_final_m, host_status, rot_deg if host_type == "MURO" else 0))
        
        stats["ok"] += 1
        results.append({
            "handle": handle, "status": "OK", "revit_id": iid(new_inst.Id),
            "unique_id": new_inst.UniqueId
        })
        
    except Exception as e:
        print("  ERROR: %s" % str(e))
        t.RollBack()
        stats["error"] += 1
        results.append({"handle": handle, "status": "ERROR", "error": str(e)})

# ============================================================================
# 7. REPORTE FINAL
# ============================================================================
print("\n" + "=" * 78)
print("REPORTE FINAL")
print("=" * 78)
print("OK: %d" % stats["ok"])
print("Errores: %d" % stats["error"])

report_path = r"D:\Work\PROJECTS\RevitElectrico\data\reporte_colocacion_F01_v66.json"
with io.open(report_path, 'w', encoding='utf-8') as f:
    json.dump({
        "version": VER,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "apartamento": APTO_NAME,
        "stats": stats,
        "results": results
    }, f, indent=2, ensure_ascii=False)

print("\nReporte guardado: %s" % report_path)
print("=" * 78)