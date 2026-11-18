# -*- coding: utf-8 -*-
"""
F6_COLOCAR_PYREVIT_v01.py
==========================
Colocación masiva de dispositivos F01/F02 en CENTRAL-V01.rvt usando pyRevit IronPython.
Ejecutar DENTRO de Revit 2026 via pyRevit Python Shell.

Basado en v70 (funcionó 34/34) + fixes actuales:
  - Offset dinámico por panel (TF 01 / TF 02) via panel DXF local
  - Solo M_Toma doble y M_Comunicaciones son face-based (WorkPlaneBased)
  - Norma COL: +90° rotación para interruptores/placas horizontales
  - Ceiling search por bounding box (más robusto)
  - Formato: inventario canónico JSON
  - IronPython 2.7 compatible: FamilyName, ElementId(Int64), etc.

USO
---
En pyRevit Python Shell con CENTRAL-V01.rvt abierto:

exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\scripts\\F6_COLOCAR_PYREVIT_v01.py").read())

# F01:
colocar_f01_f02(revit.doc, "F01")

# F02:
colocar_f01_f02(revit.doc, "F02")

# Validación 1 dispositivo:
colocar_f01_f02(revit.doc, "F01", single_handle="63")
"""

from __future__ import print_function

import json
import math
import os
import time
import sys

# IronPython 2.7 needs explicit Int64 for ElementId
from System import Int64

# Imports Revit / pyRevit
try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId, Level, BuiltInParameter,
        Plane, SketchPlane, LocationCurve, LocationPoint,
    )
    from Autodesk.Revit.DB.Structure import StructuralType
except Exception as _imp:
    print("[ERROR] Imports fallaron. Ejecuta dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(_imp))
    revit = None


# ─── Configuración ────────────────────────────────────────────────────────────

REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")
ARCHIVOS_BASE_DIR = os.path.join(REVITELECTRICO_ROOT, "ArchivosBase")

# Tolerancias (metros)
TOL_MURO = 0.61   # 2 ft = 610 mm
TOL_TECHO_BBOX = 0.05

# SOLO estas 2 familias son WorkPlaneBased (face-based en muro)
FAMILIAS_MURO_FACE = {"M_Toma doble", "M_Comunicaciones"}

# Familias de techo (hosted en cielorraso) - también face-based
FAMILIAS_TECHO_FACE = {"M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"}

# Panel name mapping
PANEL_NAME_MAP = {"F01": "TF 01", "F02": "TF 02"}
INVENTARIO_MAP = {
    "F01": "inventario_dispositivos_F01_v1.1_20261117_190929.json",
    "F02": "inventario_dispositivos_F02_v1.1_20261117_190933.json",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_int(val):
    """Convierte ElementId o int a int seguro."""
    try:
        return int(val)
    except Exception:
        try:
            return val.IntegerValue
        except Exception:
            return 0


def _load_inventario(apartamento):
    path = os.path.join(DATA_DIR, "inventarios", INVENTARIO_MAP[apartamento])
    if not os.path.exists(path):
        raise IOError("Inventario no encontrado: {}".format(path))
    with open(path, "r") as f:
        inv = json.load(f)
    return inv["dispositivos"], inv["metadatos"]


def _collect_family_symbols(doc):
    """Devuelve dict {(family_name, type_name): FamilySymbol}."""
    symbols = {}
    for sym in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
        try:
            # Use FamilyName property (not s.Family.Name)
            fam = sym.FamilyName
            tname = sym.Name
            symbols[(fam, tname)] = sym
        except Exception:
            continue
    return symbols


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
    """Devuelve dict {panelName: {id, x, y, z, levelId, elementId}}."""
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
                "x": pt.X * 304.8,
                "y": pt.Y * 304.8,
                "z": pt.Z * 304.8,
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


# ─── Placement ────────────────────────────────────────────────────────────────

def _place_on_wall_face(doc, dev, sym, x, y, z, walls):
    """Face-based placement en muro usando XYZ.BasisZ direction (fix P6)."""
    if not sym.IsActive:
        sym.Activate()

    wall = _find_wall_at(walls, x, y)
    if wall is None:
        return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                "error": "No wall within {:.2f}m of ({:.3f}, {:.3f})".format(TOL_MURO, x/304.8, y/304.8)}

    face_ref, face, normal = _get_wall_face_facing_point(wall, x/304.8, y/304.8, z/304.8)
    if face_ref is None:
        return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                "error": "No face on wall {} facing point".format(_safe_int(wall.Id)),
                "wall_id": _safe_int(wall.Id)}

    try:
        proj = face.Project(XYZ(x/304.8, y/304.8, z/304.8))
        if proj is None or proj.XYZPoint is None:
            return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                    "error": "Face.Project returned None", "wall_id": _safe_int(wall.Id)}
        projected_pt = proj.XYZPoint
    except Exception as e:
        return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                "error": "Face.Project failed: {}".format(e), "wall_id": _safe_int(wall.Id)}

    wall_base_elev = _get_wall_base_elevation(doc, wall)
    elevation_rel = (z/304.8) - wall_base_elev
    placement_pt = XYZ(projected_pt.X, projected_pt.Y, elevation_rel)

    # FIX P6: direction = XYZ.BasisZ (vertical)
    direction = XYZ.BasisZ

    try:
        new_inst = doc.Create.NewFamilyInstance(face_ref, placement_pt, direction, sym)
    except Exception as e:
        return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                "error": "NewFamilyInstance face failed: {}".format(e),
                "wall_id": _safe_int(wall.Id)}

    # Rotación: normal del muro + 90° (norma COL: placas horizontales)
    rot_deg = _calc_rotation_from_normal(normal)
    rot_deg = (rot_deg + 90) % 360
    if abs(rot_deg) > 0.1:
        try:
            loc = new_inst.Location
            if isinstance(loc, LocationPoint):
                axis = Line.CreateBound(placement_pt, XYZ(placement_pt.X, placement_pt.Y, placement_pt.Z + 1.0))
                loc.Rotate(axis, math.radians(rot_deg))
        except Exception as e:
            return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "ok_with_warning",
                    "element_id": _safe_int(new_inst.Id), "wall_id": _safe_int(wall.Id),
                    "warning": "Rotate failed: {}".format(e)}

    return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "ok",
            "element_id": _safe_int(new_inst.Id), "wall_id": _safe_int(wall.Id),
            "placement_pt": [placement_pt.X * 304.8, placement_pt.Y * 304.8, placement_pt.Z * 304.8],
            "rotation_deg": rot_deg}


