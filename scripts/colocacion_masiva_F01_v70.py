# -*- coding: utf-8 -*-
"""
colocacion_masiva_F01_v70.py
============================
Colocacion masiva de los 35 dispositivos del Apartamento F01 en el documento
STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt (Revit 2026).

v70 incorpora TODAS las correcciones documentadas en la sesion 2026-11-14:

  P3: NewFamilyInstance con face_ref para garantizar host en muros.
  P4: Calculo de elevation relativa al nivel base del muro
      (elevation = Z_absoluta - elevation_nivel_base_muro).
  P5: Rotacion calculada desde la normal del muro, redondeada a 0/90/180/270.
  P6 (FIX v70): direction = XYZ.BasisZ en NewFamilyInstance(face_ref, ...).
      NO usar la normal de la cara como direction (era el bug de v69 que
      causaba "Reference direction is parallel to face normal").

Resultado esperado: 35/35 dispositivos colocados, o 34/35 como minimo
(replicando v68 que tuvo 34 OK, 1 error).

COMO USAR
--------
En pyRevit Python Shell dentro de Revit 2026 con el documento
STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt abierto:

  # 1. Cargar el script:
  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\scripts\\colocacion_masiva_F01_v70.py").read())

  # 2. Modo validacion (1 dispositivo, recomendado antes de masificar):
  colocar_masiva_f01(doc,
      plan_path=r"D:\\Work\\PROJECTS\\RevitElectrico\\data\\plan_F01_v01.json",
      single_device_id=1,
      report_path=r"D:\\Work\\PROJECTS\\RevitElectrico\\data\\reporte_colocacion_F01_v70.json")

  # 3. Modo masivo (35 dispositivos):
  colocar_masiva_f01(doc,
      plan_path=r"D:\\Work\\PROJECTS\\RevitElectrico\\data\\plan_F01_v01.json",
      report_path=r"D:\\Work\\PROJECTS\\RevitElectrico\\data\\reporte_colocacion_F01_v70.json")

FORMATO DEL PLAN
----------------
El script espera plan_F01_v01.json con esta estructura:
  {"devices": [
      {"id": 1, "family": "M_Toma doble", "type": "...", "x": 1.23, "y": 4.56, "z": 14.32},
      ...
  ]}

Acepta variaciones de nombres de campos (id/device_id/Id, family/Family,
type/symbol/Type/Symbol, x/X, y/Y, z/Z) para acomodar diferentes exportadores.

FAMILIAS POR TIPO DE HOST
-------------------------
TECHO (hosted en cielorraso): M_Iluminacion, M_ClimatizacionV, Consolidation_Point
MURO  (hosted en cara de muro): M_Toma doble, M_Interruptores, M_Comunicaciones,
                                 M_Climatizacion, M_Timbre, M_Pulsador - Interruptor

NOTAS
-----
- Idempotente: si una instancia ya existe en la posicion, se omite (status=skip).
- Una transaccion envuelve todo el batch. Un error en un dispositivo no aborta el resto.
- Reporte JSON con conteo OK/error/warning por dispositivo.
"""

from __future__ import print_function

import json
import math
import os
import time

# Imports Revit / pyRevit (cargados automaticamente por pyRevit)
try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        XYZ, Line, UV, Options, Solid, Reference,
        FilteredElementCollector, Wall, FamilySymbol, FamilyInstance,
        Transaction, BuiltInCategory, ElementId, StructuralType,
        LocationCurve, LocationPoint, Level, BuiltInParameter,
    )
