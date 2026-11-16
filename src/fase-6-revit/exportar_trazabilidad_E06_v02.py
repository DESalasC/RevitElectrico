# -*- coding: utf-8 -*-
# EXPORTAR_TRAZABILIDAD_E06_v02.py
# Inventario limpio de elementos electricos del Piso 5 en el apartamento E06.
# Corrige duplicados por UniqueId y filtra por rango XY de E06.
#
# Copiar y pegar en consola IronPython de pyRevit dentro de Revit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\exportar_trazabilidad_E06_v02.py").read())
#   doc = __revit__.ActiveUIDocument.Document
#   exportar_trazabilidad_E06(doc)

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, BuiltInCategory, Level
)
from Autodesk.Revit.DB import Level as LevelClass
from System import Int64

import json, os, datetime

SCRIPT_VERSION = "exportar_trazabilidad_E06_v02-2026-11-12-mcp"
SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_inventario_v02.json"
# Filtro por parametro compartido RevitElectrico_Lote (GUID del lote v13) en lugar de LevelId,
# porque LevelId es read-only y Revit lo asigna por defecto (no el nivel Piso 5).
LOTE_GUID = "46c3f138-025d-47d4-b24a-41cd21181a58"
LOTE_PARAM_NAME = "RevitElectrico_Lote"

# Rango aproximado del apartamento E06 (coordenadas XY en metros, con offset DXF->Revit ya aplicado)
E06_X_MIN = 0.0
E06_X_MAX = 6.0
E06_Y_MIN = 12.0
E06_Y_MAX = 20.0

TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _ft_a_m(ft):
    return ft / 3.280839895

def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))

def _safe_str(valor):
    try:
        if valor is None:
            return None
        return str(valor)
    except Exception:
        return "(no accesible)"

def _nivel_nombre(doc, nivel_id_int):
    if nivel_id_int is None:
        return None
    try:
        for lv in FilteredElementCollector(doc).OfClass(LevelClass):
            if lv.Id.IntegerValue == nivel_id_int:
                return lv.Name
    except Exception:
        pass
    return None

