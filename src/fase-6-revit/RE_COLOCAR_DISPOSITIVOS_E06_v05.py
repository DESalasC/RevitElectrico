# -*- coding: utf-8 -*-
# RE_COLOCAR_DISPOSITIVOS_E06_v05.py
# Coloca dispositivos eléctricos de E 06 desde el INVENTARIO CANÓNICO del DXF
# (un INSERT = una instancia), no desde los extremos de tramos de ruteo.
#
# Corregiciones vs v04:
# - Lista de dispositivos desde inventario_dispositivos_E06_v01.json (INSERT del DXF)
# - Un dispositivo por INSERT, sin duplicados por extremos de polilínea
# - Rotación del bloque DXF aplicada a cada instancia
# - Hosteo en muro más cercano del nivel Piso 5 (pared) o techo más cercano (techo)
# - Deduplicación por proximidad física (≤0,10 m), no por coordenada exacta
# - dry_run obligatorio por defecto
#
# Ejecutar dentro de Revit 2026 (pyRevit agent, modo modify).
#
# Uso:
#   pyrevit agent run RE_COLOCAR_DISPOSITIVOS_E06_v05.py --mode=modify --revit=5500 --timeout=300

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import json, math, os

SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\colocar_dispositivos_E06_v05_resultado.json"
INVENTARIO_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E06_v01.json"
OFFSET_XY = [2.3682, 9.6937]  # metros, DXF -> Revit modelo (ancla EPB25-304C)

FEET_PER_METER = 3.280839895

def _eid(eid):
    try: return int(eid.IntegerValue)
    except Exception: return int(str(eid))

def _m_a_ft(m):
    return m * FEET_PER_METER

def _ft_a_m(ft):
    return ft / FEET_PER_METER

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
    """Convierte grados (0 = +X, 90 = +Y) a vector XYZ unitario en el plano XY."""
    rad = math.radians(grados)
    return XYZ(math.cos(rad), math.sin(rad), 0.0)

def obtener_nivel(doc, nombre_nivel):
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if lv.Name == nombre_nivel:
            return lv
    return None

def obtener_techo_cercano(doc, punto_xy, nivel):
    """Busca el techo más cercano al punto dado en el nivel."""
    mejor = None
    mejor_dist = None
    collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings)
    for c in collector:
        try:
            if c.LevelId.IntegerValue != nivel.Id.IntegerValue:
                continue
            loc = c.Location
            if not loc or not hasattr(loc, "Point"):
                continue
            p = loc.Point
            dist = math.hypot(p.X - punto_xy[0], p.Y - punto_xy[1])
            if mejor_dist is None or dist < mejor_dist:
                mejor_dist = dist
                mejor = c
        except Exception:
            continue
    return mejor, mejor_dist

def obtener_muro_cercano(doc, punto_xy, nivel):
    """Busca el muro más cercano al punto dado en el nivel."""
    mejor = None
    mejor_dist = None
    collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls)
    for w in collector:
        try:
            if w.LevelId.IntegerValue != nivel.Id.IntegerValue:
                continue
            loc = w.Location
            if not loc or not hasattr(loc, "Curve"):
                continue
            curve = loc.Curve
            if curve is None:
                continue
            # distancia punto a segmento de línea
            p1 = curve.GetEndPoint(0)
            p2 = curve.GetEndPoint(1)
            d = distancia_punto_segmento(punto_xy[0], punto_xy[1], p1.X, p1.Y, p2.X, p2.Y)
            if mejor_dist is None or d < mejor_dist:
                mejor_dist = d
                mejor = w
        except Exception:
            continue
    return mejor, mejor_dist

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

def existe_instancia_cercana(doc, punto_xy_m, umbral_m=0.10):
    """Verifica si ya hay una FamilyInstance eléctrica cerca del punto (en metros)."""
    px = _m_a_ft(punto_xy_m[0])
    py = _m_a_ft(punto_xy_m[1])
    umbral_ft = _m_a_ft(umbral_m)
    for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
        try:
            loc = fi.Location
            if not loc or not hasattr(loc, "Point"):
                continue
            p = loc.Point
            if math.hypot(p.X - px, p.Y - py) < umbral_ft:
                return True
        except Exception:
            continue
    return False

