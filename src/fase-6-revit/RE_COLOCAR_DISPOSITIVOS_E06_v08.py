# -*- coding: utf-8 -*-
# RE_COLOCAR_DISPOSITIVOS_E06_v08.py
# Versión corregida del v07 para el Apartamento Tipo E 06 (Piso 5).
#
# Correcciones aplicadas respecto al v07:
#   1. Mapeo DXF -> (Familia Revit, Simbolo) en lugar de buscar Family por nombre del dispositivo.
#   2. Techos: se cargan TODOS los de categoria OST_Ceilings filtrados por tipo
#      "Falso techo continuo de placa de yeso laminado", SIN ElementLevelFilter
#      (muchos techos de Piso 5 no tienen LevelId asignado).
#   3. Z absoluta (regla datum G5): Z_absoluta = nivel.Elevation * 0.3048 + altura_local.
#      Nunca se graba z_revit como altura local cruda.
#   4. Creacion SIN referencia de host:
#      doc.Create.NewFamilyInstance(punto_ft, simbolo, nivel, StructuralType.NonStructural)
#      para que Revit interprete la Z como coordenada absoluta mundial y no como
#      offset relativo al techo/pared.
#   5. Activacion perezosa de FamilySymbol con sym.Activate() si es necesario.
#
# Ejecutar dentro de Revit 2026 (pyRevit agent, modo modify).
#
# Uso:
#   pyrevit agent run RE_COLOCAR_DISPOSITIVOS_E06_v08.py --mode=modify --revit=5500 --timeout=300
#   (agregar --dry-run para validar sin crear instancias)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI import *
from System import Int64
import json, math, os, sys

SALIDA_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\colocar_dispositivos_E06_v08_resultado.json"
INVENTARIO_JSON = r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E06_v01.json"
OFFSET_XY = [2.3682, 9.6937]  # metros, DXF -> Revit modelo (ancla EPB25-304C)
RADIO_BUSQUEDA_M = 8.0  # radio maximo para buscar muro/techo
UMBRAL_DUP_M = 0.10  # deduplicacion por proximidad fisica
NIVEL_NOMBRE = "Piso 5"
FEET_PER_METER = 3.280839895

