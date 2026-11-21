# -*- coding: utf-8 -*-
"""
RE6_TEST_UNO_v01.py - Test de colocación para UN apartamento (B15)
"""

from __future__ import print_function

import json
import os
import math
import time
import sys

try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
        Plane, SketchPlane, LocationCurve, LocationPoint,
        Electrical, Mechanical, Structure,
        ElementTransformUtils,
    )
    try:
        from Autodesk.Revit.DB.Electrical import Conduit, ConduitType, ConduitRun
    except ImportError:
        Conduit = ConduitType = ConduitRun = None
    from Autodesk.Revit.DB.Structure import StructuralType
    from System import Int64
except Exception as e:
    print("[ERROR] Imports: {}".format(e))
    revit = None

REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")
MAESTRO_PATH = os.path.join(DATA_DIR, "maestro_colocacion_piso5.json")

# Solo B15 para test
TEST_APARTAMENTO = "B15"

FAMILIAS_MURO_FACE = {"M_Toma doble", "M_Comunicaciones"}
FAMILIAS_TECHO_FACE = {"M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"}
NIVEL_PISO5_ELEV_M = 13.22
TOL_MURO = 0.61

def _safe_int(val):
    try: return int(val)
    except:
        try: return val.IntegerValue
        except: return 0

def _load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def _collect_family_symbols(doc):
    symbols = {}
    for sym in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
        try:
            symbols[(sym.FamilyName, sym.Name)] = sym
        except: pass
    return symbols

def _collect_walls(doc):
    return list(FilteredElementCollector(doc).OfClass(Wall).ToElements())

def _collect_ceilings(doc):
    return list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType().ToElements())

def _collect_panels(doc):
    panels = {}
    for elem in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType():
        fi = elem
        if not isinstance(fi, FamilyInstance): continue
        loc = fi.Location
        if not isinstance(loc, LocationPoint): continue
        pt = loc.Point
        pname = ""
        param = fi.LookupParameter("Panel Name")
        if param and param.HasValue: pname = param.AsString() or ""
        if pname:
            panels[pname] = {"levelId": _safe_int(fi.LevelId)}
    return panels

def _find_symbol(family_symbols, family_name, type_name=None):
    if type_name:
        key = (family_name, type_name)
        if key in family_symbols: return family_symbols[key], type_name
    for (fam, sym_name), symbol in family_symbols.items():
        if fam == family_name: return symbol, sym_name
    fn_lower = family_name.lower()
    for (fam, sym_name), symbol in family_symbols.items():
        if fam.lower() == fn_lower: return symbol, sym_name
    return None, None

def _find_wall_at(walls, x, y, tolerance=TOL_MURO):
    best = None
    best_dist = tolerance
    for wall in walls:
        loc = wall.Location
        if not isinstance(loc, LocationCurve): continue
        curve = loc.Curve
        try:
            result = curve.Project(XYZ(x, y, 0))
            if result and result.Distance is not None and result.Distance < best_dist:
                best_dist = result.Distance
                best = wall
        except: continue
    return best

def _get_wall_face_facing_point(wall, x, y, z):
    options = Options()
    options.ComputeReferences = True
    options.IncludeNonVisibleObjects = True
    geom = wall.get_Geometry(options)
    if geom is None: return None, None, None
    loc = wall.Location
    if not isinstance(loc, LocationCurve): return None, None, None
    curve = loc.Curve
    try:
        proj_result = curve.Project(XYZ(x, y, 0))
        if proj_result is None: return None, None, None
        nearest = proj_result.XYZPoint
    except: return None, None, None
    perp = XYZ(x - nearest.X, y - nearest.Y, 0)
    perp_len = perp.GetLength()
    if perp_len < 0.001:
        try:
            direction = curve.Direction
            perp = XYZ(direction.Y, -direction.X, 0)
            perp_len = perp.GetLength()
        except: return None, None, None
    perp_norm = XYZ(perp.X / perp_len, perp.Y / perp_len, 0)
    for obj in geom:
        if not isinstance(obj, Solid): continue
        if obj.Faces.Size == 0: continue
        for face in obj.Faces:
            try:
                if abs(face.ComputeNormal(UV(0.5, 0.5)).Z) > 0.1: continue
                bbox = face.GetBoundingBox()
                u_c = (bbox.Min.U + bbox.Max.U) / 2.0
                v_c = (bbox.Min.V + bbox.Max.V) / 2.0
                normal = face.ComputeNormal(UV(u_c, v_c))
                if normal.X * perp_norm.X + normal.Y * perp_norm.Y > 0.5:
                    return face.Reference, face, normal
            except: continue
    return None, None, None

