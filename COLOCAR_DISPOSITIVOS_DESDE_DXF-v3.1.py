# -*- coding: utf-8 -*-
"""
COLOCAR_DISPOSITIVOS_DESDE_DXF v3.1 - PRODUCCIÓN FIX
Coloca dispositivos de apartamentos tipo F desde DXF a CENTRAL-V01.rvt

FIX v3.0 → v3.1:
  - M_ClimatizacionV y M_Timbre movidos de CEILING_BASED_TECHO a LB_Z_ABS_ONLY.
    En v3.0 se colocaban en la cara del techo (Z=51.903ft = altura M_Iluminacion 2.60m)
    en lugar de su altura de diseno (2.40m = Z=51.247ft), causando desviacion ~0.656ft.

CONSOLIDA TODOS LOS FIXES v2.17 → v3.1:
- Offsets hardcodeados probados (F01/F02)
- FB-MURO obligatorio: Tomas, Comm, Interruptores, Pulsador
- FB-TECHO obligatorio: Luces, CP (Campana y ClimatizacionV van LB-Z-ABS)
- Búsqueda muro robusta (2 estrategias)
- Proyección techo robusta (4 estrategias)
- Level parameter robusto (3 parámetros)
- Detección automática techo por apartamento
- Limpieza agresiva previa
- Coordenadas GLOBALES CENTRAL-V01.rvt
"""

import json, os, math, clr, datetime
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    XYZ, Line, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
    Transaction, Level, Options, Solid, Face, Reference, LocationPoint,
    GeometryObject, PlanarFace, LocationCurve, ElementTransformUtils, UV, Parameter
)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

# ════════════════════════════════════════════════════════════════
# CONFIGURACIÓN CENTRAL-V01.rvt
# ════════════════════════════════════════════════════════════════

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_F01_F02_extraido.json"

# Offsets GLOBALES probados (pies) - CENTRAL-V01 coordenadas
OFFSETS = {
    "F01": {"x": 45.98, "y": 26.28},
    "F02": {"x": 45.98, "y": 31.47},  # CORREGIDO -1.05m vs versión anterior
}

# Techos por apartamento (ElementIds CENTRAL-V01 Piso 5)
CEILING_IDS = {
    "F01": 2764963,
    "F02": 2766313,
}

# Áreas de limpieza por apartamento (pies)
CLEANUP_BOUNDS = {
    "F01": {"xmin": 30, "xmax": 50, "ymin": 0, "ymax": 30},
    "F02": {"xmin": 30, "xmax": 50, "ymin": 30, "ymax": 60},
}

# Nivel objetivo
TARGET_LEVEL_NAMES = ["PISO 5", "NIVEL 5", "LEVEL 5", "P5", "N5"]
TARGET_LEVEL_ELEV = 43.37  # ft

# ════════════════════════════════════════════════════════════════
# CLASIFICACIÓN DE FAMILIAS (basada en comportamiento real validado)
# ════════════════════════════════════════════════════════════════

# FB-MURO: Familias hosteadas en muro (cara vertical)
FACE_BASED_MURO = {
    "M_Toma doble",           # 0.30m
    "M_Comunicaciones",       # 0.30m
    "M_Interruptores",        # 1.10m
    "M_Pulsador - Interruptor" # 1.10m
}

# FB-TECHO: Familias hosteadas en techo (cara horizontal)
CEILING_BASED_TECHO = {
    "M_Iluminacion",          # 2.60m - altura del techo
    "Consolidation_Point",    # 2.70m - altura del techo
}

# LB-Z-ABS: Familias nivel-based con Z absoluto (NO hosteadas en techo/muro)
# M_ClimatizacionV y M_Timbre: altura 2.40m (51.247ft), NO altura del techo (51.903ft)
LB_Z_ABS_ONLY = {
    "EA",                     # 1.90m
    "M_ClimatizacionV",       # 2.40m - FIX: estaba en CEILING_BASED_TECHO
    "M_Timbre",               # 2.40m - FIX: estaba en CEILING_BASED_TECHO
}

