# -*- coding: utf-8 -*-
"""
RE7_RUTEAR_SERVICIOS_v02.py

Igual que v01 (red por servicios a nivel+2700, bajadas solo a interruptores,
verticales de tomas/datos, cocinas GFCI, 16/19 mm, etiqueta Servicio_Conduit)
con la REGLA CRITICA del operador:

  * DOS SEGMENTOS DE TUBERIA NO PUEDEN COMPARTIR EL MISMO RECORRIDO.

Resolutor de superposiciones (antes de crear nada):
  * dedup exacto (mismo tramo, incluso invertido)
  * bajadas a interruptor: UNA por placa (XY a 50 mm), hasta el interruptor
    mas bajo de la placa (los demas conectan a la misma tuberia)
  * verticales en la misma XY: mismo servicio -> recorte/descarte dejando una
    sola tuberia cubriendo la union; distinto servicio -> la segunda se desfaza
    40 mm (X, luego Y) porque no pueden ir por el mismo sitio
  * horizontales en la misma linea (mismo eje, misma coordenada fija, misma Z):
    mismo servicio -> recorte por barrido (los tramos quedan tocandose
    extremo con extremo; los totalmente cubiertos se descartan porque sus
    conexiones quedan como T sobre la tuberia que los cubre)
    distinto servicio -> la segunda se desfaza +50 mm en Z (como el manual:
    2700/2749/2764)

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

VERSION = "v02_servicios_sin_solapes"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_RED_MM = 2700.0
Z_NIVEL_JSON_MM = 13220.0
LARGO_MIN_MM = 5.0
DEDUP_MM = 150.0
DEDUP_Z_MM = 150.0
OFFSET_COMMS_MM = 40.0
TOL_XY_MM = 5.0
TOL_LINEA_MM = 5.0
TOL_Z_MM = 2.0
OFFSET_VERTICAL_MM = 40.0
OFFSET_HORIZONTA_MM = 50.0
PLACA_MM = 50.0
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


def geo_de(a, b):
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    dz = abs(a[2] - b[2])
    if dx <= TOL_Z_MM and dy <= TOL_Z_MM:
        return "V"
    if dz <= TOL_Z_MM:
        if dy <= TOL_Z_MM:
            return "HX"
        if dx <= TOL_Z_MM:
            return "HY"
    return "O"


def clave_linea(seg):
    """Linea de soporte: ('V', x, y) | ('HX', y, z) | ('HY', x, z) | None."""
    a, b = seg["a"], seg["b"]
    g = seg.get("_geo") or geo_de(a, b)
    seg["_geo"] = g
    if g == "V":
        return ("V", round((a[0] + b[0]) / 2.0, 0), round((a[1] + b[1]) / 2.0, 0))
    if g == "HX":
        return ("HX", round(a[1], 0), round(0.5 * (a[2] + b[2]), 0))
    if g == "HY":
        return ("HY", round(a[0], 0), round(0.5 * (a[2] + b[2]), 0))
    return None


def intervalo(seg):
    a, b = seg["a"], seg["b"]
    g = seg["_geo"]
    if g == "V":
        return (min(a[2], b[2]), max(a[2], b[2]))
    if g == "HX":
        return (min(a[0], b[0]), max(a[0], b[0]))
    if g == "HY":
        return (min(a[1], b[1]), max(a[1], b[1]))
    return None


def mismo_tramo(s1, s2, tol=TOL_XY_MM):
    a1, b1 = s1["a"], s1["b"]
    a2, b2 = s2["a"], s2["b"]
    directo = all(abs(a1[i] - a2[i]) <= tol for i in range(3)) and \
        all(abs(b1[i] - b2[i]) <= tol for i in range(3))
    inverso = all(abs(a1[i] - b2[i]) <= tol for i in range(3)) and \
        all(abs(b1[i] - a2[i]) <= tol for i in range(3))
    return directo or inverso


def detectar_solapes(segs, tol_xy=TOL_XY_MM, tol_z=TOL_Z_MM):
    """Pares de tramos que comparten recorrido (>0). Para verificacion."""
    pares = []
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            s1, s2 = segs[i], segs[j]
            g1 = s1.get("_geo") or geo_de(s1["a"], s1["b"])
            g2 = s2.get("_geo") or geo_de(s2["a"], s2["b"])
            if g1 != g2 or g1 not in ("V", "HX", "HY"):
                continue
            if g1 == "V":
                if abs(s1["a"][0] - s2["a"][0]) > tol_xy or \
                        abs(s1["a"][1] - s2["a"][1]) > tol_xy:
                    continue
                i1 = (min(s1["a"][2], s1["b"][2]), max(s1["a"][2], s1["b"][2]))
                i2 = (min(s2["a"][2], s2["b"][2]), max(s2["a"][2], s2["b"][2]))
            else:
                eje = s1["a"][2]
                if abs(0.5 * (s1["a"][2] + s1["b"][2]) -
                       0.5 * (s2["a"][2] + s2["b"][2])) > tol_z:
                    continue
                if g1 == "HX":
                    if abs(s1["a"][1] - s2["a"][1]) > tol_xy:
                        continue
                    i1 = (min(s1["a"][0], s1["b"][0]), max(s1["a"][0], s1["b"][0]))
                    i2 = (min(s2["a"][0], s2["b"][0]), max(s2["a"][0], s2["b"][0]))
                else:
                    if abs(s1["a"][0] - s2["a"][0]) > tol_xy:
                        continue
                    i1 = (min(s1["a"][1], s1["b"][1]), max(s1["a"][1], s1["b"][1]))
                    i2 = (min(s2["a"][1], s2["b"][1]), max(s2["a"][1], s2["b"][1]))
            sol = min(i1[1], i2[1]) - max(i1[0], i2[0])
            if sol > tol_z:
                pares.append({"i": i, "j": j, "solape_mm": round(sol, 1),
                              "servicio_1": s1.get("servicio"),
                              "servicio_2": s2.get("servicio")})
    return pares


def resolver_superposiciones(segs, log_acciones=None):
    """Aplica la regla: ningun par de tramos comparte recorrido.

    Devuelve (tramos_limpios, acciones) donde acciones resume lo hecho.
    """
    acciones = {"dedup_exacto": 0, "verticales_recolocadas": 0,
                "verticales_descartadas": 0, "horizontales_recolocadas": 0,
                "horizontales_descartados": 0}

    # 1. dedup exacto (solo dentro del mismo servicio: distintos servicios
    #    no se fusionan, se desfazan mas adelante)
    limpios = []
    for s in segs:
        s["_geo"] = geo_de(s["a"], s["b"])
        if any(mismo_tramo(s, q) and
               (s.get("servicio") or "") == (q.get("servicio") or "")
               for q in limpios):
            acciones["dedup_exacto"] += 1
            continue
        limpios.append(s)
    segs = limpios

    # 2. verticales: agrupar por XY; mismo servicio recorta, distinto desfaza
    grupos_v = defaultdict(list)
    fijos = []
    for s in segs:
        if s["_geo"] == "V":
            grupos_v[(round(s["a"][0] / TOL_XY_MM), round(s["a"][1] / TOL_XY_MM))
                     ].append(s)
        else:
            fijos.append(s)
    nuevos_v = []
    for clave in grupos_v:
        grupo = grupos_v[clave]
        por_servicio = defaultdict(list)
        for s in grupo:
            por_servicio[s.get("servicio") or "(vacio)"].append(s)
        desface = 0
        for servicio in sorted(por_servicio):
            qs = sorted(por_servicio[servicio],
                        key=lambda q: min(q["a"][2], q["b"][2]))
            if desface > 0:
                for s in qs:
                    s["a"] = [s["a"][0] + desface, s["a"][1], s["a"][2]]
                    s["b"] = [s["b"][0] + desface, s["b"][1], s["b"][2]]
                    s["_geo"] = "V"
                acciones["verticales_recolocadas"] += len(qs)
            prev_fin = None
            for s in qs:
                lo, hi = min(s["a"][2], s["b"][2]), max(s["a"][2], s["b"][2])
                if prev_fin is not None and lo < prev_fin - TOL_Z_MM:
                    if hi <= prev_fin + TOL_Z_MM or \
                            hi - prev_fin < LARGO_MIN_MM:
                        acciones["verticales_descartadas"] += 1
                        continue
                    if s["a"][2] <= s["b"][2]:
                        s["a"] = [s["a"][0], s["a"][1], prev_fin]
                    else:
                        s["b"] = [s["b"][0], s["b"][1], prev_fin]
                    acciones["verticales_recolocadas"] += 1
                prev_fin = max(prev_fin or hi, hi)
                nuevos_v.append(s)
            desface += OFFSET_VERTICAL_MM
    segs = fijos + nuevos_v

    # 3. horizontales: agrupar por linea+servicio; mismo servicio recorta,
    #    distinto servicio desfaza en Z. Solo los H; los V ya estan en
    #    nuevos_v (no volver a meterlos en resto)
    grupos_h = defaultdict(list)
    resto = []
    for s in segs:
        if s["_geo"] in ("HX", "HY"):
            lin = clave_linea(s)
            grupos_h[(lin[0], lin[1], lin[2], s.get("servicio") or "")].append(s)
        elif s["_geo"] != "V":
            resto.append(s)
    nuevos_h = []
    z_extra = {}
    for clave in grupos_h:
        eje, fija, z_linea, servicio = clave
        qs = sorted(grupos_h[clave], key=lambda q: min(q["a"][0], q["b"][0])
                    if eje == "HX" else min(q["a"][1], q["b"][1]))
        # linea compartida por otro servicio? -> desfase en Z
        otros = [k for k in grupos_h
                 if k[0] == eje and k[1] == fija and k[3] != servicio
                 and abs(k[2] - z_linea) <= TOL_LINEA_MM]
        if otros and not qs[0].get("_desfasada"):
            dz = OFFSET_HORIZONTA_MM * (1 + len(otros))
            z_extra[(eje, fija, z_linea, servicio)] = dz
            for s in qs:
                s["a"] = [s["a"][0], s["a"][1], s["a"][2] + dz]
                s["b"] = [s["b"][0], s["b"][1], s["b"][2] + dz]
                s["_desfasada"] = True
            acciones["horizontales_recolocadas"] += len(qs)
        prev_fin = None
        for s in qs:
            if eje == "HX":
                lo, hi = min(s["a"][0], s["b"][0]), max(s["a"][0], s["b"][0])
            else:
                lo, hi = min(s["a"][1], s["b"][1]), max(s["a"][1], s["b"][1])
            if prev_fin is not None and lo < prev_fin - TOL_Z_MM:
                if hi <= prev_fin + TOL_Z_MM or \
                        hi - prev_fin < LARGO_MIN_MM:
                    acciones["horizontales_descartados"] += 1
                    continue
                if eje == "HX":
                    if s["a"][0] <= s["b"][0]:
                        s["a"] = [prev_fin, s["a"][1], s["a"][2]]
                    else:
                        s["b"] = [prev_fin, s["b"][1], s["b"][2]]
                else:
                    if s["a"][1] <= s["b"][1]:
                        s["a"] = [s["a"][0], prev_fin, s["a"][2]]
                    else:
                        s["b"] = [s["b"][0], prev_fin, s["b"][2]]
                acciones["horizontales_recolocadas"] += 1
            prev_fin = max(prev_fin or hi, hi)
            nuevos_h.append(s)
    segs = resto + nuevos_v + nuevos_h

    for s in segs:
        s["a"] = [round(v, 1) for v in s["a"]]
        s["b"] = [round(v, 1) for v in s["b"]]
        s["_geo"] = geo_de(s["a"], s["b"])

    # verificacion interna
    pares = detectar_solapes(segs)
    acciones["solapes_restantes"] = len(pares)
    if log_acciones is not None and pares:
        for p in pares[:10]:
            log_acciones("AVISO solape restante: %s" % p)
    return segs, acciones


def plan_apto(items, coc_ids, z_nivel, z_red, apto):
    """Segmentos del apartamento (sin crear). Lista de dicts."""
    reps, dedup = dedup_por_tipo(items)
    reps_servicio = [d for d in reps if clasificar_servicio(d["familia"])]
    segs = []

    def agrega(tipo, servicio, a, b, diam, extra=None):
        if dist_3d(a, b) < LARGO_MIN_MM:
            return
        reg = {"apto": apto, "tipo": tipo, "servicio": servicio,
               "diam_mm": diam, "a": list(a), "b": list(b)}
        if extra:
            reg.update(extra)
        segs.append(reg)

    lum = [d for d in reps_servicio
           if d["familia"] in ("M_Iluminacion", "M_ClimatizacionV")]
    sw = [d for d in reps_servicio if d["familia"] == "M_Interruptores"]
    nodos = []
    for d in lum + sw:
        p = (d["pt"][0], d["pt"][1])
        if any(d2(p[0], p[1], q[0], q[1]) <= 60.0 for q in nodos):
            continue
        nodos.append(p)
    for i, j in mst_manhattan(nodos):
        for (p, q) in arista_a_segmentos(nodos[i], nodos[j]):
            agrega("iluminacion_horizontal", "ILUMINACION",
                   (p[0], p[1], z_red), (q[0], q[1], z_red), D_16_MM)

    placas = agrupar_por_proximidad(sw, PLACA_MM)
    for placa in placas:
        bajo = min(s["pt"][2] for s in placa)
        s0 = placa[0]
        agrega("bajada_interruptor", "ILUMINACION",
               (s0["pt"][0], s0["pt"][1], z_red),
               (s0["pt"][0], s0["pt"][1], bajo), D_16_MM,
               {"n_placa": len(placa)})

    for e in [d for d in reps_servicio if d["familia"] == "EA"]:
        agrega("bajada_ventilacion", "VENTILACION",
               (e["pt"][0], e["pt"][1], e["pt"][2]),
               (e["pt"][0], e["pt"][1], z_red), D_16_MM, {"disp": e["id"]})

    tomas = [d for d in reps_servicio if d["familia"].startswith("M_Toma")]
    coc = [d for d in tomas if d["id"] in coc_ids]
    resto = [d for d in tomas if d["id"] not in coc_ids]
    for grupo in agrupar_por_proximidad(coc, 200.0):
        cerca = [g for g in grupo
                 if abs(g["pt"][2] - (z_nivel + COCINA_MEDIA_MM)) <= 120.0]
        if cerca:
            gfci = [g for g in cerca if "gfci" in (g["tipo"] or "").lower()]
            ancla = gfci[0] if gfci else cerca[0]
        else:
            ancla = min(grupo, key=lambda g: abs(
                g["pt"][2] - (z_nivel + COCINA_MEDIA_MM)))
        vx, vy = ancla["pt"][0], ancla["pt"][1]
        alturas = alturas_cocina(grupo, z_nivel)
        for k in range(len(alturas) - 1):
            agrega("cocina_vertical", "TOMAS",
                   (vx, vy, alturas[k] + z_nivel),
                   (vx, vy, alturas[k + 1] + z_nivel), D_16_MM)
        agrega("cocina_riser", "TOMAS", (vx, vy, max(alturas) + z_nivel),
               (vx, vy, z_red), D_16_MM)
    for t in resto:
        agrega("vertical_toma", "TOMAS",
               (t["pt"][0], t["pt"][1], t["pt"][2]),
               (t["pt"][0], t["pt"][1], z_red), D_16_MM, {"disp": t["id"]})

    datos = [d for d in reps_servicio if d["familia"] == "M_Comunicaciones"]
    for grupo in agrupar_por_proximidad(datos, 200.0):
        x = grupo[0]["pt"][0]
        y = grupo[0]["pt"][1]
        z_bajo = min(g["pt"][2] for g in grupo)
        for signo in (-1.0, 1.0):
            agrega("vertical_datos", "COMUNICACIONES",
                   (x, y + signo * OFFSET_COMMS_MM / 2.0, z_bajo),
                   (x, y + signo * OFFSET_COMMS_MM / 2.0, z_red), D_19_MM,
                   {"n_grupo": len(grupo)})

    return segs, {"representantes": len(reps), "dedup": dedup,
                  "excluidos": sorted(set(d["familia"] for d in reps
                                          if not clasificar_servicio(d["familia"]))),
                  "luminarias": len(lum), "interruptores": len(sw)}


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
    doc_sellado = None
    inv = inp.get("inventario")
    if inv:
        log("fuente: inventario JSON %s" % inv)
        ruta = inv if os.path.isabs(inv) else os.path.join(DEFAULT_ROOT, inv)
        with open(ruta) as f:
            datos = json.load(f)
        disp = []
        for q in datos["dispositivos"]:
            if q.get("x") is None:
                continue
            disp.append({"id": q.get("id"), "pt": [q["x"], q["y"], q["z"]],
                         "mark": q.get("mark") or "",
                         "familia": q.get("familia") or "",
                         "tipo": q.get("tipo") or ""})
    elif inp.get("documento"):
        if not dry_run:
            log("ERROR: modo 'documento' solo permite dry_run.")
            return 1
        ruta = inp["documento"]
        if not os.path.isabs(ruta):
            ruta = os.path.join(DEFAULT_ROOT, ruta)
        if not os.path.exists(ruta):
            log("ERROR: no existe %s" % ruta)
            return 1
        app = app_de()
        doc_sellado = None
        for d in app.Documents:
            try:
                if d.PathName == ruta:
                    doc_sellado = d
                    break
            except Exception:
                continue
        if doc_sellado is None:
            doc_sellado = app.OpenDocumentFile(ruta)
        doc = doc_sellado
        log("fuente: documento sellado %r" % doc.Title)
        nivel = nivel_piso5(doc)
        nivel_id = id_de(nivel)
        z_nivel = float(nivel.Elevation) * FT_A_MM
        disp = leer_dispositivos_doc(doc)
    else:
        doc = obtener_doc()
        if doc is None:
            log("ERROR: sin documento activo.")
            return 1
        log("documento=%r" % doc.Title)
        if not dry_run and "STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01c" \
                not in doc.Title:
            log("ABORTADO: el documento activo no es el de trabajo.")
            return 1
        nivel = nivel_piso5(doc)
        if nivel is None:
            log("ERROR: no se encontro Piso 5.")
            return 1
        nivel_id = id_de(nivel)
        z_nivel = float(nivel.Elevation) * FT_A_MM
        disp = leer_dispositivos_doc(doc)

    z_red = z_nivel + Z_RED_MM
    log("nivel=%.0f | plano de red=%.0f mm | dispositivos=%d" % (
        z_nivel, z_red, len(disp)))
    coc_ids = cargar_ids_cocina()

    segs = []
    resumen = {}
    for apto in aptos:
        items = [d for d in disp if d["mark"].startswith(apto + "|")]
        if not items:
            log("%s: sin dispositivos" % apto)
            resumen[apto] = {"error": "sin dispositivos"}
            continue
        s_apto, info = plan_apto(items, coc_ids, z_nivel, z_red, apto)
        segs.extend(s_apto)
        resumen[apto] = info
        log("%s: %d disp | reps=%d | segmentos planificados=%d" % (
            apto, len(items), info["representantes"], len(s_apto)))

    segs, acciones = resolver_superposiciones(segs, log)
    pares = detectar_solapes(segs)
    log("")
    log("RESOLUTOR: dedup=%d | verticales recolocadas=%d descartadas=%d | "
        "horizontales recolocados=%d descartados=%d | solapes restantes=%d" % (
            acciones["dedup_exacto"], acciones["verticales_recolocadas"],
            acciones["verticales_descartadas"],
            acciones["horizontales_recolocadas"],
            acciones["horizontales_descartados"], len(pares)))

    tramos = []
    fallos = []
    if not dry_run:
        trans = Transaction(doc, "RE7_RUTEAR_SERVICIOS_v02")
        trans.Start()
        try:
            for s in segs:
                try:
                    c = Conduit.Create(doc, ElementId(Int64(TUBO_E_ID)),
                                       xyz(s["a"][0], s["a"][1], s["a"][2]),
                                       xyz(s["b"][0], s["b"][1], s["b"][2]),
                                       ElementId(Int64(nivel_id)))
                    fijar_diam(c, s["diam_mm"])
                    if not fijar_servicio(c, s["servicio"]):
                        s["servicio_no_aplicado"] = True
                    s["conduit_id"] = id_de(c)
                    tramos.append(s)
                except Exception as ex:
                    fallos.append({"tipo": s.get("tipo"),
                                   "err": str(ex)[:110]})
            trans.Commit()
            log("transaccion COMMIT")
        except Exception:
            try:
                trans.RollBack()
                log("ERROR: transaccion revertida")
            except Exception:
                pass
            log(traceback.format_exc())
            return 1
    else:
        tramos = segs

    longitud = sum(dist_3d(t["a"], t["b"]) for t in tramos)
    por_servicio = defaultdict(int)
    por_tipo = defaultdict(int)
    for t in tramos:
        por_servicio[t["servicio"]] += 1
        por_tipo[t["tipo"]] += 1
    log("")
    log("=" * 78)
    log("RESULTADO (%s): tramos=%d | longitud=%.2f m | fallos=%d | "
        "solapes=%d" % (modo, len(tramos), longitud / 1000.0, len(fallos),
                        len(pares)))
    for s in sorted(por_servicio):
        log("   %-14s %d" % (s, por_servicio[s]))
    for t in sorted(por_tipo):
        log("   %-22s %d" % (t, por_tipo[t]))
    for a in aptos:
        log("   %-5s %s" % (a, resumen.get(a)))

    out = os.path.join(DEFAULT_ROOT, "data",
                       "f7_%s_servicios_%s_v02.json" % (
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
                "resolucion": acciones,
                "solapes": pares,
                "resumen": resumen,
                "totales": {"tramos": len(tramos),
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