def _get_wall_base_elevation(doc, wall):
    try:
        bp = wall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT_PARAM)
        if bp is None: bp = wall.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if bp is None: return 0.0
        level_id = bp.AsElementId()
        if level_id is None or level_id == ElementId.InvalidElementId: return 0.0
        level = doc.GetElement(level_id)
        if level is None or not isinstance(level, Level): return 0.0
        return level.Elevation
    except: return 0.0

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
            if geom is None: continue
            for obj in geom:
                if not isinstance(obj, Solid): continue
                for face in obj.Faces:
                    try:
                        result = face.Project(XYZ(x, y, 0))
                        if result is None: continue
                        uv = result.UVPoint
                        bbox = face.GetBoundingBox()
                        if bbox.Min.U <= uv.U <= bbox.Max.U and bbox.Min.V <= uv.V <= bbox.Max.V:
                            area = face.Area
                            if area is not None and area < best_area:
                                best_area = area
                                best = ceiling
                            break
                    except: continue
        except: continue
    return best

def _place_on_wall_face(doc, dev, sym, x_m, y_m, z_abs_m, walls):
    if not sym.IsActive: sym.Activate()
    wall = _find_wall_at(walls, x_m, y_m)
    if wall is None: return {"status": "error", "error": "No wall"}
    face_ref, face, normal = _get_wall_face_facing_point(wall, x_m, y_m, z_abs_m)
    if face_ref is None: return {"status": "error", "error": "No face", "wall_id": _safe_int(wall.Id)}
    try:
        proj = face.Project(XYZ(x_m, y_m, z_abs_m))
        if proj is None or proj.XYZPoint is None: return {"status": "error", "error": "Project None", "wall_id": _safe_int(wall.Id)}
        projected_pt = proj.XYZPoint
    except Exception as e: return {"status": "error", "error": "Project failed: {}".format(e), "wall_id": _safe_int(wall.Id)}
    wall_base_elev = _get_wall_base_elevation(doc, wall)
    elevation_rel = z_abs_m - wall_base_elev
    placement_pt = XYZ(projected_pt.X, projected_pt.Y, elevation_rel)
    direction = XYZ.BasisZ
    try:
        new_inst = doc.Create.NewFamilyInstance(face_ref, placement_pt, direction, sym)
    except Exception as e: return {"status": "error", "error": "NewFamilyInstance failed: {}".format(e), "wall_id": _safe_int(wall.Id)}
    rot_deg = _calc_rotation_from_normal(normal)
    rot_deg = (rot_deg + 90) % 360
    if abs(rot_deg) > 0.1:
        try:
            loc = new_inst.Location
            if isinstance(loc, LocationPoint):
                axis = Line.CreateBound(placement_pt, XYZ(placement_pt.X, placement_pt.Y, placement_pt.Z + 1.0))
                loc.Rotate(axis, math.radians(rot_deg))
        except Exception as e: return {"status": "ok_with_warning", "element_id": _safe_int(new_inst.Id), "wall_id": _safe_int(wall.Id), "warning": "Rotate: {}".format(e)}
    return {"status": "ok", "element_id": _safe_int(new_inst.Id), "wall_id": _safe_int(wall.Id), "rotation_deg": rot_deg}

def _place_on_ceiling_face(doc, dev, sym, x_m, y_m, z_abs_m, ceilings):
    if not sym.IsActive: sym.Activate()
    ceiling = _find_ceiling_at(ceilings, x_m, y_m)
    if ceiling is None: return {"status": "error", "error": "No ceiling at ({:.3f}, {:.3f})".format(x_m, y_m)}
    placement_pt = XYZ(x_m, y_m, z_abs_m)
    try:
        new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, ceiling, StructuralType.NonStructural)
    except Exception as e_hosted:
        try: new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, StructuralType.NonStructural)
        except Exception as e_free: return {"status": "error", "error": "Ceiling place failed: {} | fallback: {}".format(e_hosted, e_free), "ceiling_id": _safe_int(ceiling.Id)}
    return {"status": "ok", "element_id": _safe_int(new_inst.Id), "ceiling_id": _safe_int(ceiling.Id), "rotation_deg": 0}