ALTURAS_M = {
    "M_Toma doble": 0.30,
    "M_Comunicaciones": 0.30,
    "M_Interruptores": 1.10,
    "M_Pulsador - Interruptor": 1.10,
    "M_Timbre": 2.40,
    "EA": 1.90,
    "M_ClimatizacionV": 2.40,
    "M_Iluminacion": 2.60,
    "Consolidation_Point": 2.70,
}

# ════════════════════════════════════════════════════════════════
# UTILIDADES
# ════════════════════════════════════════════════════════════════

exec_utc = datetime.datetime.utcnow()
exec_bogota = exec_utc - datetime.timedelta(hours=5)
FPM = 3.280839895
def m_a_ft(m): return m * FPM

def log(msg):
    print(msg)

def clean(s):
    if not s: return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

def elem_id(elem):
    if elem is None: return 0
    try:
        if hasattr(elem, 'Id'): eid_obj = elem.Id
        else: eid_obj = elem
        if hasattr(eid_obj, 'IntegerValue'): return int(eid_obj.IntegerValue)
        if hasattr(eid_obj, 'Value'): return int(eid_obj.Value)
        s = str(eid_obj)
        import re
        m = re.search(r'(\d+)', s)
        if m: return int(m.group(1))
        return int(s)
    except: return 0

def eid(val):
    return ElementId(Int64(val))

def load_json(p):
    with open(p, 'r') as f:
        return json.load(f)

# ════════════════════════════════════════════════════════════════
# SET LEVEL ROBUSTO (3 parámetros)
# ════════════════════════════════════════════════════════════════

def set_level_parameter(inst, level):
    for bp in [
        BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
        BuiltInParameter.LEVEL_PARAM,
        BuiltInParameter.FAMILY_LEVEL_PARAM
    ]:
        try:
            p = inst.get_Parameter(bp)
            if p and not p.IsReadOnly:
                p.Set(level.Id)
                return True, bp.ToString()
        except: pass
    return False, "FAILED"

# ════════════════════════════════════════════════════════════════
# BÚSQUEDA MURO ROBUSTA
# ════════════════════════════════════════════════════════════════

def find_wall_face_robust(doc, walls, target_x, target_y, target_z_ft):
    target_pt = XYZ(target_x, target_y, target_z_ft)
    best = None; best_dist = float('inf'); best_strategy = ""
    for w in walls:
        try:
            opt = Options(); opt.ComputeReferences = True
            geom = w.get_Geometry(opt)
            if not geom: continue
            for obj in geom:
                if not isinstance(obj, Solid): continue
                for face in obj.Faces:
                    if not isinstance(face, PlanarFace): continue
                    if abs(face.FaceNormal.Z) > 0.1: continue
                    # Estrategia 1: Project directo
                    try:
                        proj = face.Project(target_pt)
                        if proj:
                            uv = proj.UVPoint
                            bb = face.GetBoundingBox()
                            if bb.Min.U <= uv.U <= bb.Max.U and bb.Min.V <= uv.V <= bb.Max.V:
                                pt_on_face = face.Evaluate(uv)
                                d = target_pt.DistanceTo(pt_on_face)
                                if d < best_dist:
                                    best_dist = d; best = (face, w, pt_on_face, face.FaceNormal); best_strategy = "DIRECT_PROJECT"
                    except: pass
                    # Estrategia 2: Centro clamp
                    try:
                        bb = face.GetBoundingBox()
                        u_clamped = max(bb.Min.U, min(bb.Max.U, (bb.Min.U + bb.Max.U) / 2))
                        v_clamped = max(bb.Min.V, min(bb.Max.V, (bb.Min.V + bb.Max.V) / 2))
                        uv_clamped = UV(u_clamped, v_clamped)
                        pt_on_face = face.Evaluate(uv_clamped)
                        d = target_pt.DistanceTo(pt_on_face)
                        if d < best_dist:
                            best_dist = d; best = (face, w, pt_on_face, face.FaceNormal); best_strategy = "CENTER_CLAMP"
                    except: pass
        except: continue
    if best:
        return best[0], best[1], best[2], best[3], best_strategy
    return None, None, None, None, "NOT_FOUND"

