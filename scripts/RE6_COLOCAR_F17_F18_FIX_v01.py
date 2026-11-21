# -*- coding: utf-8 -*-
"""
RE6_COLOCAR_FIX_COORDS_v01.py
==============================
Versión corregida: convierte techo bounds de global (DXF) a local (Revit)
usando el offset del maestro (panel_revit - base_dxf).

Solo para F17 y F18 primero.
"""

import clr, json, math, os
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, UV, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, HostObjectUtils, ShellLayerType,
    Transaction, Line, PlanarFace, Options, Solid, Level, FamilyPlacementType)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")

with open(os.path.join(DATA_DIR, "maestro_colocacion_piso5.json"), 'r') as f:
    maestro = json.load(f)

with open(os.path.join(DATA_DIR, "ceilings_mapping_apto.json"), 'r') as f:
    ceilings_map = json.load(f)

doc = __revit__.ActiveUIDocument.Document

FPM = 3.280839895
def m_a_ft(m): return m * FPM
def ft_a_m(ft): return ft / FPM
def clean(s): return s.replace('\ufeff','').replace('\u200b','').strip() if s else s

print("=== COLOCAR F17 + F18 (COORDS FIX) ===")

TARGET_APTOS = ["F17", "F18"]

# NIVEL PISO 5
nivel5_id = 192512
nivel5_z = 43.37
TARGET_LEVEL_NAMES = ["PISO 5", "NIVEL 5", "LEVEL 5", "P5", "N5"]
PISO5_LEVEL = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    name = lvl.Name if hasattr(lvl, 'Name') else ""
    if any(kw in name.upper() for kw in TARGET_LEVEL_NAMES):
        PISO5_LEVEL = lvl
        break
if not PISO5_LEVEL:
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        if abs(lvl.Elevation - nivel5_z) < 0.5:
            PISO5_LEVEL = lvl
            break
if not PISO5_LEVEL:
    PISO5_LEVEL = list(FilteredElementCollector(doc).OfClass(Level).ToElements())[0]

# SÍMBOLOS
S = {}
PLACEMENT_TYPE = {}
cats = [
    BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_MechanicalEquipment, BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_FireAlarmDevices, BuiltInCategory.OST_ElectricalEquipment,
]
for cat in cats:
    for elem in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsElementType().ToElements():
        try:
            if isinstance(elem, FamilySymbol):
                fam = clean(elem.FamilyName)
                p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                typ = clean(p.AsString()) if p and p.HasValue else "SinNombre"
                S[(fam, typ)] = elem
                if fam not in PLACEMENT_TYPE:
                    PLACEMENT_TYPE[fam] = elem.Family.FamilyPlacementType
        except:
            pass
print("Simbolos: {}".format(len(S)))

# MAPEO
FAMILY_MAP = {
    ("M_Toma doble", "GFCI"): ("M_Toma doble", "GFCI"),
    ("M_Toma doble", "Normal"): ("M_Toma doble", "Normal"),
    ("M_Toma doble", "Intemperie"): ("M_Toma doble", "Intemperie"),
    ("M_Toma-Rango", "Unica"): ("M_Toma-Rango", "Unica"),
    ("M_Toma - 220V", "220V"): ("M_Toma - 220V", "220V"),
    ("M_Comunicaciones", "Datos"): ("M_Comunicaciones", "Datos"),
    ("M_Comunicaciones", "Telefono"): ("M_Comunicaciones", "Telefono"),
    ("M_Interruptores", "Simple"): ("M_Interruptores", "Simple"),
    ("M_Interruptores", "Doble"): ("M_Interruptores", "Doble"),
    ("M_Interruptores", "Triple"): ("M_Interruptores", "Triple"),
    ("M_Interruptores", "Conmutable"): ("M_Interruptores", "Conmutable"),
    ("M_Interruptores", "Simple conmutable"): ("M_Interruptores", "Simple conmutable"),
    ("M_Interruptores", "Doble conmutable"): ("M_Interruptores", "Doble conmutable"),
    ("M_Interruptores", "Triple conmutable"): ("M_Interruptores", "Triple conmutable"),
    ("M_Interruptores", "Control"): ("M_Interruptores", "Conmutable"),
    ("M_Pulsador - Interruptor", "Timbre"): ("M_Pulsador - Interruptor", "Timbre"),
    ("M_Timbre", "Campana"): ("M_Timbre", "Campana"),
    ("EA", "Extintor"): ("EA", "Extractor"),
    ("EA", "Extractor"): ("EA", "Extractor"),
    ("M_ClimatizacionV", "Ventilador"): ("M_ClimatizacionV", "Ventilador"),
    ("M_Climatizacion", "Interruptor Ventilador"): ("M_Climatizacion", "Interruptor Ventilador"),
    ("M_Iluminacion", "SONO FLEX 10 trim"): ("M_Iluminacion", "SONO FLEX 10 trim"),
    ("M_Iluminacion", "SONO FLEX 13 trim"): ("M_Iluminacion", "SONO FLEX 13 trim"),
    ("M_Iluminacion", "SONO FLEX 22 trim"): ("M_Iluminacion", "SONO FLEX 22 trim"),
}

