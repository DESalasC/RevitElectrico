# -*- coding: utf-8 -*-
# RE_COLOCAR_DISPOSITIVOS_generico.py (v08 - optimizado)
# Script GENÉRICO: coloca dispositivos eléctricos desde un inventario DXF en Revit,
# para CUALQUIER bloque "Apartamento Tipo X nn".
#
# Ejecutar: pyrevit agent run RE_COLOCAR_DISPOSITIVOS_generico.py --mode=modify --revit=5500 --timeout=600

import clr
clr.AddReference("RevitAPI")
clr.AddReference("System")
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI import *
from System import Int64
import json, math, os, sys, time

# ---------- Valores por defecto (E06) ----------
DEFAULT_INVENTARIO = r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E06_v01.json"
DEFAULT_SALIDA = r"D:\Work\PROJECTS\RevitElectrico\data\colocar_dispositivos_generico_resultado.json"
DEFAULT_OFFSET_X = 2.3682
DEFAULT_OFFSET_Y = 9.6937
DEFAULT_NIVEL = "Piso 5"
DEFAULT_UMBRAL_DUP = 0.10
DEFAULT_RADIO = 8.0

# Mapeo DXF -> Familia Revit (nombres exactos de familia y símbolo cargados en el modelo)
MAPEO_DEFAULT = {
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
    "ELEC-NET-PAU": ("Consolidation_Point", "CPB6BL"),
    "S3": ("M_Interruptores", "Triple"),
    "ELEC-CAMPANA": ("M_Timbre", "Campana"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
    "ELEC-PANEL": ("E_Panel Distribucion", "EPB25-304C"),
    "ELEC-EXT": ("EA", "EA 1010"),
}

# Delta de rotacion por familia, en grados, sumado a la rotacion del bloque DXF.
# Motivo (2026-11-15): en Colombia las tomas se montan con la placa horizontal. La familia
# M_Toma doble esta modelada con la placa vertical (su eje largo en Z: 114 mm medidos en
# CENTRAL-V01), asi que hay que girarla 90 grados para que quede horizontal.
# El delta se aplica sobre la rotacion del DXF, no la sustituye.
DELTA_ROT_POR_FAMILIA = {
    "M_Toma doble": 90.0,
}

FEET_PER_METER = 3.280839895


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


def parse_args(argv):
    args = {
        "inventario": DEFAULT_INVENTARIO,
        "salida": DEFAULT_SALIDA,
        "offset_x": DEFAULT_OFFSET_X,
        "offset_y": DEFAULT_OFFSET_Y,
        "nivel": DEFAULT_NIVEL,
        "mapeo": None,
        "dry_run": False,
        "umbral_dup": DEFAULT_UMBRAL_DUP,
        "radio": DEFAULT_RADIO,
    }
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--dry-run":
            args["dry_run"] = True
            i += 1
        elif tok in ("--inventario", "--salida", "--nivel", "--mapeo"):
            args[tok.lstrip("-").replace("-", "_")] = argv[i + 1]
            i += 2
        elif tok in ("--offset-x", "--offset-y", "--umbral-dup", "--radio"):
            key = tok.lstrip("-").replace("-", "_")
            args[key] = float(argv[i + 1])
            i += 2
        else:
            i += 1
    return args


def rotacion_a_vector(grados):
    rad = math.radians(grados)
    return XYZ(math.cos(rad), math.sin(rad), 0.0)


def obtener_nivel(doc, nombre_nivel):
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if lv.Name == nombre_nivel:
            return lv
    return None


def cargar_muros_techos_nivel(doc, nivel_id_int, nivel_nombre):
    """Carga muros y techos del nivel indicado.
    
    Muros: se filtran por ElementLevelFilter (funciona bien para paredes).
    Techos: se traen TODOS de categoría OST_Ceilings y se filtran por tipo
    de familia "Falso techo continuo de placa de yeso laminado" para excluir
    "Flanche". No se usa ElementLevelFilter para techos porque muchos no
    tienen LevelId asignado o pertenecen a otro nivel, y el techo más cercano
    por XY ya se selecciona con techo_mas_cercano dentro del radio de búsqueda.
    """
    nivel_id = _lid(nivel_id_int)
    nivel_filter = ElementLevelFilter(nivel_id)
    muros = []
    techos = []

    cat_muros = ElementCategoryFilter(BuiltInCategory.OST_Walls)
    for w in FilteredElementCollector(doc).WherePasses(cat_muros).WherePasses(nivel_filter):
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

    # Techos: todos los de categoría Ceilings, filtrados por tipo de familia.
    # No se aplica ElementLevelFilter para evitar excluir techos sin LevelId.
    cat_techos = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
    for c in FilteredElementCollector(doc).WherePasses(cat_techos):
        try:
            # Filtrar por nombre de tipo/familia: solo cielorrasos de placa de yeso
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
                # Fallback: centro del BoundingBox como referencia XY
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
            })
        except Exception:
            continue

    print("Muros '{}' cargados: {}".format(nivel_nombre, len(muros)))
    print("Techos totales (tipo cielo de yeso, sin filtro de nivel): {}".format(len(techos)))
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


