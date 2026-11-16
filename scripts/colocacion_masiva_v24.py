# -*- coding: utf-8 -*-
# colocacion_masiva_v24.py | v24.0 | 2026-11-14
# Corrección definitiva: usar muro como host para OneLevelBasedHosted
import io, json, math, datetime

VER = "24.0"
print("=" * 78)
print("COLOCACION MASIVA v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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

# ============================================================================
# 1. CARGAR PLAN DEL DRY-RUN
# ============================================================================
PLAN_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\plan_E06_v12.json"
f = io.open(PLAN_PATH, "r", encoding="utf-8")
plan_data = json.load(f)
f.close()

plan = plan_data["plan"]
print("\nDispositivos en plan: %d" % len(plan))

# ============================================================================
# 2. OBTENER NIVEL PISO 5 Y PANEL
# ============================================================================
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    if lvl.Name == "Piso 5":
        level_piso5 = lvl
        break

if not level_piso5:
    print("ERROR: Nivel 'Piso 5' no encontrado")
    exit(1)

level_elev_m = level_piso5.Elevation * FT
print("Nivel: %s (Id=%d, elevacion=%.3f m)" % (level_piso5.Name, iid(level_piso5.Id), level_elev_m))

# Panel TD 06
PANEL_TD06_ID = 5501145
panel = by_id(doc, PANEL_TD06_ID)
if not panel:
    print("ERROR: Panel TD 06 no encontrado")
    exit(1)

panel_pt = panel.Location.Point
print("Panel TD 06 (m): X=%.3f, Y=%.3f" % (panel_pt.X * FT, panel_pt.Y * FT))

# ============================================================================
# 3. CACHE DE SIMBOLOS
# ============================================================================
symbols = {}
for fs in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    symbols[iid(fs.Id)] = fs

print("Simbolos en cache: %d" % len(symbols))

# ============================================================================
# 4. COLOCACIÓN MASIVA
# ============================================================================
print("\n" + "=" * 78)
print("INICIANDO COLOCACION")
print("=" * 78)

results = []
success_count = 0
error_count = 0

for idx, item in enumerate(plan):
    handle = item["handle"]
    nombre = item["nombre"]
    host_type = item["host_type"]
    host_id = item["host_id"]
    symbol_id = item["symbol_id"]
    x_m = item["x_m"]
    y_m = item["y_m"]
    z_m = item["z_m"]
    snap_x_m = item.get("snap_x_m", x_m)
    snap_y_m = item.get("snap_y_m", y_m)
    snap_z_m = item.get("snap_z_m", z_m)
    
    print("\n[%d/%d] %s (Handle: %s)" % (idx + 1, len(plan), nombre, handle))
    
    # Obtener símbolo
    sym = symbols.get(symbol_id)
    if not sym:
        print("  ERROR: Simbolo %d no encontrado" % symbol_id)
        error_count += 1
        results.append({"handle": handle, "status": "ERROR", "error": "Simbolo no encontrado"})
        continue
    
    # Obtener host
    host = by_id(doc, host_id)
    if not host:
        print("  ERROR: Host %d no encontrado" % host_id)
        error_count += 1
        results.append({"handle": handle, "status": "ERROR", "error": "Host no encontrado"})
        continue
    
    # Convertir coordenadas a pies
    placement_pt = XYZ(x_m * M2FT, y_m * M2FT, z_m * M2FT)
    snap_pt = XYZ(snap_x_m * M2FT, snap_y_m * M2FT, snap_z_m * M2FT)
    
    # Determinar FamilyPlacementType
    try:
        placement_type = sym.Family.FamilyPlacementType
        is_workplane = (placement_type == FamilyPlacementType.WorkPlaneBased)
    except:
        is_workplane = False
    
    # Transacción individual
    t = Transaction(doc, "Colocar %s" % handle)
    t.Start()
    
    try:
        # Activar símbolo si es necesario
        if not sym.IsActive:
            sym.Activate()
            doc.Regenerate()
        
        new_inst = None
        
        if is_workplane:
            # WorkPlaneBased: usar Reference + dirección + snap_pt
            opts = Options()
            opts.ComputeReferences = True
            geo = host.get_Geometry(opts)
            
            host_face_ref = None
            host_normal = None
            
            if geo:
                for g in geo:
                    if isinstance(g, Solid):
                        for face in g.Faces:
                            if isinstance(face, PlanarFace):
                                try:
                                    it = face.Project(snap_pt)
                                    if it and face.IsInside(it.UVPoint):
                                        face_normal = face.FaceNormal
                                        
                                        # Para techos, seleccionar cara inferior (normal Z negativo)
                                        if host_type == "CEILING":
                                            if face_normal.Z < -0.9:
                                                host_face_ref = face.Reference
                                                host_normal = face_normal
                                                break
                                        else:  # WALL
                                            # Para muros, seleccionar caras verticales
                                            if abs(face_normal.Z) < 0.1:
                                                vec_to_panel = XYZ(panel_pt.X - snap_pt.X, panel_pt.Y - snap_pt.Y, 0)
                                                vec_to_panel = vec_to_panel.Normalize()
                                                dot_product = face_normal.X * vec_to_panel.X + face_normal.Y * vec_to_panel.Y
                                                if dot_product > 0:
                                                    host_face_ref = face.Reference
                                                    host_normal = face_normal
                                                    break
                                except:
                                    pass
                    if host_face_ref:
                        break
            
            if not host_face_ref:
                print("  ERROR: Cara del host no encontrada")
                error_count += 1
                results.append({"handle": handle, "status": "ERROR", "error": "Cara no encontrada"})
                t.RollBack()
                continue
            
            # Calcular dirección
            if host_type == "CEILING":
                direction = XYZ.BasisX
            else:  # WALL
                direction = host_normal.CrossProduct(XYZ.BasisZ).Normalize()
            
            # Crear en snap_pt
            new_inst = doc.Create.NewFamilyInstance(
                host_face_ref,
                snap_pt,
                direction,
                sym
            )
            
            pt_final = snap_pt
            
        else:
            # OneLevelBasedHosted: usar XYZ + Wall + StructuralType
            # Esto automáticamente asigna el nivel del muro y hospeda el elemento
            new_inst = doc.Create.NewFamilyInstance(
                placement_pt,
                sym,
                host,  # El muro como host
                StructuralType.NonStructural
            )
            
            # NO MOVER: LocationPoint.Point está en coordenadas locales del muro
            pt_final = placement_pt
            
            # Verificar que el nivel se asignó automáticamente
            try:
                p_level = new_inst.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
                if p_level:
                    assigned_level_id = p_level.AsElementId()
                    if iid(assigned_level_id) == iid(level_piso5.Id):
                        print("  Nivel asignado automaticamente: Piso 5")
                    else:
                        print("  ADVERTENCIA: Nivel asignado diferente")
            except:
                pass
        
        # Asignar Schedule Level (para WorkPlaneBased)
        if is_workplane:
            try:
                p_sl = new_inst.get_Parameter(BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM)
                if p_sl and not p_sl.IsReadOnly:
                    p_sl.Set(level_piso5.Id)
            except:
                pass
        
        # Asignar Mark
        try:
            p_mk = new_inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if p_mk and not p_mk.IsReadOnly:
                mark_val = "E06|%s|%s" % (handle, nombre[:10])
                p_mk.Set(mark_val)
        except:
            pass
        
        t.Commit()
        
        altura_sobre_nivel = (pt_final.Z * FT) - level_elev_m
        print("  OK - Id=%d | Pos=(%.2f, %.2f, %.2f) m | Altura: %.2f m | %s" % (
            iid(new_inst.Id), pt_final.X * FT, pt_final.Y * FT, pt_final.Z * FT,
            altura_sobre_nivel, "WorkPlane" if is_workplane else "LevelBased"))
        
        success_count += 1
        results.append({
            "handle": handle,
            "nombre": nombre,
            "status": "OK",
            "revit_id": iid(new_inst.Id),
            "unique_id": new_inst.UniqueId,
            "host_id": host_id,
            "placement_type": "WorkPlane" if is_workplane else "LevelBased",
            "x_m": pt_final.X * FT,
            "y_m": pt_final.Y * FT,
            "z_m": pt_final.Z * FT,
            "altura_sobre_nivel_m": altura_sobre_nivel
        })
        
    except Exception as e:
        print("  ERROR: %s" % str(e))
        error_count += 1
        results.append({"handle": handle, "status": "ERROR", "error": str(e)})
        try:
            t.RollBack()
        except:
            pass

# ============================================================================
# 5. REPORTE FINAL
# ============================================================================
print("\n" + "=" * 78)
print("REPORTE FINAL")
print("=" * 78)
print("Total procesados: %d" % len(plan))
print("Exitosos: %d" % success_count)
print("Errores: %d" % error_count)

# Reporte de alturas
print("\nResumen de alturas sobre nivel:")
alturas = {}
for r in results:
    if r["status"] == "OK":
        alt = round(r["altura_sobre_nivel_m"], 2)
        alturas[alt] = alturas.get(alt, 0) + 1

for alt in sorted(alturas.keys()):
    print("  %.2f m: %d dispositivos" % (alt, alturas[alt]))

if error_count > 0:
    print("\nDispositivos con error:")
    for r in results:
        if r["status"] == "ERROR":
            print("  - %s (%s): %s" % (r["handle"], r.get("nombre", "?"), r["error"]))

# Guardar reporte
report_path = r"D:\Work\PROJECTS\RevitElectrico\data\reporte_colocacion_E06_v24.json"
with io.open(report_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\nReporte guardado: %s" % report_path)
print("\n" + "=" * 78)
print("FIN - %s" % datetime.datetime.now().strftime("%H:%M:%S"))
print("=" * 78)