# Mapeo DXF -> (Familia Revit, Simbolo Revit). Nombres exactos cargados en el modelo.
MAPEO_DXF_REVIT = {
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    "ELEC-I-S-C1-5A": ("M_Interruptores", "Conmutable"),
    "ELEC-I-S-1-5A": ("M_Interruptores", "Simple"),
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-F-VENT": ("M_ClimatizacionV", "Ventilador"),
    "ELEC-F-CONTROL": ("M_Climatizacion", "Interruptor Ventilador"),
    "ELEC-TEL": ("M_Comunicaciones", "Telefono"),
    "ELEC-NET-PAU": ("Consolidation_Point", "CPB24BL"),
    "S3": ("M_Interruptores", "Triple"),
    "ELEC-CAMPANA": ("M_Zumbador", "Campana Timbre"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
}


def _eid(eid):
    try:
        return int(eid.IntegerValue)
    except Exception:
        return int(str(eid))


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
    """Carga muros y techos del nivel dado.

    Muros: ElementLevelFilter funciona bien para paredes (tienen LevelId).
    Techos: se traen TODOS los de categoria OST_Ceilings filtrados por tipo
    "Falso techo continuo de placa de yeso laminado" y se excluyen "Flanche".
    NO se usa ElementLevelFilter para techos porque muchos no tienen LevelId
    asignado o pertenecen a otro nivel; el techo mas cercano por XY se selecciona
    dentro del radio de búsqueda.
    """
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
                "nivel_id": _eid(w.LevelId) if w.LevelId is not None else -1,
            })
        except Exception:
            continue

    cat_techos = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
    for c in FilteredElementCollector(doc).WherePasses(cat_techos):
        try:
            tipo_nombre = ""
            try:
                tipo_nombre = c.Name
            except Exception:
                pass
            if "Falso techo continuo" not in tipo_nombre and "placa de yeso" not in tipo_nombre:
                continue
            loc = c.Location
            p = None
            if loc is not None:
                if hasattr(loc, "Point"):
                    p = loc.Point
                elif hasattr(loc, "Curve"):
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
            techos.append({
                "elemento": c,
                "id": _eid(c.Id),
                "p": (p.X, p.Y),
                "nivel_id": _eid(c.LevelId) if c.LevelId is not None else -1,
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


def muro_mas_cercano(muros, px_ft, py_ft, radio_max_ft, nivel_id_int):
    mejor = None
    mejor_dist = None
    for m in muros:
        # Restringir a muros del mismo nivel (Piso 5) para evitar host de otro piso
        if m["nivel_id"] != nivel_id_int and m["nivel_id"] != -1:
            continue
        d = distancia_punto_segmento(px_ft, py_ft, m["p1"][0], m["p1"][1], m["p2"][0], m["p2"][1])
        if d <= radio_max_ft and (mejor_dist is None or d < mejor_dist):
            mejor_dist = d
            mejor = m
    return mejor, mejor_dist


def techo_mas_cercano(techos, px_ft, py_ft, radio_max_ft, nivel_id_int):
    mejor = None
    mejor_dist = None
    for t in techos:
        # Restringir a techos del mismo nivel o sin nivel asignado (-1)
        if t["nivel_id"] != nivel_id_int and t["nivel_id"] != -1:
            continue
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


class SimboloCache:
    def __init__(self, doc):
        self.doc = doc
        self.cache = {}

    def obtener(self, nombre_familia, nombre_simbolo=None):
        clave = (nombre_familia, nombre_simbolo)
        if clave in self.cache:
            return self.cache[clave]
        simbolo = None
        for fam in FilteredElementCollector(self.doc).OfClass(Family):
            try:
                if fam.Name == nombre_familia:
                    ids = fam.GetFamilySymbolIds()
                    if ids:
                        for sid in ids:
                            try:
                                sym = self.doc.GetElement(sid)
                                if sym is None:
                                    continue
                                if not sym.IsActive:
                                    try:
                                        sym.Activate()
                                    except Exception:
                                        pass
                                if nombre_simbolo is not None:
                                    try:
                                        if sym.Name != nombre_simbolo:
                                            continue
                                    except Exception:
                                        pass
                                simbolo = sym
                                break
                            except Exception:
                                continue
                    break
            except Exception:
                continue
        self.cache[clave] = simbolo
        return simbolo


def colocar_dispositivos(doc, inventario_path=INVENTARIO_JSON, salida_json=SALIDA_JSON,
                         offset_xy=OFFSET_XY, dry_run=False, umbral_dup_m=UMBRAL_DUP_M,
                         radio_busqueda_m=RADIO_BUSQUEDA_M, nivel_nombre=NIVEL_NOMBRE,
                         mapeo=None):
    print("=== RE_COLOCAR_DISPOSITIVOS_E06_v08 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: {}".format("dry_run" if dry_run else "REAL"))
    print("Inventario: {}".format(inventario_path))
    print("Offset XY: {}".format(offset_xy))
    print("Nivel: {}".format(nivel_nombre))
    print("Mapeo DXF->Familia: {} entradas".format(len(mapeo) if mapeo else len(MAPEO_DXF_REVIT)))

    inventario = cargar_json(inventario_path)
    dispositivos = inventario["dispositivos"]

    nivel = obtener_nivel(doc, nivel_nombre)
    if nivel is None:
        print("ERROR: no se encontró el nivel '{}'".format(nivel_nombre))
        return {"error": "nivel_no_encontrado", "nivel": nivel_nombre}

    nivel_id_int = _eid(nivel.Id)
    nivel_elev_m = nivel.Elevation * 0.3048
    print("Nivel '{}': id={} elev_m={}".format(
        nivel_nombre, nivel_id_int, round(nivel_elev_m, 4)))

    # Pre-cargar muros y techos del nivel
    muros, techos = cargar_muros_techos_nivel(doc, nivel_id_int)
    print("Muros '{}' cargados: {}".format(nivel_nombre, len(muros)))
    print("Techos cargados (tipo cielo de yeso, sin filtro de nivel): {}".format(len(techos)))

    radio_max_ft = _m_a_ft(radio_busqueda_m)
    umbral_dup_ft = _m_a_ft(umbral_dup_m)

    mapeo_activo = mapeo if mapeo else MAPEO_DXF_REVIT
    simbolos = SimboloCache(doc)

    detalle = []
    creados = 0
    saltados_duplicado = 0
    errores = 0
    sin_mapeo = 0

    for disp in dispositivos:
        nombre = disp["nombre"]
        x_dxf = disp["x"]
        y_dxf = disp["y"]
        rot = disp["rotacion_grados"]
        altura_nominal = disp["altura_nominal_m"]
        handle = disp.get("handle", "")

        # Aplicar offset DXF -> Revit (metros)
        x_revit_m = x_dxf + offset_xy[0]
        y_revit_m = y_dxf + offset_xy[1]
        px_ft = _m_a_ft(x_revit_m)
        py_ft = _m_a_ft(y_revit_m)

        # Verificar duplicado por proximidad fisica
        if existe_instancia_cercana(doc, px_ft, py_ft, umbral_dup_ft):
            saltados_duplicado += 1
            detalle.append({
                "nombre": nombre,
                "handle": handle,
                "x": round(x_revit_m, 4),
                "y": round(y_revit_m, 4),
                "z_m": round(nivel_elev_m + altura_nominal, 4),
                "rotacion_grados": rot,
                "accion": "saltado_duplicado",
                "motivo": "ya existe instancia a <{} m".format(umbral_dup_m),
            })
            continue

        # Mapeo DXF -> Familia/Simbolo Revit
        entrada_mapeo = mapeo_activo.get(nombre)
        if entrada_mapeo is None:
            sin_mapeo += 1
            detalle.append({
                "nombre": nombre,
                "handle": handle,
                "x": round(x_revit_m, 4),
                "y": round(y_revit_m, 4),
                "z_m": round(nivel_elev_m + altura_nominal, 4),
                "rotacion_grados": rot,
                "accion": "error_sin_mapeo",
                "motivo": "no hay mapeo DXF->familia Revit para '{}'".format(nombre),
            })
            continue
        if isinstance(entrada_mapeo, tuple):
            nombre_familia, nombre_simbolo = entrada_mapeo
        else:
            nombre_familia = entrada_mapeo
            nombre_simbolo = None

        # Regla de dato G5: Z absoluta = elevacion del nivel + altura local de montaje
        z_revit_m = nivel_elev_m + altura_nominal

        # Determinar host (techo si altura >= 2.0, sino muro)
        es_techo = altura_nominal >= 2.0
        if es_techo:
            host_info, dist_ft = techo_mas_cercano(techos, px_ft, py_ft, radio_max_ft, nivel_id_int)
            host_categoria = "Ceilings" if host_info else None
            host_id = host_info["id"] if host_info else None
        else:
            host_info, dist_ft = muro_mas_cercano(muros, px_ft, py_ft, radio_max_ft, nivel_id_int)
            host_categoria = "Walls" if host_info else None
            host_id = host_info["id"] if host_info else None

        entry = {
            "nombre": nombre,
            "handle": handle,
            "x": round(x_revit_m, 4),
            "y": round(y_revit_m, 4),
            "z_m": round(z_revit_m, 4),
            "rotacion_grados": rot,
            "familia_revit": nombre_familia,
            "simbolo_revit": nombre_simbolo,
            "host_categoria": host_categoria,
            "host_id": host_id,
            "host_dist_m": round(dist_ft / FEET_PER_METER, 4) if dist_ft is not None else None,
            "altura_nominal_m": altura_nominal,
            "nivel_elev_m": round(nivel_elev_m, 4),
        }

        if dry_run:
            entry["accion"] = "dry_run_crear"
            entry["element_id"] = None
            creados += 1
            detalle.append(entry)
            continue

        # Ejecucion real en Revit
        try:
            simbolo = simbolos.obtener(nombre_familia, nombre_simbolo)
            if simbolo is None:
                errores += 1
                entry["accion"] = "error_simbolo_no_encontrado"
                entry["motivo"] = "no hay FamilySymbol cargado para familia '{}'".format(nombre_familia)
                detalle.append(entry)
                continue

            punto_ft = XYZ(px_ft, py_ft, _m_a_ft(z_revit_m))
            direccion = rotacion_a_vector(rot)

            t = Transaction(doc, "Colocar dispositivo {}".format(nombre))
            t.Start()
            try:
                # Crear SIN ref de host para que Revit interprete la Z como coordenada absoluta mundial.
                inst = doc.Create.NewFamilyInstance(punto_ft, simbolo, nivel, StructuralType.NonStructural)
                t.Commit()
            except Exception:
                t.RollBack()
                raise

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
        "fecha": "2026-11-12",
        "apartamento": "E06",
        "documento": doc.Title,
        "nivel": nivel_nombre,
        "nivel_id": nivel_id_int,
        "nivel_elev_m": round(nivel_elev_m, 4),
        "offset_xy_m": offset_xy,
        "umbral_duplicado_m": umbral_dup_m,
        "radio_busqueda_m": radio_busqueda_m,
        "dry_run": dry_run,
        "mapeo": mapeo_activo,
        "muros_nivel": len(muros),
        "techos_nivel": len(techos),
        "total_dispositivos_dxf": len(dispositivos),
        "creados": creados,
        "saltados_duplicado": saltados_duplicado,
        "sin_mapeo": sin_mapeo,
        "errores": errores,
        "detalle": detalle,
    }

    guardar_json(salida_json, resumen)
    print("Total dispositivos DXF: {}".format(len(dispositivos)))
    print("Creados: {}".format(creados))
    print("Saltados (duplicado): {}".format(saltados_duplicado))
    print("Sin mapeo: {}".format(sin_mapeo))
    print("Errores: {}".format(errores))
    print("JSON guardado en: {}".format(salida_json))
    return resumen


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        args = sys.argv[1:] if "__revit__" in dir() else []
        dry_run = "--dry-run" in args
        colocar_dispositivos(doc, dry_run=dry_run)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit agent).")
