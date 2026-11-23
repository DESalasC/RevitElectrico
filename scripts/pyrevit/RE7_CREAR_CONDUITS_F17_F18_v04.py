# -*- coding: utf-8 -*-
"""
RE7_CREAR_CONDUITS_F17_F18_v04.py
Etapa 4 del ruteo F7: crea conduits para F17 y F18 comparando DXF XPL con Revit.

ENFOQUE v04 (comparacion directa DXF vs Revit):
1. Lee inserts electricos del DXF XPL para F17 y F18 (f7_inserts_dxf_xpl_f17_f18_v01.json)
2. Lee segmentos de conducto del DXF XPL (f7_conductos_dxf_xpl_f17_f18_v01.json)
3. En Revit, recolecta dispositivos electricos ya colocados (OST_ElectricalFixtures)
4. Para cada bloque DXF, busca el dispositivo equivalente en Revit por nombre de familia
5. Calcula offset (dx, dy) = promedio(x_revit - x_dxf, y_revit - y_dxf) por apartamento
6. Aplica el offset a los segmentos de conducto del DXF XPL
7. Crea conduits con Conduit.Create en el nivel Piso 5
8. Verifica post-creacion que cada extremo quede a < 10 mm de su posicion esperada
9. Escribe reporte JSON

ENTRADA:
  data/f7_inserts_dxf_xpl_f17_f18_v01.json   (puntos de insercion bloques DXF)
  data/f7_conductos_dxf_xpl_f17_f18_v01.json (segmentos de conducto DXF)
SALIDA:  data/f7_conduits_creados_f17_f18_v04.json

RESTRICTION: Ejecutar solo en CENTRAL-V01b (o sucesor), NUNCA en V02-f.
Entorno: pyRevit IronPython 2.7 (consola Python de Revit)
"""
import datetime
import json
import math
import os
import sys
import traceback

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
from System import Int64

VERSION = "v04"
FT_A_MM = 304.8
DOC_PROHIBIDO = "V02-f"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
LOG_PATH = None

# Mapeo de nombre de bloque DXF -> nombre de familia Revit (para comparar)
MAPEO_DXF_REVIT = {
    "ELEC-T-D-t-15A": "M_Toma doble",
    "ELEC-T-GFCI-t-15A": "M_Toma doble",
    "ELEC-TEL": "M_Comunicaciones",
    "ELEC-NET-PAU": "M_Comunicaciones",
    "ELEC-I-S-1-5A": "M_Interruptores",
    "ELEC-I-S-2-5A": "M_Interruptores",
    "ELEC-I-S-C1-5A": "M_Interruptores",
    "ELEC-F-CONTROL": "M_Pulsador - Interruptor",
    "ELEC-F-VENT": "EA",
    "ELEC-CAMPANA": "M_Timbre",
    "ELEC-TIMBRE": "M_Timbre",
    "ELEC-EXT": "EA",
    "S3": "M_Interruptores",
    "S3C": "M_Interruptores",
    "Bala Stil Led 10W": "M_Iluminacion",
    "Bala Stil Led 13W": "M_Iluminacion",
    "Bala Stil Led 22W": "M_Iluminacion",
    "1FTN": "M_Iluminacion",
    "1FTNR": "M_Iluminacion",
    "1TNR": "M_Iluminacion",
    "1FT2R": "M_Iluminacion",
    "1FT2N": "M_Iluminacion",
    "1FTN2R": "M_Iluminacion",
    "1TN2R": "M_Iluminacion",
    "2FT2N": "M_Iluminacion",
    "1TNF4R": "M_Iluminacion",
    "1TNF3R": "M_Iluminacion",
    "1T1N3R": "M_Iluminacion",
    "2F2N1T1R": "M_Iluminacion",
}

# Z de los conduits (misma altura que dispositivos en Piso 5)
Z_CONDUIT_MM = 15930.0

# Tolerancia para considerar que un dispositivo DXF coincide con uno en Revit (mm)
TOLERANCIA_MATCH_MM = 500.0


def _raiz():
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz and os.path.exists(raiz):
        return raiz
    return DEFAULT_ROOT


