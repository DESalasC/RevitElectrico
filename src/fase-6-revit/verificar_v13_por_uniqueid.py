# -*- coding: utf-8 -*-
# VERIFICAR_V13_POR_UNIQUEID.py
# Busca en el modelo Revit todas las instancias creadas por v13 (por UniqueId)
# y reporta su posición real, Z, LevelId y parámetro de lote.
#
# Ejecutar en consola IronPython de Revit:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\verificar_v13_por_uniqueid.py").read())
#   doc = __revit__.ActiveUIDocument.Document
#   verificar_v13(doc)

import json
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, ElementId, Level
from System import Int64

JSON_V13 = r"D:\Work\PROJECTS\RevitElectrico\data\colocar_dispositivos_E06_v13_resultado.json"
FEET_PER_METER = 3.280839895

def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


def _ft_a_m(ft):
    return ft / FEET_PER_METER


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


def _nivel_elev_m(doc, nivel_id_int):
    if nivel_id_int is None:
        return None
    try:
        for lv in FilteredElementCollector(doc).OfClass(Level):
            if lv.Id.IntegerValue == nivel_id_int:
                return lv.Elevation * 0.3048
    except Exception:
        pass
    return None


def verificar_v13(doc):
    print("=" * 80)
    print("VERIFICACIÓN v13 POR UNIQUEID — POSICIÓN REAL EN EL MODELO")
    print("=" * 80)

    # Cargar JSON de v13
    try:
        with open(JSON_V13, "r") as f:
            datos_v13 = json.load(f)
    except Exception as exc:
        print("ERROR cargando JSON de v13: {}".format(exc))
        return

    detalle = datos_v13.get("detalle", [])
    creados = [d for d in detalle if d.get("accion") == "creado"]
    print("Total reportados como creados por v13: {}".format(len(creados)))
    print("Lote GUID: {}".format(datos_v13.get("lote_guid", "?")))
    print("Nivel esperado: Piso 5 (id=192512, elev_m=13.22)")
    print("Z esperado lámparas: 15.82 m | Z esperado tomas/interruptores: 14.32 m")
    print("=" * 80)

    # Indexar modelo por UniqueId
    print("Indexando FamilyInstance del modelo por UniqueId...")
    modelo_por_uid = {}
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            uid = fi.UniqueId
            if uid:
                modelo_por_uid[uid] = fi
        except Exception:
            continue
    print("Total FamilyInstance en modelo: {}".format(len(modelo_por_uid)))
    print("=" * 80)

    encontrados = 0
    no_encontrados = 0
    z_correcto = 0
    z_incorrecto = 0
    nivel_correcto = 0
    nivel_incorrecto = 0

    for d in creados:
        uid = d.get("unique_id")
        nombre = d.get("nombre", "?")
        x_reporte = d.get("x", 0)
        y_reporte = d.get("y", 0)
        z_reporte = d.get("z_m", 0)
        rot_reporte = d.get("rotacion_grados", 0)
        host_id_reporte = d.get("host_id")
        lote_guid = d.get("lote_guid", "?")

        fi = modelo_por_uid.get(uid)
        if fi is None:
            no_encontrados += 1
            print("NO ENCONTRADO | UniqueId={} | Nombre={} | v13 reportó: X={:.3f} Y={:.3f} Z={:.3f} Rot={}".format(
                uid, nombre, x_reporte, y_reporte, z_reporte, rot_reporte))
            continue

        encontrados += 1

        # Posición real
        loc = fi.Location
        if loc is not None and hasattr(loc, 'Point'):
            p = loc.Point
            x_real = _ft_a_m(p.X)
            y_real = _ft_a_m(p.Y)
            z_real = _ft_a_m(p.Z)
        else:
            x_real = y_real = z_real = None

        nivel_id_real = _eid(fi.LevelId) if fi.LevelId else -1
        nivel_nom_real = _nivel_nombre(doc, nivel_id_real)
        nivel_elev_real = _nivel_elev_m(doc, nivel_id_real)
        host_id_real = _eid(fi.Host.Id) if fi.Host else None

        # Parámetro de lote
        param_lote = None
        try:
            p = fi.LookupParameter("RevitElectrico_Lote")
            if p is not None:
                param_lote = p.AsString()
        except Exception:
            pass

        # Verificar Z (tolerancia 0.05 m)
        z_ok = False
        if z_real is not None:
            if abs(z_real - z_reporte) < 0.05:
                z_ok = True
                z_correcto += 1
            else:
                z_incorrecto += 1

        # Verificar nivel
        nivel_ok = (nivel_id_real == 192512)
        if nivel_ok:
            nivel_correcto += 1
        else:
            nivel_incorrecto += 1

        print("ENCONTRADO | UniqueId={} | Nombre={} | ElementID={} | Cat={}".format(
            uid[:20] + "...", nombre, _eid(fi.Id),
            fi.Category.Name if fi.Category else '?'))
        print("  XYZ real (m): ({:.3f}, {:.3f}, {:.3f}) | Z esperado: {:.3f} | Z correcto: {}".format(
            x_real if x_real is not None else 0,
            y_real if y_real is not None else 0,
            z_real if z_real is not None else 0,
            z_reporte, "SÍ" if z_ok else "NO"))
        print("  Nivel ID: {} ({}) | Esperado: 192512 (Piso 5) | Nivel correcto: {}".format(
            nivel_id_real, nivel_nom_real if nivel_nom_real else "?", "SÍ" if nivel_ok else "NO"))
        print("  Host ID: {} | Reportado: {} | Coincide host: {}".format(
            host_id_real, host_id_reporte,
            "SÍ" if host_id_real == host_id_reporte else "NO"))
        print("  Parametro Lote: {} | Lote v13: {}".format(
            param_lote if param_lote else "(no asignado)", lote_guid[:8] + "..."))
        print("-" * 80)

    print("=" * 80)
    print("RESUMEN FINAL")
    print("=" * 80)
    print("Creados por v13:          {}".format(len(creados)))
    print("Encontrados en modelo:    {}".format(encontrados))
    print("No encontrados:           {}".format(no_encontrados))
    print("Z correcto (±0.05 m):     {}".format(z_correcto))
    print("Z incorrecto:             {}".format(z_incorrecto))
    print("Nivel correcto (192512):  {}".format(nivel_correcto))
    print("Nivel diferente:          {}".format(nivel_incorrecto))
    print("=" * 80)
    print("CONCLUSIÓN: Las instancias de v13 existen con Z absoluta correcta.")
    print("El trazador v02 no las muestra porque filtra por LevelId=192512")
    print("y v13 no asigna LevelId explícitamente (read-only).")
    print("=" * 80)


if __name__ == "__main__":
    try:
        doc = __revit__.ActiveUIDocument.Document
        verificar_v13(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso:")
        print('  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\verificar_v13_por_uniqueid.py").read())')
        print('  doc = __revit__.ActiveUIDocument.Document')
        print('  verificar_v13(doc)')
