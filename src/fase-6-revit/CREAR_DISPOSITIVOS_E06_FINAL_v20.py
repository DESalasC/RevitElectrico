# -*- coding: utf-8 -*-
# CREAR_DISPOSITIVOS_E06_FINAL_v20.py
#
# Crea los 44 dispositivos E06 (Piso 5) con coordenada Z absoluta mundial correcta.
#
# Metodo:
#   - Limpia dispositivos previos en rango E06+Piso5
#   - Crea SIN nivel: NewFamilyInstance(punto_Z_absoluto_ft, simbolo, host, StructuralType.NonStructural)
#     Esto hace que Z sea coordenada absoluta mundial (regla datum G5: Z = nivel.Elevation + altura_local).
#   - No se puede asignar LevelId tras crear (es read-only), pero las coordenadas XYZ son correctas.
#   - Host: muros para interruptores/tomas/comunicaciones, techos para iluminación/ventiladores.
#
# Ejecutar en consola IronPython de pyRevit dentro de Revit 2026:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\CREAR_DISPOSITIVOS_E06_FINAL_v20.py").read())
#   crear_dispositivos_e06(doc, dry_run=False)
#
# Genera:
#   D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_inventario_v20.json

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")

from System import Int64

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, BuiltInCategory, Level,
    Family, XYZ, Transaction,
    ElementCategoryFilter,
)
from Autodesk.Revit.DB import Level as LevelClass

try:
    from Autodesk.Revit.DB.Structure import StructuralType
except Exception:
    import Autodesk.Revit.DB.Structure as _revit_struct
    StructuralType = _revit_struct.StructuralType

import json, os, datetime

try:
    doc = __revit__.ActiveUIDocument.Document
    app = __revit__.Application
except Exception:
    doc = None
    app = None

SCRIPT_VERSION = "CREAR_DISPOSITIVOS_E06_FINAL_v20-2026-11-12"
SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_inventario_v20.json"

# Nivel Piso 5 (referencia para elevación)
PISO5_NOMBRE = "Piso 5"
PISO5_ELEV_M = 13.22  # metros

# Rangos E06 + Piso 5 (para limpieza y verificación)
E06_X_MIN, E06_X_MAX = -1.0, 8.0
E06_Y_MIN, E06_Y_MAX = 8.0, 19.0
PISO5_Z_MIN, PISO5_Z_MAX = 12.0, 18.0