class ExistenciaCache:
    """Índice ligero de FamilyInstances existentes para evitar iterar el doc 47 veces."""
    def __init__(self, doc):
        self.puntos = []
        try:
            for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
                try:
                    loc = fi.Location
                    if loc and hasattr(loc, "Point"):
                        p = loc.Point
                        self.puntos.append((p.X, p.Y))
                except Exception:
                    continue
        except Exception:
            pass
        print("ExistenciaCache: {} FamilyInstances preexistentes indexadas".format(len(self.puntos)))

    def hay_cercano(self, px_ft, py_ft, umbral_ft):
        for (px, py) in self.puntos:
            if math.hypot(px - px_ft, py - py_ft) < umbral_ft:
                return True
        return False

    def agregar(self, px_ft, py_ft):
        self.puntos.append((px_ft, py_ft))


class SimboloCache:
    """Cache de FamilySymbol por nombre de familia, con activación perezosa."""
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
                                # Si se pide un símbolo específico, buscar por nombre
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


def colocar_dispositivos(doc, inventario_path, salida_json, offset_xy, nivel_nombre,
                         mapeo, dry_run, umbral_dup_m, radio_busqueda_m):
    t0 = time.time()
    print("=== RE_COLOCAR_DISPOSITIVOS_generico v08 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: {}".format("dry_run" if dry_run else "REAL"))
    print("Inventario: {}".format(inventario_path))
    print("Fecha/Hora ejecucion: {}".format(time.strftime("%Y-%m-%d %H:%M:%S")))
    print("Nivel: {}".format(nivel_nombre))
    print("Offset XY: {}".format(offset_xy))
    print("Mapeo DXF->Familia: {} entradas".format(len(mapeo)))

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

    muros, techos = cargar_muros_techos_nivel(doc, nivel_id_int, nivel_nombre)

    radio_max_ft = _m_a_ft(radio_busqueda_m)
    umbral_dup_ft = _m_a_ft(umbral_dup_m)

    existencia = ExistenciaCache(doc)
    simbolos = SimboloCache(doc)

    detalle = []
    creados = 0
    saltados_duplicado = 0
    errores = 0
    sin_mapeo = 0

    for i, disp in enumerate(dispositivos):
        nombre = disp["nombre"]
        x_dxf = disp["x"]
        y_dxf = disp["y"]
        rot = disp["rotacion_grados"]
        altura_nominal = disp["altura_nominal_m"]
        handle = disp.get("handle", "")

        x_revit_m = x_dxf + offset_xy[0]
        y_revit_m = y_dxf + offset_xy[1]
        px_ft = _m_a_ft(x_revit_m)
        py_ft = _m_a_ft(y_revit_m)

        if existencia.hay_cercano(px_ft, py_ft, umbral_dup_ft):
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

        entrada_mapeo = mapeo.get(nombre)
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

        es_techo = altura_nominal >= 2.0
        # Regla de datum G5: Z_absoluta = nivel.Elevation + altura_local
        z_revit_m = nivel_elev_m + altura_nominal
        if es_techo:
            host_info, dist_ft = techo_mas_cercano(techos, px_ft, py_ft, radio_max_ft)
            host_categoria = "Ceilings" if host_info else None
            host_id = host_info["id"] if host_info else None
        else:
            host_info, dist_ft = muro_mas_cercano(muros, px_ft, py_ft, radio_max_ft)
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

        try:
            simbolo = simbolos.obtener(nombre_familia, nombre_simbolo)
            if simbolo is None:
                errores += 1
                entry["accion"] = "error_simbolo_no_encontrado"
                entry["motivo"] = "no hay FamilySymbol cargado para familia '{}'".format(nombre_familia)
                detalle.append(entry)
                continue

            punto_ft = XYZ(px_ft, py_ft, _m_a_ft(z_revit_m))
            delta_rot = DELTA_ROT_POR_FAMILIA.get(nombre_familia, 0.0)
            direccion = rotacion_a_vector(rot + delta_rot)
            entry["delta_rot_grados"] = delta_rot
            entry["rotacion_aplicada"] = rot + delta_rot

            t = Transaction(doc, "Colocar dispositivo {}".format(nombre))
            t.Start()
            try:
                # Crear SIN ref de host para que Revit interprete el Z como coordenada absoluta mundial,
                # no como offset relativo al techo/pared (evita que queden en nivel 0.00).
                inst = doc.Create.NewFamilyInstance(punto_ft, simbolo, nivel, StructuralType.NonStructural)
                t.Commit()
            except Exception:
                t.RollBack()
                raise

            existencia.agregar(px_ft, py_ft)
            entry["accion"] = "creado"
            entry["element_id"] = _eid(inst.Id)
            creados += 1
            detalle.append(entry)

        except Exception as exc:
            errores += 1
            entry["accion"] = "error"
            entry["motivo"] = str(exc)
            detalle.append(entry)

    t1 = time.time()
    resumen = {
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "apartamento": nivel_nombre,
        "documento": doc.Title,
        "nivel": nivel_nombre,
        "nivel_id": nivel_id_int,
        "offset_xy_m": offset_xy,
        "umbral_duplicado_m": umbral_dup_m,
        "radio_busqueda_m": radio_busqueda_m,
        "dry_run": dry_run,
        "mapeo": mapeo,
        "muros_nivel": len(muros),
        "techos_nivel": len(techos),
        "total_dispositivos_dxf": len(dispositivos),
        "creados": creados,
        "saltados_duplicado": saltados_duplicado,
        "sin_mapeo": sin_mapeo,
        "errores": errores,
        "duracion_s": round(t1 - t0, 2),
        "detalle": detalle,
    }

    guardar_json(salida_json, resumen)
    print("Total dispositivos DXF: {}".format(len(dispositivos)))
    print("Creados: {}".format(creados))
    print("Saltados (duplicado): {}".format(saltados_duplicado))
    print("Sin mapeo: {}".format(sin_mapeo))
    print("Errores: {}".format(errores))
    print("Duración: {:.1f} s".format(t1 - t0))
    print("JSON guardado en: {}".format(salida_json))
    return resumen


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        args = parse_args(sys.argv[1:])
        mapeo = MAPEO_DEFAULT
        if args["mapeo"]:
            try:
                mapeo.update(cargar_json(args["mapeo"]))
            except Exception as ex:
                print("WARNING: no se pudo cargar archivo de mapeo '{}': {}".format(args["mapeo"], ex))
        colocar_dispositivos(
            doc,
            inventario_path=args["inventario"],
            salida_json=args["salida"],
            offset_xy=[args["offset_x"], args["offset_y"]],
            nivel_nombre=args["nivel"],
            mapeo=mapeo,
            dry_run=args["dry_run"],
            umbral_dup_m=args["umbral_dup"],
            radio_busqueda_m=args["radio"],
        )
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit agent).")