# ════════════════════════════════════════════════════════════════
# PROYECCIÓN TECHO ROBUSTA (4 estrategias)
# ════════════════════════════════════════════════════════════════

def project_on_ceiling_face_ultra(doc, ceiling_id, face, face_ref, face_z, x, y):
    if not face or not face_ref:
        return None, None, False, "NO_FACE"
    try:
        bb = face.GetBoundingBox()
        # 1. Project + clamp
        try:
            pt_above = XYZ(x, y, face_z + 10)
            res = face.Project(pt_above)
            if res:
                uv = res.UVPoint
                u_clamped = max(bb.Min.U, min(bb.Max.U, uv.U))
                v_clamped = max(bb.Min.V, min(bb.Max.V, uv.V))
                uv_clamped = UV(u_clamped, v_clamped)
                pt_on_face = face.Evaluate(uv_clamped)
                return pt_on_face, uv_clamped, True, "PROJECT+CLAMP"
        except: pass
        # 2. BBox3D mapping
        try:
            ceil = doc.GetElement(eid(ceiling_id))
            if ceil:
                opt = Options()
                g = ceil.get_Geometry(opt)
                if g:
                    for o in g:
                        if isinstance(o, Solid):
                            bbox3d = o.GetBoundingBox()
                            if bbox3d:
                                u_range = bb.Max.U - bb.Min.U
                                v_range = bb.Max.V - bb.Min.V
                                x_range = bbox3d.Max.X - bbox3d.Min.X
                                y_range = bbox3d.Max.Y - bbox3d.Min.Y
                                if x_range > 0.01 and y_range > 0.01:
                                    u_frac = max(0.0, min(1.0, (x - bbox3d.Min.X) / x_range))
                                    v_frac = max(0.0, min(1.0, (y - bbox3d.Min.Y) / y_range))
                                    u_mapped = bb.Min.U + u_frac * u_range
                                    v_mapped = bb.Min.V + v_frac * v_range
                                    u_clamped = max(bb.Min.U, min(bb.Max.U, u_mapped))
                                    v_clamped = max(bb.Min.V, min(bb.Max.V, v_mapped))
                                    uv_clamped = UV(u_clamped, v_clamped)
                                    pt_on_face = face.Evaluate(uv_clamped)
                                    return pt_on_face, uv_clamped, True, "BBOX3D_MAP"
        except: pass
        # 3. Centro fallback
        try:
            u_center = (bb.Min.U + bb.Max.U) / 2
            v_center = (bb.Min.V + bb.Max.V) / 2
            uv_center = UV(u_center, v_center)
            pt_on_face = face.Evaluate(uv_center)
            return pt_on_face, uv_center, True, "CENTER_FALLBACK"
        except: pass
    except Exception as ex:
        pass
    return None, None, False, "ALL_FAILED"

# ════════════════════════════════════════════════════════════════
# OBTENER TECHO Y CARA INFERIOR
# ════════════════════════════════════════════════════════════════

def get_ceiling_bottom_face(doc, ceiling_id):
    ceil = doc.GetElement(eid(ceiling_id))
    if not ceil: return None, None, None
    try:
        opt = Options(); opt.ComputeReferences = True
        g = ceil.get_Geometry(opt)
        if not g: return None, None, None
        for o in g:
            if not isinstance(o, Solid): continue
            for f in o.Faces:
                if not isinstance(f, PlanarFace): continue
                if f.FaceNormal.Z < -0.95:
                    bb = f.GetBoundingBox()
                    u_mid = (bb.Min.U + bb.Max.U) / 2
                    v_mid = (bb.Min.V + bb.Max.V) / 2
                    uv_mid = UV(u_mid, v_mid)
                    pt_on_face = f.Evaluate(uv_mid)
                    return f, f.Reference, pt_on_face.Z
    except: pass
    return None, None, None

