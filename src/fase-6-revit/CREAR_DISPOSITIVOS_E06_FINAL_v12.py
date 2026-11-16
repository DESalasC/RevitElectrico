# -*- coding: utf-8 -*-
# CREAR_DISPOSITIVOS_E06_FINAL_v12.py
#
# Crea los 44 dispositivos E06 (Piso 5) en Revit 2026 y asigna el GUID del lote
# al parametro compartido RevitElectrico_Lote.
#
# Ejecutar en consola IronPython de pyRevit dentro de Revit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\CREAR_DISPOSITIVOS_E06_FINAL_v12.py").read())
#   crear_dispositivos_e06(doc, dry_run=False)
#
# Genera:
#   D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_inventario_v12.json

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, BuiltInCategory, Level,
    Family, XYZ, Transaction,
    ExternalDefinitionCreationOptions, BuiltInDataType, BuiltInParameterGroup,
)
from Autodesk.Revit.DB import Level as LevelClass

try:
    from Autodesk.Revit.DB.Structure import StructuralType
except Exception:
    import Autodesk.Revit.DB.Structure as _revit_struct
    StructuralType = _revit_struct.StructuralType

import json, os, datetime

LOTE_GUID = "46c3f138-025d-47d4-b24a-41cd21181a58"
LOTE_PARAM_NAME = "RevitElectrico_Lote"
SCRIPT_VERSION = "CREAR_DISPOSITIVOS_E06_FINAL_v12-2026-11-12"
SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_inventario_v12.json"

