# -*- coding: utf-8 -*-
"""
replicate_F01_F02_CENTRAL_V01.py
=================================
Replica la colocación y ruteo de F01/F02 en CENTRAL-V01.rvt usando pyRevit IronPython 2.7.
Ejecutar DENTRO de Revit 2026 via pyRevit Python Shell con CENTRAL-V01.rvt abierto.

TypeIds confirmados (CENTRAL-V01):
  - Tubo with Fittings = 112216
  - Tubo without Fittings = 112217
  - Tubo Comunicaciones = 5508657
"""

from __future__ import print_function

import json
import os
import math
import time
import sys
from collections import defaultdict

try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
        Plane, SketchPlane, LocationCurve, LocationPoint,
        Conduit, ConduitType, ConduitFitting, ConduitRun,
        Electrical, Mechanical, Structure,
        ElementTransformUtils,
    )
    from Autodesk.Revit.DB.Structure import StructuralType
    from System import Int64
except Exception as e:
    print("[ERROR] Imports fallaron. Ejecuta dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(e))
    revit = None

# Configuración
REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")

# TypeIds confirmados para CENTRAL-V01
CONDUIT_TYPE_IDS = {
    "Tubo with Fittings": 112216,
    "Tubo without Fittings": 112217,
    "Tubo Comunicaciones": 5508657,
}

# Familias que son WorkPlaneBased (face-based en muro)
FAMILIAS_MURO_FACE = {"M_Toma doble", "M_Comunicaciones"}

# Familias de techo (face-based)
FAMILIAS_TECHO_FACE = {"M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"}

# Panel name mapping
PANEL_NAME_MAP = {"F01": "TF 01", "F02": "TF 02"}

# Offsets precalculados (mm) - anclados a Panel Name
OFFSETS = {
    "F01": (13990.9, 8010.6),
    "F02": (14037.4, 9654.7),
}

# Nivel Piso 5 en CENTRAL-V01
NIVEL_PISO5_ELEV_M = 13.22

# Tolerancias
TOL_MURO = 0.61  # 2 ft = 610 mm
TOL_TECHO_BBOX = 0.05

# Delta de rotación por familia (norma COL: +90° para placas horizontales)
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
    "M_Caja de conexiones hexagonal": 90.0,
    "M_Toma de telefono - Datos": 90.0,
}

def _safe_int(val):
    """Convierte ElementId o int a int seguro."""
    try:
        return int(val)
    except Exception:
        try:
            return val.IntegerValue
        except Exception:
            return 0

def _load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def _collect_family_symbols(doc):
    """Devuelve dict {(family_name, type_name): FamilySymbol} y {type_id: FamilySymbol}."""
    symbols = {}
    symbols_by_id = {}
    for sym in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
        try:
            fam = sym.FamilyName
            tname = sym.Name
            symbols[(fam, tname)] = sym
            symbols_by_id[_safe_int(sym.Id)] = sym
        except Exception:
            continue
    return symbols, symbols_by_id

def _collect_walls(doc):
    return list(FilteredElementCollector(doc).OfClass(Wall).ToElements())

def _collect_ceilings(doc):
    return list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Ceilings)
        .WhereElementIsNotElementType()
        .ToElements()
    )

def _collect_panels(doc):
    """Devuelve dict {panelName: {id, x_mm, y_mm, z_mm, levelId, elementId}}."""
    panels = {}
    for elem in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType():
        fi = elem
        if not isinstance(fi, FamilyInstance):
            continue
        loc = fi.Location
        if not isinstance(loc, LocationPoint):
            continue
        pt = loc.Point
        pname = ""
        param = fi.LookupParameter("Panel Name")
        if param and param.HasValue:
            pname = param.AsString() or ""
        if pname:
            panels[pname] = {
                "id": _safe_int(fi.Id),
                "x_mm": pt.X * 304.8,
                "y_mm": pt.Y * 304.8,
                "z_mm": pt.Z * 304.8,
                "levelId": _safe_int(fi.LevelId),
                "elementId": _safe_int(fi.Id),
            }
    return panels