def exportar_trazabilidad_E06(doc):
    print("=" * 80)
    print("EXPORTACIÓN DE TRAZABILIDAD LIMPIA - APARTAMENTO E06 / PISO 5")
    print("Script: {}".format(SCRIPT_VERSION))
    print("Documento: {}".format(doc.Title))
    print("Fecha y hora de ejecucion: {}".format(TIMESTAMP))
    print("Rango E06 (m): X [{}, {}] | Y [{}, {}]".format(E06_X_MIN, E06_X_MAX, E06_Y_MIN, E06_Y_MAX))
    print("=" * 80)

    categorias_validas = [
        BuiltInCategory.OST_LightingFixtures,
        BuiltInCategory.OST_ElectricalFixtures,
    ]

    elementos_vistos = {}  # clave: unique_id -> elemento (para eliminar duplicados)
    total_revisados = 0
    total_piso5 = 0

    for cat in categorias_validas:
        for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
            total_revisados += 1
            try:
                if not isinstance(fi, FamilyInstance):
                    continue

                unique_id = _safe_str(fi.UniqueId)
                if not unique_id or unique_id in elementos_vistos:
                    continue  # saltar duplicados por UniqueId

                element_id = _eid(fi.Id)
                categoria = fi.Category.Name if fi.Category else "Sin categoría"

                # Nivel (solo informativo, no se usa para filtrar porque LevelId es read-only)
                nivel_id_raw = None
                nivel_nombre = None
                try:
                    if fi.LevelId is not None:
                        nivel_id_raw = _eid(fi.LevelId)
                        nivel_nombre = _nivel_nombre(doc, nivel_id_raw)
                except Exception:
                    pass

                # Filtrar solo apartamentos con el parametro compartido RevitElectrico_Lote
                # igual al GUID del lote de colocacion v13.
                parametro_lote = None
                try:
                    param = fi.LookupParameter(LOTE_PARAM_NAME)
                    if param is not None:
                        parametro_lote = param.AsString()
                except Exception:
                    pass

                if parametro_lote != LOTE_GUID:
                    continue

                total_piso5 += 1

                # Posición XYZ
                x_m = y_m = z_m = None
                try:
                    loc = fi.Location
                    if loc is not None and hasattr(loc, 'Point'):
                        p = loc.Point
                        x_m = round(_ft_a_m(p.X), 4)
                        y_m = round(_ft_a_m(p.Y), 4)
                        z_m = round(_ft_a_m(p.Z), 4)
                except Exception:
                    pass

                # Filtrar solo rango E06
                en_rango_e06 = False
                if x_m is not None and y_m is not None:
                    if E06_X_MIN <= x_m <= E06_X_MAX and E06_Y_MIN <= y_m <= E06_Y_MAX:
                        en_rango_e06 = True

                # Familia y símbolo
                familia = "(no accesible)"
                simbolo = "(no accesible)"
                try:
                    if fi.Symbol is not None:
                        simbolo = _safe_str(fi.Symbol.Name)
                        if fi.Symbol.Family is not None:
                            familia = _safe_str(fi.Symbol.Family.Name)
                except Exception:
                    pass

                # Host
                host_element_id = None
                host_unique_id = None
                host_categoria = None
                try:
                    if fi.Host is not None:
                        host_element_id = _eid(fi.Host.Id)
                        host_unique_id = _safe_str(fi.Host.UniqueId)
                        host_categoria = fi.Host.Category.Name if fi.Host.Category else None
                except Exception:
                    pass

                # Parámetro de trazabilidad del lote
                parametro_lote = None
                try:
                    param = fi.LookupParameter("RevitElectrico_Lote")
                    if param is not None:
                        parametro_lote = param.AsString()
                except Exception:
                    pass

                elementos_vistos[unique_id] = {
                    "unique_id": unique_id,
                    "element_id": element_id,
                    "categoria": categoria,
                    "familia": familia,
                    "simbolo": simbolo,
                    "x_m": x_m,
                    "y_m": y_m,
                    "z_m": z_m,
                    "nivel_nombre": nivel_nombre,
                    "nivel_id": nivel_id_raw,
                    "en_rango_e06": en_rango_e06,
                    "host_element_id": host_element_id,
                    "host_unique_id": host_unique_id,
                    "host_categoria": host_categoria,
                    "parametro_lote": parametro_lote,
                }

            except Exception:
                continue

    elementos = list(elementos_vistos.values())
    elementos_e06 = [e for e in elementos if e["en_rango_e06"]]

    # Guardar JSON
    datos = {
        "script_version": SCRIPT_VERSION,
        "fecha": "2026-11-12",
        "timestamp_ejecucion": TIMESTAMP,
        "documento": doc.Title,
        "nivel": "Piso 5",
        "nivel_id": None,
        "rango_e06": {
            "x_min": E06_X_MIN,
            "x_max": E06_X_MAX,
            "y_min": E06_Y_MIN,
            "y_max": E06_Y_MAX,
        },
        "total_revisados": total_revisados,
        "total_piso_5": len(elementos),
        "total_en_rango_e06": len(elementos_e06),
        "elementos": elementos,
        "elementos_e06": elementos_e06,
    }

    directorio = os.path.dirname(SALIDA_JSON)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)

    with open(SALIDA_JSON, "w") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    print("Elementos revisados (todas las categorías eléctricas): {}".format(total_revisados))
    print("Elementos únicos en Piso 5 (LevelId = 192512): {}".format(len(elementos)))
    print("Elementos únicos en rango E06: {}".format(len(elementos_e06)))
    print("JSON guardado en: {}".format(SALIDA_JSON))
    print("=" * 80)

    # Resumen por categoría en rango E06
    resumen_cat = {}
    for e in elementos_e06:
        cat = e["categoria"]
        resumen_cat[cat] = resumen_cat.get(cat, 0) + 1
    if resumen_cat:
        print("Por categoría en rango E06:")
        for cat, cnt in sorted(resumen_cat.items()):
            print("  {}: {}".format(cat, cnt))
    else:
        print("Sin elementos en rango E06.")

    print("=" * 80)
    return datos


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        exportar_trazabilidad_E06(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso:")
        print('  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\exportar_trazabilidad_E06_v02.py").read())')
        print('  doc = __revit__.ActiveUIDocument.Document')
        print('  exportar_trazabilidad_E06(doc)')
