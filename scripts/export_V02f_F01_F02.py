# -*- coding: utf-8 -*-
"""export_V02f_F01_F02.py - CORREGIDO v2 (usa categorías, no clases Electrical)"""

from __future__ import print_function

import json
import os
import sys
import time
from collections import defaultdict

try:
    from pyrevit import revit
    from Autodesk.Revit.DB import (
        XYZ, FilteredElementCollector, BuiltInCategory, ElementId,
        BuiltInParameter, LocationPoint, LocationCurve, FamilyInstance,
        Wall, Ceiling, Level, Options, Solid, Conduit, ConduitFitting,
        ConduitType, ConduitRun
    )
except Exception as e:
    print("[ERROR] Imports fallaron. Ejecuta dentro de Revit via pyRevit.")
    print("[ERROR] Detalle: {}".format(e))
    revit = None

# Configuración
REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")
EXPORT_DIR = os.path.join(DATA_DIR, "exports", "V02f_F01_F02_{}".format(time.strftime("%Y%m%d_%H%M%S")))

# Apartamentos objetivo y sus paneles
TARGET_APARTAMENTOS = {
    "F01": {"panel_name": "TF 01", "panel_xy_mm": (13990.9, 8010.6)},
    "F02": {"panel_name": "TF 02", "panel_xy_mm": (14037.4, 9654.7)},
}

# Nivel Piso 5 en V02-f
NIVEL_PISO5_ELEV_M = 13.22

# Tolerancia para asociar dispositivos a apartamentos (radio desde panel en mm)
TOL_APTO_MM = 6000  # 6m radio aprox

# Categorías de dispositivos a exportar
DEVICE_CATS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
]

def _safe_int(val):
    """Convierte ElementId o int a int seguro."""
    try:
        return int(val)
    except Exception:
        try:
            return val.IntegerValue
        except Exception:
            return 0

def _clean(s):
    if not s: return s
    return s.replace(u"\ufeff", "").replace(u"\u200b", "").strip()

def _get_type_name(elem):
    """Obtener nombre del tipo de un elemento."""
    try:
        type_id = elem.GetTypeId()
        if type_id and _safe_int(type_id) > 0:
            tipo = revit.doc.GetElement(type_id)
            if tipo:
                try:
                    return _clean(tipo.Name)
                except:
                    pass
                try:
                    p = tipo.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                    if p and p.HasValue:
                        return _clean(p.AsString())
                except:
                    pass
    except:
        pass
    return "desconocido"

def _get_family_name(elem):
    """Obtener nombre de familia."""
    try:
        if hasattr(elem, 'FamilyName'):
            return _clean(elem.FamilyName)
        if isinstance(elem, FamilyInstance) and elem.Symbol:
            return _clean(elem.Symbol.FamilyName)
    except:
        pass
    return "desconocida"

def _collect_panels(doc):
    """Recolecta paneles eléctricos con Panel Name."""
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
                "elevation_m": pt.Z * 0.3048,
            }
    return panels

def _point_distance_2d(pt1, pt2):
    """Distancia 2D entre dos puntos XYZ en metros."""
    dx = pt1.X - pt2.X
    dy = pt1.Y - pt2.Y
    return (dx*dx + dy*dy)**0.5 * 0.3048  # a metros

def _assign_apartamento(device_pt, panels_xy):
    """Asigna dispositivo a F01/F02 por proximidad a panel."""
    best = None
    best_dist = TOL_APTO_MM / 1000.0  # convertir a metros
    for apto, data in panels_xy.items():
        panel_pt = XYZ(data["x_mm"]/304.8, data["y_mm"]/304.8, 0)
        dist = _point_distance_2d(device_pt, panel_pt)
        if dist < best_dist:
            best_dist = dist
            best = apto
    return best

def _get_host_info(elem, doc):
    """Obtiene info del host (muro, techo, nivel)."""
    host_info = {"tipo": "none", "id": None, "level_id": None}
    try:
        if hasattr(elem, 'Host') and elem.Host:
            host = elem.Host
            host_info["id"] = _safe_int(host.Id)
            if isinstance(host, Wall):
                host_info["tipo"] = "wall"
            elif isinstance(host, Ceiling):
                host_info["tipo"] = "ceiling"
            elif isinstance(host, Level):
                host_info["tipo"] = "level"
            # Nivel del host
            try:
                p_level = host.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
                if not p_level:
                    p_level = host.get_Parameter(BuiltInParameter.LEVEL_PARAM)
                if p_level and p_level.AsElementId():
                    host_info["level_id"] = _safe_int(p_level.AsElementId())
            except:
                pass
        elif isinstance(elem, FamilyInstance):
            # Para level-based, obtener nivel del parámetro
            p_level = elem.get_Parameter(BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM)
            if not p_level:
                p_level = elem.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
            if not p_level:
                p_level = elem.get_Parameter(BuiltInParameter.LEVEL_PARAM)
            if p_level and p_level.AsElementId():
                host_info["level_id"] = _safe_int(p_level.AsElementId())
                host_info["tipo"] = "level"
    except:
        pass
    return host_info