def _find_symbol(family_symbols, family_name, type_name=None):
    if type_name:
        key = (family_name, type_name)
        if key in family_symbols:
            return family_symbols[key], type_name
    for (fam, sym_name), symbol in family_symbols.items():
        if fam == family_name:
            return symbol, sym_name
    fn_lower = family_name.lower()
    for (fam, sym_name), symbol in family_symbols.items():
        if fam.lower() == fn_lower:
            return symbol, sym_name
    return None, None

def _find_wall_at(walls, x, y, tolerance=TOL_MURO):
    best = None
    best_dist = tolerance
    for wall in walls:
        loc = wall.Location
        if not isinstance(loc, LocationCurve):
            continue
        curve = loc.Curve
        try:
            result = curve.Project(XYZ(x, y, 0))
            if result and result.Distance is not None and result.Distance < best_dist:
                best_dist = result.Distance
                best = wall
        except Exception:
            continue
    return best

def _get_wall_face_facing_point(wall, x, y, z):
    options = Options()
    options.ComputeReferences = True
    options.IncludeNonVisibleObjects = True
    geom = wall.get_Geometry(options)
    if geom is None:
        return None, None, None
    loc = wall.Location
    if not isinstance(loc, LocationCurve):
        return None, None, None
    curve = loc.Curve
    try:
        proj_result = curve.Project(XYZ(x, y, 0))
        if proj_result is None:
            return None, None, None
        nearest = proj_result.XYZPoint
    except Exception:
        return None, None, None

    perp = XYZ(x - nearest.X, y - nearest.Y, 0)
    perp_len = perp.GetLength()
    if perp_len < 0.001:
        try:
            direction = curve.Direction
            perp = XYZ(direction.Y, -direction.X, 0)
            perp_len = perp.GetLength()
        except Exception:
            return None, None, None
    perp_norm = XYZ(perp.X / perp_len, perp.Y / perp_len, 0)

    for obj in geom:
        if not isinstance(obj, Solid):
            continue
        if obj.Faces.Size == 0:
            continue
        for face in obj.Faces:
            try:
                if abs(face.ComputeNormal(UV(0.5, 0.5)).Z) > 0.1:
                    continue
                bbox = face.GetBoundingBox()
                u_c = (bbox.Min.U + bbox.Max.U) / 2.0
                v_c = (bbox.Min.V + bbox.Max.V) / 2.0
                normal = face.ComputeNormal(UV(u_c, v_c))
                if normal.X * perp_norm.X + normal.Y * perp_norm.Y > 0.5:
                    return face.Reference, face, normal
            except Exception:
                continue
    return None, None, None

def _get_wall_base_elevation(doc, wall):
    try:
        bp = wall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT_PARAM)
        if bp is None:
            bp = wall.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if bp is None:
            return 0.0
        level_id = bp.AsElementId()
        if level_id is None or level_id == ElementId.InvalidElementId:
            return 0.0
        level = doc.GetElement(level_id)
        if level is None or not isinstance(level, Level):
            return 0.0
        return level.Elevation
    except Exception:
        return 0.0

def _calc_rotation_from_normal(normal):
    angle_rad = math.atan2(normal.Y, normal.X)
    angle_deg = math.degrees(angle_rad)
    rounded = int(round(angle_deg / 90.0) * 90)
    return rounded % 360

def _find_ceiling_at(ceilings, x, y):
    best = None
    best_area = float('inf')
    options = Options()
    options.ComputeReferences = False
    for ceiling in ceilings:
        try:
            geom = ceiling.get_Geometry(options)
            if geom is None:
                continue
            for obj in geom:
                if not isinstance(obj, Solid):
                    continue
                for face in obj.Faces:
                    try:
                        result = face.Project(XYZ(x, y, 0))
                        if result is None:
                            continue
                        uv = result.UVPoint
                        bbox = face.GetBoundingBox()
                        if bbox.Min.U <= uv.U <= bbox.Max.U and bbox.Min.V <= uv.V <= bbox.Max.V:
                            area = face.Area
                            if area is not None and area < best_area:
                                best_area = area
                                best = ceiling
                            break
                    except Exception:
                        continue
        except Exception:
            continue
    return best

