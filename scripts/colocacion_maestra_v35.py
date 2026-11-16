# -*- coding: utf-8 -*-
# colocacion_maestra_v35.py | v35.0 | 2026-11-14
# Integra: idempotencia, detección de duplicados, verificacion post, parametrizacion
import io, json, math, datetime, hashlib, os

VER = "35.0"
print("=" * 78)
print("COLOCACION MAESTRA v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 78)

try:
    _ = doc.Title
except:
    doc = __revit__.ActiveUIDocument.Document

DOC_TITLE = doc.Title
print("Documento: " + DOC_TITLE)

# SHA256 del archivo (G - trazabilidad)
try:
    doc_path = doc.PathName
    if doc_path and os.path.exists(doc_path):
        with open(doc_path, 'rb') as f:
            DOC_SHA256 = hashlib.sha256(f.read()).hexdigest()[:16]
    else:
        DOC_SHA256 = "no_guardado"
except:
    DOC_SHA256 = "desconocido"
print("SHA256 doc: %s" % DOC_SHA256)

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
# 1. CONFIGURACION PARAMETRIZADA (E)
# ============================================================================
CONFIG = {
    "apto_name": "E05",
    "panel_id": 5501144,
    "ceiling_id": 2766255,
    "level_name": "Piso 5",
    "json_path": r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E05_v01.json",
    "tolerancia_xy_m": 0.10,      # (C) umbral de duplicado
    "tolerancia_post_m": 0.02,    # (D) tolerancia de verificacion post
    "mark_prefix": "E05",
}

# Reglas de rotacion extraidas del E06
REGLAS_ROTACION = {
    "M_Interruptores": 180.0,
    "M_Comunicaciones": -120.0,
    "M_Pulsador - Interruptor": 90.0,
    "M_Toma doble": -75.0,
    "M_Climatizacion": 0.0,
    "M_ClimatizacionV": 0.0,
    "M_Iluminacion": 0.0,
    "M_Timbre": 0.0,
    "Consolidation_Point": 0.0,
}

# Mapeo DXF -> Revit
DXF_TO_REVIT = {
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    "ELEC-I-S-C1-5A": ("M_Interruptores", "Simple conmutable"),
    "ELEC-I-S-1-5A": ("M_Interruptores", "Simple"),
    "S3": ("M_Interruptores", "Triple"),
    "ELEC-F-CONTROL": ("M_Climatizacion", "Interruptor Ventilador"),
    "ELEC-F-VENT": ("M_ClimatizacionV", "Ventilador"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    "ELEC-CAMPANA": ("M_Timbre", "Campana"),
    "ELEC-NET-PAU": ("Consolidation_Point", "CPB6BL"),
    "ELEC-TEL": ("M_Comunicaciones", "Datos"),
    "ELEC-EXT": ("EA", "M_Extractor"),
}

print("\nConfiguracion:")
for k, v in CONFIG.items():
    print("  %s = %s" % (k, v))

# ============================================================================
# 2. CARGAR DATOS
# ============================================================================
print("\nCargando JSON...")
with io.open(CONFIG["json_path"], 'r', encoding='utf-8') as f:
    data = json.load(f)
dispositivos = data['dispositivos']
print("Dispositivos: %d" % len(dispositivos))

# Panel
panel = by_id(doc, CONFIG["panel_id"])
if not panel:
    print("ERROR: Panel Id=%d no encontrado" % CONFIG["panel_id"])
    exit(1)
panel_pt = panel.Location.Point

# Nivel
level = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    if lvl.Name == CONFIG["level_name"]:
        level = lvl
        break
if not level:
    print("ERROR: Nivel '%s' no encontrado" % CONFIG["level_name"])
    exit(1)
level_elev_m = level.Elevation * FT

# Cielo raso
ceiling = by_id(doc, CONFIG["ceiling_id"])
if not ceiling:
    print("ERROR: Cielo raso Id=%d no encontrado" % CONFIG["ceiling_id"])
    exit(1)

# Cache de familias
symbols = {}
for fs in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    fam = clean(fs.FamilyName) if hasattr(fs, 'FamilyName') else ""
    typ = get_type_name(fs)
    if fam and typ:
        symbols["{}|{}".format(fam, typ).lower()] = fs

# ============================================================================
# 3. (F) IDEMPOTENCIA: Indexar elementos existentes por Mark
# ============================================================================
print("\nIndexando elementos existentes por Mark (idempotencia)...")
existing_by_mark = {}
cats_busqueda = [BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
                 BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_CommunicationDevices,
                 BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_MechanicalEquipment]

for cat in cats_busqueda:
    for e in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
        try:
            p_mk = e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mk and p_mk.HasValue:
                mk = p_mk.AsString()
                if mk and mk.startswith(CONFIG["mark_prefix"] + "|"):
                    # Extraer handle: formato "E05|<handle>|..."
                    partes = mk.split("|")
                    if len(partes) >= 2:
                        handle = partes[1]
                        existing_by_mark[handle] = e
        except:
            pass

print("Elementos existentes del apartamento %s: %d" % (CONFIG["apto_name"], len(existing_by_mark)))

# ============================================================================
# 4. COLOCACION MASIVA
# ============================================================================
print("\n" + "=" * 78)
print("INICIANDO COLOCACION")
print("=" * 78)

results = []
stats = {"ok": 0, "skip_idempotente": 0, "skip_duplicado_xy": 0, "error": 0}

for idx, dev in enumerate(dispositivos):
    handle = dev.get('handle', '?')
    nombre = dev['nombre']
    
    print("\n[%d/%d] %s (Handle: %s)" % (idx + 1, len(dispositivos), nombre, handle))
    
    # (F) Verificar idempotencia
    if handle in existing_by_mark:
        print("  SKIP (ya existe con Mark): Id=%d" % iid(existing_by_mark[handle].Id))
        stats["skip_idempotente"] += 1
        results.append({"handle": handle, "status": "SKIPPED_IDEMPOTENTE", "existing_id": iid(existing_by_mark[handle].Id)})
        continue
    
    # Transformacion
    x_rev = (dev['x'] + 2.251292587795678) * M2FT
    y_rev = (dev['y'] + 9.672656623969722) * M2FT
    z_rev = (level_elev_m + dev.get('altura_nominal_m', 1.10)) * M2FT
    placement_pt = XYZ(x_rev, y_rev, z_rev)
    
    # (C) Verificar duplicado XY con elementos existentes
    duplicado_encontrado = None
    for cat in cats_busqueda:
        for e in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
            try:
                loc = e.Location
                if isinstance(loc, LocationPoint):
                    pt = loc.Point
                    dist = math.sqrt((pt.X - x_rev)**2 + (pt.Y - y_rev)**2) * FT
                    if dist < CONFIG["tolerancia_xy_m"]:
                        duplicado_encontrado = e
                        break
            except: pass
        if duplicado_encontrado:
            break
    
    if duplicado_encontrado:
        print("  SKIP (duplicado XY a %.3f m): Id=%d" % (
            math.sqrt((duplicado_encontrado.Location.Point.X - x_rev)**2 + 
                      (duplicado_encontrado.Location.Point.Y - y_rev)**2) * FT,
            iid(duplicado_encontrado.Id)))
        stats["skip_duplicado_xy"] += 1
        results.append({"handle": handle, "status": "SKIPPED_DUPLICADO_XY", "existing_id": iid(duplicado_encontrado.Id)})
        continue
    
    # Buscar familia
    dxf_name = nombre
    if dxf_name not in DXF_TO_REVIT:
        print("  ERROR: No en mapeo DXF_TO_REVIT")
        stats["error"] += 1
        continue
    
    fam_name, type_name = DXF_TO_REVIT[dxf_name]
    key = "{}|{}".format(fam_name, type_name).lower()
    sym = symbols.get(key)
    
    if not sym:
        # Fallback: buscar por familia
        for k, fs in symbols.items():
            if fam_name.lower() in k:
                sym = fs
                break
    
    if not sym:
        print("  ERROR: Familia no encontrada (%s / %s)" % (fam_name, type_name))
        stats["error"] += 1
        continue
    
    # Determinar tipo
    try:
        is_workplane = (sym.Family.FamilyPlacementType == FamilyPlacementType.WorkPlaneBased)
    except:
        is_workplane = False
    
    t = Transaction(doc, "Colocar %s" % handle)
    t.Start()
    
    try:
        if not sym.IsActive:
            sym.Activate()
            doc.Regenerate()
        
        new_inst = None
        
        if is_workplane:
            opts = Options()
            opts.ComputeReferences = True
            geo = ceiling.get_Geometry(opts)
            host_face_ref = None
            
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
            
        else:
            # OneLevelBasedHosted: buscar muro
            walls = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().ToElements()
            best_wall = None
            min_dist = float('inf')
            opts = Options()
            opts.ComputeReferences = True
            
            for w in walls:
                bb = w.get_BoundingBox(None)
                if not bb: continue
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
                                        except: pass
                except: pass
            
            if not best_wall or min_dist > 0.5:
                print("  ERROR: Muro host no encontrado")
                t.RollBack()
                stats["error"] += 1
                continue
            
            new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, best_wall, StructuralType.NonStructural)
        
        # Aplicar regla de rotacion
        fam_actual = clean(sym.FamilyName)
        delta_rot = REGLAS_ROTACION.get(fam_actual, 0.0)
        if delta_rot != 0.0:
            loc = new_inst.Location
            if isinstance(loc, LocationPoint):
                rot_actual = loc.Rotation
                rot_objetivo = math.radians(dev.get('rotacion_grados', 0) + delta_rot)
                delta_rad = rot_objetivo - rot_actual
                if abs(delta_rad) > 0.001:
                    axis = Line.CreateBound(placement_pt, XYZ(placement_pt.X, placement_pt.Y, placement_pt.Z + 1))
                    loc.Rotate(axis, delta_rad)
        
        # Asignar Mark
        try:
            p_mk = new_inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mk and not p_mk.IsReadOnly:
                p_mk.Set("%s|%s|%s" % (CONFIG["mark_prefix"], handle, nombre[:10]))
        except: pass
        
        # Asignar nivel
        try:
            if is_workplane:
                p_sl = new_inst.get_Parameter(BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM)
                if p_sl and not p_sl.IsReadOnly: p_sl.Set(level.Id)
            else:
                p_lv = new_inst.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
                if p_lv and not p_lv.IsReadOnly: p_lv.Set(level.Id)
        except: pass
        
        t.Commit()
        
        # (D) Verificacion post-colocacion
        loc = new_inst.Location
        if isinstance(loc, LocationPoint):
            pt_final = loc.Point
            # Para WorkPlaneBased, LocationPoint.Point puede ser local; comparar solo si es razonable
            if is_workplane:
                # En WorkPlaneBased, la Z deberia coincidir con el plano del techo
                dist_z = abs(pt_final.Z * FT - (level_elev_m + dev.get('altura_nominal_m', 1.10)))
                if dist_z > CONFIG["tolerancia_post_m"]:
                    print("  WARNING: Z post=%.3f m, esperado=%.3f m (delta=%.3f)" % (
                        pt_final.Z * FT, level_elev_m + dev.get('altura_nominal_m', 1.10), dist_z))
            else:
                # Para LevelBased, comparar XY
                dist_xy = math.sqrt((pt_final.X - x_rev)**2 + (pt_final.Y - y_rev)**2) * FT
                if dist_xy > CONFIG["tolerancia_post_m"]:
                    print("  WARNING: XY post=(%.3f, %.3f), esperado=(%.3f, %.3f) (delta=%.3f)" % (
                        pt_final.X * FT, pt_final.Y * FT, x_rev * M2FT, y_rev * M2FT, dist_xy))
        
        print("  OK - Id=%d" % iid(new_inst.Id))
        stats["ok"] += 1
        results.append({
            "handle": handle, "status": "OK",
            "revit_id": iid(new_inst.Id),
            "unique_id": new_inst.UniqueId,
            "x_m": round(pt_final.X * FT, 4) if isinstance(loc, LocationPoint) else None,
            "y_m": round(pt_final.Y * FT, 4) if isinstance(loc, LocationPoint) else None,
            "z_m": round(pt_final.Z * FT, 4) if isinstance(loc, LocationPoint) else None,
        })
        
    except Exception as e:
        print("  ERROR: %s" % str(e))
        t.RollBack()
        stats["error"] += 1
        results.append({"handle": handle, "status": "ERROR", "error": str(e)})

# ============================================================================
# 5. REPORTE FINAL
# ============================================================================
print("\n" + "=" * 78)
print("REPORTE FINAL")
print("=" * 78)
print("OK: %d" % stats["ok"])
print("Skip idempotente: %d" % stats["skip_idempotente"])
print("Skip duplicado XY: %d" % stats["skip_duplicado_xy"])
print("Errores: %d" % stats["error"])

report_path = r"D:\Work\PROJECTS\RevitElectrico\data\reporte_%s_v35.json" % CONFIG["apto_name"]
with io.open(report_path, 'w', encoding='utf-8') as f:
    json.dump({
        "version": VER,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": DOC_TITLE,
        "sha256": DOC_SHA256,
        "config": CONFIG,
        "stats": stats,
        "results": results
    }, f, indent=2, ensure_ascii=False)

print("\nReporte guardado: %s" % report_path)
print("=" * 78)