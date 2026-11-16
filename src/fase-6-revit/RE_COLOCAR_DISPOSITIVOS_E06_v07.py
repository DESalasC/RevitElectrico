# -*- coding: utf-8 -*-
# RE_COLOCAR_DISPOSITIVOS_E06_v07.py
# Versión corregida: usa filtros NATIVOS de Revit (ElementLevelFilter + ElementCategoryFilter)
# para cargar muros y techos de Piso 5 sin iterar en Python. Ejecución REAL (dry_run=False).
#
# Coloca dispositivos eléctricos de E 06 desde el INVENTARIO CANÓNICO del DXF
# (un INSERT = una instancia), no desde los extremos de tramos de ruteo.
#
# Ejecutar dentro de Revit 2026 (pyRevit agent, modo modify).
#
# Uso:
#   pyrevit agent run RE_COLOCAR_DISPOSITIVOS_E06_v07.py --mode=modify --revit=5500 --timeout=300

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from System import Int64
import json, math, os

SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\colocar_dispositivos_E06_v07_resultado.json"
INVENTARIO_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E06_v01.json"
OFFSET_XY = [2.3682, 9.6937]  # metros, DXF -> Revit modelo (ancla EPB25-304C)
RADIO_BUSQUEDA_M = 8.0  # radio máximo para buscar muro/techo (evita recorrer todo el edificio)
UMBRAL_DUP_M = 0.10  # deduplicación por proximidad física

FEET_PER_METER = 3.280839895

def _eid(eid):
    try: return int(eid.IntegerValue)
    except Exception: return int(str(eid))

def _lid(int_val):
    return ElementId(Int64(int_val))

def _m_a_ft(m):
    return m * FEET_PER_METER

def cargar_json(path):
    with open(path, "r") as f:
        return json.load(f)

def guardar_json(path, datos):
    directorio = os.path.dirname(path)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(path, "w") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def rotacion_a_vector(grados):
    rad = math.radians(grados)
    return XYZ(math.cos(rad), math.sin(rad), 0.0)

def obtener_nivel(doc, nombre_nivel):
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if lv.Name == nombre_nivel:
            return lv
    return None

def cargar_muros_techos_nivel(doc, nivel_id_int):
    """Pre-carga muros y techos del nivel dado usando filtros NATIVOS de Revit."""
    nivel_id = _lid(nivel_id_int)
    nivel_filter = ElementLevelFilter(nivel_id)
    muros = []
    techos = []

    cat_muros = ElementCategoryFilter(BuiltInCategory.OST_Walls)
    collector_m = FilteredElementCollector(doc).WherePasses(cat_muros).WherePasses(nivel_filter)
    for w in collector_m:
        try:
            loc = w.Location
            if not loc or not hasattr(loc, "Curve"):
                continue
            curva = loc.Curve
            if curva is None:
                continue
            p1 = curva.GetEndPoint(0)
            p2 = curva.GetEndPoint(1)
            muros.append({
                "elemento": w,
                "id": _eid(w.Id),
                "p1": (p1.X, p1.Y),
                "p2": (p2.X, p2.Y),
            })
        except Exception:
            continue

    cat_techos = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
    collector_c = FilteredElementCollector(doc).WherePasses(cat_techos).WherePasses(nivel_filter)
    for c in collector_c:
        try:
            loc = c.Location
            if not loc or not hasattr(loc, "Point"):
                continue
            p = loc.Point
            techos.append({
                "elemento": c,
                "id": _eid(c.Id),
                "p": (p.X, p.Y),
            })
        except Exception:
            continue

    return muros, techos

def distancia_punto_segmento(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0, min(1, t))
    cx = x1 + t * dx
    cy = y1 + t * dy
    return math.hypot(px - cx, py - cy)