def _get_conduit_type(doc, tipo_conduit, diametro_pulg):
    """Obtiene el ConduitType adecuado según tipo y diámetro."""
    # Primero intentar por TypeId conocido
    if tipo_conduit in CONDUIT_TYPE_IDS:
        type_id = ElementId(Int64(CONDUIT_TYPE_IDS[tipo_conduit]))
        ct = doc.GetElement(type_id)
        if ct and isinstance(ct, ConduitType):
            return ct

    # Buscar por nombre y diámetro
    for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsElementType().ToElements():
        try:
            if _clean(fs.Name) == tipo_conduit or _clean(fs.FamilyName) == tipo_conduit:
                p_diam = fs.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
                if p_diam and p_diam.HasValue and diametro_pulg:
                    diam = round(p_diam.AsDouble() * 0.3048 * 39.3701, 2)
                    if abs(diam - diametro_pulg) < 0.05:
                        return fs
                elif not diametro_pulg:
                    return fs
        except Exception:
            continue

    # Fallback: primer tipo disponible
    for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsElementType().ToElements():
        return fs

    return None

def _get_fitting_type(doc, tipo_fitting="Estándar"):
    """Obtiene un tipo de fitting disponible."""
    for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ConduitFitting).WhereElementIsElementType().ToElements():
        try:
            if _clean(fs.Name) == tipo_fitting or tipo_fitting.lower() in _clean(fs.Name).lower():
                return fs
        except Exception:
            continue
    # Fallback
    for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ConduitFitting).WhereElementIsElementType().ToElements():
        return fs
    return None

def _place_on_wall_face(doc, dev, sym, x_mm, y_mm, z_abs_mm, walls):
    """Face-based placement en muro."""
    if not sym.IsActive:
        sym.Activate()

    wall = _find_wall_at(walls, x_mm/304.8, y_mm/304.8)
    if wall is None:
        return {"status": "error", "error": "No wall within {:.2f}m".format(TOL_MURO)}

    face_ref, face, normal = _get_wall_face_facing_point(wall, x_mm/304.8, y_mm/304.8, z_abs_mm/304.8)
    if face_ref is None:
        return {"status": "error", "error": "No face on wall facing point", "wall_id": _safe_int(wall.Id)}

    try:
        proj = face.Project(XYZ(x_mm/304.8, y_mm/304.8, z_abs_mm/304.8))
        if proj is None or proj.XYZPoint is None:
            return {"status": "error", "error": "Face.Project returned None", "wall_id": _safe_int(wall.Id)}
        projected_pt = proj.XYZPoint
    except Exception as e:
        return {"status": "error", "error": "Face.Project failed: {}".format(e), "wall_id": _safe_int(wall.Id)}

    wall_base_elev = _get_wall_base_elevation(doc, wall)
    elevation_rel = (z_abs_mm/304.8) - wall_base_elev
    placement_pt = XYZ(projected_pt.X, projected_pt.Y, elevation_rel)

    direction = XYZ.BasisZ  # Fix P6: vertical direction

    try:
        new_inst = doc.Create.NewFamilyInstance(face_ref, placement_pt, direction, sym)
    except Exception as e:
        return {"status": "error", "error": "NewFamilyInstance face failed: {}".format(e), "wall_id": _safe_int(wall.Id)}

    # Rotación: normal del muro + 90° (norma COL)
    rot_deg = _calc_rotation_from_normal(normal)
    rot_deg = (rot_deg + 90) % 360
    if abs(rot_deg) > 0.1:
        try:
            loc = new_inst.Location
            if isinstance(loc, LocationPoint):
                axis = Line.CreateBound(placement_pt, XYZ(placement_pt.X, placement_pt.Y, placement_pt.Z + 1.0))
                loc.Rotate(axis, math.radians(rot_deg))
        except Exception as e:
            return {"status": "ok_with_warning", "element_id": _safe_int(new_inst.Id),
                    "wall_id": _safe_int(wall.Id), "warning": "Rotate failed: {}".format(e)}

    return {"status": "ok", "element_id": _safe_int(new_inst.Id), "wall_id": _safe_int(wall.Id),
            "placement_pt": [placement_pt.X * 304.8, placement_pt.Y * 304.8, placement_pt.Z * 304.8],
            "rotation_deg": rot_deg}

