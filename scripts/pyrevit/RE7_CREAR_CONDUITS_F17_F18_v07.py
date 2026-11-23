# -*- coding: utf-8 -*-
"""
RE7_CREAR_CONDUITS_F17_F18_v07.py
Ruteo F7: crea conduits para F17 y F18 anclados a dispositivos REALES en Revit.

ENFOQUE v07 (corregido basado en piloto v06):
1. Borra conduits v05 existentes de F17/F18 (IDs del reporte v05)
2. Lee conductos del DXF XPL para F17 y F18 (f7_conectividad_dxf_f17_f18_v01.json)
3. Lee dispositivos eléctricos ya colocados en Revit
4. Para cada segmento de conducto (entre vertices consecutivos del DXF):
   - Encuentra el dispositivo más cercano a cada extremo (radio 300mm)
   - Si ambos extremos tienen dispositivo: crea conduit entre esos dos dispositivos
   - Si solo un extremo tiene dispositivo: crea conduit desde dispositivo hasta coordenada DXF
   - Si ninguno tiene dispositivo: usa coordenadas DXF con Z por defecto
5. Z por tipo de dispositivo (toma=300, interruptor=1100, luminaria=2600, etc.)
6. Salta conduits demasiado cortos (< 3mm entre extremos)
7. Verifica post-creacion: cada extremo a < 10mm del dispositivo real (si hay dispositivo)
8. Escribe reporte JSON con estadísticas detalladas

ENTRADA:
  data/f7_conectividad_dxf_f17_f18_v01.json  (conductos DXF F17/F18)
  data/f7_conduits_creados_f17_f18_v05.json  (para borrado previo)
SALIDA:  data/f7_conduits_creados_f17_f18_v07.json

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

VERSION = "v07"
FT_A_MM = 304.8
DOC_PROHIBIDO = "V02-f"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
LOG_PATH = None

# Z por tipo de dispositivo (mm sobre nivel Piso 5)
Z_POR_DISPOSITIVO = {
    "M_Toma doble": 300.0,
    "M_Comunicaciones": 300.0,
    "M_Interruptores": 1100.0,
    "M_Pulsador - Interruptor": 1100.0,
    "M_Timbre": 1100.0,
    "M_Iluminacion": 2600.0,
    "EA": 2400.0,
    "M_ClimatizacionV": 2400.0,
    "Consolidation_Point": 2700.0,
}

Z_DEFAULT_MM = 15930.0
RADIO_BUSQUEDA_MM = 300.0
LARGO_MINIMO_MM = 3.0  # Conduits mas cortos que esto se saltan


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
    LOG_PATH = os.path.join(carpeta, "f7_crear_conduits_f17_f18_v07.log")


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


def cargar_conductos_dxf(path_json, apto=None):
    with open(path_json, "r") as f:
        datos = json.load(f)
    conductos = datos.get("conductos", [])
    if apto:
        return [c for c in conductos if c.get("apto") == apto]
    return conductos


def recolectar_dispositivos_revit(doc):
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
            nombre_familia = ""
            try:
                sym = el.Symbol
                if sym is not None:
                    try:
                        nombre_familia = sym.get_Parameter(
                            BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or ""
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


def encontrar_dispositivo_cercano(x_mm, y_mm, dispositivos, radio_mm=RADIO_BUSQUEDA_MM):
    """Encuentra el dispositivo mas cercano a una coordenada 2D dentro del radio."""
    mejor = None
    mejor_dist = None
    for d in dispositivos:
        d2 = dist_2d([x_mm, y_mm], [d["x_mm"], d["y_mm"]])
        if mejor_dist is None or d2 < mejor_dist:
            mejor_dist = d2
            mejor = d
    if mejor is not None and mejor_dist <= radio_mm:
        return mejor, mejor_dist
    return None, mejor_dist


def z_por_dispositivo(dispositivo):
    """Devuelve la Z esperada para un dispositivo basado en su familia."""
    familia = dispositivo.get("familia", "")
    return Z_POR_DISPOSITIVO.get(familia, Z_DEFAULT_MM)


def descomponer_lwpolyline_en_segmentos(vertices):
    """Descompone una polilinea en segmentos rectos entre vertices consecutivos."""
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


def crear_conduit(doc, tipo_id, level_id, a_mm, b_mm, z_a_mm, z_b_mm):
    """Crea un conduit entre dos puntos con Z potencialmente diferentes."""
    return Conduit.Create(doc, ElementId(Int64(tipo_id)),
                          xyz_mm(a_mm[0], a_mm[1], z_a_mm),
                          xyz_mm(b_mm[0], b_mm[1], z_b_mm),
                          ElementId(Int64(level_id)))


def borrar_conduits_por_ids(doc, conduit_ids):
    borrados = 0
    no_encontrados = 0
    trans = Transaction(doc, "RE7_BORRAR_CONDUITS_V05_V06")
    trans.Start()
    try:
        for cid in conduit_ids:
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
    except Exception:
        trans.RollBack()
        raise
    return borrados, no_encontrados


def main():
    _iniciar_log()
    log("=" * 60)
    log("RE7_CREAR_CONDUITS_F17_F18_{} - Ruteo F7 (dispositivos reales)".format(VERSION))
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

    # --- PASO 1: Borrar conduits v05/v06 existentes ---
    raiz = _raiz()
    conduit_ids_borrar = []
    for nombre_reporte in ["f7_conduits_creados_f17_f18_v05.json",
                           "f7_conduits_f17_piloto_v06.json"]:
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
        borrados, no_encontrados = borrar_conduits_por_ids(doc, conduit_ids_borrar)
        log("Borrado: %d eliminados, %d no encontrados." % (borrados, no_encontrados))

    # --- PASO 2: Nivel y tipos ---
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

    # --- PASO 3: Dispositivos en Revit ---
    dispositivos_revit = recolectar_dispositivos_revit(doc)
    log("Dispositivos electricos en Revit: {}".format(len(dispositivos_revit)))

    # --- PASO 4: Leer conductos DXF para F17 y F18 ---
    conductos_f17 = cargar_conductos_dxf(
        os.path.join(raiz, "data", "f7_conectividad_dxf_f17_f18_v01.json"), apto="F17")
    conductos_f18 = cargar_conductos_dxf(
        os.path.join(raiz, "data", "f7_conectividad_dxf_f17_f18_v01.json"), apto="F18")
    log("Conductos DXF F17: %d, F18: %d" % (len(conductos_f17), len(conductos_f18)))

    # --- PASO 5: Procesar conductos ---
    segmentos_a_crear = []
    total_segmentos = 0
    ambos_dispositivos = 0
    solo_dispositivo_a = 0
    solo_dispositivo_b = 0
    ninguno_dispositivo = 0
    saltados_corto = 0

    for apto, conductos_dxf in [("F17", conductos_f17), ("F18", conductos_f18)]:
        for c in conductos_dxf:
            layer = c["layer"]
            diametro = 16.0 if "LIGHT" in layer.upper() else 21.0
            vertices = c["vertices"]
            seglist = descomponer_lwpolyline_en_segmentos(vertices)

            for seg in seglist:
                total_segmentos = total_segmentos + 1
                a_2d = seg["a_mm"]
                b_2d = seg["b_mm"]

                # Buscar dispositivo cercano a cada extremo
                dev_a, dist_a = encontrar_dispositivo_cercano(a_2d[0], a_2d[1], dispositivos_revit)
                dev_b, dist_b = encontrar_dispositivo_cercano(b_2d[0], b_2d[1], dispositivos_revit)

                tiene_a = dev_a is not None
                tiene_b = dev_b is not None

                if tiene_a and tiene_b:
                    ambos_dispositivos = ambos_dispositivos + 1
                elif tiene_a:
                    solo_dispositivo_a = solo_dispositivo_a + 1
                elif tiene_b:
                    solo_dispositivo_b = solo_dispositivo_b + 1
                else:
                    ninguno_dispositivo = ninguno_dispositivo + 1

                # Z para cada extremo
                z_a = z_por_dispositivo(dev_a) if dev_a else Z_DEFAULT_MM
                z_b = z_por_dispositivo(dev_b) if dev_b else Z_DEFAULT_MM

                # Coordenadas finales
                ax = dev_a["x_mm"] if dev_a else a_2d[0]
                ay = dev_a["y_mm"] if dev_a else a_2d[1]
                bx = dev_b["x_mm"] if dev_b else b_2d[0]
                by = dev_b["y_mm"] if dev_b else b_2d[1]

                # Verificar largo mínimo
                largo = dist_3d([ax, ay, z_a], [bx, by, z_b])
                if largo < LARGO_MINIMO_MM:
                    saltados_corto = saltados_corto + 1
                    log("  SALTADO (muy corto, %.1fmm): dxf_a=(%.1f,%.1f) dxf_b=(%.1f,%.1f)" % (
                        largo, a_2d[0], a_2d[1], b_2d[0], b_2d[1]))
                    continue

                segmentos_a_crear.append({
                    "apto": apto,
                    "layer": layer,
                    "diametro_mm": diametro,
                    "a_mm": [ax, ay, z_a],
                    "b_mm": [bx, by, z_b],
                    "a_dxf": [a_2d[0], a_2d[1], 0.0],
                    "b_dxf": [b_2d[0], b_2d[1], 0.0],
                    "dev_a_id": dev_a["id"] if dev_a else None,
                    "dev_b_id": dev_b["id"] if dev_b else None,
                    "dev_a_dist": round(dist_a, 2) if dist_a else None,
                    "dev_b_dist": round(dist_b, 2) if dist_b else None,
                    "dev_a_familia": dev_a["familia"] if dev_a else None,
                    "dev_b_familia": dev_b["familia"] if dev_b else None,
                    "z_a_mm": z_a,
                    "z_b_mm": z_b,
                    "tiene_dev_a": tiene_a,
                    "tiene_dev_b": tiene_b,
                })

    log("Total segmentos: %d" % total_segmentos)
    log("  Ambos dispositivos: %d" % ambos_dispositivos)
    log("  Solo dispositivo A: %d" % solo_dispositivo_a)
    log("  Solo dispositivo B: %d" % solo_dispositivo_b)
    log("  Ningún dispositivo: %d" % ninguno_dispositivo)
    log("  Saltados por corto: %d" % saltados_corto)
    log("  Segmentos a crear: %d" % len(segmentos_a_crear))

    if len(segmentos_a_crear) == 0:
        log("ERROR: no hay segmentos para crear.")
        return 1

    # --- PASO 6: Crear conduits ---
    creados = []
    fallos = []
    trans = Transaction(doc, "RE7_CREAR_CONDUITS_F17_F18_v07")
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
                c = crear_conduit(
                    doc, tipo_id, id_de(nivel),
                    seg["a_mm"], seg["b_mm"], seg["z_a_mm"], seg["z_b_mm"])
                creados.append({
                    "index": i,
                    "conduit_id": id_de(c),
                    "tipo_id": tipo_id,
                    "apto": seg.get("apto"),
                    "layer": seg.get("layer"),
                    "diametro_mm": diametro,
                    "a_mm": seg["a_mm"],
                    "b_mm": seg["b_mm"],
                    "a_dxf": seg["a_dxf"],
                    "b_dxf": seg["b_dxf"],
                    "dev_a_id": seg["dev_a_id"],
                    "dev_b_id": seg["dev_b_id"],
                    "dev_a_dist": seg["dev_a_dist"],
                    "dev_b_dist": seg["dev_b_dist"],
                    "dev_a_familia": seg["dev_a_familia"],
                    "dev_b_familia": seg["dev_b_familia"],
                    "z_a_mm": seg["z_a_mm"],
                    "z_b_mm": seg["z_b_mm"],
                    "tiene_dev_a": seg["tiene_dev_a"],
                    "tiene_dev_b": seg["tiene_dev_b"],
                    "largo_mm": round(dist_3d(seg["b_mm"], seg["a_mm"]), 3),
                })
                if (i + 1) % 10 == 0:
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
        "script": "RE7_CREAR_CONDUITS_F17_F18_v07",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": {"titulo": titulo, "ruta": doc.PathName},
        "nivel": {"id": id_de(nivel), "nombre": nivel.Name,
                  "elevacion_mm": round(nivel.Elevation * FT_A_MM, 3)},
        "parametros": {"total_segmentos": len(segmentos_a_crear),
                       "tipos_conduit": len(tipos),
                       "radio_busqueda_mm": RADIO_BUSQUEDA_MM,
                       "largo_minimo_mm": LARGO_MINIMO_MM},
        "borrado_previo": {"ids": conduit_ids_borrar, "contador": len(conduit_ids_borrar)},
        "estadisticas": {
            "total_segmentos_dxf": total_segmentos,
            "ambos_dispositivos": ambos_dispositivos,
            "solo_dispositivo_a": solo_dispositivo_a,
            "solo_dispositivo_b": solo_dispositivo_b,
            "ninguno_dispositivo": ninguno_dispositivo,
            "saltados_corto": saltados_corto,
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
            "index": item["index"],
            "conduit_id": item["conduit_id"],
            "apto": item["apto"],
            "layer": item["layer"],
            "diametro_mm": item["diametro_mm"],
            "a_mm_esperado": item["a_mm"],
            "b_mm_esperado": item["b_mm"],
            "a_mm_real": [round(v, 3) for v in a_real] if a_real else None,
            "b_mm_real": [round(v, 3) for v in b_real] if b_real else None,
            "dist_a_mm": round(da, 3) if da is not None else None,
            "dist_b_mm": round(db, 3) if db is not None else None,
            "largo_esperado_mm": item["largo_mm"],
            "largo_real_mm": round(largo_real, 3) if largo_real is not None else None,
            "verificado": ok,
            "dev_a_id": item["dev_a_id"],
            "dev_b_id": item["dev_b_id"],
            "dev_a_dist_dxf": item["dev_a_dist"],
            "dev_b_dist_dxf": item["dev_b_dist"],
            "dev_a_familia": item["dev_a_familia"],
            "dev_b_familia": item["dev_b_familia"],
            "z_a_mm": item["z_a_mm"],
            "z_b_mm": item["z_b_mm"],
            "tiene_dev_a": item["tiene_dev_a"],
            "tiene_dev_b": item["tiene_dev_b"],
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

    out_json = os.path.join(raiz, "data", "f7_conduits_creados_f17_f18_v07.json")
    contenido = json.dumps(reporte, ensure_ascii=True, indent=2)
    if escribir_archivo_texto(out_json, contenido):
        log("Reporte guardado en: {}".format(out_json))
    else:
        log("ERROR: no se pudo escribir el reporte JSON.")

    log("RESULTADO: %d conduits creados, %d verificados OK, %d fallos en creacion, %d saltados por corto." % (
        len(creados), verificados_ok, len(fallos), saltados_corto))
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
