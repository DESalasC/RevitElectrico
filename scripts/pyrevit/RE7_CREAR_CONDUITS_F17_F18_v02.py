# -*- coding: utf-8 -*-
"""
RE7_CREAR_CONDUITS_F17_F18_v02.py
Etapa 2 del ruteo F7: crea conduits para F17 y F18 sobre dispositivos REALES del modelo.

PROBLEMA v01: El alineamiento de coordenadas (RE7_ALIGN_COORDS_v01.py) uso pocos
dispositivos para calcular el offset y creo conduits en ubicacion incorrecta
(F17a/F18a o fuera del edificio). Estos conduits fueron borrados por el operador.

ENFOQUE v02:
1. Colecciona TODOS los dispositivos electricos del modelo Revit (categoria OST_ElectricalFixtures)
2. Agrupa dispositivos por proximidad espacial (clusters = apartamentos)
3. Para F17 y F18, identifica el cluster de dispositivos correspondiente
4. Calcula el offset (dx, dy) que alinea los extremos de segmento con ese cluster
5. Crea conduits con Conduit.Create en el nivel Piso 5
6. Verifica post-creacion que cada extremo quede a < 10 mm de su posicion esperada
7. Escribe reporte JSON con todos los resultados

ENTRADA: data/f7_segmentos_f17_f18_v01.json  (segmentos en coords del DXF, sin offset)
SALIDA:  data/f7_conduits_creados_f17_f18_v02.json (reporte de conduits creados)

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

VERSION = "v02"
FT_A_MM = 304.8
DOC_PROHIBIDO = "V02-f"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
LOG_PATH = None


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
    LOG_PATH = os.path.join(carpeta, "f7_crear_conduits_f17_f18_v02.log")


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


def buscar_nivel(doc, nombre_esperado="Piso 5", elevacion_m=13.22, tolerancia_mm=5.0):
    mejor = None
    mejor_delta = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        delta = abs(lvl.Elevation * FT_A_MM - elevacion_m * 1000.0)
        if mejor_delta is None or delta < mejor_delta:
            mejor = lvl
            mejor_delta = delta
        if lvl.Name == nombre_esperado or delta <= tolerancia_mm:
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


def cargar_segmentos(path_seg):
    with open(path_seg, "r") as f:
        datos = json.load(f)
    return datos.get("segmentos", [])


def recolectar_dispositivos(doc):
    """Recolecta todos los dispositivos electricos del modelo con sus coords."""
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
            dispositivos.append({
                "id": id_de(el),
                "x_mm": pt.X * FT_A_MM,
                "y_mm": pt.Y * FT_A_MM,
                "z_mm": pt.Z * FT_A_MM,
                "nombre": el.Name,
                "categoria": el.Category.Name if el.Category else "",
            })
        except Exception:
            continue
    return dispositivos


def centroide(puntos):
    if not puntos:
        return (0.0, 0.0)
    sx = 0.0
    sy = 0.0
    for p in puntos:
        sx = sx + p[0]
        sy = sy + p[1]
    n = len(puntos)
    return (sx / n, sy / n)


def agrupar_dispositivos_por_cluster(dispositivos, tam_celda_mm=3000.0):
    """Agrupa dispositivos en cajas espaciales (una caja ~= un apartamento)."""
    grid = {}
    for d in dispositivos:
        x = d.get("x_mm")
        y = d.get("y_mm")
        if x is None or y is None:
            continue
        gx = int(x // tam_celda_mm)
        gy = int(y // tam_celda_mm)
        clave = str(gx) + "," + str(gy)
        if clave not in grid:
            grid[clave] = []
        grid[clave].append(d)
    return grid


def buscar_offset_para_apartamento(segmentos, dispositivos_validos, nombre_apto,
                                    clusters, tolerancia_mm=300.0):
    """Para un apartamento, busca el cluster de dispositivos que mejor coincide
    y devuelve el offset (dx,dy) que alinea los extremos de segmento con ese cluster."""
    extremos = []
    for s in segmentos:
        apto = s.get("apto", "")
        if nombre_apto in apto:
            extremos.append(s["a_mm"])
            extremos.append(s["b_mm"])
    if not extremos:
        return None
    cen_ext = centroide(extremos)

    mejor_cluster = None
    mejor_offset = None
    mejor_n_match = -1
    mejor_detalle = ""

    for clave in clusters:
        disps = clusters[clave]
        if not disps:
            continue
        pts = []
        for d in disps:
            if d.get("x_mm") is not None and d.get("y_mm") is not None:
                pts.append((d["x_mm"], d["y_mm"]))
        if not pts:
            continue
        cen_dis = centroide(pts)
        dx = cen_dis[0] - cen_ext[0]
        dy = cen_dis[1] - cen_ext[1]
        # Contar cuántos extremos (desplazados) quedan cerca de un dispositivo
        n_match = 0
        for e in extremos:
            ex = e[0] + dx
            ey = e[1] + dy
            mejor_dist = None
            for p in pts:
                d2 = dist_2d([ex, ey], p)
                if mejor_dist is None or d2 < mejor_dist:
                    mejor_dist = d2
            if mejor_dist is not None and mejor_dist <= tolerancia_mm:
                n_match = n_match + 1
        if n_match > mejor_n_match:
            mejor_n_match = n_match
            mejor_cluster = clave
            mejor_offset = (dx, dy)
            mejor_detalle = "cluster=%s n_disps=%d n_match=%d/%d" % (
                clave, len(disps), n_match, len(extremos))

    if mejor_offset is None:
        return None

    dx, dy = mejor_offset
    return {
        "apto": nombre_apto,
        "cluster": mejor_cluster,
        "dx_mm": round(dx, 3),
        "dy_mm": round(dy, 3),
        "n_extremos": len(extremos),
        "n_match": mejor_n_match,
        "detalle": mejor_detalle,
    }


def aplicar_offset_a_segmentos(segmentos, offsets):
    out = []
    for s in segmentos:
        apto = s.get("apto", "")
        off = None
        for key in offsets:
            if key in apto:
                off = offsets[key]
                break
        dx = off["dx_mm"] if off else 0.0
        dy = off["dy_mm"] if off else 0.0
        ns = dict(s)
        ns["a_mm"] = [round(s["a_mm"][0] + dx, 3),
                      round(s["a_mm"][1] + dy, 3), s["a_mm"][2]]
        ns["b_mm"] = [round(s["b_mm"][0] + dx, 3),
                      round(s["b_mm"][1] + dy, 3), s["b_mm"][2]]
        ns["offset_aplicado"] = {"dx_mm": dx, "dy_mm": dy}
        out.append(ns)
    return out


def crear_conduit(doc, tipo_id, level_id, a_mm, b_mm):
    return Conduit.Create(doc, ElementId(Int64(tipo_id)),
                          xyz_mm(*a_mm), xyz_mm(*b_mm),
                          ElementId(Int64(level_id)))


def main():
    _iniciar_log()
    log("=" * 60)
    log("RE7_CREAR_CONDUITS_F17_F18_{} - Etapa 2 F7 (dispositivos reales)".format(VERSION))
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

    raiz = _raiz()
    seg_path = os.path.join(raiz, "data", "f7_segmentos_f17_f18_v01.json")
    if not os.path.exists(seg_path):
        log("ERROR: no existe {}".format(seg_path))
        return 1

    segmentos = cargar_segmentos(seg_path)
    log("Segmentos cargados: {}".format(len(segmentos)))

    # Recolectar dispositivos reales del modelo
    dispositivos = recolectar_dispositivos(doc)
    log("Dispositivos electricos en modelo: {}".format(len(dispositivos)))

    # Agrupar por cluster espacial
    clusters = agrupar_dispositivos_por_cluster(dispositivos, tam_celda_mm=3000.0)
    log("Clusters espaciales detectados: {}".format(len(clusters)))

    # Calcular offset para F17 y F18
    aptos_buscar = ["Apartamento Tipo F 17", "Apartamentos Tipo F 18"]
    offsets = {}
    for apto in aptos_buscar:
        res = buscar_offset_para_apartamento(
            segmentos, dispositivos, apto, clusters, tolerancia_mm=300.0)
        if res:
            offsets[apto] = res
            log("  %s: dx=%.3f dy=%.3f | %s" % (
                res["apto"], res["dx_mm"], res["dy_mm"], res["detalle"]))
        else:
            log("  %s: NO SE ENCONTRO OFFSET" % apto)

    if not offsets:
        log("ERROR: no se encontro offset para ninguno de los apartamentos.")
        return 1

    # Aplicar offset a segmentos
    segmentos_alineados = aplicar_offset_a_segmentos(segmentos, offsets)

    # Verificar cobertura: cuántos extremos quedan cerca de un dispositivo
    pts_dis = []
    for d in dispositivos:
        if d.get("x_mm") is not None and d.get("y_mm") is not None:
            pts_dis.append((d["x_mm"], d["y_mm"]))
    cubiertos = 0
    total_extremos = 0
    distancias = []
    for s in segmentos_alineados:
        for extremo in [s["a_mm"], s["b_mm"]]:
            total_extremos = total_extremos + 1
            if pts_dis:
                mejor = None
                for p in pts_dis:
                    d2 = dist_2d(extremo, p)
                    if mejor is None or d2 < mejor:
                        mejor = d2
                distancias.append(mejor)
                if mejor <= 300.0:
                    cubiertos = cubiertos + 1
    distancias.sort()
    n = len(distancias)
    p50 = distancias[n // 2] if n else 0
    p95 = distancias[int(n * 0.95)] if n else 0
    pmax = distancias[-1] if n else 0
    log("Cobertura: %d/%d extremos dentro de 300mm de un dispositivo" % (cubiertos, total_extremos))
    log("  p50=%.1fmm p95=%.1fmm max=%.1fmm" % (p50, p95, pmax))

    # Crear conduits
    creados = []
    fallos = []
    trans = Transaction(doc, "RE7_CREAR_CONDUITS_F17_F18_v02")
    trans.Start()
    try:
        for i in range(len(segmentos_alineados)):
            s = segmentos_alineados[i]
            try:
                diametro = float(s.get("diametro_mm", 21.03))
                tipo = seleccionar_tipo_por_diametro(tipos, diametro)
                if tipo is None:
                    fallos.append({"id": s.get("id"), "error": "tipo no encontrado"})
                    continue
                tipo_id = id_de(tipo)
                a_mm = [float(s["a_mm"][0]), float(s["a_mm"][1]), float(s["a_mm"][2])]
                b_mm = [float(s["b_mm"][0]), float(s["b_mm"][1]), float(s["b_mm"][2])]
                c = crear_conduit(doc, tipo_id, id_de(nivel), a_mm, b_mm)
                creados.append({
                    "id_ref": s.get("id"),
                    "conduit_id": id_de(c),
                    "tipo_id": tipo_id,
                    "apto": s.get("apto"),
                    "servicio": s.get("servicio"),
                    "a_mm": a_mm,
                    "b_mm": b_mm,
                    "largo_mm": round(dist_3d(b_mm, a_mm), 3),
                    "diametro_mm": diametro,
                    "tamano": s.get("tamano", ""),
                    "polilinea_id": s.get("polilinea_id", ""),
                })
                if (i + 1) % 20 == 0:
                    log("  creados %d de %d..." % (i + 1, len(segmentos_alineados)))
            except Exception as e:
                fallos.append({"id": s.get("id"), "error": str(e)[:200]})
                log("  ERROR creando id %s: %s" % (s.get("id"), str(e)[:100]))
        trans.Commit()
        log("Transaccion COMMIT: %d conduits creados, %d fallos." % (len(creados), len(fallos)))
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    # Verificacion post-creacion
    reporte = {
        "version": VERSION,
        "script": "RE7_CREAR_CONDUITS_F17_F18_v02",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "nivel": {"id": id_de(nivel), "nombre": nivel.Name,
                  "elevacion_mm": round(nivel.Elevation * FT_A_MM, 3)},
        "parametros": {"total_segmentos": len(segmentos_alineados),
                       "tipos_conduit": len(tipos)},
        "offsets": offsets,
        "cobertura_pre_creacion": {
            "total_extremos": total_extremos,
            "cubiertos_300mm": cubiertos,
            "p50_mm": round(p50, 2),
            "p95_mm": round(p95, 2),
            "max_mm": round(pmax, 2),
        },
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
            "id_ref": item["id_ref"],
            "conduit_id": item["conduit_id"],
            "apto": item["apto"],
            "servicio": item["servicio"],
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
            "tamano": item["tamano"],
            "polilinea_id": item["polilinea_id"],
        }
        reporte["conduits"].append(item_reporte)
        if not ok:
            log("  VERIF FALLO id=%s: dist_a=%s dist_b=%s" % (
                item["id_ref"], item_reporte["dist_a_mm"],
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

    out_json = os.path.join(raiz, "data", "f7_conduits_creados_f17_f18_v02.json")
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