def _place_on_ceiling_face(doc, dev, sym, x_mm, y_mm, z_abs_mm, ceilings):
    """Face-based placement en techo."""
    if not sym.IsActive:
        sym.Activate()

    ceiling = _find_ceiling_at(ceilings, x_mm/304.8, y_mm/304.8)
    if ceiling is None:
        return {"status": "error", "error": "No ceiling found at ({:.3f}, {:.3f})".format(x_mm/304.8, y_mm/304.8)}

    placement_pt = XYZ(x_mm/304.8, y_mm/304.8, z_abs_mm/304.8)

    try:
        new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, ceiling, StructuralType.NonStructural)
    except Exception as e_hosted:
        try:
            new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, StructuralType.NonStructural)
        except Exception as e_free:
            return {"status": "error", "error": "Ceiling place failed: {} | fallback: {}".format(e_hosted, e_free),
                    "ceiling_id": _safe_int(ceiling.Id)}

    return {"status": "ok", "element_id": _safe_int(new_inst.Id), "ceiling_id": _safe_int(ceiling.Id),
            "placement_pt": [x_mm, y_mm, z_abs_mm], "rotation_deg": 0}

def _place_level_based(doc, dev, sym, x_mm, y_mm, alt_mm, level_id, rot_final):
    """Level-based placement."""
    if not sym.IsActive:
        sym.Activate()

    level = doc.GetElement(ElementId(Int64(level_id)))
    if level is None:
        return {"status": "error", "error": "Level not found: {}".format(level_id)}

    pt = XYZ(x_mm/304.8, y_mm/304.8, alt_mm/304.8)  # Z relativo al nivel

    try:
        new_inst = doc.Create.NewFamilyInstance(pt, sym, level, StructuralType.NonStructural)
    except Exception as e:
        return {"status": "error", "error": "NewFamilyInstance level failed: {}".format(e)}

    # Rotación: rot_final + 90° (norma COL)
    rot_deg = (rot_final + 90) % 360
    if abs(rot_deg) > 0.1:
        try:
            loc = new_inst.Location
            if isinstance(loc, LocationPoint):
                axis = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1.0))
                loc.Rotate(axis, math.radians(rot_deg))
        except Exception as e:
            return {"status": "ok_with_warning", "element_id": _safe_int(new_inst.Id), "warning": "Rotate failed: {}".format(e)}

    # Elevación via parámetro
    if alt_mm > 0:
        try:
            for p in new_inst.Parameters:
                pname = p.Definition.Name
                if pname in ("Elevation", "Offset") and not p.IsReadOnly:
                    p.Set(alt_mm / 304.8)
                    break
        except Exception:
            pass

    return {"status": "ok", "element_id": _safe_int(new_inst.Id), "level_id": level_id,
            "placement_pt": [x_mm, y_mm, alt_mm + level.Elevation * 304.8],
            "rotation_deg": rot_deg}