def _get_rotation(elem):
    """Obtiene rotación en grados alrededor de Z."""
    try:
        loc = elem.Location
        if isinstance(loc, LocationPoint):
            rot = loc.Rotation  # en radianes
            return round(rot * 180.0 / 3.14159265359, 2)
    except:
        pass
    return 0.0

def export_dispositivos(doc, panels):
    """Exporta todos los dispositivos eléctricos de F01/F02."""
    print("\n" + "="*70)
    print("EXPORTANDO DISPOSITIVOS F01/F02")
    print("="*70)

    # Paneles XY para asignación
    panels_xy = {}
    for apto, info in TARGET_APARTAMENTOS.items():
        pname = info["panel_name"]
        if pname in panels:
            panels_xy[apto] = {"x_mm": panels[pname]["x_mm"], "y_mm": panels[pname]["y_mm"]}
            print("[INFO] Panel {} encontrado en ({:.1f}, {:.1f}) mm".format(
                pname, panels[pname]["x_mm"], panels[pname]["y_mm"]))
        else:
            print("[WARN] Panel {} NO encontrado".format(pname))

    if not panels_xy:
        print("[ERROR] No se encontraron paneles objetivo")
        return []

    dispositivos = []
    stats = defaultdict(int)

    for cat in DEVICE_CATS:
        elems = FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements()
        print("[INFO] Categoría {}: {} elementos".format(cat, len(elems)))

        for elem in elems:
            try:
                loc = elem.Location
                if not isinstance(loc, LocationPoint):
                    continue

                pt = loc.Point
                z_m = pt.Z * 0.3048

                # Filtrar solo Piso 5 (13m - 16m)
                if not (12.5 <= z_m <= 16.5):
                    continue

                # Asignar a apartamento
                apto = _assign_apartamento(pt, panels_xy)
                if not apto:
                    continue

                # Datos del dispositivo
                fam_name = _get_family_name(elem)
                type_name = _get_type_name(elem)
                rot = _get_rotation(elem)
                host_info = _get_host_info(elem, doc)

                # Altura local relativa al nivel Piso 5
                altura_local_m = z_m - NIVEL_PISO5_ELEV_M

                dev = {
                    "apartamento": apto,
                    "element_id": _safe_int(elem.Id),
                    "unique_id": elem.UniqueId,
                    "familia_revit": fam_name,
                    "tipo_revit": type_name,
                    "categoria": elem.Category.Name if elem.Category else "desconocida",
                    "posicion": {
                        "x_m": round(pt.X * 0.3048, 4),
                        "y_m": round(pt.Y * 0.3048, 4),
                        "z_m": round(z_m, 4),
                    },
                    "altura_local_m": round(altura_local_m, 3),
                    "rotacion_grados": rot,
                    "host": host_info,
                    "nivel_elevacion_m": NIVEL_PISO5_ELEV_M,
                }
                dispositivos.append(dev)
                stats[apto] += 1
                stats["total"] += 1

            except Exception as e:
                print("[WARN] Error procesando elemento {}: {}".format(_safe_int(elem.Id), e))

    print("\nResumen dispositivos:")
    for apto in ["F01", "F02", "total"]:
        print("  {}: {}".format(apto, stats.get(apto, 0)))

    return dispositivos

