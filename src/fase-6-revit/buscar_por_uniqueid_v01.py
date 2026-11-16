# -*- coding: utf-8 -*-
# BUSCAR_POR_UNIQUEID_v01.py
# Busca en el modelo Revit los elementos cuyos UniqueID reportó v11 como creados,
# y compara con las coordenadas que v11 afirmaba.
#
# Copiar y pegar en consola IronPython de pyRevit dentro de Revit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\buscar_por_uniqueid_v01.py").read())
#   doc = __revit__.ActiveUIDocument.Document
#   buscar_por_uniqueid(doc)

import json
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, ElementId, Level
from System import Int64

SCRIPT_VERSION = "buscar_por_uniqueid_v01-2026-11-12"
JSON_V11 = r"D:\Work\PROJECTS\RevitElectrico\data\colocar_dispositivos_E06_v11_resultado.json"

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
        for lv in FilteredElementCollector(doc).OfClass(Level):
            if lv.Id.IntegerValue == nivel_id_int:
                return lv.Name
    except Exception:
        pass
    return None

def buscar_por_uniqueid(doc):
    print("=" * 90)
    print("BÚSQUEDA POR UNIQUEID - COMPARACIÓN v11 vs MODELO REAL")
    print("Script: {}".format(SCRIPT_VERSION))
    print("Documento: {}".format(doc.Title))
    print("JSON de v11: {}".format(JSON_V11))
    print("=" * 90)

    # Cargar JSON de v11
    try:
        with open(JSON_V11, "r") as f:
            datos_v11 = json.load(f)
    except Exception as exc:
        print("ERROR cargando JSON de v11: {}".format(exc))
        return

    # Construir índice del modelo por UniqueId
    print("Indexando FamilyInstance del modelo por UniqueId...")
    modelo_por_uid = {}
    total_instancias = 0
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        total_instancias += 1
        try:
            uid = fi.UniqueId
            if uid:
                modelo_por_uid[uid] = fi
        except Exception:
            continue
    print("Total FamilyInstance en el modelo: {}".format(total_instancias))
    print("Con UniqueId indexados: {}".format(len(modelo_por_uid)))

    # Extraer elementos creados por v11
    creados_v11 = []
    for det in datos_v11.get("detalle", []):
        if det.get("accion") == "creado":
            creados_v11.append(det)

    print("Elementos reportados como 'creado' por v11: {}".format(len(creados_v11)))
    print("=" * 90)

    encontrados = 0
    no_encontrados = 0
    coordenadas_diferentes = 0

    for det in creados_v11:
        uid_v11 = det.get("unique_id")
        nombre = det.get("nombre", "?")
        x_reporte = det.get("x", 0)
        y_reporte = det.get("y", 0)
        z_reporte = det.get("z_m", 0)
        lote = det.get("lote_guid", "?")

        fi = modelo_por_uid.get(uid_v11)
        if fi is None:
            no_encontrados += 1
            print("NO ENCONTRADO | UniqueId={} | Nombre={} | v11 reportó: X={:.3f} Y={:.3f} Z={:.3f} | Lote={}".format(
                uid_v11, nombre, x_reporte, y_reporte, z_reporte, lote))
            continue

        # Encontrado en el modelo
        encontrados += 1
        loc = fi.Location
        if loc is not None and hasattr(loc, 'Point'):
            p = loc.Point
            x_real = _ft_a_m(p.X)
            y_real = _ft_a_m(p.Y)
            z_real = _ft_a_m(p.Z)
        else:
            x_real = y_real = z_real = None

        nivel_id_real = _eid(fi.LevelId) if fi.LevelId else -1
        nivel_nombre_real = _nivel_nombre(doc, nivel_id_real)
        host_id_real = _eid(fi.Host.Id) if fi.Host else None

        # Comparar coordenadas
        coord_diferente = False
        if x_real is not None:
            if abs(x_real - x_reporte) > 0.001 or abs(y_real - y_reporte) > 0.001 or abs(z_real - z_reporte) > 0.001:
                coord_diferente = True
                coordenadas_diferentes += 1

        print("ENCONTRADO  | UniqueId={} | Nombre={} | ElementID={} | Cat={} | XYZ(m)=({:.3f}, {:.3f}, {:.3f}) | NivelID={} ({}) | HostID={} | CoordsIguales={}".format(
            uid_v11, nombre, _eid(fi.Id),
            fi.Category.Name if fi.Category else '?',
            x_real if x_real is not None else 0,
            y_real if y_real is not None else 0,
            z_real if z_real is not None else 0,
            nivel_id_real, nivel_nombre_real,
            host_id_real,
            "NO" if coord_diferente else "SÍ"))

    print("=" * 90)
    print("RESUMEN:")
    print("  Reportados como creados por v11: {}".format(len(creados_v11)))
    print("  Encontrados en el modelo:        {}".format(encontrados))
    print("  NO encontrados en el modelo:     {}".format(no_encontrados))
    print("  Con coordenadas diferentes:      {}".format(coordenadas_diferentes))
    print("=" * 90)


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        buscar_por_uniqueid(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso:")
        print('  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\buscar_por_uniqueid_v01.py").read())')
        print('  doc = __revit__.ActiveUIDocument.Document')
        print('  buscar_por_uniqueid(doc)')