def colocar_dispositivos(doc, inventario_path=INVENTARIO_JSON, salida_json=SALIDA_JSON,
                         offset_xy=OFFSET_XY, dry_run=True, umbral_dup_m=0.10):
    print("=== RE_COLOCAR_DISPOSITIVOS_E06_v05 ===")
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

        # Verificar duplicado por proximidad física
        if existe_instancia_cercana(doc, [x_revit_m, y_revit_m], umbral_dup_m):
            saltados_duplicado += 1
            detalle.append({
                "nombre": nombre,
                "handle": disp["handle"],
                "x": x_revit_m,
                "y": y_revit_m,
                "z_m": altura_nominal,
                "rotacion_grados": rot,
                "accion": "saltado_duplicado",
                "motivo": "ya existe instancia a <{} m".format(umbral_dup_m),
            })
            continue

        # Determinar host: techo si altura >= 2.0, muro si no
        es_techo = altura_nominal >= 2.0

        if es_techo:
            host, dist = obtener_techo_cercano(doc, [x_revit_m, y_revit_m], nivel)
            host_categoria = "Ceilings" if host else None
            host_id = _eid(host.Id) if host else None
            z_revit_m = altura_nominal  # sobre el piso de referencia
        else:
            host, dist = obtener_muro_cercano(doc, [x_revit_m, y_revit_m], nivel)
            host_categoria = "Walls" if host else None
            host_id = _eid(host.Id) if host else None
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
            "host_dist_m": round(dist, 4) if dist is not None else None,
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
            # Buscar símbolo de familia por nombre (simplificado: usar nombre como familia)
            # En producción se usaría MAPA_BLOQUES_REVIT
            simbolo = None
            for fam in FilteredElementCollector(doc).OfClass(Family):
                if fam.Name.lower() == nombre.lower():
                    ids = fam.GetFamilySymbolIds()
                    if ids:
                        simbolo = doc.GetElement(ids[0])
                        break

            if simbolo is None:
                # fallback: usar cualquier símbolo de la primera familia que coincida parcialmente
                for fam in FilteredElementCollector(doc).OfClass(Family):
                    if nombre.lower() in fam.Name.lower():
                        ids = fam.GetFamilySymbolIds()
                        if ids:
                            simbolo = doc.GetElement(ids[0])
                            break

            if simbolo is None:
                errores += 1
                entry["accion"] = "error_simbolo_no_encontrado"
                entry["motivo"] = "no hay familia cargada para '{}'".format(nombre)
                detalle.append(entry)
                continue

            punto_ft = XYZ(_m_a_ft(x_revit_m), _m_a_ft(y_revit_m), _m_a_ft(z_revit_m))
            direccion = rotacion_a_vector(rot)

            if es_techo and host is not None:
                # Face-hosting en techo
                # (simplificado: crear en nivel, sin face por ahora por complejidad de Face reference)
                inst = doc.Create.NewFamilyInstance(punto_ft, simbolo, StructuralType.NonStructural)
            elif host is not None:
                # Face-hosting en muro
                try:
                    # Obtener referencia de cara del muro
                    # Buscar la cara más cercana al punto
                    ref = host.FindNearestReference(punto_ft)
                    inst = doc.Create.NewFamilyInstance(ref, punto_ft, direccion, simbolo)
                except Exception:
                    inst = doc.Create.NewFamilyInstance(punto_ft, simbolo, host, nivel, StructuralType.NonStructural)
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
        "offset_xy_m": offset_xy,
        "umbral_duplicado_m": umbral_dup_m,
        "dry_run": dry_run,
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
        colocar_dispositivos(doc, dry_run=True)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit agent).")