def _place_on_ceiling_face(doc, dev, sym, x, y, z, ceilings):
    """Face-based placement en techo."""
    if not sym.IsActive:
        sym.Activate()

    ceiling = _find_ceiling_at(ceilings, x/304.8, y/304.8)
    if ceiling is None:
        return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                "error": "No ceiling found at ({:.3f}, {:.3f})".format(x/304.8, y/304.8)}

    placement_pt = XYZ(x/304.8, y/304.8, z/304.8)

    try:
        new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, ceiling, StructuralType.NonStructural)
    except Exception as e_hosted:
        try:
            new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, StructuralType.NonStructural)
        except Exception as e_free:
            return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                    "error": "Ceiling place failed: {} | fallback: {}".format(e_hosted, e_free),
                    "ceiling_id": _safe_int(ceiling.Id)}

    return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "ok",
            "element_id": _safe_int(new_inst.Id), "ceiling_id": _safe_int(ceiling.Id),
            "placement_pt": [x, y, z], "rotation_deg": 0}


def _place_level_based(doc, dev, sym, x, y, z, level_id, altura_local_mm, rotacion_final):
    """Level-based placement (para interruptores, timbre, climatización, etc.).
    En pyRevit, NewFamilyInstance con Level SÍ respeta X,Y del punto."""
    if not sym.IsActive:
        sym.Activate()

    level = doc.GetElement(ElementId(Int64(level_id)))
    if level is None:
        return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                "error": "Level not found: {}".format(level_id)}

    pt = XYZ(x/304.8, y/304.8, z/304.8)  # z es RELATIVO al nivel (altura_local_mm)

    try:
        new_inst = doc.Create.NewFamilyInstance(pt, sym, level, StructuralType.NonStructural)
    except Exception as e:
        return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "error",
                "error": "NewFamilyInstance level failed: {}".format(e)}

    # Rotación: rotacion_final + 90° (norma COL)
    rot_deg = (rotacion_final + 90) % 360
    if abs(rot_deg) > 0.1:
        try:
            loc = new_inst.Location
            if isinstance(loc, LocationPoint):
                axis = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1.0))
                loc.Rotate(axis, math.radians(rot_deg))
        except Exception as e:
            return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "ok_with_warning",
                    "element_id": _safe_int(new_inst.Id), "warning": "Rotate failed: {}".format(e)}

    # Elevación via parámetro
    if altura_local_mm > 0:
        try:
            for p in new_inst.Parameters:
                pname = p.Definition.Name
                if pname in ("Elevation", "Offset") and not p.IsReadOnly:
                    p.Set(altura_local_mm / 304.8)
                    break
        except Exception:
            pass

    return {"device_id": dev.get("handle"), "family": dev.get("familia_revit"), "status": "ok",
            "element_id": _safe_int(new_inst.Id), "level_id": level_id,
            "placement_pt": [x, y, z + level.Elevation * 304.8],
            "rotation_deg": rot_deg}