def export_conduits(doc):
    """Exporta todos los conduits y fittings del modelo usando categorías."""
    print("\n" + "="*70)
    print("EXPORTANDO CONDUITS Y FITTINGS")
    print("="*70)

    conduits = []
    conduit_elements = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().ToElements()
    print("[INFO] Conduits totales en modelo: {}".format(len(conduit_elements)))

    for c in conduit_elements:
        try:
            info = {
                "id": _safe_int(c.Id),
                "tipo": _get_type_name(c),
                "tipo_id": _safe_int(c.GetTypeId()),
            }

            # Geometría
            loc = c.Location
            if isinstance(loc, LocationCurve):
                curve = loc.Curve
                pt_start = curve.GetEndPoint(0)
                pt_end = curve.GetEndPoint(1)

                info["inicio"] = {
                    "x_m": round(pt_start.X * 0.3048, 4),
                    "y_m": round(pt_start.Y * 0.3048, 4),
                    "z_m": round(pt_start.Z * 0.3048, 4),
                }
                info["fin"] = {
                    "x_m": round(pt_end.X * 0.3048, 4),
                    "y_m": round(pt_end.Y * 0.3048, 4),
                    "z_m": round(pt_end.Z * 0.3048, 4),
                }

                info["longitud_m"] = round(curve.Length * 0.3048, 4)

                # Orientación
                dz = abs(pt_end.Z - pt_start.Z) * 0.3048
                dx = abs(pt_end.X - pt_start.X) * 0.3048
                dy = abs(pt_end.Y - pt_start.Y) * 0.3048
                if dz < 0.01:
                    info["orientacion"] = "horizontal"
                elif dx < 0.01 and dy < 0.01:
                    info["orientacion"] = "vertical"
                else:
                    info["orientacion"] = "inclinada"

                info["altura_promedio_m"] = round((pt_start.Z + pt_end.Z) / 2 * 0.3048, 4)

            # Conectores
            conectores = []
            try:
                for conn in c.MEPModel.ConnectorManager.Connectors:
                    for ref in conn.AllRefs:
                        if ref.Owner.Id != c.Id:
                            conectores.append(_safe_int(ref.Owner.Id))
            except:
                pass
            info["conectores"] = list(set(conectores))

            # Nivel
            try:
                p_lv = c.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
                if p_lv and p_lv.AsElementId() and _safe_int(p_lv.AsElementId()) > 0:
                    lvl_elem = doc.GetElement(p_lv.AsElementId())
                    info["nivel"] = _clean(lvl_elem.Name) if lvl_elem else ""
                else:
                    info["nivel"] = ""
            except:
                info["nivel"] = ""

            # Diámetro
            try:
                p_diam = c.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
                if p_diam and p_diam.HasValue:
                    info["diametro_pulg"] = round(p_diam.AsDouble() * 0.3048 * 39.3701, 2)
                else:
                    info["diametro_pulg"] = None
            except:
                info["diametro_pulg"] = None

            # Determinar si es de F01/F02 por altura y posición
            if "altura_promedio_m" in info:
                z = info["altura_promedio_m"]
                if 13.0 <= z <= 16.5:
                    info["posible_F01_F02"] = True
                else:
                    info["posible_F01_F02"] = False

            conduits.append(info)

        except Exception as e:
            print("[WARN] Error en conduit {}: {}".format(_safe_int(c.Id), e))

    # Fittings (cajas de conexión, codos, tes) - usar categoría
    fittings = []
    fitting_elements = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ConduitFitting).WhereElementIsNotElementType().ToElements()
    print("[INFO] Fittings totales en modelo: {}".format(len(fitting_elements)))

    for f in fitting_elements:
        try:
            info = {
                "id": _safe_int(f.Id),
                "tipo": _get_type_name(f),
                "tipo_id": _safe_int(f.GetTypeId()),
            }

            loc = f.Location
            if isinstance(loc, LocationPoint):
                pt = loc.Point
                info["posicion"] = {
                    "x_m": round(pt.X * 0.3048, 4),
                    "y_m": round(pt.Y * 0.3048, 4),
                    "z_m": round(pt.Z * 0.3048, 4),
                }

            # Conectores
            conectores = []
            try:
                for conn in f.MEPModel.ConnectorManager.Connectors:
                    for ref in conn.AllRefs:
                        if ref.Owner.Id != f.Id:
                            conectores.append(_safe_int(ref.Owner.Id))
            except:
                pass
            info["conectores"] = list(set(conectores))

            fittings.append(info)

        except Exception as e:
            print("[WARN] Error en fitting {}: {}".format(_safe_int(f.Id), e))

    print("\nResumen:")
    print("  Conduits exportados: {}".format(len(conduits)))
    print("  Fittings exportados: {}".format(len(fittings)))

    # Filtrar solo los de Piso 5 (F01/F02)
    conduits_f01_f02 = [c for c in conduits if c.get("posible_F01_F02", False)]
    fittings_f01_f02 = [f for f in fittings if 13.0 <= f.get("posicion", {}).get("z_m", 0) <= 16.5]

    print("  Conduits Piso 5 (F01/F02): {}".format(len(conduits_f01_f02)))
    print("  Fittings Piso 5 (F01/F02): {}".format(len(fittings_f01_f02)))

    return {
        "conduits_todos": conduits,
        "fittings_todos": fittings,
        "conduits_F01_F02": conduits_f01_f02,
        "fittings_F01_F02": fittings_f01_f02,
    }