def crear_conduits(doc, ruteo_data, conduit_type_map):
    """Crea los conduits y fittings basados en el JSON de ruteo."""
    print("\n" + "="*60)
    print("CREANDO CONDUITS Y FITTINGS")
    print("="*60)

    results = {"conduits": [], "fittings": [], "errors": []}

    # Crear mapa de ID viejo -> nuevo para conectar
    id_map = {}

    # 1. Crear conduits
    for c in ruteo_data["conduits_F01_F02"]:
        try:
            tipo = c.get("tipo", "Tubo without Fittings")
            diametro = c.get("diametro_pulg")
            conduit_type = _get_conduit_type(doc, tipo, diametro)

            if not conduit_type:
                results["errors"].append("No conduit type for: {} Ø{}".format(tipo, diametro))
                continue

            pt_start = XYZ(c["inicio"]["x_m"]/0.3048, c["inicio"]["y_m"]/0.3048, c["inicio"]["z_m"]/0.3048)
            pt_end = XYZ(c["fin"]["x_m"]/0.3048, c["fin"]["y_m"]/0.3048, c["fin"]["z_m"]/0.3048)

            line = Line.CreateBound(pt_start, pt_end)
            conduit = doc.Create.NewConduit(conduit_type, line)

            new_id = _safe_int(conduit.Id)
            old_id = c["id"]
            id_map[old_id] = new_id
            results["conduits"].append({"old_id": old_id, "new_id": new_id, "tipo": tipo, "diametro": diametro})

        except Exception as e:
            results["errors"].append("Conduit {}: {}".format(c.get("id"), e))

    print("  Conduits creados: {}".format(len(results["conduits"])))

    # 2. Crear fittings en las conexiones
    fitting_type = _get_fitting_type(doc)
    if fitting_type:
        for f in ruteo_data["fittings_F01_F02"]:
            try:
                conectores = f.get("conectores", [])
                # Mapear conectores viejos a nuevos
                new_connectors = []
                for old_cid in conectores:
                    if old_cid in id_map:
                        new_connectors.append(id_map[old_cid])

                if len(new_connectors) >= 2:
                    # Crear fitting en la posición
                    pos = f.get("posicion", {})
                    pt = XYZ(pos["x_m"]/0.3048, pos["y_m"]/0.3048, pos["z_m"]/0.3048)

                    # Intentar crear fitting conectando los conduits
                    # En Revit API, los fittings se crean automáticamente al conectar conduits
                    # Aquí solo registramos la posición para referencia
                    results["fittings"].append({
                        "old_id": f["id"],
                        "posicion": pos,
                        "conectores_nuevos": new_connectors,
                        "tipo": f.get("tipo")
                    })
            except Exception as e:
                results["errors"].append("Fitting {}: {}".format(f.get("id"), e))

    print("  Fittings registrados: {}".format(len(results["fittings"])))
    if results["errors"]:
        print("  Errores: {}".format(len(results["errors"])))
        for err in results["errors"][:5]:
            print("    - {}".format(err))

    return results