def _place_level_based(doc, dev, sym, x_m, y_m, alt_m, level_id, rot_final):
    if not sym.IsActive: sym.Activate()
    level = doc.GetElement(ElementId(Int64(level_id)))
    if level is None: return {"status": "error", "error": "Level not found: {}".format(level_id)}
    pt = XYZ(x_m, y_m, alt_m)
    try:
        new_inst = doc.Create.NewFamilyInstance(pt, sym, level, StructuralType.NonStructural)
    except Exception as e: return {"status": "error", "error": "NewFamilyInstance level failed: {}".format(e)}
    rot_deg = (rot_final + 90) % 360
    if abs(rot_deg) > 0.1:
        try:
            loc = new_inst.Location
            if isinstance(loc, LocationPoint):
                axis = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1.0))
                loc.Rotate(axis, math.radians(rot_deg))
        except Exception as e: return {"status": "ok_with_warning", "element_id": _safe_int(new_inst.Id), "warning": "Rotate: {}".format(e)}
    if alt_m > 0:
        try:
            for p in new_inst.Parameters:
                pname = p.Definition.Name
                if pname in ("Elevation", "Offset") and not p.IsReadOnly:
                    p.Set(alt_m); break
        except: pass
    return {"status": "ok", "element_id": _safe_int(new_inst.Id), "level_id": level_id, "rotation_deg": rot_deg}

def main():
    if revit is None: print("[ERROR] Sin Revit"); return
    doc = revit.doc
    if "CENTRAL-V01" not in doc.Title: print("[ERROR] No es CENTRAL-V01a: {}".format(doc.Title)); return

    print("="*60)
    print("TEST COLOCACIÓN: {}".format(TEST_APARTAMENTO))
    print("="*60)

    maestro = _load_json(MAESTRO_PATH)
    apto_data = maestro["apartamentos"].get(TEST_APARTAMENTO)
    if not apto_data: print("[ERROR] {} no en maestro".format(TEST_APARTAMENTO)); return

    print("Dispositivos: {}".format(apto_data["total_dispositivos"]))
    print("Panel: {} @ ({:.3f}, {:.3f})".format(apto_data["panel_name_revit"], apto_data["panel_revit_m"]["x"], apto_data["panel_revit_m"]["y"]))

    family_symbols = _collect_family_symbols(doc)
    print("FamilySymbols: {}".format(len(family_symbols)))
    walls = _collect_walls(doc)
    print("Walls: {}".format(len(walls)))
    ceilings = _collect_ceilings(doc)
    print("Ceilings: {}".format(len(ceilings)))
    panels = _collect_panels(doc)
    print("Panels: {}".format(len(panels)))
    level_id = panels.get(apto_data["panel_name_revit"], {}).get("levelId", 0)
    print("LevelId: {}".format(level_id))

    ok = okw = err = 0
    with revit.Transaction("Test {}".format(TEST_APARTAMENTO)):
        for i, dev in enumerate(apto_data["dispositivos"], 1):
            fam = dev["familia_revit"]; tip = dev["tipo_revit"]; rot = dev["rotacion_grados"]
            alt_m = dev["altura_local_m"]; x_m = dev["posicion_revit_m"]["x"]; y_m = dev["posicion_revit_m"]["y"]
            z_abs_m = NIVEL_PISO5_ELEV_M + alt_m
            print("[{}/{}] {} {} -> ".format(i, len(apto_data["dispositivos"]), dev.get("nombre_dxf", ""), fam), end="")
            sym, _ = _find_symbol(family_symbols, fam, tip)
            if sym is None:
                print("ERROR: Symbol not found"); err += 1; continue
            if fam in FAMILIAS_MURO_FACE: result = _place_on_wall_face(doc, dev, sym, x_m, y_m, z_abs_m, walls)
            elif fam in FAMILIAS_TECHO_FACE: result = _place_on_ceiling_face(doc, dev, sym, x_m, y_m, z_abs_m, ceilings)
            else: result = _place_level_based(doc, dev, sym, x_m, y_m, alt_m, level_id, rot)
            status = result.get("status", "unknown")
            if status == "ok": print("OK (id={}, rot={}°)".format(result.get("element_id"), result.get("rotation_deg", 0))); ok += 1
            elif status == "ok_with_warning": print("OK-WARN (id={}, warn={})".format(result.get("element_id"), result.get("warning", "")[:50])); okw += 1
            else: print("ERROR: {}".format(result.get("error", "?")[:80])); err += 1

    print("\nRESUMEN {}: OK={}, OK+WARN={}, ERROR={}".format(TEST_APARTAMENTO, ok, okw, err))

main()