def find_sym(fam, typ):
    fam = clean(fam); typ = clean(typ)
    if (fam, typ) in FAMILY_MAP:
        target = FAMILY_MAP[(fam, typ)]
        if target in S: return S[target]
    if (fam, typ) in S: return S[(fam, typ)]
    for (f, t), s in S.items():
        if f == fam and (t == typ or typ in t or t in typ): return s
    for (f, t), s in S.items():
        if f == fam: return s
    return None

def get_placement_type(fam):
    fpt = PLACEMENT_TYPE.get(fam)
    fpt_str = str(fpt) if fpt else ""
    if fpt_str == "WorkPlaneBased":
        if fam in ["M_ClimatizacionV", "M_Iluminacion"]:
            return "FACE_CEILING"
        return "FACE_WALL"
    return "LEVEL"

ALTURAS = {
    "M_Toma doble": nivel5_z + m_a_ft(0.30),
    "M_Toma-Rango": nivel5_z + m_a_ft(0.30),
    "M_Toma - 220V": nivel5_z + m_a_ft(0.30),
    "M_Comunicaciones": nivel5_z + m_a_ft(1.00),
    "Consolidation_Point": nivel5_z + m_a_ft(2.70),
    "M_Pulsador - Interruptor": nivel5_z + m_a_ft(1.10),
    "M_Timbre": nivel5_z + m_a_ft(2.40),
    "M_Interruptores": nivel5_z + m_a_ft(1.10),
    "EA": nivel5_z + m_a_ft(2.40),
    "M_ClimatizacionV": nivel5_z + m_a_ft(2.60),
    "M_Iluminacion": nivel5_z + m_a_ft(2.60),
}

def calc_place_dir(normal, rot_json):
    up_vec = XYZ.BasisZ
    along_vec = XYZ.CrossProduct(normal, up_vec)
    rot = rot_json % 360
    if rot <= 45 or rot >= 315:
        return up_vec
    elif rot <= 135:
        return along_vec
    elif rot <= 225:
        return XYZ(-up_vec.X, -up_vec.Y, -up_vec.Z)
    else:
        return XYZ(-along_vec.X, -along_vec.Y, -along_vec.Z)

# MUROS PISO 5
walls = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id = int(bp.AsElementId().Value) if bp and bp.HasValue else 0
    lvl_id = int(w.LevelId.Value)
    if not ((bp_id == nivel5_id or lvl_id == nivel5_id) and w.Location):
        continue
    curve = w.Location.Curve
    if not curve: continue
    interior_ref = None
    normal = None
    try:
        int_refs = HostObjectUtils.GetSideFaces(w, ShellLayerType.Interior)
        for ref in int_refs:
            f = w.GetGeometryObjectFromReference(ref)
            if f and abs(f.FaceNormal.Z) < 0.1:
                interior_ref = ref
                normal = f.FaceNormal
                break
    except:
        continue
    if interior_ref:
        wall_dir = XYZ.CrossProduct(normal, XYZ.BasisZ)
        walls.append((w.Id, curve, interior_ref, normal, wall_dir))
print("Muros Piso 5: {}".format(len(walls)))

def find_wall_ref(pt_xy, max_dist=5.0):
    best = None
    best_d = float('inf')
    pt_at_z = XYZ(pt_xy.X, pt_xy.Y, nivel5_z)
    for w_id, curve, ref, normal, wall_dir in walls:
        try:
            d = curve.Distance(pt_at_z)
            if d < best_d and d < max_dist:
                best_d = d
                best = (w_id, ref, normal, wall_dir, d)
        except:
            continue
    return best

def point_in_bounds(x, y, bounds):
    return bounds["xmin"] <= x <= bounds["xmax"] and bounds["ymin"] <= y <= bounds["ymax"]