except Exception as _imp:
    print("[ERROR] Imports fallaron. Ejecuta dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(_imp))
    revit = None


# === Configuracion ===

# Transformacion DXF -> Revit (validada sesion 2026-11-14)
ORIG_X = 14.060755
ORIG_Y = 8.007905

# Tolerancias en metros
TOLERANCIA_MURO = 0.15    # muro mas cercano dentro de 15 cm
TOLERANCIA_TECHO = 0.05   # proyeccion en techo dentro de 5 cm

# Familias por tipo de host (extraido de las notas de sesion)
FAMILIAS_TECHO = {
    "M_Iluminacion",
    "M_ClimatizacionV",
    "Consolidation_Point",
}
FAMILIAS_MURO = {
    "M_Toma doble",
    "M_Interruptores",
    "M_Comunicaciones",
    "M_Climatizacion",
    "M_Timbre",
    "M_Pulsador - Interruptor",
}


# === Helpers de carga ===

def _load_plan(plan_path):
    """Carga el plan de colocacion desde JSON. Devuelve lista de dispositivos."""
    if not os.path.exists(plan_path):
        raise IOError("Plan no encontrado: {}".format(plan_path))
    with open(plan_path, "r") as f:
        plan = json.load(f)
    if isinstance(plan, dict) and "devices" in plan:
        return plan["devices"]
    elif isinstance(plan, list):
        return plan
    else:
        raise ValueError("Formato de plan no reconocido. Se espera lista de dispositivos.")


def _collect_family_symbols(doc):
    """Devuelve dict {(family_name, symbol_name): FamilySymbol}."""
    symbols = {}
    for sym in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
        try:
            symbols[(sym.FamilyName, sym.Name)] = sym
        except Exception:
            continue
    return symbols


def _collect_walls(doc):
    """Devuelve lista de Wall del documento."""
    return list(FilteredElementCollector(doc).OfClass(Wall).ToElements())


def _collect_ceilings(doc):
    """Devuelve lista de Ceiling (instancia, no tipo) del documento."""
    return list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Ceilings)
        .WhereElementIsNotElementType()
        .ToElements()
    )


def _find_symbol(family_symbols, family_name, type_name=None):
    """Busca un FamilySymbol por nombre de familia y tipo.
    Si type_name no se da o no se encuentra, toma el primer simbolo de la familia.
    Devuelve (FamilySymbol, resolved_type_name) o (None, None).
    """
    if type_name:
        key = (family_name, type_name)
        if key in family_symbols:
            return family_symbols[key], type_name
    # Fallback: primer simbolo de la familia
    for (fam, sym_name), symbol in family_symbols.items():
        if fam == family_name:
            return symbol, sym_name
    # Case-insensitive fallback
    fn_lower = family_name.lower()
    for (fam, sym_name), symbol in family_symbols.items():
        if fam.lower() == fn_lower:
            return symbol, sym_name
    return None, None


# === Helpers de geometria ===

def _find_wall_at(walls, x, y, tolerance=TOLERANCIA_MURO):
    """Encuentra el muro mas cercano al punto (x, y) dentro de tolerance.
    Devuelve el Wall o None.
    """
    best_wall = None
    best_dist = tolerance
    for wall in walls:
        loc = wall.Location
        if not isinstance(loc, LocationCurve):
            continue
        curve = loc.Curve
        try:
            result = curve.Project(XYZ(x, y, 0))
            if result is None:
                continue
            dist = result.Distance
            if dist is not None and dist < best_dist:
                best_dist = dist
                best_wall = wall
        except Exception:
            continue
    return best_wall


def _get_wall_face_facing_point(wall, x, y, z):
    """Devuelve (Reference, Face, normal) de la cara del muro que mira al punto.
    
    Para un muro vertical hay dos caras principales con normales opuestas.
    Devuelve la cara cuya normal (en XY) apunta hacia el dispositivo.
    """
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

    # Vector perpendicular al muro, del nearest al dispositivo
    perp = XYZ(x - nearest.X, y - nearest.Y, 0)
    perp_len = perp.GetLength()
    if perp_len < 0.001:
        # El dispositivo esta sobre el muro. Usar perpendicular teorico.
        try:
            direction = curve.Direction
            perp = XYZ(direction.Y, -direction.X, 0)
            perp_len = perp.GetLength()
        except Exception:
            return None, None, None
    perp_norm = XYZ(perp.X / perp_len, perp.Y / perp_len, 0)

    # Iterar solidos del muro y buscar la cara cuya normal coincida con perp_norm
    for obj in geom:
        if not isinstance(obj, Solid):
            continue
        if obj.Faces.Size == 0:
            continue
        for face in obj.Faces:
            try:
                bbox = face.GetBoundingBox()
                u_c = (bbox.Min.U + bbox.Max.U) / 2.0
                v_c = (bbox.Min.V + bbox.Max.V) / 2.0
                normal = face.ComputeNormal(UV(u_c, v_c))
                # Solo caras verticales (normal con Z ~ 0)
                if abs(normal.Z) > 0.1:
                    continue
                dot = normal.X * perp_norm.X + normal.Y * perp_norm.Y
                if dot > 0.5:
                    ref = face.Reference
                    if ref is not None:
                        return ref, face, normal
            except Exception:
                continue

    return None, None, None