def _iniciar_log():
    global LOG_PATH
    raiz = _raiz()
    carpeta = os.path.join(raiz, "data")
    try:
        if not os.path.exists(carpeta):
            os.makedirs(carpeta)
    except Exception:
        carpeta = os.environ.get("TEMP", ".")
    LOG_PATH = os.path.join(carpeta, "f7_crear_conduits_f17_f18_v04.log")


def log(msg):
    try:
        print(msg)
    except Exception:
        pass
    try:
        sys.stdout.flush()
    except Exception:
        pass
    if LOG_PATH:
        try:
            with open(LOG_PATH, "a") as f:
                f.write("[{}] {}\n".format(
                    datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), msg))
        except Exception:
            pass


def escribir_archivo_texto(ruta, contenido_texto):
    try:
        with open(ruta, "w") as f:
            f.write(contenido_texto)
        return True
    except Exception:
        return False


def obtener_doc():
    try:
        app = __revit__
        if app is not None and hasattr(app, "ActiveUIDocument"):
            return app.ActiveUIDocument.Document
    except Exception:
        pass
    try:
        from pyrevit import revit as _revit
        if getattr(_revit, "doc", None) is not None:
            return _revit.doc
    except Exception:
        pass
    return None


def id_de(elemento):
    eid_val = elemento.Id
    if hasattr(eid_val, "IntegerValue"):
        return int(eid_val.IntegerValue)
    return int(eid_val.Value)


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz_mm(x_mm, y_mm, z_mm):
    return XYZ(mm_a_ft(x_mm), mm_a_ft(y_mm), mm_a_ft(z_mm))


def dist_3d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def dist_2d(p, q):
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def buscar_nivel(doc, nombre_esperado="Piso 5", elevacion_m=13.22):
    mejor = None
    mejor_delta = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        delta = abs(lvl.Elevation * FT_A_MM - elevacion_m * 1000.0)
        if mejor_delta is None or delta < mejor_delta:
            mejor = lvl
            mejor_delta = delta
        if lvl.Name == nombre_esperado:
            return lvl
    return mejor


def listar_tipos_conduit(doc):
    tipos = []
    for t in FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
        try:
            if not Conduit.IsValidConduitType(doc, t.Id):
                continue
        except Exception:
            continue
        diametro_mm = None
        try:
            p = t.get_Parameter(BuiltInParameter.CONDUIT_DIAMETER)
            if p is not None:
                diametro_mm = p.AsDouble() * FT_A_MM
        except Exception:
            diametro_mm = None
        tipos.append({"tipo": t, "id": id_de(t), "diametro_mm": diametro_mm})
    return tipos


def seleccionar_tipo_por_diametro(tipos, diametro_deseado_mm):
    if not tipos:
        return None
    mejor = None
    mejor_delta = None
    for info in tipos:
        dt = info["diametro_mm"]
        if dt is None:
            continue
        delta = abs(dt - diametro_deseado_mm)
        if mejor_delta is None or delta < mejor_delta:
            mejor = info["tipo"]
            mejor_delta = delta
    if mejor is not None:
        return mejor
    return tipos[0]["tipo"]


def cargar_inserts(path_json):
    with open(path_json, "r") as f:
        datos = json.load(f)
    return datos.get("inserts_f17", []), datos.get("inserts_f18", [])


def cargar_conductos(path_json):
    with open(path_json, "r") as f:
        datos = json.load(f)
    return datos.get("conductos_f17", []), datos.get("conductos_f18", [])