# PROCESAR F17 Y F18 CON FIX DE COORDENADAS
for apto_key in TARGET_APTOS:
    apto_data = maestro["apartamentos"].get(apto_key)
    if not apto_data:
        print("[WARN] {} no en maestro".format(apto_key))
        continue
    
    devices = apto_data["dispositivos"]
    panel_revit = apto_data["panel_name_revit"]
    
    # Techo info (global DXF)
    ceiling_info = ceilings_map["mapping"].get(apto_key)
    if not ceiling_info:
        print("[WARN] {} sin techo mapeado".format(apto_key))
        continue
    
    ceiling_id = ceiling_info["ceiling_id"]
    ceiling_z_global = ceiling_info["ceiling_face_z_ft"]
    bounds_global = ceiling_info["ceiling_bounds_ft"]
    
    # OFFSET: panel_revit (local) - panel_dxf_global (en pies)
    # El maestro tiene base_dxf_ft (posición del panel en DXF global)
    base_dxf_ft = apto_data.get("base_dxf_ft", {})
    panel_revit_ft = {
        "x": apto_data["panel_revit_m"]["x"] / FT_TO_M,
        "y": apto_data["panel_revit_m"]["y"] / FT_TO_M
    }
    
    # Calcular offset: local = global + offset
    # offset = panel_revit_local - base_dxf_global
    offset_x = panel_revit_ft["x"] - base_dxf_ft.get("x", 0)
    offset_y = panel_revit_ft["y"] - base_dxf_ft.get("y", 0)
    
    print("\n=== {} ===".format(apto_key))
    print("Panel Revit: ({:.2f}, {:.2f}) ft".format(panel_revit_ft["x"], panel_revit_ft["y"]))
    print("Base DXF: ({:.2f}, {:.2f}) ft".format(base_dxf_ft.get("x", 0), base_dxf_ft.get("y", 0)))
    print("Offset (local - global): ({:.2f}, {:.2f}) ft".format(offset_x, offset_y))
    
    # Convertir techo bounds a LOCAL
    bounds_local = {
        "xmin": bounds_global["xmin"] + offset_x,
        "xmax": bounds_global["xmax"] + offset_x,
        "ymin": bounds_global["ymin"] + offset_y,
        "ymax": bounds_global["ymax"] + offset_y,
    }
    ceiling_z_local = ceiling_z_global + offset_y  # Z no cambia, pero por consistencia
    
    print("Techo Global: Centro=({:.2f},{:.2f}) Bounds X=[{:.2f},{:.2f}] Y=[{:.2f},{:.2f}]".format(
        ceiling_info["ceiling_center_ft"]["x"], ceiling_info["ceiling_center_ft"]["y"],
        bounds_global["xmin"], bounds_global["xmax"], bounds_global["ymin"], bounds_global["ymax"]))
    print("Techo LOCAL:  Centro=({:.2f},{:.2f}) Bounds X=[{:.2f},{:.2f}] Y=[{:.2f},{:.2f}]".format(
        ceiling_info["ceiling_center_ft"]["x"] + offset_x, ceiling_info["ceiling_center_ft"]["y"] + offset_y,
        bounds_local["xmin"], bounds_local["xmax"], bounds_local["ymin"], bounds_local["ymax"]))
    
    # Verificar que dispositivos caen en techo local
    in_local = 0
    for dev in devices[:10]:
        x = dev["posicion_revit_m"]["x"] / FT_TO_M
        y = dev["posicion_revit_m"]["y"] / FT_TO_M
        if bounds_local["xmin"] <= x <= bounds_local["xmax"] and bounds_local["ymin"] <= y <= bounds_local["ymax"]:
            in_local += 1
    print("Dispositivos en techo LOCAL (primeros 10): {}/10".format(in_local))
    
    # Obtener techo elemento y cara inferior
    f02_ceiling = doc.GetElement(ElementId(Int64(ceiling_id)))
    if not f02_ceiling:
        print("[WARN] Techo ID {} no encontrado".format(ceiling_id))
        continue
    
    f02_ceiling_face = None
    opt = Options(); opt.ComputeReferences = True
    geom = f02_ceiling.get_Geometry(opt)
    if geom:
        for obj in geom:
            if obj.GetType().Name == "Solid":
                for f in obj.Faces:
                    if isinstance(f, PlanarFace) and f.FaceNormal.Z < -0.9:
                        f02_ceiling_face = f
                        break
    if not f02_ceiling_face:
        print("[WARN] Sin cara inferior")
        continue
    
    ceiling_normal = f02_ceiling_face.FaceNormal
    ceiling_wall_dir = XYZ.CrossProduct(ceiling_normal, XYZ.BasisZ)
    
    print("Dispositivos: {}".format(len(devices)))
    
    # LIMPIAR EXISTENTES
    to_delete = []
    elec_cats = [
        BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_LightingFixtures,
        BuiltInCategory.OST_TelephoneDevices, BuiltInCategory.OST_DataDevices,
        BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_MechanicalEquipment,
        BuiltInCategory.OST_FireAlarmDevices, BuiltInCategory.OST_ElectricalEquipment,
    ]
    for cat in elec_cats:
        for elem in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
            mark_p = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if mark_p and mark_p.HasValue:
                mark_val = mark_p.AsString()
                if mark_val and mark_val.startswith(apto_key):
                    to_delete.append(elem.Id)
    
    if to_delete:
        t_clean = Transaction(doc, "Limpiar {}".format(apto_key))
        t_clean.Start()
        for eid in to_delete:
            try: doc.Delete(eid)
            except: pass
        t_clean.Commit()
        print("Eliminados: {}".format(len(to_delete)))
    
    # COLOCAR
    t = Transaction(doc, "Colocar {}".format(apto_key))
    t.Start()
    
    ok_fb_wall = ok_fb_ceil = ok_lb = skipped = 0
    
    for dev in devices:
        fam = dev["familia_revit"]
        typ = dev["tipo_revit"]
        rot_json = dev.get("rotacion_grados", 0) % 360
        
        s = find_sym(fam, typ)
        if not s:
            skipped += 1
            continue
        
        x = dev["posicion_revit_m"]["x"] / FT_TO_M  # ya en metros, convertir a pies
        y = dev["posicion_revit_m"]["y"] / FT_TO_M
        
        pt_xy = XYZ(x, y, 0)
        placement = get_placement_type(fam)
        
        if placement == "FACE_CEILING":
            z = ceiling_z_global  # Z no cambia con offset XY
        else:
            z = ALTURAS.get(fam, nivel5_z + m_a_ft(0.30))
        pt = XYZ(x, y, z)
        
        try:
            if not s.IsActive: s.Activate()
            inst = None
            
            if placement == "FACE_WALL":
                result = find_wall_ref(pt_xy)
                if not result:
                    skipped += 1
                    continue
                w_id, ref, normal, wall_dir, dist = result
                place_dir = calc_place_dir(normal, rot_json)
                inst = doc.Create.NewFamilyInstance(ref, pt, place_dir, s)
                ok_fb_wall += 1
            
            elif placement == "FACE_CEILING":
                # Usar bounds LOCAL para validar
                if not point_in_bounds(x, y, bounds_local):
                    skipped += 1
                    continue
                z_ceiling = ceiling_z_global
                if fam == "M_ClimatizacionV":
                    z_ceiling -= 0.65
                pt_ceiling = XYZ(x, y, z_ceiling)
                place_dir = ceiling_wall_dir
                if rot_json != 0:
                    angle = rot_json * math.pi / 180.0
                    cos_a = math.cos(angle)
                    sin_a = math.sin(angle)
                    nx = ceiling_wall_dir.X * cos_a - ceiling_wall_dir.Y * sin_a
                    ny = ceiling_wall_dir.X * sin_a + ceiling_wall_dir.Y * cos_a
                    place_dir = XYZ(nx, ny, 0)
                inst = doc.Create.NewFamilyInstance(f02_ceiling_face, pt_ceiling, place_dir, s)
                ok_fb_ceil += 1
            
            else:  # LEVEL
                pt_level = XYZ(x, y, z)
                inst = doc.Create.NewFamilyInstance(pt_level, s, PISO5_LEVEL, StructuralType.NonStructural)
                ok_lb += 1
                
                fpt = PLACEMENT_TYPE.get(fam)
                fpt_str = str(fpt) if fpt else ""
                if fpt_str == "OneLevelBasedHosted" and fam in ["M_Interruptores", "EA", "M_Toma-Rango", "M_Toma - 220V"]:
                    try:
                        result = find_wall_ref(pt_xy)
                        if result:
                            w_id, ref, normal, wall_dir, dist = result
                            host_param = inst.get_Parameter(BuiltInParameter.HOST_ID_PARAM)
                            if host_param and not host_param.IsReadOnly:
                                host_param.Set(w_id)
                    except:
                        pass
                
                if rot_json != 0:
                    try:
                        rot_rad = rot_json * math.pi / 180.0
                        axis = Line.CreateBound(XYZ(x, y, nivel5_z), XYZ(x, y, nivel5_z + 10))
                        from Autodesk.Revit.DB import ElementTransformUtils
                        ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot_rad)
                    except:
                        pass
            
            # Mark ÚNICO (incluye posición)
            if inst:
                mark = "{}|{}|{}|{:.3f}_{:.3f}".format(
                    apto_key, panel_revit, fam.replace(' ', '_').replace('-', ''), x, y)
                mp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
                if mp: mp.Set(mark)
        
        except Exception as e:
            skipped += 1
            continue
    
    t.Commit()
    apto_total = ok_fb_wall + ok_fb_ceil + ok_lb
    print("  FB-Muro: {} | FB-Techo: {} | Level: {} | Total: {} | Skipped: {}".format(
        ok_fb_wall, ok_fb_ceil, ok_lb, apto_total, skipped))

print("\n=== COMPLETADO ===")