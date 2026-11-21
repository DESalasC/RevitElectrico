# -*- coding: utf-8 -*-
"""
RE6_COLOCAR_TODOS_v01.py
========================
Script único data-driven para colocar TODOS los apartamentos del Piso 5 en CENTRAL-V01a.rvt.
Lee maestro_colocacion_piso5.json (generado desde STM-T5-P5_bloques_electricos.dxf - FUENTE DE VERDAD ABSOLUTA).

Ejecutar DENTRO de Revit 2026 via pyRevit Python Shell con CENTRAL-V01a.rvt abierto.

CARACTERÍSTICAS:
- Un solo script para todos los apartamentos (no 20 scripts)
- Clasificación automática por familia: face-based (muro/techo) vs level-based
- Norma COL: +90° rotación en placas horizontales (tomas, interruptores, datos)
- Offsets anclados a Panel Name (ya calculados en maestro)
- TypeIds conduit confirmados: 112216 / 112217 / 5508657
- Reporte por apartamento + consolidado con timestamp
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
        Electrical, Mechanical, Structure,
        ElementTransformUtils,
    )
    # Conduit classes - try Electrical namespace (Revit 2022+)
    try:
        from Autodesk.Revit.DB.Electrical import Conduit, ConduitType, ConduitRun
    except ImportError:
        Conduit = ConduitType = ConduitRun = None
    from Autodesk.Revit.DB.Structure import StructuralType
    from System import Int64
except Exception as e:
    print("[ERROR] Imports fallaron. Ejecuta dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(e))
    revit = None

# CONFIGURACIÓN
REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")
MAESTRO_PATH = os.path.join(DATA_DIR, "maestro_colocacion_piso5.json")

# Apartamentos a SALTAR (ya colocados y validados como referencias intocables)
SKIP_APARTAMENTOS = {"F01", "F02"}  # F01/F02 ya están en el modelo como referencia

# TypeIds confirmados para CENTRAL-V01a
CONDUIT_TYPE_IDS = {
    "Tubo with Fittings": 112216,
    "Tubo without Fittings": 112217,
    "Tubo Comunicaciones": 5508657,
}

# Familias face-based en MURO (WorkPlaneBased/OneLevelBasedHosted que funcionan en muro)
FAMILIAS_MURO_FACE = {"M_Toma doble", "M_Comunicaciones"}

# Familias face-based en TECHO
FAMILIAS_TECHO_FACE = {"M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"}

# Nivel Piso 5 en CENTRAL-V01a (elevación 13.22 m = 43.3727 ft)
NIVEL_PISO5_ELEV_M = 13.22

# Tolerancias
TOL_MURO = 0.61  # 2 ft = 610 mm
TOL_TECHO_BBOX = 0.05

# Delta de rotación por familia (norma COL: +90° para placas horizontales)
DELTA_ROT = {
    "M_Toma doble": 90.0,
    "M_Interruptores": 90.0,
    "M_Comunicaciones": 90.0,
    "M_ClimatizacionV": 0.0,
    "M_Timbre": 90.0,
    "M_Pulsador - Interruptor": 90.0,
    "M_Iluminacion": 0.0,
    "Consolidation_Point": 0.0,
    "EA": 0.0,
    "M_Caja de conexiones hexagonal": 90.0,
    "M_Toma de telefono - Datos": 90.0,
}

def _safe_int(val):
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
                "x_m": pt.X,
                "y_m": pt.Y,
                "z_m": pt.Z,
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

def _place_on_wall_face(doc, dev, sym, x_m, y_m, z_abs_m, walls):
    if not sym.IsActive:
        sym.Activate()

    wall = _find_wall_at(walls, x_m, y_m)
    if wall is None:
        return {"status": "error", "error": "No wall within {:.2f}m".format(TOL_MURO)}

    face_ref, face, normal = _get_wall_face_facing_point(wall, x_m, y_m, z_abs_m)
    if face_ref is None:
        return {"status": "error", "error": "No face on wall facing point", "wall_id": _safe_int(wall.Id)}

    try:
        proj = face.Project(XYZ(x_m, y_m, z_abs_m))
        if proj is None or proj.XYZPoint is None:
            return {"status": "error", "error": "Face.Project returned None", "wall_id": _safe_int(wall.Id)}
        projected_pt = proj.XYZPoint
    except Exception as e:
        return {"status": "error", "error": "Face.Project failed: {}".format(e), "wall_id": _safe_int(wall.Id)}

    wall_base_elev = _get_wall_base_elevation(doc, wall)
    elevation_rel = z_abs_m - wall_base_elev
    placement_pt = XYZ(projected_pt.X, projected_pt.Y, elevation_rel)
    direction = XYZ.BasisZ

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
            "placement_pt": [placement_pt.X, placement_pt.Y, placement_pt.Z],
            "rotation_deg": rot_deg}

def _place_on_ceiling_face(doc, dev, sym, x_m, y_m, z_abs_m, ceilings):
    if not sym.IsActive:
        sym.Activate()

    ceiling = _find_ceiling_at(ceilings, x_m, y_m)
    if ceiling is None:
        return {"status": "error", "error": "No ceiling found at ({:.3f}, {:.3f})".format(x_m, y_m)}

    placement_pt = XYZ(x_m, y_m, z_abs_m)

    try:
        new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, ceiling, StructuralType.NonStructural)
    except Exception as e_hosted:
        try:
            new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, StructuralType.NonStructural)
        except Exception as e_free:
            return {"status": "error", "error": "Ceiling place failed: {} | fallback: {}".format(e_hosted, e_free),
                    "ceiling_id": _safe_int(ceiling.Id)}

    return {"status": "ok", "element_id": _safe_int(new_inst.Id), "ceiling_id": _safe_int(ceiling.Id),
            "placement_pt": [x_m, y_m, z_abs_m], "rotation_deg": 0}

def _place_level_based(doc, dev, sym, x_m, y_m, alt_m, level_id, rot_final):
    if not sym.IsActive:
        sym.Activate()

    level = doc.GetElement(ElementId(Int64(level_id)))
    if level is None:
        return {"status": "error", "error": "Level not found: {}".format(level_id)}

    # Z relativo al nivel
    pt = XYZ(x_m, y_m, alt_m)

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
    if alt_m > 0:
        try:
            for p in new_inst.Parameters:
                pname = p.Definition.Name
                if pname in ("Elevation", "Offset") and not p.IsReadOnly:
                    p.Set(alt_m)
                    break
        except Exception:
            pass

    return {"status": "ok", "element_id": _safe_int(new_inst.Id), "level_id": level_id,
            "placement_pt": [x_m, y_m, alt_m + level.Elevation],
            "rotation_deg": rot_deg}

def colocar_apartamento(doc, apto_key, apto_data, family_symbols, walls, ceilings, level_id, report_dir):
    print("\n" + "="*60)
    print("COLOCANDO {} ({} dispositivos)".format(apto_key, apto_data["total_dispositivos"]))
    print("="*60)
    print("Panel Revit: {} @ ({:.3f}, {:.3f}) m".format(
        apto_data["panel_name_revit"], apto_data["panel_revit_m"]["x"], apto_data["panel_revit_m"]["y"]))

    results = {"dispositivos": []}
    panel_name = apto_data["panel_name_revit"]

    with revit.Transaction("Colocar {}".format(apto_key)):
        for i, dev in enumerate(apto_data["dispositivos"], 1):
            fam = dev["familia_revit"]
            tip = dev["tipo_revit"]
            rot = dev["rotacion_grados"]
            alt_m = dev["altura_local_m"]
            x_m = dev["posicion_revit_m"]["x"]
            y_m = dev["posicion_revit_m"]["y"]
            z_abs_m = NIVEL_PISO5_ELEV_M + alt_m

            print("[{}/{}] {} {} -> ".format(i, len(apto_data["dispositivos"]), dev.get("nombre_dxf", ""), fam), end="")

            sym, resolved_type = _find_symbol(family_symbols, fam, tip)
            if sym is None:
                r = dict(dev)
                r["status"] = "error"
                r["error"] = "Symbol not found: {} / {}".format(fam, tip)
                results["dispositivos"].append(r)
                print("ERROR: Symbol not found")
                continue

            # Decidir estrategia por familia
            if fam in FAMILIAS_MURO_FACE:
                result = _place_on_wall_face(doc, dev, sym, x_m, y_m, z_abs_m, walls)
            elif fam in FAMILIAS_TECHO_FACE:
                result = _place_on_ceiling_face(doc, dev, sym, x_m, y_m, z_abs_m, ceilings)
            else:
                result = _place_level_based(doc, dev, sym, x_m, y_m, alt_m, level_id, rot)

            r = dict(dev)
            r.update(result)
            results["dispositivos"].append(r)

            status = result.get("status", "unknown")
            if status == "ok":
                print("OK (elem={}, rot={}°)".format(result.get("element_id"), result.get("rotation_deg", 0)))
            elif status == "ok_with_warning":
                print("OK-WARN (elem={}, warn={})".format(result.get("element_id"), result.get("warning", "")[:60]))
            else:
                print("ERROR: {}".format(result.get("error", "?")[:100]))

    # Reporte individual
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, "colocacion_{}_{}.json".format(apto_key, time.strftime("%Y%m%d_%H%M%S")))
        ok = sum(1 for r in results["dispositivos"] if r.get("status") == "ok")
        okw = sum(1 for r in results["dispositivos"] if r.get("status") == "ok_with_warning")
        err = sum(1 for r in results["dispositivos"] if r.get("status") == "error")
        report = {
            "version": "RE6_COLOCAR_TODOS_v01",
            "document": doc.Title,
            "apartamento": apto_key,
            "panel_revit": panel_name,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "dispositivos": {
                "total": len(results["dispositivos"]),
                "ok": ok, "ok_with_warning": okw, "errors": err,
                "results": results["dispositivos"]
            }
        }
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print("[OK] Reporte: {}".format(report_path))

    return results

def main():
    if revit is None:
        print("[ERROR] Sin acceso a Revit. Ejecuta via pyRevit Python Shell.")
        return

    doc = revit.doc
    if "CENTRAL-V01" not in doc.Title:
        print("[ERROR] Documento activo no es CENTRAL-V01a: {}".format(doc.Title))
        return

    print("="*70)
    print("RE6_COLOCAR_TODOS_v01 - COLOCACIÓN MASIVA PISO 5")
    print("Documento: {}".format(doc.Title))
    print("Fuente: STM-T5-P5_bloques_electricos.dxf (FUENTE DE VERDAD ABSOLUTA)")
    print("="*70)

    # Cargar maestro
    if not os.path.exists(MAESTRO_PATH):
        print("[ERROR] Maestro no encontrado: {}".format(MAESTRO_PATH))
        return

    maestro = _load_json(MAESTRO_PATH)
    print("[INFO] Maestro cargado: {} apartamentos, {} dispositivos totales".format(
        len(maestro["apartamentos"]), sum(a["total_dispositivos"] for a in maestro["apartamentos"].values())))

    # Pre-cargar datos de Revit
    print("\n[INFO] Cargando FamilySymbols...")
    family_symbols, _ = _collect_family_symbols(doc)
    print("  {} símbolos".format(len(family_symbols)))

    print("[INFO] Cargando Walls...")
    walls = _collect_walls(doc)
    print("  {} muros".format(len(walls)))

    print("[INFO] Cargando Ceilings...")
    ceilings = _collect_ceilings(doc)
    print("  {} cielorrasos".format(len(ceilings)))

    print("[INFO] Cargando Paneles (para LevelId)...")
    panels = _collect_panels(doc)
    print("  {} paneles con Panel Name".format(len(panels)))

    # LevelId del Piso 5 (usar del primer panel encontrado)
    level_id = None
    for p in panels.values():
        if p["levelId"] != 0 and p["levelId"] != -1:
            level_id = p["levelId"]
            break
    if level_id is None:
        level_id = panels.get("TAB-F-01-P5", {}).get("levelId", 0)
    print("[INFO] LevelId Piso 5: {}".format(level_id))

    # Directorio de reportes
    report_dir = os.path.join(DATA_DIR, "reports", "colocacion_todos_{}".format(time.strftime("%Y%m%d_%H%M%S")))

    # Resultados consolidados
    consolidado = {
        "version": "RE6_COLOCAR_TODOS_v01",
        "document": doc.Title,
        "timestamp_inicio": time.strftime("%Y-%m-%d %H:%M:%S"),
        "apartamentos": {}
    }

    total_ok = total_okw = total_err = 0

    # Iterar apartamentos (ordenados)
    for apto_key in sorted(maestro["apartamentos"].keys()):
        apto_data = maestro["apartamentos"][apto_key]

        if apto_key in SKIP_APARTAMENTOS:
            print("\n[SKIP] {} - ya colocado (referencia intocable)".format(apto_key))
            continue

        print("\n>>> INICIANDO {} <<<".format(apto_key))
        result = colocar_apartamento(doc, apto_key, apto_data, family_symbols, walls, ceilings, level_id, report_dir)
        consolidado["apartamentos"][apto_key] = result

        ok = sum(1 for r in result["dispositivos"] if r.get("status") == "ok")
        okw = sum(1 for r in result["dispositivos"] if r.get("status") == "ok_with_warning")
        err = sum(1 for r in result["dispositivos"] if r.get("status") == "error")
        total_ok += ok
        total_okw += okw
        total_err += err

    consolidado["timestamp_fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
    consolidado["resumen"] = {
        "apartamentos_procesados": len(consolidado["apartamentos"]),
        "total_dispositivos": total_ok + total_okw + total_err,
        "ok": total_ok, "ok_with_warning": total_okw, "errors": total_err,
    }

    # Reporte consolidado
    os.makedirs(report_dir, exist_ok=True)
    cons_path = os.path.join(report_dir, "CONSOLIDADO_{}.json".format(time.strftime("%Y%m%d_%H%M%S")))
    with open(cons_path, "w") as f:
        json.dump(consolidado, f, indent=2, ensure_ascii=False)

    print("\n" + "="*70)
    print("COLOCACIÓN MASIVA COMPLETA")
    print("="*70)
    print("Apartamentos procesados: {}".format(len(consolidado["apartamentos"])))
    print("Dispositivos - Total: {}, OK: {}, OK+WARN: {}, Errores: {}".format(
        consolidado["resumen"]["total_dispositivos"], total_ok, total_okw, total_err))
    if consolidado["resumen"]["total_dispositivos"] > 0:
        print("Tasa OK: {:.1f}%".format((total_ok + total_okw) * 100.0 / consolidado["resumen"]["total_dispositivos"]))
    print("Reportes en: {}".format(report_dir))
    print("="*70)

if __name__ == "__main__":
    main()