def export_conduit_types(doc):
    """Exporta los tipos de conduit disponibles con sus IDs."""
    print("\n" + "="*70)
    print("EXPORTANDO TIPOS DE CONDUIT")
    print("="*70)

    types = []
    for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsElementType().ToElements():
        try:
            type_info = {
                "type_id": _safe_int(fs.Id),
                "nombre": _clean(fs.Name),
                "familia": _clean(fs.FamilyName) if hasattr(fs, 'FamilyName') else "Tubo",
            }
            # Diámetro
            try:
                p_diam = fs.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
                if p_diam and p_diam.HasValue:
                    type_info["diametro_pulg"] = round(p_diam.AsDouble() * 0.3048 * 39.3701, 2)
            except:
                type_info["diametro_pulg"] = None

            types.append(type_info)
        except Exception as e:
            print("[WARN] Error en tipo {}: {}".format(_safe_int(fs.Id), e))

    print("[INFO] Tipos de conduit encontrados: {}".format(len(types)))
    for t in types:
        print("  ID={} | {} | Ø={}\"".format(t["type_id"], t["nombre"], t.get("diametro_pulg", "?")))

    return types

def main():
    if revit is None:
        print("[ERROR] Sin acceso a Revit. Ejecuta via pyRevit Python Shell.")
        return

    doc = revit.doc
    print("="*70)
    print("EXPORT V02-f -> F01/F02")
    print("Documento: {}".format(doc.Title))
    print("="*70)

    if "V02-f" not in doc.Title and "CENTRA_V02-f" not in doc.Title:
        print("[WARN] Documento no parece ser V02-f: {}".format(doc.Title))

    # Crear directorio de exportación
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    # 1. Paneles
    panels = _collect_panels(doc)
    print("\nPaneles encontrados:")
    for name, data in panels.items():
        print("  {}: Id={}, ({:.1f}, {:.1f}) mm".format(name, data["id"], data["x_mm"], data["y_mm"]))

    # 2. Dispositivos
    dispositivos = export_dispositivos(doc, panels)

    # 3. Conduits y fittings
    ruteo = export_conduits(doc)

    # 4. Tipos de conduit
    conduit_types = export_conduit_types(doc)

    # 5. Guardar JSONs
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Inventario dispositivos
    inv_path = os.path.join(EXPORT_DIR, "inventario_F01_F02_{}.json".format(timestamp))
    with open(inv_path, 'w') as f:
        json.dump({
            "version": "1.0",
            "timestamp": timestamp,
            "documento": doc.Title,
            "nivel_referencia_m": NIVEL_PISO5_ELEV_M,
            "paneles_referencia": TARGET_APARTAMENTOS,
            "total_dispositivos": len(dispositivos),
            "dispositivos": dispositivos,
        }, f, indent=2, ensure_ascii=False)
    print("\n[OK] Inventario guardado: {}".format(inv_path))

    # Ruteo conduits
    rut_path = os.path.join(EXPORT_DIR, "ruteo_conduits_F01_F02_{}.json".format(timestamp))
    with open(rut_path, 'w') as f:
        json.dump({
            "version": "1.0",
            "timestamp": timestamp,
            "documento": doc.Title,
            "conduit_types": conduit_types,
            "conduits_F01_F02": ruteo["conduits_F01_F02"],
            "fittings_F01_F02": ruteo["fittings_F01_F02"],
            "conduits_todos": ruteo["conduits_todos"],
            "fittings_todos": ruteo["fittings_todos"],
        }, f, indent=2, ensure_ascii=False)
    print("[OK] Ruteo guardado: {}".format(rut_path))

    # Resumen final
    print("\n" + "="*70)
    print("EXPORTACIÓN COMPLETA")
    print("="*70)
    print("Directorio: {}".format(EXPORT_DIR))
    print("Dispositivos F01/F02: {}".format(len(dispositivos)))
    print("Conduits Piso 5: {}".format(len(ruteo["conduits_F01_F02"])))
    print("Fittings Piso 5: {}".format(len(ruteo["fittings_F01_F02"])))
    print("Tipos conduit: {}".format(len(conduit_types)))
    print("="*70)

    return EXPORT_DIR

# Ejecutar si es script principal
if __name__ == "__main__":
    main()