def replicar_apartamento(doc, apartamento, inventario_data, ruteo_data, report_path=None):
    """Réplica un apartamento completo (dispositivos + ruteo)."""
    print("\n" + "="*60)
    print("REPLICANDO {} EN CENTRAL-V01".format(apartamento))
    print("="*60)

    if revit is None:
        print("[ERROR] Sin acceso a Revit. Ejecuta via pyRevit Python Shell.")
        return None

    # Panel objetivo
    target_panel_name = PANEL_NAME_MAP[apartamento]
    panels = _collect_panels(doc)
    panel_obj = panels.get(target_panel_name)
    if not panel_obj:
        print("[ERROR] Panel '{}' no encontrado en CENTRAL-V01".format(target_panel_name))
        return None
    print("[INFO] Panel objetivo: {} @ ({:.1f}, {:.1f}) mm | LevelId: {}".format(
        target_panel_name, panel_obj["x_mm"], panel_obj["y_mm"], panel_obj["levelId"]))

    offset_x, offset_y = OFFSETS[apartamento]
    print("[INFO] Offset {}: ({:.1f}, {:.1f}) mm".format(apartamento, offset_x, offset_y))

    level_id = panel_obj["levelId"]
    nivel_elevacion = NIVEL_PISO5_ELEV_M

    # Pre-cargar datos
    print("[INFO] Cargando FamilySymbols...")
    family_symbols, symbols_by_id = _collect_family_symbols(doc)
    print("[INFO]   {} símbolos".format(len(family_symbols)))

    print("[INFO] Cargando Walls...")
    walls = _collect_walls(doc)
    print("[INFO]   {} muros".format(len(walls)))

    print("[INFO] Cargando Ceilings...")
    ceilings = _collect_ceilings(doc)
    print("[INFO]   {} cielorrasos".format(len(ceilings)))

    # Filtrar dispositivos de este apartamento
    dispositivos = [d for d in inventario_data["dispositivos"] if d["apartamento"] == apartamento]
    print("[INFO] Dispositivos a replicar: {}".format(len(dispositivos)))

    # Mapeo de type_ids de conduit de V02-f a CENTRAL-V01
    conduit_type_map = {}
    for ct in inventario_data.get("conduit_types", []):
        conduit_type_map[ct["type_id"]] = ct

    results = {"dispositivos": [], "ruteo": None}

    # Transacción única para todo
    with revit.Transaction("Replica {} F01/F02".format(apartamento)):
        # 1. Colocar dispositivos
        print("\n[INFO] Colocando dispositivos...")
        for i, d in enumerate(dispositivos, 1):
            fam = d["familia_revit"]
            tip = d["tipo_revit"]
            rot = d["rotacion_grados"]
            alt_mm = int(d["altura_local_m"] * 1000)

            # Coordenadas con offset
            x_mm = d["posicion"]["x_m"] * 1000 + offset_x
            y_mm = d["posicion"]["y_m"] * 1000 + offset_y
            z_abs_mm = (nivel_elevacion + d["altura_local_m"]) * 1000

            print("[{}/{}] {} {} -> ".format(i, len(dispositivos), d["element_id"], d["nombre_dxf"] if "nombre_dxf" in d else fam))

            sym, resolved_type = _find_symbol(family_symbols, fam, tip)
            if sym is None:
                r = dict(d)
                r["status"] = "error"
                r["error"] = "Symbol not found: {} / {}".format(fam, tip)
                results["dispositivos"].append(r)
                print("        ERROR: Symbol not found")
                continue

            # Decidir estrategia por familia
            if fam in FAMILIAS_MURO_FACE:
                result = _place_on_wall_face(doc, d, sym, x_mm, y_mm, z_abs_mm, walls)
            elif fam in FAMILIAS_TECHO_FACE:
                result = _place_on_ceiling_face(doc, d, sym, x_mm, y_mm, z_abs_mm, ceilings)
            else:
                result = _place_level_based(doc, d, sym, x_mm, y_mm, alt_mm, level_id, rot)

            r = dict(d)
            r.update(result)
            results["dispositivos"].append(r)
            status = result.get("status", "unknown")
            if status == "ok":
                print("        OK (elem={}, rot={}°)".format(result.get("element_id"), result.get("rotation_deg", 0)))
            elif status == "ok_with_warning":
                print("        OK-WARN (elem={}, warn={})".format(result.get("element_id"), result.get("warning", "")[:60]))
            else:
                print("        ERROR: {}".format(result.get("error", "?")[:100]))

        # 2. Crear ruteo de conduits
        print("\n[INFO] Creando ruteo de conduits...")
        results["ruteo"] = crear_conduits(doc, ruteo_data, conduit_type_map)

    # Reporte
    if report_path:
        try:
            report_dir = os.path.dirname(report_path)
            if report_dir and not os.path.exists(report_dir):
                os.makedirs(report_dir)

            ok = sum(1 for r in results["dispositivos"] if r.get("status") == "ok")
            okw = sum(1 for r in results["dispositivos"] if r.get("status") == "ok_with_warning")
            err = sum(1 for r in results["dispositivos"] if r.get("status") == "error")

            report = {
                "version": "pyRevit_replica_v01",
                "document": doc.Title,
                "apartamento": apartamento,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "panel": target_panel_name,
                "offset_mm": {"x": offset_x, "y": offset_y},
                "dispositivos": {
                    "total": len(results["dispositivos"]),
                    "ok": ok, "ok_with_warning": okw, "errors": err,
                    "results": results["dispositivos"]
                },
                "ruteo": results["ruteo"]
            }
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print("\n[OK] Reporte: {}".format(report_path))
        except Exception as e:
            print("[WARN] No pude escribir reporte: {}".format(e))

    # Resumen
    print("\n" + "="*60)
    print("  RESUMEN {} REPLICA".format(apartamento))
    print("="*60)
    ok = sum(1 for r in results["dispositivos"] if r.get("status") == "ok")
    okw = sum(1 for r in results["dispositivos"] if r.get("status") == "ok_with_warning")
    err = sum(1 for r in results["dispositivos"] if r.get("status") == "error")
    total = len(results["dispositivos"])
    print("  Dispositivos - Total: {}, OK: {}, OK+WARN: {}, Errores: {}".format(total, ok, okw, err))
    if total > 0:
        print("  Tasa OK: {:.1f}%".format((ok + okw) * 100.0 / total))
    print("  Conduits creados: {}".format(len(results["ruteo"]["conduits"])))
    print("  Fittings: {}".format(len(results["ruteo"]["fittings"])))
    print("="*60)

    return results

