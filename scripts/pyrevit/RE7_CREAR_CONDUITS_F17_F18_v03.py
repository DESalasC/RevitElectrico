# -*- coding: utf-8 -*-
"""
RE7_CREAR_CONDUITS_F17_F18_v03.py
Etapa 3 del ruteo F7: crea conduits para F17 y F18 sobre el DXF XPL como referencia directa.

ENFOQUE v03 (corregido):
1. Borra conduits creados por v02 (ubicacion incorrecta) usando los conduit_ids del reporte v02
2. Lee conductos directamente del DXF XPL (f7_conductos_dxf_xpl_f17_f18_v01.json)
   - El DXF XPL es la fuente de verdad, mismo sistema de coordenadas que los dispositivos
3. Descompone cada LWPOLYLINE en segmentos consecutivos (pares de puntos)
4. Crea conduits con Conduit.Create en el nivel Piso 5
5. Tipo de conduit por capa: ELEC-LIGHT-PIPE -> Ø16, ELEC-POWER- PIPE -> Ø21, ELEC-Powr-Pipe-Idem Piso -> Ø21
6. Verifica post-creacion que cada extremo quede a < 10 mm de su posicion esperada
7. Escribe reporte JSON

ENTRADA: data/f7_conductos_dxf_xpl_f17_f18_v01.json (conductos del DXF XPL)
SALIDA:  data/f7_conduits_creados_f17_f18_v03.json (reporte)

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
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
from System import Int64

VERSION = "v03"
FT_A_MM = 304.8
DOC_PROHIBIDO = "V02-f"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
LOG_PATH = None

# Mapeo de capa a diametro de conduit (mm)
CAPA_DIAMETRO = {
    "ELEC-LIGHT-PIPE": 16.0,      # iluminacion -> conduit mas delgado
    "ELEC-POWER- PIPE": 21.0,     # fuerza -> conduit estandar
    "ELEC-Powr-Pipe-Idem Piso": 21.0,  # otros -> conduit estandar
}


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
    LOG_PATH = os.path.join(carpeta, "f7_crear_conduits_f17_f18_v03.log")


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


def cargar_conductos_dxf(path_json):
    with open(path_json, "r") as f:
        datos = json.load(f)
    return datos.get("conductos_f17", []), datos.get("conductos_f18", [])


def descomponer_lwpolyline_en_segmentos(vertices):
    """Convierte una lista de vertices [x,y] en segmentos consecutivos (pares de puntos)."""
    segmentos = []
    for i in range(len(vertices) - 1):
        a = vertices[i]
        b = vertices[i + 1]
        # Saltar segmentos de longitud cero
        if abs(a[0] - b[0]) < 0.001 and abs(a[1] - b[1]) < 0.001:
            continue
        segmentos.append({
            "a_mm": [a[0], a[1], 0.0],  # Z se asignara despues
            "b_mm": [b[0], b[1], 0.0],
        })
    return segmentos


def crear_conduit(doc, tipo_id, level_id, a_mm, b_mm, z_mm):
    return Conduit.Create(doc, ElementId(Int64(tipo_id)),
                          xyz_mm(a_mm[0], a_mm[1], z_mm),
                          xyz_mm(b_mm[0], b_mm[1], z_mm),
                          ElementId(Int64(level_id)))


def borrar_conduits_por_ids(doc, conduit_ids):
    """Borra conduits por lista de IDs. Devuelve (borrados, no_encontrados)."""
    borrados = 0
    no_encontrados = []
    trans = Transaction(doc, "RE7_BORRAR_CONDUITS_F17_F18_V02")
    trans.Start()
    try:
        for cid in conduit_ids:
            try:
                el = doc.GetElement(ElementId(Int64(cid)))
                if el is not None:
                    doc.Delete(el.Id)
                    borrados = borrados + 1
                else:
                    no_encontrados.append(cid)
            except Exception:
                no_encontrados.append(cid)
        trans.Commit()
    except Exception:
        trans.RollBack()
        raise
    return borrados, no_encontrados


def main():
    _iniciar_log()
    log("=" * 60)
    log("RE7_CREAR_CONDUITS_F17_F18_{} - Etapa 3 F7 (DXF XPL directo)".format(VERSION))
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

    # --- PASO 1: Borrar conduits creados por v02 ---
    raiz = _raiz()
    reporte_v02_path = os.path.join(raiz, "data", "f7_conduits_creados_f17_f18_v02.json")
    conduit_ids_borrar = []
    if os.path.exists(reporte_v02_path):
        with open(reporte_v02_path, "r") as f:
            reporte_v02 = json.load(f)
        for c in reporte_v02.get("conduits", []):
            cid = c.get("conduit_id")
            if cid is not None:
                conduit_ids_borrar.append(cid)
        log("Conduits v02 a borrar: %d" % len(conduit_ids_borrar))
    else:
        log("ADVERTENCIA: no existe reporte v02, saltando borrado.")

    if conduit_ids_borrar:
        borrados, no_encontrados = borrar_conduits_por_ids(doc, conduit_ids_borrar)
        log("Borrado: %d conduits eliminados, %d no encontrados." % (borrados, len(no_encontrados)))

    # --- PASO 2: Crear conduits desde DXF XPL ---
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

    # Z de los conduits (misma altura que dispositivos: 15930 mm = nivel Piso 5 aprox)
    Z_CONDUIT_MM = 15930.0

    conductos_f17, conductos_f18 = cargar_conductos_dxf(
        os.path.join(raiz, "data", "f7_conductos_dxf_xpl_f17_f18_v01.json"))

    # Construir lista de segmentos a crear
    segmentos_a_crear = []

    for c in conductos_f17:
        layer = c["layer"]
        diametro = CAPA_DIAMETRO.get(layer, 21.0)
        seglist = descomponer_lwpolyline_en_segmentos(c["vertices"])
        for seg in seglist:
            seg["apto"] = "Apartamento Tipo F 17"
            seg["servicio"] = "ILUMINACION" if "LIGHT" in layer.upper() else "FUERZA"
            seg["diametro_mm"] = diametro
            seg["layer"] = layer
            seg["z_mm"] = Z_CONDUIT_MM
            segmentos_a_crear.append(seg)

    for c in conductos_f18:
        layer = c["layer"]
        diametro = CAPA_DIAMETRO.get(layer, 21.0)
        seglist = descomponer_lwpolyline_en_segmentos(c["vertices"])
        for seg in seglist:
            seg["apto"] = "Apartamento Tipo F 18"
            seg["servicio"] = "ILUMINACION" if "LIGHT" in layer.upper() else "FUERZA"
            seg["diametro_mm"] = diametro
            seg["layer"] = layer
            seg["z_mm"] = Z_CONDUIT_MM
            segmentos_a_crear.append(seg)

    log("Segmentos a crear: F17=%d, F18=%d, total=%d" % (
        len(conductos_f17), len(conductos_f18), len(segmentos_a_crear)))

    if len(segmentos_a_crear) == 0:
        log("ERROR: no hay segmentos para crear.")
        return 1

    # --- PASO 3: Crear conduits ---
    creados = []
    fallos = []
    trans = Transaction(doc, "RE7_CREAR_CONDUITS_F17_F18_v03")
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

    # --- PASO 4: Verificacion post-creacion ---
    reporte = {
        "version": VERSION,
        "script": "RE7_CREAR_CONDUITS_F17_F18_v03",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "nivel": {"id": id_de(nivel), "nombre": nivel.Name,
                  "elevacion_mm": round(nivel.Elevation * FT_A_MM, 3)},
        "parametros": {"total_segmentos": len(segmentos_a_crear),
                       "tipos_conduit": len(tipos),
                       "z_conduit_mm": Z_CONDUIT_MM},
        "borrado_v02": {"ids": conduit_ids_borrar, "contador": len(conduit_ids_borrar)},
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

    out_json = os.path.join(raiz, "data", "f7_conduits_creados_f17_f18_v03.json")
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
