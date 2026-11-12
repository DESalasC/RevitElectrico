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

# Mapeo DXF -> Familia Revit (nombres exactos de familia cargada en el modelo)
MAPEO_DEFAULT = {
    "Bala Stil Led 13W": "M_Iluminacion",
    "Bala Stil Led 10W": "M_Iluminacion",
    "Bala Stil Led 22W": "M_Iluminacion",
    "ELEC-I-S-C1-5A": "M_Interruptores",
    "ELEC-I-S-1-5A": "M_Interruptores",
    "ELEC-T-D-t-15A": "M_Toma doble",
    "ELEC-T-GFCI-t-15A": "M_Toma doble",
    "ELEC-F-VENT": "M_ClimatizacionV",
    "ELEC-F-CONTROL": "M_Climatizacion",
    "ELEC-TEL": "M_Comunicaciones",
    "ELEC-NET-PAU": "Consolidation_Point",
    "S3": "M_Interruptores",
    "ELEC-CAMPANA": "M_Zumbador",
    "ELEC-TIMBRE": "M_Pulsador - Interruptor",
    "ELEC-PANEL": "E_Panel Distribucion",
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


def cargar_muros_techos_nivel(doc, nivel_id_int):
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

    cat_techos = ElementCategoryFilter(BuiltInCategory.OST_Ceilings)
    for c in FilteredElementCollector(doc).WherePasses(cat_techos).WherePasses(nivel_filter):
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

    def obtener(self, nombre_familia):
        if nombre_familia in self.cache:
            return self.cache[nombre_familia]
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
                                simbolo = sym
                                break
                            except Exception:
                                continue
                    break
            except Exception:
                continue
        self.cache[nombre_familia] = simbolo
        return simbolo


def colocar_dispositivos(doc, inventario_path, salida_json, offset_xy, nivel_nombre,
                         mapeo, dry_run, umbral_dup_m, radio_busqueda_m):
    t0 = time.time()
    print("=== RE_COLOCAR_DISPOSITIVOS_generico v08 ===")
    print("Documento: {}".format(doc.Title))
    print("Modo: {}".format("dry_run" if dry_run else "REAL"))
    print("Inventario: {}".format(inventario_path))
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
    print("Nivel '{}': id={} elev_m={}".format(
        nivel_nombre, nivel_id_int, round(nivel.Elevation * 0.3048, 4)))

    muros, techos = cargar_muros_techos_nivel(doc, nivel_id_int)
    print("Muros '{}' cargados: {}".format(nivel_nombre, len(muros)))
    print("Techos '{}' cargados: {}".format(nivel_nombre, len(techos)))

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
                "z_m": altura_nominal,
                "rotacion_grados": rot,
                "accion": "saltado_duplicado",
                "motivo": "ya existe instancia a <{} m".format(umbral_dup_m),
            })
            continue

        nombre_familia = mapeo.get(nombre)
        if nombre_familia is None:
            sin_mapeo += 1
            detalle.append({
                "nombre": nombre,
                "handle": handle,
                "x": round(x_revit_m, 4),
                "y": round(y_revit_m, 4),
                "z_m": altura_nominal,
                "rotacion_grados": rot,
                "accion": "error_sin_mapeo",
                "motivo": "no hay mapeo DXF->familia Revit para '{}'".format(nombre),
            })
            continue

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
            simbolo = simbolos.obtener(nombre_familia)
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
                if host_info is not None:
                    elemento_host = host_info["elemento"]
                    try:
                        ref = elemento_host.FindNearestReference(punto_ft)
                        inst = doc.Create.NewFamilyInstance(ref, punto_ft, direccion, simbolo)
                    except Exception:
                        inst = doc.Create.NewFamilyInstance(punto_ft, simbolo, elemento_host, nivel, StructuralType.NonStructural)
                else:
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
        "fecha": "2026-11-11",
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
