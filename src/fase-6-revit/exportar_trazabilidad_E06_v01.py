# -*- coding: utf-8 -*-
# EXPORTAR_TRAZABILIDAD_E06_v01.py
# Exporta a JSON un inventario completo de todos los elementos electricos del Piso 5
# en el modelo Revit actual, con UniqueId persistente para trazabilidad entre sesiones.
#
# Copiar y pegar en consola IronPython de pyRevit dentro de Revit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\exportar_trazabilidad_E06_v01.py").read())
#   doc = __revit__.ActiveUIDocument.Document
#   exportar_trazabilidad_E06(doc)

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, BuiltInCategory
)
from Autodesk.Revit.DB import Level
from System import Int64

import json, os, datetime

SCRIPT_VERSION = "exportar_trazabilidad_E06_v01-2026-11-12"
SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\trazabilidad_E06_piso5_inventario.json"
NIVEL_PISO5_ID = 192512

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

def _nivel_nivel_id(doc, nivel_id_int):
    """Devuelve (nombre_nivel, nivel_id_int) o (None, nivel_id_int)."""
    if nivel_id_int is None:
        return None, None
    try:
        for lv in FilteredElementCollector(doc).OfClass(Level):
            if lv.Id.IntegerValue == nivel_id_int:
                return lv.Name, lv.Id.IntegerValue
    except Exception:
        pass
    return None, nivel_id_int

def exportar_trazabilidad_E06(doc):
    print("=" * 80)
    print("EXPORTACIÓN DE TRAZABILIDAD - APARTAMENTO E06 / PISO 5")
    print("Script: {}".format(SCRIPT_VERSION))
    print("Documento: {}".format(doc.Title))
    print("Fecha y hora: 2026-11-12")
    print("=" * 80)

    # Categorías eléctricas relevantes
    categorias_validas = [
        BuiltInCategory.OST_LightingFixtures,
        BuiltInCategory.OST_ElectricalFixtures,
    ]

    elementos = []
    total_revisados = 0
    total_piso5 = 0

    for cat in categorias_validas:
        for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
            total_revisados += 1
            try:
                # Categoría
                categoria = fi.Category.Name if fi.Category else "Sin categoría"

                # Únicamente FamilyInstance
                if not isinstance(fi, FamilyInstance):
                    continue

                # Datos básicos
                unique_id = _safe_str(fi.UniqueId)
                element_id = _eid(fi.Id)
                nombre_tipo = _safe_str(fi.Name)

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

                # Nivel y LevelId
                nivel_id_raw = None
                nivel_nombre = None
                try:
                    if fi.LevelId is not None:
                        nivel_id_raw = _eid(fi.LevelId)
                        nivel_nombre, nivel_id_raw = _nivel_nivel_id(doc, nivel_id_raw)
                except Exception:
                    pass

                # Filtrar solo Piso 5 (LevelId = 192512)
                if nivel_id_raw != NIVEL_PISO5_ID:
                    continue

                total_piso5 += 1

                # Host (techo o muro padre)
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

                elementos.append({
                    "unique_id": unique_id,
                    "element_id": element_id,
                    "categoria": categoria,
                    "familia": familia,
                    "simbolo": simbolo,
                    "nombre_tipo": nombre_tipo,
                    "x_m": x_m,
                    "y_m": y_m,
                    "z_m": z_m,
                    "nivel_nombre": nivel_nombre,
                    "nivel_id": nivel_id_raw,
                    "host_element_id": host_element_id,
                    "host_unique_id": host_unique_id,
                    "host_categoria": host_categoria,
                    "parametro_lote": parametro_lote,
                })

            except Exception:
                continue

    # Guardar JSON
    datos = {
        "script_version": SCRIPT_VERSION,
        "fecha": "2026-11-12",
        "documento": doc.Title,
        "nivel": "Piso 5",
        "nivel_id": NIVEL_PISO5_ID,
        "total_revisados": total_revisados,
        "total_piso_5": total_piso5,
        "elementos": elementos,
    }

    directorio = os.path.dirname(SALIDA_JSON)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)

    with open(SALIDA_JSON, "w") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    print("Elementos revisados (todas las categorías eléctricas): {}".format(total_revisados))
    print("Elementos en Piso 5 (LevelId = 192512): {}".format(total_piso5))
    print("JSON guardado en: {}".format(SALIDA_JSON))
    print("=" * 80)

    # Resumen por categoría
    resumen_cat = {}
    for e in elementos:
        cat = e["categoria"]
        resumen_cat[cat] = resumen_cat.get(cat, 0) + 1
    for cat, cnt in sorted(resumen_cat.items()):
        print("  {}: {}".format(cat, cnt))

    print("=" * 80)
    return datos


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        exportar_trazabilidad_E06(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso:")
        print('  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\exportar_trazabilidad_E06_v01.py").read())')
        print('  doc = __revit__.ActiveUIDocument.Document')
        print('  exportar_trazabilidad_E06(doc)')