def muro_mas_cercano(muros, px_ft, py_ft, radio_max_ft):
    mejor = None
    mejor_dist = None
    for m in muros:
        d = distancia_punto_segmento(px_ft, py_ft, m["p1"][0], m["p1"][1], m["p2"][0], m["p2"][1])
        if d <= radio_max_ft and (mejor_dist is None or d < mejor_dist):
            mejor_dist = d
            mejor = m
    return mejor, mejor_dist

def techo_mas_cercano(techos, px_ft, py_ft, radio_max_ft):
    mejor = None
    mejor_dist = None
    for t in techos:
        d = math.hypot(px_ft - t["p"][0], py_ft - t["p"][1])
        if d <= radio_max_ft and (mejor_dist is None or d < mejor_dist):
            mejor_dist = d
            mejor = t
    return mejor, mejor_dist

def existe_instancia_cercana(doc, px_ft, py_ft, umbral_ft):
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            loc = fi.Location
            if not loc or not hasattr(loc, "Point"):
                continue
            p = loc.Point
            if math.hypot(p.X - px_ft, p.Y - py_ft) < umbral_ft:
                return True
        except Exception:
            continue
    return False

def obtener_simbolo(doc, nombre):
    """Busca un FamilySymbol por nombre de familia (exacto o contiene)."""
    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            if fam.Name == nombre:
                ids = fam.GetFamilySymbolIds()
                if ids:
                    return doc.GetElement(ids[0])
        except Exception:
            continue
    # fallback: contiene
    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            if nombre.lower() in fam.Name.lower():
                ids = fam.GetFamilySymbolIds()
                if ids:
                    return doc.GetElement(ids[0])
        except Exception:
            continue
    return None