def recolectar_dispositivos_revit(doc):
    """Recolecta dispositivos electricos ya colocados en Revit."""
    dispositivos = []
    cat = BuiltInCategory.OST_ElectricalFixtures
    for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
        try:
            loc = el.Location
            if loc is None:
                continue
            pt = None
            try:
                pt = loc.Point
            except Exception:
                continue
            if pt is None:
                continue
            # Obtener nombre de familia
            nombre_familia = ""
            try:
                sym = el.Symbol
                if sym is not None:
                    try:
                        nombre_familia = sym.get_Parameter(
                            BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
                    except Exception:
                        nombre_familia = sym.Name if hasattr(sym, "Name") else ""
            except Exception:
                nombre_familia = el.Name
            dispositivos.append({
                "id": id_de(el),
                "x_mm": pt.X * FT_A_MM,
                "y_mm": pt.Y * FT_A_MM,
                "z_mm": pt.Z * FT_A_MM,
                "familia": nombre_familia,
                "nombre": el.Name,
            })
        except Exception:
            continue
    return dispositivos


def calcular_offset_por_apartamento(inserts_dxf, dispositivos_revit, nombre_apto):
    """
    Para un apartamento, compara cada insert DXF con el dispositivo equivalente
    en Revit y calcula el offset promedio (dx, dy).
    """
    # Agrupar dispositivos de Revit por familia
    devs_por_familia = {}
    for d in dispositivos_revit:
        fam = d.get("familia", "")
        if fam not in devs_por_familia:
            devs_por_familia[fam] = []
        devs_por_familia[fam].append(d)

    offsets_x = []
    offsets_y = []
    matches = 0
    total = 0
    detalle = []

    for ins in inserts_dxf:
        bloque = ins["bloque"]
        if bloque not in MAPEO_DXF_REVIT:
            continue
        familia_revit = MAPEO_DXF_REVIT[bloque]
        if familia_revit not in devs_por_familia:
            continue

        x_dxf = ins["x"]
        y_dxf = ins["y"]

        # Buscar el dispositivo de Revit mas cercano de esa familia
        mejor_dev = None
        mejor_dist = None
        for d in devs_por_familia[familia_revit]:
            d2 = dist_2d([x_dxf, y_dxf], [d["x_mm"], d["y_mm"]])
            if mejor_dist is None or d2 < mejor_dist:
                mejor_dist = d2
                mejor_dev = d

        if mejor_dev is not None and mejor_dist <= TOLERANCIA_MATCH_MM:
            dx = mejor_dev["x_mm"] - x_dxf
            dy = mejor_dev["y_mm"] - y_dxf
            offsets_x.append(dx)
            offsets_y.append(dy)
            matches = matches + 1
            detalle.append("  %s: dxf=(%.1f,%.1f) revit=(%.1f,%.1f) dx=%.1f dy=%.1f dist=%.1f" % (
                bloque, x_dxf, y_dxf, mejor_dev["x_mm"], mejor_dev["y_mm"], dx, dy, mejor_dist))
        total = total + 1

    if matches == 0:
        return None

    dx_prom = sum(offsets_x) / len(offsets_x)
    dy_prom = sum(offsets_y) / len(offsets_y)

    # Calcular desviacion estandar para reportar calidad
    var_x = sum((d - dx_prom) ** 2 for d in offsets_x) / len(offsets_x)
    var_y = sum((d - dy_prom) ** 2 for d in offsets_y) / len(offsets_y)
    std_x = math.sqrt(var_x)
    std_y = math.sqrt(var_y)

    return {
        "apto": nombre_apto,
        "dx_mm": round(dx_prom, 3),
        "dy_mm": round(dy_prom, 3),
        "std_x_mm": round(std_x, 2),
        "std_y_mm": round(std_y, 2),
        "n_inserts_dxf": total,
        "n_matches": matches,
        "cobertura": round(100.0 * matches / total, 1) if total else 0.0,
        "detalle": detalle,
    }


def descomponer_lwpolyline_en_segmentos(vertices):
    """Convierte una lista de vertices [x,y] en segmentos consecutivos."""
    segmentos = []
    for i in range(len(vertices) - 1):
        a = vertices[i]
        b = vertices[i + 1]
        if abs(a[0] - b[0]) < 0.001 and abs(a[1] - b[1]) < 0.001:
            continue
        segmentos.append({
            "a_mm": [a[0], a[1], 0.0],
            "b_mm": [b[0], b[1], 0.0],
        })
    return segmentos


def crear_conduit(doc, tipo_id, level_id, a_mm, b_mm, z_mm):
    return Conduit.Create(doc, ElementId(Int64(tipo_id)),
                          xyz_mm(a_mm[0], a_mm[1], z_mm),
                          xyz_mm(b_mm[0], b_mm[1], z_mm),
                          ElementId(Int64(level_id)))


def main():
    _iniciar_log()
    log("=" * 60)
    log("RE7_CREAR_CONDUITS_F17_F18_{} - Etapa 4 F7 (DXF vs Revit directo)".format(VERSION))
    log("ejecutado_utc={}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo de Revit.")
        return 1

    titulo = doc.Title
    if DOC_PROHIBIDO in titulo:
        log("ERROR: documento prohibido para escritura: {!r}".format(titulo))
        return 1

    log("documento={!r} modificado={}".format(titulo, bool(doc.IsModified)))
    log("=" * 60)

    # --- PASO 1: Borrar conduits creados por v02 y v03 ---
    raiz = _raiz()
    conduit_ids_borrar = []
    for nombre_reporte in ["f7_conduits_creados_f17_f18_v02.json",
                           "f7_conduits_creados_f17_f18_v03.json"]:
        reporte_path = os.path.join(raiz, "data", nombre_reporte)
        if os.path.exists(reporte_path):
            try:
                with open(reporte_path, "r") as f:
                    reporte_previo = json.load(f)
                for c in reporte_previo.get("conduits", []):
                    cid = c.get("conduit_id")
                    if cid is not None:
                        conduit_ids_borrar.append(cid)
            except Exception:
                pass

    log("Conduits previos a borrar: %d" % len(conduit_ids_borrar))
    if conduit_ids_borrar:
        trans = Transaction(doc, "RE7_BORRAR_CONDUITS_PREVIOS")
        trans.Start()
        try:
            borrados = 0
            no_encontrados = 0
            for cid in conduit_ids_borrar:
                try:
                    el = doc.GetElement(ElementId(Int64(cid)))
                    if el is not None:
                        doc.Delete(el.Id)
                        borrados = borrados + 1
                    else:
                        no_encontrados = no_encontrados + 1
                except Exception:
                    no_encontrados = no_encontrados + 1
            trans.Commit()
            log("Borrado: %d eliminados, %d no encontrados." % (borrados, no_encontrados))
        except Exception:
            trans.RollBack()
            raise

    # --- PASO 2: Obtener nivel y tipos ---
    nivel = buscar_nivel(doc)
    if nivel is None:
        log("ERROR: no se encontro nivel Piso 5.")
        return 1
    log("nivel: {!r} id={} elevacion={} mm".format(
        nivel.Name, id_de(nivel), round(nivel.Elevation * FT_A_MM, 3)))

    tipos = listar_tipos_conduit(doc)
    log("Tipos de conduit validos: {}".format(len(tipos)))
    for info in tipos:
        log("  id={} diametro_mm={}".format(info["id"], info["diametro_mm"]))

    if not tipos:
        log("ERROR: no se encontro ningun tipo de conduit valido.")
        return 1

    # --- PASO 3: Recolectar dispositivos en Revit ---
    dispositivos_revit = recolectar_dispositivos_revit(doc)
    log("Dispositivos electricos en Revit: {}".format(len(dispositivos_revit)))

    # --- PASO 4: Calcular offset por apartamento ---
    inserts_f17, inserts_f18 = cargar_inserts(
        os.path.join(raiz, "data", "f7_inserts_dxf_xpl_f17_f18_v01.json"))

    offset_f17 = calcular_offset_por_apartamento(
        inserts_f17, dispositivos_revit, "Apartamento Tipo F 17")
    offset_f18 = calcular_offset_por_apartamento(
        inserts_f18, dispositivos_revit, "Apartamentos Tipo F 18")

    offsets = {}
    if offset_f17:
        offsets["Apartamento Tipo F 17"] = offset_f17
        log("F17: dx=%.3f dy=%.3f matches=%d/%d (cobertura %s%%) std=(%.1f,%.1f)" % (
            offset_f17["dx_mm"], offset_f17["dy_mm"],
            offset_f17["n_matches"], offset_f17["n_inserts_dxf"],
            offset_f17["cobertura"], offset_f17["std_x_mm"], offset_f17["std_y_mm"]))
    else:
        log("F17: NO SE PUDO CALCULAR OFFSET")

    if offset_f18:
        offsets["Apartamentos Tipo F 18"] = offset_f18
        log("F18: dx=%.3f dy=%.3f matches=%d/%d (cobertura %s%%) std=(%.1f,%.1f)" % (
            offset_f18["dx_mm"], offset_f18["dy_mm"],
            offset_f18["n_matches"], offset_f18["n_inserts_dxf"],
            offset_f18["cobertura"], offset_f18["std_x_mm"], offset_f18["std_y_mm"]))
    else:
        log("F18: NO SE PUDO CALCULAR OFFSET")

    if not offsets:
        log("ERROR: no se encontro offset para ningun apartamento.")
        return 1

    # --- PASO 5: Aplicar offset a segmentos de conducto del DXF ---
    conductos_f17, conductos_f18 = cargar_conductos(
        os.path.join(raiz, "data", "f7_conductos_dxf_xpl_f17_f18_v01.json"))

    segmentos_a_crear = []

    def agregar_conductos(conductos, apto_key, offset_info):
        if not offset_info:
            return
        dx = offset_info["dx_mm"]
        dy = offset_info["dy_mm"]
        for c in conductos:
            layer = c["layer"]
            diametro = 16.0 if "LIGHT" in layer.upper() else 21.0
            seglist = descomponer_lwpolyline_en_segmentos(c["vertices"])
            for seg in seglist:
                seg["apto"] = apto_key
                seg["servicio"] = "ILUMINACION" if "LIGHT" in layer.upper() else "FUERZA"
                seg["diametro_mm"] = diametro
                seg["layer"] = layer
                seg["z_mm"] = Z_CONDUIT_MM
                seg["a_mm"] = [
                    round(seg["a_mm"][0] + dx, 3),
                    round(seg["a_mm"][1] + dy, 3),
                    Z_CONDUIT_MM,
                ]
                seg["b_mm"] = [
                    round(seg["b_mm"][0] + dx, 3),
                    round(seg["b_mm"][1] + dy, 3),
                    Z_CONDUIT_MM,
                ]
                segmentos_a_crear.append(seg)

    agregar_conductos(conductos_f17, "Apartamento Tipo F 17", offset_f17)
    agregar_conductos(conductos_f18, "Apartamentos Tipo F 18", offset_f18)

    log("Segmentos a crear: total=%d" % len(segmentos_a_crear))

    if len(segmentos_a_crear) == 0:
        log("ERROR: no hay segmentos para crear.")
        return 1

    # --- PASO 6: Crear conduits ---
    creados = []
    fallos = []
    trans = Transaction(doc, "RE7_CREAR_CONDUITS_F17_F18_v04")
    trans.Start()
    try:
        for i in range(len(segmentos_a_crear)):
            seg = segmentos_a_crear[i]
            try:
                diametro = float(seg.get("diametro_mm", 21.0))
                tipo = seleccionar_tipo_por_diametro(tipos, diametro)
                if tipo is None:
                    fallos.append({"index": i, "error": "tipo no encontrado"})
                    continue
                tipo_id = id_de(tipo)
                z_mm = float(seg.get("z_mm", Z_CONDUIT_MM))
                a_mm = [float(seg["a_mm"][0]), float(seg["a_mm"][1]), z_mm]
                b_mm = [float(seg["b_mm"][0]), float(seg["b_mm"][1]), z_mm]
                c = crear_conduit(doc, tipo_id, id_de(nivel), a_mm, b_mm, z_mm)
                creados.append({
                    "index": i,
                    "conduit_id": id_de(c),
                    "tipo_id": tipo_id,
                    "apto": seg.get("apto"),
                    "servicio": seg.get("servicio"),
                    "layer": seg.get("layer"),
                    "a_mm": a_mm,
                    "b_mm": b_mm,
                    "largo_mm": round(dist_3d(b_mm, a_mm), 3),
                    "diametro_mm": diametro,
                    "z_mm": z_mm,
                })
                if (i + 1) % 20 == 0:
                    log("  creados %d de %d..." % (i + 1, len(segmentos_a_crear)))
            except Exception as e:
                fallos.append({"index": i, "error": str(e)[:200]})
                log("  ERROR creando seg %d: %s" % (i, str(e)[:100]))
        trans.Commit()
        log("Transaccion COMMIT: %d conduits creados, %d fallos." % (len(creados), len(fallos)))
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    # --- PASO 7: Verificacion post-creacion ---
    reporte = {
        "version": VERSION,
        "script": "RE7_CREAR_CONDUITS_F17_F18_v04",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "nivel": {"id": id_de(nivel), "nombre": nivel.Name,
                  "elevacion_mm": round(nivel.Elevation * FT_A_MM, 3)},
        "parametros": {"total_segmentos": len(segmentos_a_crear),
                       "tipos_conduit": len(tipos),
                       "z_conduit_mm": Z_CONDUIT_MM},
        "borrado_previo": {"ids": conduit_ids_borrar, "contador": len(conduit_ids_borrar)},
        "offsets_calculados": offsets,
        "resumen": {"creados": len(creados), "fallos": len(fallos)},
        "conduits": [],
        "fallos": fallos,
    }

    for item in creados:
        c = doc.GetElement(ElementId(Int64(item["conduit_id"])))
        if c is None:
            continue
        loc = c.Location
        a_real = None
        b_real = None
        if isinstance(loc, LocationCurve):
            curva = loc.Curve
            ep0 = curva.GetEndPoint(0)
            ep1 = curva.GetEndPoint(1)
            a_real = [ep0.X * FT_A_MM, ep0.Y * FT_A_MM, ep0.Z * FT_A_MM]
            b_real = [ep1.X * FT_A_MM, ep1.Y * FT_A_MM, ep1.Z * FT_A_MM]

        def dist(p, q):
            return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 +
                             (p[2] - q[2]) ** 2)
        da = dist(a_real, item["a_mm"]) if a_real else None
        db = dist(b_real, item["b_mm"]) if b_real else None
        largo_real = dist(a_real, b_real) if (a_real and b_real) else None
        ok = (da is not None and db is not None and da < 10.0 and db < 10.0)
        item_reporte = {
            "index": item["index"],
            "conduit_id": item["conduit_id"],
            "apto": item["apto"],
            "servicio": item["servicio"],
            "layer": item["layer"],
            "a_mm_esperado": item["a_mm"],
            "b_mm_esperado": item["b_mm"],
            "a_mm_real": [round(v, 3) for v in a_real] if a_real else None,
            "b_mm_real": [round(v, 3) for v in b_real] if b_real else None,
            "dist_a_mm": round(da, 3) if da is not None else None,
            "dist_b_mm": round(db, 3) if db is not None else None,
            "largo_esperado_mm": item["largo_mm"],
            "largo_real_mm": round(largo_real, 3) if largo_real is not None else None,
            "verificado": ok,
            "diametro_mm": item["diametro_mm"],
            "z_mm": item["z_mm"],
        }
        reporte["conduits"].append(item_reporte)
        if not ok:
            log("  VERIF FALLO id=%s: dist_a=%s dist_b=%s" % (
                item["conduit_id"], item_reporte["dist_a_mm"],
                item_reporte["dist_b_mm"]))

    todos_ok = True
    if reporte["conduits"]:
        for c in reporte["conduits"]:
            if not c["verificado"]:
                todos_ok = False
                break
    verificados_ok = 0
    verificados_fallo = 0
    for c in reporte["conduits"]:
        if c["verificado"]:
            verificados_ok = verificados_ok + 1
        else:
            verificados_fallo = verificados_fallo + 1
    reporte["resumen"]["verificados_ok"] = verificados_ok
    reporte["resumen"]["verificados_fallo"] = verificados_fallo

    out_json = os.path.join(raiz, "data", "f7_conduits_creados_f17_f18_v04.json")
    contenido = json.dumps(reporte, ensure_ascii=True, indent=2)
    if escribir_archivo_texto(out_json, contenido):
        log("Reporte guardado en: {}".format(out_json))
    else:
        log("ERROR: no se pudo escribir el reporte JSON.")

    log("RESULTADO: %d conduits creados, %d verificados OK, %d fallos en creacion." % (
        len(creados), verificados_ok, len(fallos)))
    log("FIN")
    log("=" * 60)
    return 0 if todos_ok and len(fallos) == 0 else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    try:
        log("EXCEPCION NO CONTROLADA:\n" + traceback.format_exc())
    except Exception:
        pass
    raise SystemExit(1)