# ════════════════════════════════════════════════════════════════
# EJECUCIÓN PRINCIPAL
# ════════════════════════════════════════════════════════════════

log("=" * 70)
log("COLOCAR_DISPOSITIVOS_DESDE_DXF v3.1 - PRODUCCIÓN FIX")
log("Ejecutado: " + exec_bogota.strftime("%Y-%m-%d %H:%M:%S") + " (Bogotá GMT-5)")
log("=" * 70)

doc = None
try:
    doc = __revit__.ActiveUIDocument.Document
except:
    try:
        from pyrevit import revit
        doc = revit.doc
    except:
        pass

if not doc:
    log("[ERROR] No documento activo")
else:
    log("[OK] " + doc.Title)

# Cargar datos DXF
data = load_json(JSON_PATH)
f01_devices = [d for d in data.get('F01', {}).get('devices', []) if 'familia_revit' in d]
f02_devices = [d for d in data.get('F02', {}).get('devices', []) if 'familia_revit' in d]

log("F01: " + str(len(f01_devices)) + " dispositivos")
log("F02: " + str(len(f02_devices)) + " dispositivos")

# Level Piso 5
PISO5_LEVEL = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    name = lvl.Name if hasattr(lvl, 'Name') else ""
    if any(kw in name.upper() for kw in TARGET_LEVEL_NAMES):
        PISO5_LEVEL = lvl; break
if PISO5_LEVEL is None:
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if abs(lvl.Elevation - TARGET_LEVEL_ELEV) < 0.5:
            PISO5_LEVEL = lvl; break
if PISO5_LEVEL is None:
    PISO5_LEVEL = list(FilteredElementCollector(doc).OfClass(Level).ToElements())[0]

NIVEL5_ELEV = PISO5_LEVEL.Elevation
PISO5_LEVEL_ID_INT = elem_id(PISO5_LEVEL)
log("[LEVEL] '" + PISO5_LEVEL.Name + "' Id=" + str(PISO5_LEVEL_ID_INT) + " Elev=" + str(round(NIVEL5_ELEV,2)) + "ft")

# Techos
ceiling_data = {}
for apto in ["F01", "F02"]:
    face, face_ref, face_z = get_ceiling_bottom_face(doc, CEILING_IDS[apto])
    ceiling_data[apto] = {"id": CEILING_IDS[apto], "face": face, "face_ref": face_ref, "face_z": face_z}
    log("[TECHO " + apto + " Id=" + str(CEILING_IDS[apto]) + "] Cara Z=" + str(round(face_z,2) if face_z else 0) + "ft Ref=" + ("OK" if face_ref else "NO"))

# Muros Piso 5
walls = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id_int = elem_id(bp.AsElementId()) if bp and bp.HasValue else 0
    lvl_id_int = elem_id(w.LevelId)
    if (bp_id_int == PISO5_LEVEL_ID_INT or lvl_id_int == PISO5_LEVEL_ID_INT) and w.Location:
        walls.append(w)
log("[MUROS] Piso 5: " + str(len(walls)) + " muros")

# Símbolos
S = {}
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol):
            fam = clean(elem.FamilyName)
            p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            typ = clean(p.AsString()) if p and p.HasValue else "SinNombre"
            S[(fam, typ)] = elem
    except: pass
log("[SÍMBOLOS] Cargados: " + str(len(S)))

def find_sym(fam, typ):
    fam = clean(fam); typ = clean(typ)
    if (fam, typ) in S: return S[(fam, typ)]
    for (f, t), s in S.items():
        if f == fam and (t == typ or typ in t or t in typ): return s
    for (f, t), s in S.items():
        if f == fam: return s
    return None

# Limpieza agresiva
log("\n[LIMPIEZA] Borrando instancias previas...")
to_delete = []
for apto, bounds in CLEANUP_BOUNDS.items():
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            loc = fi.Location
            if not loc or not hasattr(loc, "Point"): continue
            p = loc.Point
            if bounds["xmin"] <= p.X <= bounds["xmax"] and bounds["ymin"] <= p.Y <= bounds["ymax"]:
                to_delete.append(fi.Id)
        except: pass