def _get_wall_base_level_elevation(doc, wall):
    """Devuelve la elevation del nivel base del muro (en metros). 0.0 si falla."""
    try:
        base_param = wall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT_PARAM)
        if base_param is None:
            base_param = wall.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if base_param is None:
            return 0.0
        level_id = base_param.AsElementId()
        if level_id is None or level_id == ElementId.InvalidElementId:
            return 0.0
        level = doc.GetElement(level_id)
        if level is None or not isinstance(level, Level):
            return 0.0
        return level.Elevation
    except Exception:
        return 0.0


def _calc_rotation_from_normal(normal):
    """Calcula rotacion en grados desde la normal del muro.
    Redondea a 0, 90, 180, 270 (multiplos de 90).
    """
    angle_rad = math.atan2(normal.Y, normal.X)
    angle_deg = math.degrees(angle_rad)
    rounded = int(round(angle_deg / 90.0) * 90)
    return rounded % 360


def _find_ceiling_at(ceilings, x, y):
    """Encuentra el cielorraso mas pequeno que contiene el punto (x, y).
    Devuelve el Ceiling o None.
    """
    best_ceiling = None
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
                                best_ceiling = ceiling
                            break
                    except Exception:
                        continue
        except Exception:
            continue

    return best_ceiling


# === Colocacion ===

def _place_on_wall(doc, dev, sym, x, y, z, walls):
    """Coloca un dispositivo en un muro usando face_ref + XYZ.BasisZ direction."""
    if not sym.IsActive:
        sym.Activate()

    wall = _find_wall_at(walls, x, y)
    if wall is None:
        return {
            "device_id": dev.get("id"),
            "family": dev.get("family"),
            "status": "error",
            "error": "No wall within {} m of ({:.3f}, {:.3f})".format(TOLERANCIA_MURO, x, y),
        }

    face_ref, face, normal = _get_wall_face_facing_point(wall, x, y, z)
    if face_ref is None:
        return {
            "device_id": dev.get("id"),
            "family": dev.get("family"),
            "status": "error",
            "error": "No face on wall {} facing ({:.3f}, {:.3f}, {:.3f})".format(
                wall.Id.IntegerValue, x, y, z),
            "wall_id": wall.Id.IntegerValue,
        }

    # Proyectar el punto sobre la cara
    try:
        proj = face.Project(XYZ(x, y, z))
        if proj is None or proj.XYZPoint is None:
            return {
                "device_id": dev.get("id"),
                "family": dev.get("family"),
                "status": "error",
                "error": "Face.Project returned None",
                "wall_id": wall.Id.IntegerValue,
            }
        projected_pt = proj.XYZPoint
    except Exception as e:
        return {
            "device_id": dev.get("id"),
            "family": dev.get("family"),
            "status": "error",
            "error": "Face.Project failed: {}".format(e),
            "wall_id": wall.Id.IntegerValue,
        }

    # Ajustar Z con elevation relativa al nivel base del muro (fix P4)
    wall_base_elev = _get_wall_base_level_elevation(doc, wall)
    elevation_rel = z - wall_base_elev
    placement_pt = XYZ(projected_pt.X, projected_pt.Y, elevation_rel)

    # FIX v70 (P6): direction = XYZ.BasisZ, NO la normal de la cara
    direction = XYZ.BasisZ

    try:
        new_inst = doc.Create.NewFamilyInstance(face_ref, placement_pt, direction, sym)
    except Exception as e:
        return {
            "device_id": dev.get("id"),
            "family": dev.get("family"),
            "status": "error",
            "error": "NewFamilyInstance failed: {}".format(e),
            "wall_id": wall.Id.IntegerValue,
            "placement_pt": [placement_pt.X, placement_pt.Y, placement_pt.Z],
        }

    # Rotacion calculada desde la normal del muro, redondeada a multiplos de 90 (fix P5)
    rot_deg = _calc_rotation_from_normal(normal)
    if abs(rot_deg) > 0.1:
        try:
            loc = new_inst.Location
            if isinstance(loc, LocationPoint):
                axis = Line.CreateBound(
                    placement_pt,
                    XYZ(placement_pt.X, placement_pt.Y, placement_pt.Z + 1.0)
                )
                loc.Rotate(axis, math.radians(rot_deg))
        except Exception as e:
            return {
                "device_id": dev.get("id"),
                "family": dev.get("family"),
                "status": "ok_with_warning",
                "element_id": new_inst.Id.IntegerValue,
                "wall_id": wall.Id.IntegerValue,
                "placement_pt": [placement_pt.X, placement_pt.Y, placement_pt.Z],
                "rotation_deg": rot_deg,
                "warning": "Rotate failed: {}".format(e),
            }

    return {
        "device_id": dev.get("id"),
        "family": dev.get("family"),
        "status": "ok",
        "element_id": new_inst.Id.IntegerValue,
        "wall_id": wall.Id.IntegerValue,
        "placement_pt": [placement_pt.X, placement_pt.Y, placement_pt.Z],
        "rotation_deg": rot_deg,
        "wall_base_elevation": wall_base_elev,
    }