# ─── Main ────────────────────────────────────────────────────────────────────

def colocar_f01_f02(doc, apartamento, single_handle=None, report_path=None):
    """Coloca dispositivos de F01 o F02 en el documento Revit.

    Args:
        doc: Documento Revit activo
        apartamento: "F01" o "F02"
        single_handle: handle DXF de un solo dispositivo para validación
        report_path: ruta opcional para reporte JSON
    """
    if revit is None:
        print("[ERROR] Sin acceso a Revit. Ejecuta via pyRevit Python Shell.")
        return None

    print("=" * 60)
    print("  COLOCACIÓN {} EN CENTRAL-V01 (pyRevit v01)".format(apartamento))
    print("=" * 60)
    print("[INFO] Documento: {}".format(doc.Title))

    # 1. Cargar inventario
    try:
        dispositivos, meta = _load_inventario(apartamento)
    except Exception as e:
        print("[ERROR] No pude cargar inventario: {}".format(e))
        return None
    print("[INFO] Dispositivos en inventario: {}".format(len(dispositivos)))

    # 2. Filtrar single_handle
    if single_handle:
        dispositivos = [d for d in dispositivos if d.get("handle") == single_handle]
        if not dispositivos:
            print("[ERROR] No se encontro dispositivo handle={}".format(single_handle))
            return None
        print("[INFO] MODO VALIDACION: 1 dispositivo")

    # 3. Panel objetivo
    target_panel_name = PANEL_NAME_MAP[apartamento]
    panels = _collect_panels(doc)
    panel_obj = panels.get(target_panel_name)
    if not panel_obj:
        print("[ERROR] Panel '{}' no encontrado en CENTRAL-V01".format(target_panel_name))
        return None
    print("[INFO] Panel objetivo: {} @ ({:.1f}, {:.1f}) mm | LevelId: {}".format(
        target_panel_name, panel_obj["x"], panel_obj["y"], panel_obj["levelId"]))

    # 4. Offset dinámico (pre-calculado)
    OFFSETS = {
        "F01": (13990.9, 8010.6),
        "F02": (14037.4, 9654.7),
    }
    offset_x, offset_y = OFFSETS[apartamento]
    print("[INFO] Offset {}: ({:.1f}, {:.1f}) mm".format(apartamento, offset_x, offset_y))

    level_id = panel_obj["levelId"]
    nivel_elevacion = meta["nivel_elevacion_m"]

    # 5. Pre-cargar datos
    print("[INFO] Cargando FamilySymbols...")
    family_symbols = _collect_family_symbols(doc)
    print("[INFO]   {} símbolos".format(len(family_symbols)))

    print("[INFO] Cargando Walls...")
    walls = _collect_walls(doc)
    print("[INFO]   {} muros".format(len(walls)))

    print("[INFO] Cargando Ceilings...")
    ceilings = _collect_ceilings(doc)
    print("[INFO]   {} cielorrasos".format(len(ceilings)))
    print("")

    # 6. Procesar en transacción
    results = []
    print("[INFO] Iniciando transacción...")
    with revit.Transaction("Colocacion {} v01".format(apartamento)):
        for i, d in enumerate(dispositivos, 1):
            if not d.get("familia_revit"):
                r = dict(d)
                r["status"] = "skip"
                r["error"] = "Sin mapeo Revit"
                results.append(r)
                print("[{}/{}] {} {} -> SKIP (sin mapeo)".format(i, len(dispositivos), d.get("handle"), d.get("nombre_dxf")))
                continue

            fam = d["familia_revit"]
            tip = d["tipo_revit"]
            rot = d["rotacion_final_grados"]
            alt_mm = int(d["altura_local_m"] * 1000)

            # Coordenadas DXF local (m) -> Revit (mm) con offset
            x_mm = d["x"] * 1000 + offset_x
            y_mm = d["y"] * 1000 + offset_y
            z_abs_mm = (nivel_elevacion + d["altura_local_m"]) * 1000  # Z absoluto para face-based

            print("[{}/{}] {} {} -> ".format(i, len(dispositivos), d["handle"], d["nombre_dxf"]))

            sym, resolved_type = _find_symbol(family_symbols, fam, tip)
            if sym is None:
                r = dict(d)
                r["status"] = "error"
                r["error"] = "Symbol not found: {} / {}".format(fam, tip)
                results.append(r)
                print("        ERROR: Symbol not found")
                continue

            # Decidir estrategia por familia
            if fam in FAMILIAS_MURO_FACE:
                # Face-based en muro: Z absoluto
                result = _place_on_wall_face(doc, d, sym, x_mm, y_mm, z_abs_mm, walls)
            elif fam in FAMILIAS_TECHO_FACE:
                # Face-based en techo: Z absoluto
                result = _place_on_ceiling_face(doc, d, sym, x_mm, y_mm, z_abs_mm, ceilings)
            else:
                # Level-based: Z RELATIVO al nivel (altura_local_mm)
                result = _place_level_based(doc, d, sym, x_mm, y_mm, alt_mm, level_id, alt_mm, rot)

            r = dict(d)
            r.update(result)
            results.append(r)
            status = result.get("status", "unknown")
            if status == "ok":
                print("        OK (elem={}, rot={}°)".format(result.get("element_id"), result.get("rotation_deg", 0)))
            elif status == "ok_with_warning":
                print("        OK-WARN (elem={}, warn={})".format(result.get("element_id"), result.get("warning", "")[:60]))
            else:
                print("        ERROR: {}".format(result.get("error", "?")[:100]))

    # 7. Reporte
    if report_path:
        try:
            report_dir = os.path.dirname(report_path)
            if report_dir and not os.path.exists(report_dir):
                os.makedirs(report_dir)
            ok = sum(1 for r in results if r.get("status") == "ok")
            okw = sum(1 for r in results if r.get("status") == "ok_with_warning")
            err = sum(1 for r in results if r.get("status") == "error")
            skip = sum(1 for r in results if r.get("status") == "skip")
            report = {
                "version": "pyRevit_v01",
                "document": doc.Title,
                "apartamento": apartamento,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "panel": target_panel_name,
                "offset_mm": {"x": offset_x, "y": offset_y},
                "total": len(results),
                "ok": ok, "ok_with_warning": okw, "errors": err, "skipped": skip,
                "results": results,
            }
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print("\n[OK] Reporte: {}".format(report_path))
        except Exception as e:
            print("[WARN] No pude escribir reporte: {}".format(e))

    # 8. Resumen
    print("\n" + "=" * 60)
    print("  RESUMEN {} pyRevit_v01".format(apartamento))
    print("=" * 60)
    ok = sum(1 for r in results if r.get("status") == "ok")
    okw = sum(1 for r in results if r.get("status") == "ok_with_warning")
    err = sum(1 for r in results if r.get("status") == "error")
    skip = sum(1 for r in results if r.get("status") == "skip")
    total = len(results)
    print("  Total:   {}".format(total))
    print("  OK:      {}".format(ok))
    print("  OK+WARN: {}".format(okw))
    print("  Errores: {}".format(err))
    print("  Skip:    {}".format(skip))
    if total > 0:
        print("  Tasa OK: {:.1f}%".format((ok + okw) * 100.0 / total))
    print("=" * 60)

    return results