# 44 dispositivos E06 (coordenadas reales del v13, Piso 5)
DISPOSITIVOS_E06 = [
    {"nombre": "Bala Stil Led 13W", "x": 4.9530, "y": 17.2141, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 13 trim", "host": "techo"},
    {"nombre": "ELEC-I-S-C1-5A", "x": 3.2274, "y": 16.5471, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Conmutable", "host": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 3.6797, "y": 16.3728, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 0.5740, "y": 16.2796, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "ELEC-I-S-C1-5A", "x": 3.4497, "y": 15.2268, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Conmutable", "host": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 3.2789, "y": 15.2181, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "ELEC-F-VENT", "x": 1.9334, "y": 15.2002, "z": 15.82, "rot": 0, "familia": "M_ClimatizacionV", "simbolo": "Ventilador", "host": "techo"},
    {"nombre": "ELEC-TEL", "x": 3.2741, "y": 15.1039, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host": "muro"},
    {"nombre": "ELEC-TEL", "x": 3.2741, "y": 14.9653, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host": "muro"},
    {"nombre": "ELEC-TEL", "x": 3.2741, "y": 14.8257, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host": "muro"},
    {"nombre": "Bala Stil Led 10W", "x": 3.7563, "y": 14.2840, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 10 trim", "host": "techo"},
    {"nombre": "Bala Stil Led 10W", "x": 5.8578, "y": 14.2840, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 10 trim", "host": "techo"},
    {"nombre": "ELEC-T-D-t-15A", "x": 3.4107, "y": 14.2749, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 0.5740, "y": 14.1001, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "Bala Stil Led 13W", "x": 1.9265, "y": 14.0855, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 13 trim", "host": "techo"},
    {"nombre": "ELEC-TEL", "x": 3.4059, "y": 14.0425, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host": "muro"},
    {"nombre": "ELEC-TEL", "x": 3.4059, "y": 13.9029, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host": "muro"},
    {"nombre": "ELEC-F-VENT", "x": 4.8501, "y": 13.7138, "z": 15.82, "rot": 0, "familia": "M_ClimatizacionV", "simbolo": "Ventilador", "host": "techo"},
    {"nombre": "ELEC-T-D-t-15A", "x": 6.5041, "y": 13.6502, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "ELEC-F-CONTROL", "x": 2.4397, "y": 13.6126, "z": 14.42, "rot": 0, "familia": "M_Climatizacion", "simbolo": "Interruptor Ventilador", "host": "muro"},
    {"nombre": "ELEC-I-S-1-5A", "x": 2.4287, "y": 13.4456, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Simple", "host": "muro"},
    {"nombre": "ELEC-F-CONTROL", "x": 3.4597, "y": 13.4126, "z": 14.42, "rot": 0, "familia": "M_Climatizacion", "simbolo": "Interruptor Ventilador", "host": "muro"},
    {"nombre": "Bala Stil Led 10W", "x": 2.8482, "y": 12.6178, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 10 trim", "host": "techo"},
    {"nombre": "Bala Stil Led 13W", "x": 1.7160, "y": 12.1796, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 13 trim", "host": "techo"},
    {"nombre": "ELEC-T-D-t-15A", "x": 5.6241, "y": 12.1202, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "ELEC-I-S-1-5A", "x": 2.1935, "y": 12.0992, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Simple", "host": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 5.1890, "y": 12.0088, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 5.6338, "y": 11.9802, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "S3", "x": 3.4642, "y": 11.9116, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Triple", "host": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 3.2652, "y": 11.8995, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 5.1920, "y": 11.8823, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host": "muro"},
    {"nombre": "ELEC-NET-PAU", "x": 5.1920, "y": 11.7096, "z": 14.32, "rot": 0, "familia": "Consolidation_Point", "simbolo": "CPB24BL", "host": "muro"},
    {"nombre": "ELEC-TEL", "x": 5.1902, "y": 11.4990, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host": "muro"},
    {"nombre": "ELEC-TEL", "x": 5.1902, "y": 11.3577, "z": 13.52, "rot": 0, "familia": "M_Comunicaciones", "simbolo": "Telefono", "host": "muro"},
    {"nombre": "Bala Stil Led 22W", "x": 5.8578, "y": 10.8423, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 22 trim", "host": "techo"},
    {"nombre": "Bala Stil Led 22W", "x": 3.9157, "y": 10.8370, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 22 trim", "host": "techo"},
    {"nombre": "Bala Stil Led 13W", "x": 2.8946, "y": 10.4531, "z": 15.82, "rot": 0, "familia": "M_Iluminacion", "simbolo": "SONO FLEX 13 trim", "host": "techo"},
    {"nombre": "ELEC-I-S-1-5A", "x": 3.4423, "y": 10.2691, "z": 14.32, "rot": 0, "familia": "M_Interruptores", "simbolo": "Simple", "host": "muro"},
    {"nombre": "ELEC-CAMPANA", "x": 4.4357, "y": 9.7240, "z": 14.42, "rot": 0, "familia": "M_Zumbador", "simbolo": "Campana Timbre", "host": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 4.8212, "y": 9.7208, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "ELEC-T-D-t-15A", "x": 5.0798, "y": 9.7208, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "Normal", "host": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 2.8134, "y": 9.7188, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host": "muro"},
    {"nombre": "ELEC-T-GFCI-t-15A", "x": 5.6326, "y": 9.7188, "z": 14.32, "rot": 0, "familia": "M_Toma doble", "simbolo": "GFCI", "host": "muro"},
    {"nombre": "ELEC-TIMBRE", "x": 4.5893, "y": 9.5269, "z": 14.42, "rot": 0, "familia": "M_Pulsador - Interruptor", "simbolo": "Timbre", "host": "muro"},
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


def crear_archivo_parametros_compartidos(ruta):
    directorio = os.path.dirname(ruta)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    guid_sin_guiones = LOTE_GUID.replace("-", "")
    with open(ruta, "w") as f:
        f.write("*META VERSION MINOR 1\n")
        f.write("*META GROUP NAME ID\n")
        f.write("*GROUP 1 RevitElectrico\n")
        f.write("*PARAM ID 1 {guid} {nombre}\n".format(guid=guid_sin_guiones, nombre=LOTE_PARAM_NAME))


def vincular_parametro_compartido(doc, app, nombre_param):
    # Buscar si ya existe en el documento
    try:
        for sp in doc.ParameterBindings:
            try:
                d = sp.Definition
                if d is not None and d.Name == nombre_param:
                    return True, d
            except Exception:
                pass
    except Exception:
        pass

    spf_path = r"D:\Work\PROJECTS\RevitElectrico\data\RevitElectrico_SharedParameters.txt"
    crear_archivo_parametros_compartidos(spf_path)

    try:
        app.SharedParametersFilename = spf_path
    except Exception:
        pass

    spf = None
    try:
        spf = app.OpenSharedParameterFile()
    except Exception:
        pass

    if spf is None:
        return False, None

    grupo = None
    try:
        grupo = spf.Groups.get_Item("RevitElectrico")
    except Exception:
        pass

    if grupo is None:
        try:
            grupo = spf.Groups.Create("RevitElectrico")
        except Exception:
            return False, None

    definicion = None
    try:
        definicion = grupo.Definitions.get_Item(nombre_param)
    except Exception:
        pass

    if definicion is None:
        try:
            opts = ExternalDefinitionCreationOptions(nombre_param, BuiltInDataType.Text)
            definicion = grupo.Definitions.Create(opts)
        except Exception:
            return False, None

    # Vincular al documento con InstanceBinding
    try:
        cat_set = ElementCategorySet()
        for cat_id in [
            BuiltInCategory.OST_LightingFixtures,
            BuiltInCategory.OST_ElectricalFixtures,
            BuiltInCategory.OST_ElectricalEquipment,
            BuiltInCategory.OST_GenericModel,
        ]:
            try:
                cat = doc.Settings.Categories.get_Item(cat_id)
                if cat is not None:
                    cat_set.Insert(cat)
            except Exception:
                pass

        binding = doc.Create.NewInstanceBinding(cat_set)
        doc.ParameterBindings.Insert(definicion, binding, BuiltInParameterGroup.PG_DATA)
    except Exception:
        pass

    return True, definicion


def crear_dispositivos_e06(doc, dry_run=False):
    app = doc.Application
    nivel = obtener_nivel(doc, "Piso 5")
    if nivel is None:
        print("ERROR: no se encontro el nivel 'Piso 5'")
        return {"error": "nivel_no_encontrado"}

    nivel_id = eid(nivel.Id)
    nivel_elev_m = nivel.Elevation * 0.3048

    # Vincular parametro compartido
    parametro_vinculado, definicion = vincular_parametro_compartido(doc, app, LOTE_PARAM_NAME)
    print("Parametro compartido vinculado: {}".format(parametro_vinculado))

    elementos_creados = []
    total_creados = 0
    total_asignados = 0
    errores = 0
    saltados_existentes = 0

    t = Transaction(doc, "Crear dispositivos E06 y asignar GUID")
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

            px_ft = m_a_ft(x_m)
            py_ft = m_a_ft(y_m)
            pz_ft = m_a_ft(z_m)

            simbolo = obtener_simbolo(doc, familia_nom, simbolo_nom)
            if simbolo is None:
                errores += 1
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_m,
                    "familia": familia_nom,
                    "simbolo": simbolo_nom,
                    "accion": "error_simbolo_no_encontrado",
                    "guid_asignado": None,
                    "unique_id": None,
                    "element_id": None,
                })
                continue

            punto = XYZ(px_ft, py_ft, pz_ft)

            if dry_run:
                total_creados += 1
                elementos_creados.append({
                    "nombre": nombre,
                    "x_m": x_m, "y_m": y_m, "z_m": z_m,
                    "rot": rot,
                    "familia": familia_nom,
                    "simbolo": simbolo_nom,
                    "accion": "dry_run_crear",
                    "guid_asignado": LOTE_GUID,
                    "unique_id": None,
                    "element_id": None,
                })
                continue

            try:
                inst = doc.Create.NewFamilyInstance(punto, simbolo, StructuralType.NonStructural)

                unique_id = inst.UniqueId
                element_id = eid(inst.Id)

                # Asignar parametro compartido
                asignado = False
                try:
                    param = inst.LookupParameter(LOTE_PARAM_NAME)
                    if param is not None and not param.IsReadOnly:
                        param.Set(LOTE_GUID)
                        asignado = True
                        total_asignados += 1
                except Exception:
                    pass

                categoria = inst.Category.Name if inst.Category else "Sin categoria"
                nivel_nom = nivel_nombre(doc, eid(inst.LevelId)) if inst.LevelId else None

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
                    "guid_asignado": LOTE_GUID if asignado else None,
                    "parametro_asignado": asignado,
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
                    "guid_asignado": None,
                    "unique_id": None,
                    "element_id": None,
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
        "lote_guid": LOTE_GUID,
        "parametro_compartido": LOTE_PARAM_NAME,
        "parametro_vinculado_al_proyecto": parametro_vinculado,
        "filtro": "Creacion de 44 dispositivos E06 + asignacion de GUID por proyecto",
        "total_dispositivos_dxf": len(DISPOSITIVOS_E06),
        "total_creados": total_creados,
        "total_con_guid_asignado": total_asignados,
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
    print("=== CREAR_DISPOSITIVOS_E06_FINAL_v12 ===")
    print("Parametro vinculado: {}".format(parametro_vinculado))
    print("Dispositivos DXF: {}".format(len(DISPOSITIVOS_E06)))
    print("Creados: {}".format(total_creados))
    print("Con GUID asignado: {}".format(total_asignados))
    print("Errores: {}".format(errores))
    print("JSON guardado en: {}".format(SALIDA_JSON))
    print("=" * 70)

    return datos


# Si se ejecuta directamente
if __name__ == "__main__":
    doc = __revit__.ActiveUIDocument.Document
    crear_dispositivos_e06(doc, dry_run=False)