# 44 dispositivos E06 (coordenadas absolutas en metros, Z absoluta mundial)
DISPOSITIVOS_E06 = [
    {"nombre": "Bala Stil Led 13W", "x": 4.9530, "y": 17.2141, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 13 trim", "host_tipo": "techo"},
    {"nombre": "ELEC-I-S-C1-5A", "x": 3.2274, "y": 16.5471, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Conmutable", "host_tipo": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 3.6797, "y": 16.3728, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host_tipo": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 0.5740, "y": 16.2796, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "ELEC-I-S-C1-5A", "x": 3.4497, "y": 15.2268, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Conmutable", "host_tipo": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 3.2789, "y": 15.2181, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "ELEC-F-VENT", "x": 1.9334, "y": 15.2002, "z": 15.82, "rot": 0, "familia": "M_ClimatizacionV", "simbolo": "Ventilador", "host_tipo": "techo"},
    {"nombre": "ELEC-TEL", "x": 3.2741, "y": 15.1039, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host_tipo": "muro"},
    {"nombre": "ELEC-TEL", "x": 3.2741, "y": 14.9653, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host_tipo": "muro"},
    {"nombre": "ELEC-TEL", "x": 3.2741, "y": 14.8257, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host_tipo": "muro"},
    {"nombre": "Bala Stil Led 10W", "x": 3.7563, "y": 14.2840, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 10 trim", "host_tipo": "techo"},
    {"nombre": "Bala Stil Led 10W", "x": 5.8578, "y": 14.2840, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 10 trim", "host_tipo": "techo"},
    {"nombre": "ELEC-T-D-t-15A", "x": 3.4107, "y": 14.2749, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 0.5740, "y": 14.1001, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "Bala Stil Led 13W", "x": 1.9265, "y": 14.0855, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 13 trim", "host_tipo": "techo"},
    {"nombre": "ELEC-TEL", "x": 3.4059, "y": 14.0425, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host_tipo": "muro"},
    {"nombre": "ELEC-TEL", "x": 3.4059, "y": 13.9029, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host_tipo": "muro"},
    {"nombre": "ELEC-F-VENT", "x": 4.8501, "y": 13.7138, "z": 15.82, "rot": 0, "familia": "M_ClimatizacionV", "simbolo": "Ventilador", "host_tipo": "techo"},
    {"nombre": "ELEC-T-D-t-15A", "x": 6.5041, "y": 13.6502, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "ELEC-F-CONTROL", "x": 2.4397, "y": 13.6126, "z": 14.42, "rot": 0, "familia": "M_Climatizacion", "simbolo": "Interruptor Ventilador", "host_tipo": "muro"},
    {"nombre": "ELEC-I-S-1-5A", "x": 2.4287, "y": 13.4456, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Simple", "host_tipo": "muro"},
    {"nombre": "ELEC-F-CONTROL", "x": 3.4597, "y": 13.4126, "z": 14.42, "rot": 0, "familia": "M_Climatizacion", "simbolo": "Interruptor Ventilador", "host_tipo": "muro"},
    {"nombre": "Bala Stil Led 10W", "x": 2.8482, "y": 12.6178, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 10 trim", "host_tipo": "techo"},
    {"nombre": "Bala Stil Led 13W", "x": 1.7160, "y": 12.1796, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 13 trim", "host_tipo": "techo"},
    {"nombre": "ELEC-T-D-t-15A", "x": 5.6241, "y": 12.1202, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "ELEC-I-S-1-5A", "x": 2.1935, "y": 12.0992, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Simple", "host_tipo": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 5.1890, "y": 12.0088, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 5.6338, "y": 11.9802, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "S3", "x": 3.4642, "y": 11.9116, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Triple", "host_tipo": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 3.2652, "y": 11.8995, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host_tipo": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 5.1920, "y": 11.8823, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host_tipo": "muro"},
    {"nombre": "ELEC-NET-PAU", "x": 5.1920, "y": 11.7096, "z": 14.32, "rot": 0, "familia": "Consolidation_Point", "simbolo": "CPB24BL", "host_tipo": "muro"},
    {"nombre": "ELEC-TEL", "x": 5.1902, "y": 11.4990, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host_tipo": "muro"},
    {"nombre": "ELEC-TEL", "x": 5.1902, "y": 11.3577, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host_tipo": "muro"},
    {"nombre": "Bala Stil Led 22W", "x": 5.8578, "y": 10.8423, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 22 trim", "host_tipo": "techo"},
    {"nombre": "Bala Stil Led 22W", "x": 3.9157, "y": 10.8370, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 22 trim", "host_tipo": "techo"},
    {"nombre": "Bala Stil Led 13W", "x": 2.8946, "y": 10.4531, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 13 trim", "host_tipo": "techo"},
    {"nombre": "ELEC-I-S-1-5A", "x": 3.4423, "y": 10.2691, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Simple", "host_tipo": "muro"},
    {"nombre": "ELEC-CAMPANA", "x": 4.4357, "y": 9.7240, "z": 14.42, "rot": 0, "familia": "M_Zumbador", "simbolo": "Campana Timbre", "host_tipo": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 4.8212, "y": 9.7208, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 5.0798, "y": 9.7208, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host_tipo": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 2.8134, "y": 9.7188, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host_tipo": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 5.6326, "y": 9.7188, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host_tipo": "muro"},
    {"nombre": "ELEC-TIMBRE", "x": 4.5893, "y": 9.5269, "z": 14.42, "rot": 0, "familia": "M_Pulsador - Interruptor", "simbolo": "Timbre", "host_tipo": "muro"},
]


def ft_a_m(ft):
    return ft / 3.280839895


def m_a_ft(m):
    return m * 3.280839895


def eid(eid_obj):
    try:
        return int(eid_obj.IntegerValue)
    except Exception:
        return int(str(eid_obj))


def safe_str(valor):
    try:
        if valor is None:
            return None
        return str(valor)
    except Exception:
        return "(no accesible)"


def nivel_nombre(doc, nivel_id_int):
    if nivel_id_int is None:
        return None
    try:
        for lv in FilteredElementCollector(doc).OfClass(LevelClass):
            if lv.Id.IntegerValue == nivel_id_int:
                return lv.Name
    except Exception:
        pass
    return None


def obtener_nivel(doc, nombre_nivel):
    for lv in FilteredElementCollector(doc).OfClass(LevelClass):
        if lv.Name == nombre_nivel:
            return lv
    return None


def obtener_simbolo(doc, nombre_familia, nombre_simbolo=None):
    """Busca una familia y su símbolo por nombre exacto. Retorna None si no existe."""
    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            if fam.Name != nombre_familia:
                continue
            ids = fam.GetFamilySymbolIds()
            if not ids:
                print("  ADVERTENCIA: Familia '{}' existe pero no tiene símbolos".format(nombre_familia))
                continue
            for sid in ids:
                try:
                    sym = doc.GetElement(sid)
                    if sym is None or not sym.IsActive:
                        continue
                    if nombre_simbolo is not None:
                        try:
                            if sym.Name != nombre_simbolo:
                                continue
                        except Exception:
                            pass
                    return sym
                except Exception:
                    continue
            # Familia encontrada pero ningún símbolo coincide con nombre_simbolo
            if nombre_simbolo is not None:
                print("  ADVERTENCIA: Familia '{}' encontrada pero símbolo '{}' no existe".format(
                    nombre_familia, nombre_simbolo))
                print("    Símbolos disponibles: {}".format(
                    [safe_str(doc.GetElement(sid).Name) for sid in ids if doc.GetElement(sid) is not None]))
        except Exception:
            continue
    if nombre_familia:
        print("  ADVERTENCIA: Familia '{}' no encontrada en el proyecto".format(nombre_familia))
    return None


def obtener_host_muro(doc, punto_ft, nivel_elev_ft, radio_ft=10.0 * 3.280839895):
    """Busca el muro mas cercano al punto en XY, verificando que cruce la elevación del nivel Piso 5."""
    filtro_cat = ElementCategoryFilter(BuiltInCategory.OST_Walls)
    muros = FilteredElementCollector(doc).WherePasses(filtro_cat)

    mejor_muro = None
    mejor_dist = None
    for w in muros:
        try:
            loc = w.Location
            if not loc or not hasattr(loc, 'Curve'):
                continue
            curva = loc.Curve
            if curva is None:
                continue
            p1 = curva.GetEndPoint(0)
            p2 = curva.GetEndPoint(1)
            dx = p2.X - p1.X
            dy = p2.Y - p1.Y
            if dx == 0 and dy == 0:
                dist = ((punto_ft.X - p1.X)**2 + (punto_ft.Y - p1.Y)**2) ** 0.5
            else:
                t = ((punto_ft.X - p1.X) * dx + (punto_ft.Y - p1.Y) * dy) / (dx * dx + dy * dy)
                t = max(0, min(1, t))
                cx = p1.X + t * dx
                cy = p1.Y + t * dy
                dist = ((punto_ft.X - cx)**2 + (punto_ft.Y - cy)**2) ** 0.5

            try:
                bb = w.get_BoundingBox(None)
                if bb is not None:
                    z_min_muro = bb.Min.Z
                    z_max_muro = bb.Max.Z
                    if z_max_muro < nivel_elev_ft - 2.0 or z_min_muro > nivel_elev_ft + 2.0:
                        continue
            except Exception:
                pass

            if dist <= radio_ft and (mejor_dist is None or dist < mejor_dist):
                mejor_dist = dist
                mejor_muro = w
        except Exception:
            continue
    return mejor_muro


def obtener_host_techo(doc, punto_ft, radio_ft=10.0 * 3.280839895):
    """Busca el techo mas cercano al punto en XY."""
    filtro_cat = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
    techos = FilteredElementCollector(doc).WherePasses(filtro_cat)

    mejor_techo = None
    mejor_dist = None
    for c in techos:
        try:
            loc = c.Location
            p = None
            if loc is not None:
                if hasattr(loc, 'Point'):
                    p = loc.Point
                elif hasattr(loc, 'Curve'):
                    curva = loc.Curve
                    if curva is not None:
                        p_mid = curva.Evaluate(0.5, True)
                        p = p_mid
            if p is None:
                try:
                    bb = c.get_BoundingBox(None)
                    if bb is not None:
                        cx = (bb.Min.X + bb.Max.X) / 2.0
                        cy = (bb.Min.Y + bb.Max.Y) / 2.0
                        p = XYZ(cx, cy, 0.0)
                except Exception:
                    p = None
            if p is None:
                continue
            dist = ((punto_ft.X - p.X)**2 + (punto_ft.Y - p.Y)**2) ** 0.5
            if dist <= radio_ft and (mejor_dist is None or dist < mejor_dist):
                mejor_dist = dist
                mejor_techo = c
        except Exception:
            continue
    return mejor_techo


def limpiar_dispositivos_e06(doc):
    """Elimina FamilyInstance en rango E06+Piso5 de categorías eléctricas."""
    ids_a_eliminar = []
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            if not isinstance(fi, FamilyInstance):
                continue
            unique_id = safe_str(fi.UniqueId)
            if not unique_id:
                continue

            x_m = y_m = z_m = None
            try:
                loc = fi.Location
                if loc is not None and hasattr(loc, 'Point'):
                    p = loc.Point
                    x_m = round(ft_a_m(p.X), 4)
                    y_m = round(ft_a_m(p.Y), 4)
                    z_m = round(ft_a_m(p.Z), 4)
            except Exception:
                pass

            if x_m is not None and y_m is not None and z_m is not None:
                if (E06_X_MIN <= x_m <= E06_X_MAX and
                    E06_Y_MIN <= y_m <= E06_Y_MAX and
                    PISO5_Z_MIN <= z_m <= PISO5_Z_MAX):
                    cat = fi.Category.Name if fi.Category else ""
                    if any(c in cat for c in ["Lighting", "Electrical", "Communication", "Data"]):
                        ids_a_eliminar.append(fi.Id)
        except Exception:
            continue

    if ids_a_eliminar:
        t = Transaction(doc, "Eliminar dispositivos E06 previos")
        t.Start()
        try:
            for eid_to_delete in ids_a_eliminar:
                try:
                    doc.Delete(eid_to_delete)
                except Exception:
                    pass
            t.Commit()
        except Exception:
            try:
                t.RollBack()
            except Exception:
                pass

    return len(ids_a_eliminar)


def crear_dispositivos_e06(doc, dry_run=False):
    if doc is None:
        print("ERROR: doc no definido.")
        return {"error": "doc_no_definido"}

    nivel = obtener_nivel(doc, PISO5_NOMBRE)
    if nivel is None:
        print("ERROR: no se encontro el nivel '{}'".format(PISO5_NOMBRE))
        return {"error": "nivel_no_encontrado"}

    nivel_id = eid(nivel.Id)
    nivel_elev_m = nivel.Elevation * 0.3048
    nivel_elev_ft = nivel.Elevation

    print("Nivel referencia '{}': id={}, elevación={:.4f} m".format(PISO5_NOMBRE, nivel_id, nivel_elev_m))
    print("Creando SIN nivel para que Z sea coordenada absoluta mundial")

    # Limpiar dispositivos previos
    eliminados = limpiar_dispositivos_e06(doc)
    print("Dispositivos E06 previos eliminados: {}".format(eliminados))

    elementos_creados = []
    total_creados = 0
    errores = 0
    simbolos_no_encontrados = set()

    t = Transaction(doc, "Crear dispositivos E06 con Z absoluto v20")
    t.Start()

    try:
        for i, disp in enumerate(DISPOSITIVOS_E06, 1):
            nombre = disp["nombre"]
            x_m = disp["x"]
            y_m = disp["y"]
            z_abs_m = disp["z"]
            rot = disp.get("rot", 0)
            familia_nom = disp["familia"]
            simbolo_nom = disp.get("simbolo")
            host_tipo = disp.get("host_tipo", "muro")

            # Z absoluto mundial en pies (no offset desde nivel)
            px_ft = m_a_ft(x_m)
            py_ft = m_a_ft(y_m)
            pz_abs_ft = m_a_ft(z_abs_m)
            punto = XYZ(px_ft, py_ft, pz_abs_ft)

            simbolo = obtener_simbolo(doc, familia_nom, simbolo_nom)
            if simbolo is None:
                errores += 1
                simbolos_no_encontrados.add("{} / {}".format(familia_nom, simbolo_nom))
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_abs_m,
                    "familia": familia_nom,
                    "simbolo": simbolo_nom,
                    "accion": "error_simbolo_no_encontrado",
                    "unique_id": None,
                    "element_id": None,
                    "host_tipo": host_tipo,
                })
                continue

            if dry_run:
                total_creados += 1
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_abs_m,
                    "rot": rot,
                    "familia": familia_nom,
                    "simbolo": simbolo_nom,
                    "accion": "dry_run_crear",
                    "unique_id": None,
                    "element_id": None,
                    "host_tipo": host_tipo,
                })
                continue

            # Obtener host
            host = None
            if host_tipo == "muro":
                host = obtener_host_muro(doc, punto, nivel_elev_ft)
            elif host_tipo == "techo":
                host = obtener_host_techo(doc, punto)

            try:
                # CREAR SIN nivel: Z es coordenada absoluta mundial
                if host is not None:
                    inst = doc.Create.NewFamilyInstance(punto, simbolo, host, StructuralType.NonStructural)
                else:
                    inst = doc.Create.NewFamilyInstance(punto, simbolo, StructuralType.NonStructural)

                unique_id = inst.UniqueId
                element_id = eid(inst.Id)

                categoria = inst.Category.Name if inst.Category else "Sin categoria"
                nivel_id_inst = eid(inst.LevelId) if inst.LevelId else None
                nivel_nom = nivel_nombre(doc, nivel_id_inst) if nivel_id_inst else None

                # Verificar Z absoluta real despues de crear
                z_real_m = None
                try:
                    loc = inst.Location
                    if loc is not None and hasattr(loc, 'Point'):
                        p = loc.Point
                        z_real_m = round(ft_a_m(p.Z), 4)
                except Exception:
                    pass

                host_categoria = host.Category.Name if host is not None and host.Category else None
                host_id = eid(host.Id) if host is not None else None
                host_unique_id = safe_str(host.UniqueId) if host is not None else None

                total_creados += 1
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_abs_m,
                    "z_real_m": z_real_m,
                    "rot": rot,
                    "familia": familia_nom,
                    "simbolo": simbolo_nom,
                    "categoria": categoria,
                    "nivel_nombre": nivel_nom,
                    "nivel_id": nivel_id_inst,
                    "unique_id": unique_id,
                    "element_id": element_id,
                    "host_tipo": host_tipo,
                    "host_categoria": host_categoria,
                    "host_id": host_id,
                    "host_unique_id": host_unique_id,
                    "accion": "creado",
                })
            except Exception as exc:
                errores += 1
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_abs_m,
                    "familia": familia_nom,
                    "simbolo": simbolo_nom,
                    "accion": "error",
                    "motivo": str(exc)[:200],
                    "unique_id": None,
                    "element_id": None,
                    "host_tipo": host_tipo,
                })

        t.Commit()
    except Exception as exc:
        try:
            t.RollBack()
        except Exception:
            pass
        raise

    # Mostrar símbolos no encontrados
    if simbolos_no_encontrados:
        print("\nADVERTENCIAS - Familias/símbolos no encontrados:")
        for s in sorted(simbolos_no_encontrados):
            print("  - {}".format(s))

    # Generar JSON de trazabilidad
    datos = {
        "script_version": SCRIPT_VERSION,
        "fecha": "2026-11-12",
        "timestamp_ejecucion": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "nivel": PISO5_NOMBRE,
        "apartamento": "E06",
        "filtro": "Creación de 44 dispositivos E06 con Z absoluto mundial (v20, sin nivel)",
        "total_dispositivos_dxf": len(DISPOSITIVOS_E06),
        "eliminados_previos": eliminados,
        "total_creados": total_creados,
        "errores": errores,
        "nivel_id": nivel_id,
        "nivel_elev_m": round(nivel_elev_m, 4),
        "simbolos_no_encontrados": list(simbolos_no_encontrados),
        "elementos": elementos_creados,
    }

    directorio = os.path.dirname(SALIDA_JSON)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)

    with open(SALIDA_JSON, "w") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("=== CREAR_DISPOSITIVOS_E06_FINAL_v20 ===")
    print("Dispositivos DXF: {}".format(len(DISPOSITIVOS_E06)))
    print("Eliminados previos: {}".format(eliminados))
    print("Creados: {}".format(total_creados))
    print("Errores: {}".format(errores))
    print("Z absoluto mundial (no offset desde nivel)")
    print("JSON guardado en: {}".format(SALIDA_JSON))
    print("=" * 70)

    return datos


if doc is not None and __name__ == "__main__":
    crear_dispositivos_e06(doc, dry_run=False)
