# -*- coding: utf-8 -*-
# CREAR_DISPOSITIVOS_E06_FINAL_v17.py
#
# Limpia dispositivos E06 mal colocados, crea los 44 correctos (Piso 5) con hosts
# (paredes para interruptores/tomas, techos para iluminacion/ventiladores).
# Corrige: doc definido al inicio (sin NameError), sin TransactionFailureHandlingOptions
# ni FailureHandlingOptions (no existen en esta version de Revit API).
#
# Nota: si Revit muestra un dialogo de advertencia (objetos muy cercanos),
# dale a "continuar" una vez. No hay forma de suprimirlo desde IronPython 2.7.
#
# Ejecutar en consola IronPython de pyRevit dentro de Revit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\CREAR_DISPOSITIVOS_E06_FINAL_v17.py").read())
#   crear_dispositivos_e06(doc, dry_run=False)
#
# Genera:
#   D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_inventario_v17.json

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

# DOC definido al inicio para evitar NameError al usar exec()
try:
    doc = __revit__.ActiveUIDocument.Document
    app = __revit__.Application
except Exception:
    doc = None
    app = None

SCRIPT_VERSION = "CREAR_DISPOSITIVOS_E06_FINAL_v17-2026-11-12"
SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_inventario_v17.json"

# 44 dispositivos E06 (coordenadas reales del v13, Piso 5)
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
    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            if fam.Name != nombre_familia:
                continue
            ids = fam.GetFamilySymbolIds()
            if not ids:
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
        except Exception:
            continue
    return None


def obtener_host(doc, punto_ft, host_tipo, nivel_id, radio_ft=8.0 * 3.280839895):
    """Busca el muro o techo mas cercano al punto para usarlo como host."""
    if host_tipo == "muro":
        from Autodesk.Revit.DB import ElementLevelFilter
        nivel_filter = ElementLevelFilter(ElementId(Int64(nivel_id)))
        filtro_cat = ElementCategoryFilter(BuiltInCategory.OST_Walls)
        muros = FilteredElementCollector(doc).WherePasses(filtro_cat).WherePasses(nivel_filter)

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
                if dist <= radio_ft and (mejor_dist is None or dist < mejor_dist):
                    mejor_dist = dist
                    mejor_muro = w
            except Exception:
                continue
        return mejor_muro

    elif host_tipo == "techo":
        filtro_cat = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
        techos = FilteredElementCollector(doc).WherePasses(filtro_cat)

        mejor_techo = None
        mejor_dist = None
        for c in techos:
            try:
                tipo_nombre = ""
                try:
                    tipo_nombre = c.Name
                except Exception:
                    pass
                if "Falso techo continuo" not in tipo_nombre and "placa de yeso" not in tipo_nombre and "ceiling" not in tipo_nombre.lower():
                    continue
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

    return None


def limpiar_dispositivos_e06(doc):
    """Elimina FamilyInstance en rango E06+Piso5 que sean de categorias electricas."""
    E06_X_MIN, E06_X_MAX = -1.0, 8.0
    E06_Y_MIN, E06_Y_MAX = 8.0, 19.0
    PISO5_Z_MIN, PISO5_Z_MAX = 12.0, 18.0

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
        print("ERROR: doc no definido. Ejecuta primero: doc = __revit__.ActiveUIDocument.Document")
        return {"error": "doc_no_definido"}

    nivel = obtener_nivel(doc, "Piso 5")
    if nivel is None:
        print("ERROR: no se encontro el nivel 'Piso 5'")
        return {"error": "nivel_no_encontrado"}

    nivel_id = eid(nivel.Id)
    nivel_elev_m = nivel.Elevation * 0.3048

    # Limpiar dispositivos previos
    eliminados = limpiar_dispositivos_e06(doc)
    print("Dispositivos E06 previos eliminados: {}".format(eliminados))

    elementos_creados = []
    total_creados = 0
    errores = 0

    t = Transaction(doc, "Crear dispositivos E06 con hosts")
    t.Start()

    try:
        for i, disp in enumerate(DISPOSITIVOS_E06, 1):
            nombre = disp["nombre"]
            x_m = disp["x"]
            y_m = disp["y"]
            z_m = disp["z"]
            rot = disp.get("rot", 0)
            familia_nom = disp["familia"]
            simbolo_nom = disp.get("simbolo")
            host_tipo = disp.get("host_tipo", "muro")

            px_ft = m_a_ft(x_m)
            py_ft = m_a_ft(y_m)
            pz_ft = m_a_ft(z_m)
            punto = XYZ(px_ft, py_ft, pz_ft)

            simbolo = obtener_simbolo(doc, familia_nom, simbolo_nom)
            if simbolo is None:
                errores += 1
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_m,
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
                    "x_m": x_m, "y_m": y_m, "z_m": z_m,
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
            host = obtener_host(doc, punto, host_tipo, nivel_id)

            try:
                if host is not None:
                    inst = doc.Create.NewFamilyInstance(punto, simbolo, host, StructuralType.NonStructural)
                else:
                    inst = doc.Create.NewFamilyInstance(punto, simbolo, StructuralType.NonStructural)

                unique_id = inst.UniqueId
                element_id = eid(inst.Id)

                categoria = inst.Category.Name if inst.Category else "Sin categoria"
                nivel_nom = nivel_nombre(doc, eid(inst.LevelId)) if inst.LevelId else None

                host_categoria = host.Category.Name if host is not None and host.Category else None
                host_id = eid(host.Id) if host is not None else None

                total_creados += 1
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_m,
                    "rot": rot,
                    "familia": familia_nom,
                    "simbolo": simbolo_nom,
                    "categoria": categoria,
                    "nivel_nombre": nivel_nom,
                    "nivel_id": eid(inst.LevelId) if inst.LevelId else None,
                    "unique_id": unique_id,
                    "element_id": element_id,
                    "host_tipo": host_tipo,
                    "host_categoria": host_categoria,
                    "host_id": host_id,
                    "accion": "creado",
                })
            except Exception as exc:
                errores += 1
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_m,
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

    # Generar JSON de trazabilidad
    datos = {
        "script_version": SCRIPT_VERSION,
        "fecha": "2026-11-12",
        "timestamp_ejecucion": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "nivel": "Piso 5",
        "apartamento": "E06",
        "filtro": "Creacion de 44 dispositivos E06 con hosts (sin parametro compartido)",
        "total_dispositivos_dxf": len(DISPOSITIVOS_E06),
        "eliminados_previos": eliminados,
        "total_creados": total_creados,
        "errores": errores,
        "nivel_id": nivel_id,
        "nivel_elev_m": round(nivel_elev_m, 4),
        "elementos": elementos_creados,
    }

    directorio = os.path.dirname(SALIDA_JSON)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)

    with open(SALIDA_JSON, "w") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("=== CREAR_DISPOSITIVOS_E06_FINAL_v17 ===")
    print("Dispositivos DXF: {}".format(len(DISPOSITIVOS_E06)))
    print("Eliminados previos: {}".format(eliminados))
    print("Creados: {}".format(total_creados))
    print("Errores: {}".format(errores))
    print("JSON guardado en: {}".format(SALIDA_JSON))
    print("=" * 70)

    return datos


# Si se ejecuta directamente como script (no via exec)
if doc is not None and __name__ == "__main__":
    crear_dispositivos_e06(doc, dry_run=False)