def colocar_dispositivos(doc, inventario_path=INVENTARIO_JSON, salida_json=SALIDA_JSON,
                         offset_xy=OFFSET_XY, dry_run=False, umbral_dup_m=UMBRAL_DUP_M,
                         radio_busqueda_m=RADIO_BUSQUEDA_M):
    print("=== RE_COLOCAR_DISPOSITIVOS_E06_v07 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: {}".format("dry_run" if dry_run else "REAL"))
    print("Inventario: {}".format(inventario_path))
    print("Offset XY: {}".format(offset_xy))

    inventario = cargar_json(inventario_path)
    dispositivos = inventario["dispositivos"]

    nivel = obtener_nivel(doc, "Piso 5")
    if nivel is None:
        print("ERROR: no se encontró el nivel 'Piso 5'")
        return {"error": "nivel_no_encontrado"}

    nivel_id_int = _eid(nivel.Id)
    print("Nivel Piso 5: id={} elev_m={}".format(nivel_id_int, round(nivel.Elevation*0.3048, 4)))

    # Pre-cargar muros y techos del nivel (una sola vez, filtros nativos)
    muros, techos = cargar_muros_techos_nivel(doc, nivel_id_int)
    print("Muros Piso 5 cargados: {}".format(len(muros)))
    print("Techos Piso 5 cargados: {}".format(len(techos)))

    radio_max_ft = _m_a_ft(radio_busqueda_m)
    umbral_dup_ft = _m_a_ft(umbral_dup_m)

    detalle = []
    creados = 0
    saltados_duplicado = 0
    errores = 0

    for disp in dispositivos:
        nombre = disp["nombre"]
        x_dxf = disp["x"]
        y_dxf = disp["y"]
        rot = disp["rotacion_grados"]
        altura_nominal = disp["altura_nominal_m"]

        # Aplicar offset DXF -> Revit (metros)
        x_revit_m = x_dxf + offset_xy[0]
        y_revit_m = y_dxf + offset_xy[1]
        px_ft = _m_a_ft(x_revit_m)
        py_ft = _m_a_ft(y_revit_m)

        # Verificar duplicado por proximidad física
        if existe_instancia_cercana(doc, px_ft, py_ft, umbral_dup_ft):
            saltados_duplicado += 1
            detalle.append({
                "nombre": nombre,
                "handle": disp["handle"],
                "x": round(x_revit_m, 4),
                "y": round(y_revit_m, 4),
                "z_m": altura_nominal,
                "rotacion_grados": rot,
                "accion": "saltado_duplicado",
                "motivo": "ya existe instancia a <{} m".format(umbral_dup_m),
            })
            continue

        # Determinar host
        es_techo = altura_nominal >= 2.0

        if es_techo:
            host_info, dist_ft = techo_mas_cercano(techos, px_ft, py_ft, radio_max_ft)
            host_categoria = "Ceilings" if host_info else None
            host_id = host_info["id"] if host_info else None
            z_revit_m = altura_nominal
        else:
            host_info, dist_ft = muro_mas_cercano(muros, px_ft, py_ft, radio_max_ft)
            host_categoria = "Walls" if host_info else None
            host_id = host_info["id"] if host_info else None
            z_revit_m = altura_nominal

        entry = {
            "nombre": nombre,
            "handle": disp["handle"],
            "x": round(x_revit_m, 4),
            "y": round(y_revit_m, 4),
            "z_m": round(z_revit_m, 4),
            "rotacion_grados": rot,
            "host_categoria": host_categoria,
            "host_id": host_id,
            "host_dist_m": round(dist_ft / FEET_PER_METER, 4) if dist_ft is not None else None,
            "altura_nominal_m": altura_nominal,
        }

        if dry_run:
            entry["accion"] = "dry_run_crear"
            entry["element_id"] = None
            creados += 1
            detalle.append(entry)
            continue

        # Ejecución real en Revit
        try:
            simbolo = obtener_simbolo(doc, nombre)
            if simbolo is None:
                errores += 1
                entry["accion"] = "error_simbolo_no_encontrado"
                entry["motivo"] = "no hay familia cargada para '{}'".format(nombre)
                detalle.append(entry)
                continue

            punto_ft = XYZ(px_ft, py_ft, _m_a_ft(z_revit_m))
            direccion = rotacion_a_vector(rot)

            if host_info is not None:
                elemento_host = host_info["elemento"]
                try:
                    ref = elemento_host.FindNearestReference(punto_ft)
                    inst = doc.Create.NewFamilyInstance(ref, punto_ft, direccion, simbolo)
                except Exception:
                    inst = doc.Create.NewFamilyInstance(punto_ft, simbolo, elemento_host, nivel, StructuralType.NonStructural)
            else:
                inst = doc.Create.NewFamilyInstance(punto_ft, simbolo, nivel, StructuralType.NonStructural)

            entry["accion"] = "creado"
            entry["element_id"] = _eid(inst.Id)
            creados += 1
            detalle.append(entry)

        except Exception as exc:
            errores += 1
            entry["accion"] = "error"
            entry["motivo"] = str(exc)
            detalle.append(entry)

    resumen = {
        "fecha": "2026-11-11",
        "apartamento": "E06",
        "documento": doc.Title,
        "nivel": "Piso 5",
        "nivel_id": nivel_id_int,
        "offset_xy_m": offset_xy,
        "umbral_duplicado_m": umbral_dup_m,
        "radio_busqueda_m": radio_busqueda_m,
        "dry_run": dry_run,
        "muros_nivel": len(muros),
        "techos_nivel": len(techos),
        "total_dispositivos_dxf": len(dispositivos),
        "creados": creados,
        "saltados_duplicado": saltados_duplicado,
        "errores": errores,
        "detalle": detalle,
    }

    guardar_json(salida_json, resumen)
    print("Total dispositivos DXF: {}".format(len(dispositivos)))
    print("Creados: {}".format(creados))
    print("Saltados (duplicado): {}".format(saltados_duplicado))
    print("Errores: {}".format(errores))
    print("JSON guardado en: {}".format(salida_json))
    return resumen


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        colocar_dispositivos(doc, dry_run=False)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit agent).")