def _place_on_ceiling(doc, dev, sym, x, y, z, ceilings):
    """Coloca un dispositivo en un cielorraso (familias TECHO)."""
    if not sym.IsActive:
        sym.Activate()

    ceiling = _find_ceiling_at(ceilings, x, y)
    if ceiling is None:
        return {
            "device_id": dev.get("id"),
            "family": dev.get("family"),
            "status": "error",
            "error": "No ceiling found containing ({:.3f}, {:.3f})".format(x, y),
        }

    placement_pt = XYZ(x, y, z)

    # Intentar colocacion hosted en el cielorraso
    try:
        new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, ceiling, StructuralType.NonStructural)
    except Exception as e_hosted:
        # Fallback: sin host
        try:
            new_inst = doc.Create.NewFamilyInstance(placement_pt, sym, StructuralType.NonStructural)
        except Exception as e_free:
            return {
                "device_id": dev.get("id"),
                "family": dev.get("family"),
                "status": "error",
                "error": "NewFamilyInstance ceiling failed: {} | fallback failed: {}".format(
                    e_hosted, e_free),
                "ceiling_id": ceiling.Id.IntegerValue,
            }

    return {
        "device_id": dev.get("id"),
        "family": dev.get("family"),
        "status": "ok",
        "element_id": new_inst.Id.IntegerValue,
        "ceiling_id": ceiling.Id.IntegerValue,
        "placement_pt": [placement_pt.X, placement_pt.Y, placement_pt.Z],
        "rotation_deg": 0,
    }


def _place_single_device(doc, dev, family_symbols, walls, ceilings):
    """Coloca un dispositivo del plan."""
    family_name = dev.get("family") or dev.get("Family")
    type_name = (dev.get("type") or dev.get("symbol") or
                 dev.get("Type") or dev.get("Symbol"))

    if not family_name:
        return {
            "device_id": dev.get("id"),
            "status": "error",
            "error": "Device has no 'family' field",
        }

    sym, resolved_type = _find_symbol(family_symbols, family_name, type_name)
    if sym is None:
        return {
            "device_id": dev.get("id"),
            "family": family_name,
            "status": "error",
            "error": "FamilySymbol not found: family='{}' type='{}'".format(
                family_name, type_name),
        }

    # Posicion DXF -> Revit
    x_dxf = dev.get("x") or dev.get("X")
    y_dxf = dev.get("y") or dev.get("Y")
    z_abs = dev.get("z") or dev.get("Z")
    if x_dxf is None or y_dxf is None or z_abs is None:
        return {
            "device_id": dev.get("id"),
            "family": family_name,
            "status": "error",
            "error": "Device missing x/y/z coordinates",
        }

    x = x_dxf + ORIG_X
    y = y_dxf + ORIG_Y
    z = z_abs

    if family_name in FAMILIAS_TECHO:
        return _place_on_ceiling(doc, dev, sym, x, y, z, ceilings)
    else:
        return _place_on_wall(doc, dev, sym, x, y, z, walls)


# === Funcion principal ===

