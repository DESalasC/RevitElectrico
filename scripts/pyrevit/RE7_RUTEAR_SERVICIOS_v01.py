# -*- coding: utf-8 -*-
"""
RE7_RUTEAR_SERVICIOS_v01.py

Ruteo incremental por SERVICIO (decision del operador 2026-11-22, validado
contra el ruteo manual de V02-f):

  * La red horizontal corre a nivel + 2700 mm (plano de cielorraso), como el
    manual (horizontales de ILUMINACION a 2700; bajadas desde ~2550).
  * ILUMINACION (luminarias + interruptores + ventilador M_ClimatizacionV):
    arbol rectilineo (MST Manhattan) a +2700 por los XY de las luminarias y
    de los interruptores; BAJADAS SOLO a los interruptores. Diametro 16.
  * VENTILACION (EA extractor): bajada vertical a +2700. Diametro 16.
  * TOMAS: verticales desde cada toma a +2700; en cocina la regla del
    operador (vertical unica en la GFCI con cadena 0.70/1.05/1.65 + riser).
    Diametro 16.
  * COMUNICACIONES: pareja de 2 tubos separados 40 mm por agrupacion, desde
    la cota mas baja a +2700. Diametro 19.
  * Cada conduit se etiqueta con el parametro de proyecto Servicio_Conduit.
  * Esta ronda NO dibuja: horizontales de tomas/datos, conexion al CP/Panel
    ni el troncal. Quedan para la siguiente.

Fuentes de dispositivos:
  * modo crear: el documento activo (como v09)
  * dry_run con inputs={"inventario": "<json>"}: lee del inventario exportado
    y NO toca ningun documento abierto (plan puro).

Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import math
import os
import sys
import traceback
from collections import defaultdict

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB.Electrical import Conduit
from System import Int64

VERSION = "v01_servicios"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_RED_MM = 2700.0          # plano de la red sobre el nivel (cielorraso)
Z_NIVEL_JSON_MM = 13220.0  # para el modo inventario
LARGO_MIN_MM = 5.0
DEDUP_MM = 150.0
DEDUP_Z_MM = 150.0
MIN_RAMAL_MM = 25.0
OFFSET_COMMS_MM = 40.0
COCINA_BAJA_MM = 700.0
COCINA_MEDIA_MM = 1050.0
COCINA_ALTA_MM = 1650.0
TOL_ALTURA_COCINA_MM = 60.0

D_16_MM = 16.0
D_19_MM = 19.0
NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size"]
PARAM_SERVICIO = "Servicio_Conduit"
TUBO_E_ID = 112216

SERVICIO_POR_FAMILIA = {
    "M_Iluminacion": "ILUMINACION",
    "M_Interruptores": "ILUMINACION",
    "M_ClimatizacionV": "ILUMINACION",
    "EA": "VENTILACION",
    "M_Toma doble": "TOMAS",
    "M_Toma resistente a la intemperie": "TOMAS",
    "M_Toma - 220V": "TOMAS",
    "M_Comunicaciones": "COMUNICACIONES",
}

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]

CLAVES_DATOS = ("comunicacion", "datos", "telephone", "data devices", "pau")


def log(msg):
    print(msg)
    try:
        sys.stdout.flush()
    except Exception:
        pass


# --------------------------------------------------------------------------
# funciones puras
# --------------------------------------------------------------------------
def clasificar_servicio(familia):
    return SERVICIO_POR_FAMILIA.get(familia, None)


def apto_de_mark(mark):
    if not mark or "|" not in mark:
        return None
    pref = mark.split("|")[0].strip().upper()
    return pref or None


def d2(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def dist_3d(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def dedup_por_tipo(items, tolerancia_mm=DEDUP_MM, tolerancia_z_mm=DEDUP_Z_MM):
    grupos = {}
    for d in items:
        grupos.setdefault(d.get("tipo") or "", []).append(d)
    reps = []
    dedup = 0
    for tipo in grupos:
        grupo = sorted(grupos[tipo], key=lambda z: -z["pt"][2])
        usados = set()
        for i in range(len(grupo)):
            if i in usados:
                continue
            reps.append(grupo[i])
            for j in range(i + 1, len(grupo)):
                if j in usados:
                    continue
                if (d2(grupo[i]["pt"][0], grupo[i]["pt"][1],
                       grupo[j]["pt"][0], grupo[j]["pt"][1]) <= tolerancia_mm
                        and abs(grupo[i]["pt"][2] - grupo[j]["pt"][2])
                        <= tolerancia_z_mm):
                    usados.add(j)
                    dedup += 1
    return reps, dedup


def agrupar_por_proximidad(items, tolerancia_mm):
    usados = set()
    grupos = []
    for i in range(len(items)):
        if i in usados:
            continue
        grupo = [items[i]]
        usados.add(i)
        for j in range(i + 1, len(items)):
            if j in usados:
                continue
            if d2(items[i]["pt"][0], items[i]["pt"][1],
                  items[j]["pt"][0], items[j]["pt"][1]) <= tolerancia_mm:
                grupo.append(items[j])
                usados.add(j)
        grupos.append(grupo)
    return grupos


def mst_manhattan(puntos):
    """Arbol rectilineo (Prim con distancia Manhattan). puntos=[(x,y),...]."""
    n = len(puntos)
    if n <= 1:
        return []
    usados = {0}
    aristas = []
    while len(usados) < n:
        mejor = None
        for i in usados:
            for j in range(n):
                if j in usados:
                    continue
                d = abs(puntos[i][0] - puntos[j][0]) + \
                    abs(puntos[i][1] - puntos[j][1])
                if mejor is None or d < mejor[0]:
                    mejor = (d, i, j)
        aristas.append((mejor[1], mejor[2]))
        usados.add(mejor[2])
    return aristas


def arista_a_segmentos(p, q):
    segs = []
    if abs(p[0] - q[0]) > 0.5:
        segs.append(((p[0], p[1]), (q[0], p[1])))
    if abs(p[1] - q[1]) > 0.5:
        segs.append(((q[0], p[1]), (q[0], q[1])))
    return segs


def alturas_cocina(grupo, z_nivel):
    alturas = set()
    for g in grupo:
        rel = g["pt"][2] - z_nivel
        if (COCINA_BAJA_MM - TOL_ALTURA_COCINA_MM <= rel <=
                COCINA_ALTA_MM + TOL_ALTURA_COCINA_MM):
            alturas.add(round(rel / 10.0) * 10.0)
    if not alturas:
        alturas.add(COCINA_MEDIA_MM)
    return sorted(alturas)


# --------------------------------------------------------------------------
# acceso a Revit
# --------------------------------------------------------------------------
def app_de():
    try:
        app = __revit__
        if app is not None and hasattr(app, "Application"):
            return app.Application
    except Exception:
        pass
    try:
        from pyrevit import revit as _revit
        if _revit.app is not None:
            return _revit.app
    except Exception:
        pass
    return None


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


def id_de(el):
    v = el.Id
    if hasattr(v, "IntegerValue"):
        return int(v.IntegerValue)
    return int(v.Value)


def punto(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            p = loc.Point
            return [p.X * FT_A_MM, p.Y * FT_A_MM, p.Z * FT_A_MM]
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            a = c.GetEndPoint(0)
            b = c.GetEndPoint(1)
            return [0.5 * (a.X + b.X) * FT_A_MM,
                    0.5 * (a.Y + b.Y) * FT_A_MM,
                    0.5 * (a.Z + b.Z) * FT_A_MM]
    except Exception:
        pass
    return None


def texto(el, nombres):
    for n in nombres:
        try:
            p = el.LookupParameter(n)
            if p is not None:
                s = p.AsString()
                if s is not None:
                    return s
        except Exception:
            pass
    return None


def fam_tipo(el):
    fam = tip = None
    try:
        if el.Symbol is not None:
            if el.Symbol.Family is not None:
                fam = el.Symbol.Family.Name
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                tip = p.AsString()
    except Exception:
        pass
    return fam, tip


def fijar_diam(el, mm):
    for n in NOMBRES_DIAM:
        try:
            p = el.LookupParameter(n)
            if p is not None and not p.IsReadOnly:
                p.Set(mm / FT_A_MM)
                return True
        except Exception:
            pass
    return False


def fijar_servicio(el, servicio):
    try:
        p = el.LookupParameter(PARAM_SERVICIO)
        if p is not None and not p.IsReadOnly and \
                p.StorageType.ToString() == "String":
            p.Set(servicio)
            return True
    except Exception:
        pass
    return False


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz(x, y, z):
    return XYZ(mm_a_ft(x), mm_a_ft(y), mm_a_ft(z))


def nivel_piso5(doc):
    mejor = None
    mejor_d = None
    for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
        dd = abs(lvl.Elevation * FT_A_MM - 13220.0)
        if mejor_d is None or dd < mejor_d:
            mejor = lvl
            mejor_d = dd
    return mejor


def cargar_ids_cocina():
    try:
        p = os.path.join(DEFAULT_ROOT, "data", "f7_cocinas_ids_v01.json")
        with open(p) as f:
            return set(int(x) for x in json.load(f)["ids"])
    except Exception:
        return set()


def leer_inputs():
    try:
        g = globals().get("inputs")
        if isinstance(g, dict):
            return g
    except Exception:
        pass
    return {}


def leer_dispositivos_doc(doc):
    disp = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto(el)
            if pt is None:
                continue
            fam, tip = fam_tipo(el)
            disp.append({"id": id_de(el), "pt": pt,
                         "mark": texto(el, ["Mark"]) or "",
                         "familia": fam or "", "tipo": tip or ""})
    return disp


def leer_dispositivos_json(ruta):
    disp = []
    with open(ruta) as f:
        datos = json.load(f)
    for q in datos["dispositivos"]:
        if q.get("x") is None:
            continue
        disp.append({"id": q.get("id"), "pt": [q["x"], q["y"], q["z"]],
                     "mark": q.get("mark") or "",
                     "familia": q.get("familia") or "",
                     "tipo": q.get("tipo") or ""})
    return disp


def main():
    log("=" * 78)
    log("RE7_RUTEAR_SERVICIOS_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    inp = leer_inputs()
    dry_run = bool(inp.get("dry_run", False))
    modo = "dry_run" if dry_run else "crear"
    env = os.environ.get("APTOS_RUTEO", "").strip()
    aptos = inp.get("aptos")
    if not aptos:
        aptos = [a.strip().upper() for a in env.split(",")] if env else ["F01", "F02"]
    aptos = [str(a).strip().upper() for a in aptos]
    log("modo=%s | apartamentos=%s" % (modo, aptos))

    doc = None
    z_nivel = Z_NIVEL_JSON_MM
    nivel_id = None
    inv = inp.get("inventario")
    doc_sellado = None
    if inv:
        log("fuente de dispositivos: inventario JSON %s" % inv)
        disp = leer_dispositivos_json(os.path.join(DEFAULT_ROOT, inv)
                                      if not os.path.isabs(inv) else inv)
    elif inp.get("documento"):
        if not dry_run:
            log("ERROR: el modo 'documento' sellado solo permite dry_run.")
            return 1
        ruta = inp["documento"]
        if not os.path.isabs(ruta):
            ruta = os.path.join(DEFAULT_ROOT, ruta)
        if not os.path.exists(ruta):
            log("ERROR: no existe %s" % ruta)
            return 1
        app = app_de()
        if app is None:
            log("ERROR: sin Application para abrir el documento sellado")
            return 1
        doc_sellado = None
        for d in app.Documents:
            try:
                if d.PathName == ruta:
                    doc_sellado = d
                    break
            except Exception:
                continue
        if doc_sellado is None:
            try:
                doc_sellado = app.OpenDocumentFile(ruta)
            except Exception:
                log("ERROR abriendo documento sellado:")
                log(traceback.format_exc())
                return 1
        doc = doc_sellado
        log("fuente de dispositivos: documento sellado %r" % doc.Title)
        nivel = nivel_piso5(doc)
        if nivel is None:
            log("ERROR: no se encontro Piso 5.")
            return 1
        nivel_id = id_de(nivel)
        z_nivel = float(nivel.Elevation) * FT_A_MM
        disp = leer_dispositivos_doc(doc)
    else:
        doc = obtener_doc()
        if doc is None:
            log("ERROR: sin documento activo ni inventario.")
            return 1
        log("documento=%r" % doc.Title)
        nivel = nivel_piso5(doc)
        if nivel is None:
            log("ERROR: no se encontro Piso 5.")
            return 1
        nivel_id = id_de(nivel)
        z_nivel = float(nivel.Elevation) * FT_A_MM
        disp = leer_dispositivos_doc(doc)
    z_red = z_nivel + Z_RED_MM
    log("nivel=%.0f | plano de red=%.0f mm" % (z_nivel, z_red))
    log("dispositivos leidos: %d" % len(disp))

    coc_ids = cargar_ids_cocina()
    log("ids cocina: %d" % len(coc_ids))

    tramos = []
    fallos = []

    def crear(apto, tipo, servicio, a, b, diam, extra=None):
        largo = dist_3d(a, b)
        if largo < LARGO_MIN_MM:
            return False
        reg = {"apto": apto, "tipo": tipo, "servicio": servicio,
               "diam_mm": diam, "largo_mm": round(largo, 1),
               "a": [round(a[0], 1), round(a[1], 1), round(a[2], 1)],
               "b": [round(b[0], 1), round(b[1], 1), round(b[2], 1)]}
        if extra:
            reg.update(extra)
        if not dry_run:
            try:
                c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                   xyz(a[0], a[1], a[2]),
                                   xyz(b[0], b[1], b[2]),
                                   ElementId(Int64(nivel_id)))
                fijar_diam(c, diam)
                if not fijar_servicio(c, servicio):
                    reg["servicio_no_aplicado"] = True
                try:
                    reg["conduit_id"] = id_de(c)
                except Exception:
                    pass
            except Exception as ex:
                fallos.append({"apto": apto, "tipo": tipo,
                               "err": str(ex)[:110]})
                return False
        tramos.append(reg)
        return True

    trans = None
    if not dry_run:
        if "STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01c" not in doc.Title:
            log("ABORTADO: el documento activo no es el de trabajo "
                "(CENTRAL-V01c). No se crea en %r." % doc.Title)
            return 1
        trans = Transaction(doc, "RE7_RUTEAR_SERVICIOS_v01")
        trans.Start()

    resumen = {}
    try:
        for apto in aptos:
            items = [d for d in disp if d["mark"].startswith(apto + "|")]
            if not items:
                log("%s: sin dispositivos" % apto)
                resumen[apto] = {"error": "sin dispositivos"}
                continue
            reps, dedup = dedup_por_tipo(items)
            reps_servicio = [d for d in reps
                             if clasificar_servicio(d["familia"]) is not None]
            excluidos = [d for d in reps
                         if clasificar_servicio(d["familia"]) is None]
            log("")
            log("%s: %d disp | reps=%d (dedup %d) | excluidos %d (%s)" % (
                apto, len(items), len(reps), dedup, len(excluidos),
                sorted(set(d["familia"] for d in excluidos))))

            # ---------- ILUMINACION: arbol + bajadas a interruptores ----------
            lum = [d for d in reps_servicio
                   if d["familia"] in ("M_Iluminacion", "M_ClimatizacionV")]
            sw = [d for d in reps_servicio if d["familia"] == "M_Interruptores"]
            nodos = [(d["pt"][0], d["pt"][1]) for d in lum + sw]
            aristas = mst_manhattan(nodos)
            n_hor = 0
            for i, j in aristas:
                for (p, q) in arista_a_segmentos(nodos[i], nodos[j]):
                    if crear(apto, "iluminacion_horizontal", "ILUMINACION",
                             (p[0], p[1], z_red), (q[0], q[1], z_red),
                             D_16_MM):
                        n_hor += 1
            n_baj = 0
            for s in sw:
                if crear(apto, "bajada_interruptor", "ILUMINACION",
                         (s["pt"][0], s["pt"][1], z_red),
                         (s["pt"][0], s["pt"][1], s["pt"][2]), D_16_MM,
                         {"disp": s["id"]}):
                    n_baj += 1
            log("   ILUMINACION: %d nodos | %d aristas -> %d horizontales | "
                "%d bajadas a interruptor" % (
                    len(nodos), len(aristas), n_hor, n_baj))

            # ---------- VENTILACION (EA) ----------
            ea = [d for d in reps_servicio if d["familia"] == "EA"]
            for e in ea:
                crear(apto, "bajada_ventilacion", "VENTILACION",
                      (e["pt"][0], e["pt"][1], e["pt"][2]),
                      (e["pt"][0], e["pt"][1], z_red), D_16_MM,
                      {"disp": e["id"]})
            if ea:
                log("   VENTILACION: %d bajadas (EA)" % len(ea))

            # ---------- TOMAS ----------
            tomas = [d for d in reps_servicio
                     if d["familia"].startswith("M_Toma")]
            coc = [d for d in tomas if d["id"] in coc_ids]
            resto = [d for d in tomas if d["id"] not in coc_ids]
            grupos_coc = agrupar_por_proximidad(coc, 200.0)
            n_vert_coc = 0
            for grupo in grupos_coc:
                cerca = [g for g in grupo
                         if abs(g["pt"][2] - (z_nivel + COCINA_MEDIA_MM))
                         <= 120.0]
                if cerca:
                    gfci = [g for g in cerca
                            if "gfci" in (g["tipo"] or "").lower()]
                    ancla = gfci[0] if gfci else cerca[0]
                else:
                    ancla = min(grupo, key=lambda g: abs(
                        g["pt"][2] - (z_nivel + COCINA_MEDIA_MM)))
                vx, vy = ancla["pt"][0], ancla["pt"][1]
                alturas = alturas_cocina(grupo, z_nivel)
                for k in range(len(alturas) - 1):
                    if crear(apto, "cocina_vertical", "TOMAS",
                             (vx, vy, alturas[k] + z_nivel),
                             (vx, vy, alturas[k + 1] + z_nivel), D_16_MM):
                        n_vert_coc += 1
                if crear(apto, "cocina_riser", "TOMAS",
                         (vx, vy, max(alturas) + z_nivel),
                         (vx, vy, z_red), D_16_MM):
                    n_vert_coc += 1
            n_vert_tomas = 0
            for t in resto:
                if crear(apto, "vertical_toma", "TOMAS",
                         (t["pt"][0], t["pt"][1], t["pt"][2]),
                         (t["pt"][0], t["pt"][1], z_red), D_16_MM,
                         {"disp": t["id"]}):
                    n_vert_tomas += 1
            log("   TOMAS: %d cocina (%d verticales) | %d sueltas (%d "
                "verticales)" % (len(grupos_coc), n_vert_coc, len(resto),
                                 n_vert_tomas))

            # ---------- COMUNICACIONES: pareja de tubos ----------
            datos = [d for d in reps_servicio
                     if d["familia"] == "M_Comunicaciones"]
            grupos_datos = agrupar_por_proximidad(datos, 200.0)
            n_vert_datos = 0
            for grupo in grupos_datos:
                x = grupo[0]["pt"][0]
                y = grupo[0]["pt"][1]
                z_bajo = min(g["pt"][2] for g in grupo)
                for signo in (-1.0, 1.0):
                    if crear(apto, "vertical_datos", "COMUNICACIONES",
                             (x, y + signo * OFFSET_COMMS_MM / 2.0, z_bajo),
                             (x, y + signo * OFFSET_COMMS_MM / 2.0, z_red),
                             D_19_MM, {"n_grupo": len(grupo)}):
                        n_vert_datos += 1
            log("   COMUNICACIONES: %d grupos -> %d tubos verticales" % (
                len(grupos_datos), n_vert_datos))

            resumen[apto] = {
                "dispositivos": len(items), "representantes": len(reps),
                "dedup": dedup,
                "iluminacion": {"luminarias": len(lum),
                                "interruptores": len(sw),
                                "horizontales": n_hor, "bajadas": n_baj},
                "ventilacion": len(ea),
                "tomas": {"cocina_grupos": len(grupos_coc),
                          "cocina_verticales": n_vert_coc,
                          "sueltas": len(resto),
                          "verticales": n_vert_tomas},
                "datos": {"grupos": len(grupos_datos),
                          "verticales": n_vert_datos},
                "excluidos": sorted(set(d["familia"] for d in excluidos)),
            }

        if trans is not None:
            trans.Commit()
            log("transaccion COMMIT")
    except Exception:
        if trans is not None:
            try:
                trans.RollBack()
                log("ERROR: transaccion revertida")
            except Exception:
                pass
        log(traceback.format_exc())
        return 1

    total = len(tramos)
    longitud = sum(dist_3d(t["a"], t["b"]) for t in tramos)
    por_servicio = defaultdict(int)
    por_tipo = defaultdict(int)
    for t in tramos:
        por_servicio[t["servicio"]] += 1
        por_tipo[t["tipo"]] += 1
    log("")
    log("=" * 78)
    log("RESULTADO (%s): tramos=%d | longitud=%.2f m | fallos=%d" % (
        modo, total, longitud / 1000.0, len(fallos)))
    for s in sorted(por_servicio):
        log("   %-14s %d" % (s, por_servicio[s]))
    for t in sorted(por_tipo):
        log("   %-20s %d" % (t, por_tipo[t]))
    for a in aptos:
        log("   %-5s %s" % (a, resumen.get(a)))
    for f in fallos[:6]:
        log("   %s" % f)

    out = os.path.join(DEFAULT_ROOT, "data",
                       "f7_%s_servicios_%s_v01.json" % (
                           "plan" if dry_run else "creado", "_".join(aptos)))
    try:
        with open(out, "w") as fh:
            fh.write(json.dumps({
                "version": VERSION,
                "modo": modo,
                "generado_utc": datetime.datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"),
                "nivel_mm": round(z_nivel, 1),
                "plano_red_mm": round(z_red, 1),
                "resumen": resumen,
                "totales": {"tramos": total,
                            "longitud_m": round(longitud / 1000.0, 2),
                            "por_servicio": dict(por_servicio),
                            "por_tipo": dict(por_tipo),
                            "fallos": len(fallos)},
                "tramos": tramos,
                "fallos": fallos,
            }, ensure_ascii=True, indent=1))
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    if doc_sellado is not None:
        try:
            doc_sellado.Close(False)
            log("documento sellado cerrado sin guardar")
        except Exception:
            log("AVISO: el API no permitio cerrar el documento sellado")
    log("=" * 78)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
