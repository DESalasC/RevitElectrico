# -*- coding: utf-8 -*-
"""
RE7_AUDITAR_RED_CONDUITS_v01.py

SOLO LECTURA. No abre transacciones.

Responde con datos del modelo, sin suponer nada:
  A) Tipos de conduit existentes: id, nombre y TODOS sus parametros
     (nombre + valor), para localizar el parametro de diametro/tamano.
  B) Conduits creados: cuantos por tipo y que diametro reporta la instancia,
     con indicacion de si el parametro es de solo lectura.
  C) Datos/Comunicaciones: dispositivos por apartamento, agrupados a 200 mm,
     y cuantos tramos verticales hay en cada agrupacion (deberia haber 2).
  D) Cocinas: dispositivos con Comment='Cocina', campanas y dispositivos
     cercanos a una campana; para cada uno, si su riser es recto o tiene
     segmentos (escalones 700/1050/1650).

Salida: data/f7_auditoria_red_conduits_v01.json
Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
import math
import os
import sys
import traceback
from collections import defaultdict, Counter

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    LocationCurve,
    LocationPoint,
)
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType

VERSION = "v01_auditoria_red"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
Z_PLENUM_MM = 15930.0
Z_TOL_MM = 25.0
CLUSTER_MM = 200.0
RADIO_DEVICE_MM = 300.0

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


def punto_real(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            p = loc.Point
            return [p.X * FT_A_MM, p.Y * FT_A_MM, p.Z * FT_A_MM]
        if isinstance(loc, LocationCurve):
            c = loc.Curve
            p0 = c.GetEndPoint(0)
            p1 = c.GetEndPoint(1)
            return [0.5 * (p0.X + p1.X) * FT_A_MM,
                    0.5 * (p0.Y + p1.Y) * FT_A_MM,
                    0.5 * (p0.Z + p1.Z) * FT_A_MM]
    except Exception:
        pass
    return None


def extremos_conduit(el):
    try:
        loc = el.Location
        if not isinstance(loc, LocationCurve):
            return None
        c = loc.Curve
        e0 = c.GetEndPoint(0)
        e1 = c.GetEndPoint(1)
        return ([e0.X * FT_A_MM, e0.Y * FT_A_MM, e0.Z * FT_A_MM],
                [e1.X * FT_A_MM, e1.Y * FT_A_MM, e1.Z * FT_A_MM])
    except Exception:
        return None


def valor_texto(el, nombres):
    for nombre in nombres:
        try:
            p = el.LookupParameter(nombre)
            if p is not None:
                s = p.AsString()
                if s is not None:
                    return s
        except Exception:
            pass
    return None


def nombre_familia(el):
    try:
        if el.Symbol is not None and el.Symbol.Family is not None:
            return el.Symbol.Family.Name
    except Exception:
        pass
    return None


def nombre_tipo_el(el):
    try:
        if el.Symbol is not None:
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                return p.AsString()
    except Exception:
        pass
    return None


def nombre_tipo_conduit(el):
    try:
        t = el.GetTypeId()
        if t is not None and t.IntegerValue > 0:
            te = el.Document.GetElement(t)
            if te is not None:
                return te.Name
    except Exception:
        pass
    return None


def parametros_diagnostico(el, solo_interesantes=True):
    out = []
    try:
        for p in el.Parameters:
            try:
                nom = p.Definition.Name
            except Exception:
                continue
            if solo_interesantes:
                low = nom.lower()
                if not ("diam" in low or "size" in low or "tama" in low or "diám" in low):
                    continue
            try:
                vs = p.AsValueString()
            except Exception:
                vs = None
            if vs is None:
                try:
                    vs = p.AsString()
                except Exception:
                    vs = None
            if vs is None:
                try:
                    vs = str(p.AsDouble())
                except Exception:
                    vs = None
            ro = None
            try:
                ro = p.IsReadOnly
            except Exception:
                pass
            out.append({"nombre": nom, "valor": vs, "readonly": ro})
    except Exception:
        pass
    return out


def dist2d(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def main():
    log("=" * 74)
    log("RE7_AUDITAR_RED_CONDUITS_%s  (SOLO LECTURA)" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    # ---------------- A) tipos de conduit ----------------
    log("")
    log("-" * 74)
    log("A) TIPOS DE CONDUIT")
    tipos = []
    try:
        for t in FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
            params = parametros_diagnostico(t, solo_interesantes=False)
            interesantes = [p for p in params
                            if ("diam" in p["nombre"].lower() or "size" in p["nombre"].lower()
                                or "tama" in p["nombre"].lower())]
            tipos.append({"id": id_de(t), "nombre": t.Name,
                          "params_interesantes": interesantes})
            log("   id=%-9s %-28s %s" % (id_de(t), t.Name,
                "; ".join("%s=%s" % (p["nombre"], p["valor"]) for p in interesantes) or "(sin param de diametro)"))
    except Exception:
        log("   ERROR leyendo ConduitType")
        log(traceback.format_exc())

    # ---------------- B) conduits creados ----------------
    log("")
    log("-" * 74)
    log("B) CONDUITS")
    conduits = []
    verticales = []
    horizontales = []
    otros = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        par = extremos_conduit(el)
        if par is None:
            continue
        e0, e1 = par
        nombre_t = nombre_tipo_conduit(el)
        info_diam = parametros_diagnostico(el, solo_interesantes=True)
        d = {
            "id": id_de(el),
            "tipo": nombre_t,
            "diam": info_diam,
            "a": [round(v, 1) for v in e0],
            "b": [round(v, 1) for v in e1],
        }
        conduits.append(d)
        if abs(e0[0] - e1[0]) <= 2.0 and abs(e0[1] - e1[1]) <= 2.0:
            if abs(max(e0[2], e1[2]) - Z_PLENUM_MM) <= Z_TOL_MM:
                verticales.append(d)
            else:
                otros.append(d)
        elif abs(e0[2] - Z_PLENUM_MM) <= Z_TOL_MM and abs(e1[2] - Z_PLENUM_MM) <= Z_TOL_MM:
            horizontales.append(d)
        else:
            otros.append(d)

    log("   total=%d | verticales a plenum=%d | horizontales plenum=%d | otros=%d" % (
        len(conduits), len(verticales), len(horizontales), len(otros)))
    log("   por tipo: %s" % dict(Counter(c["tipo"] for c in conduits)))
    diam_vals = Counter()
    for c in conduits:
        for p in c["diam"]:
            diam_vals["%s=%s" % (p["nombre"], p["valor"])] += 1
    log("   parametros de diametro (muestra): %s" % dict(diam_vals))

    # ---------------- C) datos por apartamento ----------------
    log("")
    log("-" * 74)
    log("C) DATOS / COMUNICACIONES")
    disp = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto_real(el)
            if pt is None:
                continue
            mk = valor_texto(el, ["Mark"]) or ""
            apto = mk.split("|")[0] if "|" in mk else None
            fam = nombre_familia(el) or ""
            tip = nombre_tipo_el(el) or ""
            disp.append({"id": id_de(el), "pt": pt, "apto": apto,
                         "familia": fam, "tipo": tip, "mark": mk,
                         "comment": valor_texto(el, ["Comments"])})

    def es_datos(d):
        s = (d["familia"] + " " + d["tipo"]).lower()
        return any(k in s for k in ("comunicacion", "datos", "telephone", "data devices", "pau"))

    datos = [d for d in disp if es_datos(d)]
    log("   dispositivos datos/comunicaciones: %d" % len(datos))

    clústeres = []
    por_apto = defaultdict(list)
    for d in datos:
        por_apto[d["apto"] or "?"].append(d)

    resumen_datos = {}
    for apto in sorted(por_apto.keys()):
        items = por_apto[apto]
        usados = set()
        clusters = []
        for i, d in enumerate(items):
            if i in usados:
                continue
            grupo = [d]
            usados.add(i)
            for j in range(i + 1, len(items)):
                if j in usados:
                    continue
                if dist2d(d["pt"][0], d["pt"][1], items[j]["pt"][0], items[j]["pt"][1]) <= CLUSTER_MM:
                    grupo.append(items[j])
                    usados.add(j)
            # verticales en este cluster
            vs = []
            for v in verticales:
                for g in grupo:
                    if dist2d(v["a"][0], v["a"][1], g["pt"][0], g["pt"][1]) <= RADIO_DEVICE_MM:
                        vs.append(v["id"])
                        break
            clusters.append({"n_outlets": len(grupo),
                             "ids": [g["id"] for g in grupo],
                             "verticales": len(set(vs)),
                             "vertical_ids": sorted(set(vs))})
        resumen_datos[apto] = {
            "outlets": len(items),
            "clusters": len(clusters),
            "verticales": sum(c["verticales"] for c in clusters),
            "detalle": clusters,
        }
        log("   %-6s outlets=%-3d clusters=%-3d verticales=%-3d  (esperado 2 por cluster)" % (
            apto, len(items), len(clusters), resumen_datos[apto]["verticales"]))

    # ---------------- D) cocinas ----------------
    log("")
    log("-" * 74)
    log("D) COCINAS")
    coc = [d for d in disp if (d["comment"] or "").lower().find("cocina") >= 0]
    camp = [d for d in disp if "campana" in (d["familia"] + " " + d["tipo"]).lower()]
    log("   con Comment='Cocina': %d | campanas: %d" % (len(coc), len(camp)))

    def riser_info(x, y):
        """Devuelve (n_verticales, n_segmentos_total) del riser en esa XY."""
        ids = []
        zs = []
        for v in verticales:
            if dist2d(x, y, v["a"][0], v["a"][1]) <= 50.0:
                ids.append(v["id"])
                zs.append((min(v["a"][2], v["b"][2]), max(v["a"][2], v["b"][2])))
        return len(ids), zs

    resumen_coc = []
    for d in coc:
        n, zs = riser_info(d["pt"][0], d["pt"][1])
        resumen_coc.append({
            "id": d["id"], "mark": d["mark"], "tipo": d["tipo"],
            "z": round(d["pt"][2], 1), "verticales": n,
            "tramos_z": [[round(a, 1), round(b, 1)] for (a, b) in zs],
        })
    segmentadas = sum(1 for r in resumen_coc if len(r["tramos_z"]) > 1)
    log("   risers de cocina con mas de un tramo (segmentados): %d de %d" % (
        segmentadas, len(resumen_coc)))
    for r in resumen_coc[:15]:
        log("      id=%-9s z=%-7.0f verticales=%d tramos=%s" % (
            r["id"], r["z"], r["verticales"], r["tramos_z"]))

    # ---------------- JSON ----------------
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    rep = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "tipos_conduit": tipos,
        "conduits": {
            "total": len(conduits),
            "verticales": len(verticales),
            "horizontales": len(horizontales),
            "otros": len(otros),
            "por_tipo": dict(Counter(c["tipo"] for c in conduits)),
        },
        "datos": resumen_datos,
        "cocinas": {"con_comment": len(coc), "campanas": len(camp),
                    "detalle": resumen_coc},
    }
    out = os.path.join(raiz, "data", "f7_auditoria_red_conduits_v01.json")
    try:
        with open(out, "w") as f:
            f.write(json.dumps(rep, ensure_ascii=True, indent=1))
        log("")
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    log("=" * 74)
    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