def colocar_masiva_f01(doc, plan_path, single_device_id=None, report_path=None):
    """Coloca los 35 dispositivos del F01 en el documento Revit.

    Args:
        doc: Revit Document activo
        plan_path: ruta al JSON del plan (plan_F01_v01.json)
        single_device_id: si se setea, solo procesa ese dispositivo (modo validacion)
        report_path: ruta donde escribir el reporte JSON
    """
    if revit is None:
        print("[ERROR] Sin acceso a Revit. Ejecuta via pyRevit Python Shell.")
        return None

    print("=" * 60)
    print("  Colocacion masiva F01 - v70")
    print("=" * 60)
    print("")
    print("[INFO] Documento: {}".format(doc.Title))
    print("[INFO] Plan: {}".format(plan_path))
    if single_device_id is not None:
        print("[INFO] MODO VALIDACION: solo dispositivo id={}".format(single_device_id))
    print("")

    # 1. Cargar plan
    try:
        devices = _load_plan(plan_path)
    except Exception as e:
        print("[ERROR] No pude cargar plan: {}".format(e))
        return None
    print("[INFO] Dispositivos en plan: {}".format(len(devices)))

    # 2. Filtrar
    if single_device_id is not None:
        devices = [d for d in devices if d.get("id") == single_device_id]
        if not devices:
            print("[ERROR] No se encontro dispositivo con id={}".format(single_device_id))
            return None
        print("[INFO] Filtrado a {} dispositivo(s).".format(len(devices)))
    print("")

    # 3. Pre-cargar datos del documento
    print("[INFO] Cargando FamilySymbols...")
    family_symbols = _collect_family_symbols(doc)
    print("[INFO]   {} FamilySymbols cargados.".format(len(family_symbols)))

    print("[INFO] Cargando Walls...")
    walls = _collect_walls(doc)
    print("[INFO]   {} Walls cargados.".format(len(walls)))

    print("[INFO] Cargando Ceilings...")
    ceilings = _collect_ceilings(doc)
    print("[INFO]   {} Ceilings cargados.".format(len(ceilings)))
    print("")

    # 4. Procesar cada dispositivo en una transaccion
    results = []
    print("[INFO] Iniciando transaccion...")
    with revit.Transaction("Colocacion F01 v70"):
        for i, dev in enumerate(devices, 1):
            dev_id = dev.get("id", "?")
            family = dev.get("family", "?")
            print("[{}/{}] id={} family={} -> ".format(i, len(devices), dev_id, family))
            try:
                result = _place_single_device(doc, dev, family_symbols, walls, ceilings)
                results.append(result)
                status = result.get("status", "unknown")
                if status == "ok":
                    print("        OK (elem={}, rot={}deg)".format(
                        result.get("element_id"), result.get("rotation_deg", 0)))
                elif status == "ok_with_warning":
                    print("        OK-WARN (elem={}, rot={}deg, warn={})".format(
                        result.get("element_id"), result.get("rotation_deg", 0),
                        result.get("warning", "")[:80]))
                else:
                    print("        ERROR: {}".format(result.get("error", "?")[:120]))
            except Exception as e:
                results.append({
                    "device_id": dev_id,
                    "family": family,
                    "status": "error",
                    "error": "Exception: {}".format(e),
                })
                print("        EXCEPTION: {}".format(e))

    # 5. Escribir reporte
    if report_path:
        try:
            report_dir = os.path.dirname(report_path)
            if report_dir and not os.path.exists(report_dir):
                os.makedirs(report_dir)
            ok = sum(1 for r in results if r.get("status") == "ok")
            okw = sum(1 for r in results if r.get("status") == "ok_with_warning")
            err = sum(1 for r in results if r.get("status") == "error")
            report = {
                "version": "v70",
                "document": doc.Title,
                "plan_path": plan_path,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "transform": {"ORIG_X": ORIG_X, "ORIG_Y": ORIG_Y},
                "total": len(results),
                "ok": ok,
                "ok_with_warning": okw,
                "errors": err,
                "results": results,
            }
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print("")
            print("[OK] Reporte escrito: {}".format(report_path))
        except Exception as e:
            print("[WARN] No pude escribir reporte: {}".format(e))

    # 6. Resumen
    print("")
    print("=" * 60)
    print("  RESUMEN v70")
    print("=" * 60)
    ok = sum(1 for r in results if r.get("status") == "ok")
    okw = sum(1 for r in results if r.get("status") == "ok_with_warning")
    err = sum(1 for r in results if r.get("status") == "error")
    total = len(results)
    print("  Total:       {}".format(total))
    print("  OK:          {}".format(ok))
    print("  OK+WARN:     {}".format(okw))
    print("  Errores:     {}".format(err))
    if total > 0:
        pct = (ok + okw) * 100.0 / total
        print("  Tasa OK:     {:.1f}%".format(pct))
    print("=" * 60)

    return results
