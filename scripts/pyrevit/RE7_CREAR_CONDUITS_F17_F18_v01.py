# -*- coding: utf-8 -*-
"""
RE7_CREAR_CONDUITS_F17_F18_v01.py
Etapa 2 del ruteo F7: crea conduits en Revit para los apartamentos F17 y F18,
replicando los segmentos generados desde el DXF y alineados al modelo.

Lee:  data/f7_segmentos_f17_f18_v02_aligned.json  (segmentos ya alineados al modelo Revit)
Escribe: data/f7_conduits_creados_f17_f18_v01.json  (reporte de conduits creados)

RESTRICTION: Ejecutar solo en CENTRAL-V01b (o sucesor), NUNCA en V02-f (referencia intocable).
Piloto: CENTRAL-V01b.

Uso (consola Python de Revit, IronPython 2.7):
    exec(open(r"D:\Work\PROJECTS\RevitElectrico\scripts\pyrevit\RE7_CREAR_CONDUITS_F17_F18_v01.py").read())
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
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
from System import Int64, IO

VERSION = "v01"
FT_A_MM = 304.8
DOC_PROHIBIDO = "V02-f"  # referencia intocable
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
    LOG_PATH = os.path.join(carpeta, "f7_crear_conduits_f17_f18_v01.log")
    try:
        with open(LOG_PATH, "a") as f:
            f.write("[{}] INICIO RE7_CREAR_CONDUITS_F17_F18_{}\n".format(
                datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), VERSION))
    except Exception:
        pass


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


def escribir_archivo_binario(ruta, contenido_bytes):
    try:
        IO.File.WriteAllBytes(ruta, contenido_bytes)
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


def crear_conduit(doc, tipo_id, level_id, a_mm, b_mm):
    return Conduit.Create(doc, ElementId(Int64(tipo_id)), xyz_mm(*a_mm), xyz_mm(*b_mm), ElementId(Int64(level_id)))


def main():
    _iniciar_log()
    log("=" * 60)
    log("RE7_CREAR_CONDUITS_F17_F18_{} - Etapa 2 F7".format(VERSION))
    log("ejecutado_utc={}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo de Revit.")
        return 1

    titulo = doc.Title
    if DOC_PROHIBIDO in titulo:
        log("ERROR: documento prohibido para escritura: {!r}".format(titulo))
        log("     El piloto de creacion va en CENTRAL-V01b, no en V02-f (referencia).")
        return 1

    try:
        app_version = doc.Application.Version
    except Exception:
        app_version = "?"
    log("documento={!r} version_revit={} modificado={}".format(titulo, app_version, bool(doc.IsModified)))
    log("=" * 60)

    nivel = buscar_nivel(doc)
    if nivel is None:
        log("ERROR: no se encontro nivel Piso 5.")
        return 1
    log("nivel: {!r} id={} elevacion={} mm".format(nivel.Name, id_de(nivel), round(nivel.Elevation * FT_A_MM, 3)))

    tipos = listar_tipos_conduit(doc)
    log("Tipos de conduit validos encontrados: {}".format(len(tipos)))
    for info in tipos:
        log("  id={} diametro_mm={}".format(info["id"], info["diametro_mm"]))

    if not tipos:
        log("ERROR: no se encontro ningun tipo de conduit valido.")
        return 1

    raiz = _raiz()
    seg_path = os.path.join(raiz, "data", "f7_segmentos_f17_f18_v02_aligned.json")
    if not os.path.exists(seg_path):
        log("ERROR: no existe {}".format(seg_path))
        return 1

    segmentos = cargar_segmentos(seg_path)
    log("Segmentos cargados: {}".format(len(segmentos)))

    # Desglose por servicio y apartamento
    conteo_servicio = {}
    conteo_apto = {}
    for s in segmentos:
        svc = s.get("servicio", "") or "(vacio)"
        apto = s.get("apto", "") or "(vacio)"
        conteo_servicio[svc] = conteo_servicio.get(svc, 0) + 1
        conteo_apto[apto] = conteo_apto.get(apto, 0) + 1
    log("Desglose por servicio: {}".format(conteo_servicio))
    log("Desglose por apartamento: {}".format(conteo_apto))

    creados = []
    fallos = []
    trans = Transaction(doc, "RE7_CREAR_CONDUITS_F17_F18_v01")
    trans.Start()
    try:
        for i, s in enumerate(segmentos):
            try:
                diametro = float(s.get("diametro_mm", 21.03))
                tipo = seleccionar_tipo_por_diametro(tipos, diametro)
                if tipo is None:
                    log("AVISO: no se encontro tipo para diametro {}, saltando id {}".format(diametro, s.get("id")))
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
                    log("  creados {} de {}...".format(i + 1, len(segmentos)))
            except Exception as e:
                fallos.append({"id": s.get("id"), "error": str(e)[:200]})
                log("  ERROR creando id {}: {}".format(s.get("id"), str(e)[:100]))
        trans.Commit()
        log("Transaccion COMMIT: {} conduits creados, {} fallos.".format(len(creados), len(fallos)))
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida.")
        traceback.print_exc()
        return 1

    # Verificacion post-creacion
    reporte = {
        "version": VERSION,
        "script": "RE7_CREAR_CONDUITS_F17_F18_v01",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "nivel": {"id": id_de(nivel), "nombre": nivel.Name, "elevacion_mm": round(nivel.Elevation * FT_A_MM, 3)},
        "parametros": {"total_segmentos": len(segmentos), "tipos_conduit": len(tipos)},
        "resumen": {"creados": len(creados), "fallos": len(fallos)},
        "conduits": [],
        "fallos": fallos,
    }

    for item in creados:
        c = doc.GetElement(ElementId(Int64(item["conduit_id"])))
        if c is None:
            continue
        loc = c.Location
        a_real = b_real = None
        if isinstance(loc, LocationCurve):
            curva = loc.Curve
            a_real = [curva.GetEndPoint(0).X * FT_A_MM, curva.GetEndPoint(0).Y * FT_A_MM, curva.GetEndPoint(0).Z * FT_A_MM]
            b_real = [curva.GetEndPoint(1).X * FT_A_MM, curva.GetEndPoint(1).Y * FT_A_MM, curva.GetEndPoint(1).Z * FT_A_MM]

        def dist(p, q):
            return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)
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
            log("  VERIF FALLO id={}: dist_a={} dist_b={}".format(item["id_ref"], item_reporte["dist_a_mm"], item_reporte["dist_b_mm"]))

    todos_ok = all(c["verificado"] for c in reporte["conduits"]) if reporte["conduits"] else False
    reporte["resumen"]["verificados_ok"] = sum(1 for c in reporte["conduits"] if c["verificado"])
    reporte["resumen"]["verificados_fallo"] = sum(1 for c in reporte["conduits"] if not c["verificado"])

    out_json = os.path.join(raiz, "data", "f7_conduits_creados_f17_f18_v01.json")
    try:
        contenido = json.dumps(reporte, ensure_ascii=True, indent=2).encode("utf-8")
        if escribir_archivo_binario(out_json, contenido):
            log("Reporte guardado en: {}".format(out_json))
        else:
            log("ERROR: no se pudo escribir el reporte JSON.")
    except Exception as e:
        log("ERROR al escribir reporte JSON: {}".format(e))

    log("RESULTADO: {} conduits creados, {} verificados OK, {} fallos en creacion.".format(
        len(creados), reporte["resumen"]["verificados_ok"], len(fallos)))
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