def main():
    if revit is None:
        print("[ERROR] Sin acceso a Revit. Ejecuta via pyRevit Python Shell.")
        return

    doc = revit.doc
    print("="*70)
    print("REPLICA F01/F02 -> CENTRAL-V01")
    print("Documento: {}".format(doc.Title))
    print("="*70)

    if "CENTRAL-V01" not in doc.Title:
        print("[ERROR] Documento activo no es CENTRAL-V01: {}".format(doc.Title))
        return

    # Cargar datos exportados de V02-f
    # Buscar el directorio de exportación más reciente
    exports_base = os.path.join(DATA_DIR, "exports")
    if not os.path.exists(exports_base):
        print("[ERROR] No hay directorio de exports: {}".format(exports_base))
        return

    export_dirs = [d for d in os.listdir(exports_base) if d.startswith("V02f_F01_F02_")]
    if not export_dirs:
        print("[ERROR] No hay exports de V02f_F01_F02 en {}".format(exports_base))
        return

    export_dirs.sort(reverse=True)
    latest_export = os.path.join(exports_base, export_dirs[0])
    print("[INFO] Usando export: {}".format(latest_export))

    inv_file = None
    rut_file = None
    for f in os.listdir(latest_export):
        if f.startswith("inventario_F01_F02_"):
            inv_file = os.path.join(latest_export, f)
        elif f.startswith("ruteo_conduits_F01_F02_"):
            rut_file = os.path.join(latest_export, f)

    if not inv_file or not rut_file:
        print("[ERROR] Archivos de export no encontrados")
        return

    print("[INFO] Cargando inventario: {}".format(inv_file))
    inventario_data = _load_json(inv_file)

    print("[INFO] Cargando ruteo: {}".format(rut_file))
    ruteo_data = _load_json(rut_file)

    # Directorio de reportes
    report_dir = os.path.join(DATA_DIR, "reports", "replica_F01_F02_{}".format(time.strftime("%Y%m%d_%H%M%S")))
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)

    # Replicar F01
    report_f01 = os.path.join(report_dir, "replica_F01_{}.json".format(time.strftime("%Y%m%d_%H%M%S")))
    replicar_apartamento(doc, "F01", inventario_data, ruteo_data, report_f01)

    # Replicar F02
    report_f02 = os.path.join(report_dir, "replica_F02_{}.json".format(time.strftime("%Y%m%d_%H%M%S")))
    replicar_apartamento(doc, "F02", inventario_data, ruteo_data, report_f02)

    print("\n" + "="*70)
    print("REPLICACIÓN COMPLETA")
    print("Reportes en: {}".format(report_dir))
    print("="*70)

if __name__ == "__main__":
    main()