if to_delete:
    from System.Collections.Generic import List
    tx_del = Transaction(doc, "Limpiar previos")
    tx_del.Start()
    try:
        doc.Delete(List[ElementId](to_delete))
        tx_del.Commit()
        log("[LIMPIEZA] Borradas " + str(len(to_delete)) + " instancias")
    except Exception as e:
        tx_del.RollBack()
        log("[LIMPIEZA ERROR] " + str(e))
else:
    log("[LIMPIEZA] Nada que borrar")

# Duplicados
def existe_cercano(doc, px, py, umbral):
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            loc = fi.Location
            if not loc or not hasattr(loc, "Point"): continue
            p = loc.Point
            if math.hypot(p.X - px, p.Y - py) < umbral:
                return True
        except: continue
    return False

UMBRAL_DUP = m_a_ft(0.05)
HORIZONTAL_DIR = XYZ(1, 0, 0)

# ════════════════════════════════════════════════════════════════
# COLOCAR POR APARTAMENTO
# ════════════════════════════════════════════════════════════════

def place_apartment(apto_name, devices, off_x, off_y, ceiling_id, face, face_ref, face_z):
    if not devices: return 0, 0, 0

    if not face_z:
        log("⚠️ " + apto_name + ": Sin cara techo válida")

    log("\n===== " + apto_name + " (Techo Id=" + str(ceiling_id) + ", Cara Z=" + str(round(face_z,2) if face_z else 0) + "ft) =====")
    ok = er = saltados = 0

    tx = Transaction(doc, "Colocar " + apto_name)
    tx.Start()
    try:
        for i, dev in enumerate(devices, 1):
            fam = dev['familia_revit']; typ = dev['tipo_revit']
            s = find_sym(fam, typ)
            if not s:
                log("[" + str(i) + "] " + fam + "/" + typ + " -> NO SYM"); er += 1; continue

            x_abs = dev['x'] * FPM + off_x
            y_abs = dev['y'] * FPM + off_y
            rot = dev.get('rotation', 0)
            h_m = ALTURAS_M.get(fam, 0.30)

            if existe_cercano(doc, x_abs, y_abs, UMBRAL_DUP):
                log("  [DUP] " + dev['name'] + "(" + dev.get('handle','') + ") -> SALTADO"); saltados += 1; continue

            target_z_ft = NIVEL5_ELEV + m_a_ft(h_m)
            dxf_name = dev.get('name', '')
            dxf_handle = dev.get('handle', '')

            log("  [PLACE] " + dxf_name + "(" + dxf_handle + ") " + fam + " @ XY=(" + str(round(x_abs,2)) + "," + str(round(y_abs,2)) + ") GLOBAL")

            placed = False
            z_final = target_z_ft
            method = ""

            # 1. FB-MURO (prioridad 1 para familias de muro)
            if fam in FACE_BASED_MURO and walls:
                face_w, wall, pt_on_face, normal, strategy = find_wall_face_robust(doc, walls, x_abs, y_abs, target_z_ft)
                if face_w and pt_on_face:
                    if not s.IsActive: s.Activate()
                    try:
                        inst = doc.Create.NewFamilyInstance(face_w.Reference, pt_on_face, HORIZONTAL_DIR, s)
                        set_level_parameter(inst, PISO5_LEVEL)
                        rotation = rot
                        ang = (rotation + 90) % 360
                        if abs(ang) > 0.1:
                            try:
                                ax = Line.CreateBound(pt_on_face, XYZ(pt_on_face.X, pt_on_face.Y, pt_on_face.Z+1))
                                inst.Location.Rotate(ax, math.radians(ang))
                            except: pass
                        z_final = pt_on_face.Z
                        method = "FB-MURO-" + apto_name + "/" + strategy
                        log("    [FB-MURO/" + strategy + "] " + dxf_name + " -> Muro Id=" + str(elem_id(wall.Id)) + " Z=" + str(round(z_final,2)))
                        placed = True
                    except Exception as e:
                        log("    [FB-MURO ERR] " + dxf_name + ": " + str(e))
                else:
                    log("    [FB-MURO FALLÓ] " + dxf_name)

            # 2. FB-TECHO (familias de techo: M_Iluminacion, Consolidation_Point)
            if not placed and fam in CEILING_BASED_TECHO and face and face_ref and face_z:
                pt_on_face, uv, success, strategy = project_on_ceiling_face_ultra(doc, ceiling_id, face, face_ref, face_z, x_abs, y_abs)
                if success and pt_on_face:
                    if not s.IsActive: s.Activate()
                    try:
                        inst = doc.Create.NewFamilyInstance(face_ref, pt_on_face, HORIZONTAL_DIR, s)
                        set_level_parameter(inst, PISO5_LEVEL)
                        host_id = elem_id(inst.Host.Id) if inst.Host else -1
                        host_ok = "✅" if host_id == ceiling_id else "⚠️"
                        z_final = pt_on_face.Z
                        method = "FB-TECHO-" + apto_name + "/" + strategy
                        log("    [FB-TECHO/" + strategy + "] " + dxf_name + " -> Techo " + str(ceiling_id) + " " + host_ok + " Z=" + str(round(z_final,2)))
                        placed = True
                    except Exception as e:
                        log("    [FB-TECHO ERR] " + dxf_name + ": " + str(e))
                else:
                    log("    [FB-TECHO FALLÓ] " + dxf_name + " strategy=" + strategy)

            # 3. LB-Z-ABS (EA, M_ClimatizacionV, M_Timbre y cualquier otra no colocada)
            if not placed:
                pt = XYZ(x_abs, y_abs, target_z_ft)
                if not s.IsActive: s.Activate()
                try:
                    inst = doc.Create.NewFamilyInstance(pt, s, StructuralType.NonStructural)
                    set_level_parameter(inst, PISO5_LEVEL)
                    rotation = rot
                    ang = (rotation + 90) % 360
                    if abs(ang) > 0.1:
                        try:
                            ax = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z+1))
                            inst.Location.Rotate(ax, math.radians(ang))
                        except: pass
                    z_final = target_z_ft
                    method = "LB-Z-ABS"
                    log("    [LB-Z-ABS] " + dxf_name + " Z=" + str(round(z_final,2)))
                    placed = True
                except Exception as e:
                    log("[" + str(i) + "] " + dxf_name + " -> ERR Level: " + str(e)); er += 1; continue

            if placed:
                uid = inst.UniqueId
                log("[" + str(i) + "] " + dxf_name + "(" + dxf_handle + ") @ XY=(" + str(round(x_abs,2)) + "," + str(round(y_abs,2)) + ") GLOBAL ft Z=" + str(round(z_final,2)) + "ft -> OK id=" + str(elem_id(inst)) + " " + method + " UID=" + uid[:8])
                ok += 1
            else:
                log("[" + str(i) + "] " + dxf_name + " -> NO PLACED"); er += 1
        tx.Commit()
    except Exception as e:
        tx.RollBack(); log("[TXN ERR] " + str(e))
    return ok, er, saltados

# Ejecutar F01 y F02
for apto in ["F01", "F02"]:
    devices = f01_devices if apto == "F01" else f02_devices
    off = OFFSETS[apto]
    cd = ceiling_data[apto]
    o, e, s = place_apartment(apto, devices, off["x"], off["y"], cd["id"], cd["face"], cd["face_ref"], cd["face_z"])
    log(apto + " -> OK:" + str(o) + " ERR:" + str(e) + " SALTADOS:" + str(s))

log("\n" + "=" * 70)
log("v3.1 COMPLETADO - Listo para validar")
log("FB-MURO: Tomas, Comm, Interruptores, Pulsador")
log("FB-TECHO: Luces, Consolidation_Point")
log("LB-Z-ABS: EA, M_ClimatizacionV (2.40m), M_Timbre (2.40m)")
log("Offsets: F01(45.98,26.28) F02(45.98,31.47)")
log("=" * 70)