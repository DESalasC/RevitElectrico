# -*- coding: utf-8 -*-
"""
RE7_CORREGIR_RED_v01.py

Aplica las tres correcciones pedidas sobre los conduits ya creados:

  1) DIAMETROS: tomas/iluminacion/fuerza -> 16 mm (1/2"); datos y
     comunicaciones -> 19 mm (3/4"). Nunca 25 mm.
     Si el parametro de instancia es de solo lectura, se informa y no se
     fuerza nada (no se inventan tipos).

  2) DATOS: en cada agrupacion de salidas (<=200 mm) debe haber UN SOLO par
     de tubos (2 conduits separados ~40 mm). Si hay mas verticales, se
     conservan los 2 mas centrados en la agrupacion y se borran los demas.

  3) COCINAS: los risers de cocina se rehacen segmentados pasando por las
     alturas nivel+700, nivel+1050, nivel+1650 y plenum. Se borra el riser
     recto previo y se crean los tramos.

Lee: data/f7_cocinas_ids_v01.json (ids de dispositivos de cocina)
Salvaguardas:
  * Nunca borra elementos con GroupId valido (miembros de grupo).
  * Todo en UNA transaccion; RollBack si algo falla.
  * Verifica diametro leyendo de vuelta.

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
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
from System import Int64

VERSION = "v01_corregir_red"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"

Z_PLENUM_MM = 15930.0
Z_TOL_MM = 25.0
CLUSTER_MM = 200.0
RADIO_VERTICAL_MM = 300.0
RADIO_VERTICAL_DATOS_MM = 120.0
RADIO_MISMA_XY_MM = 60.0
LARGO_MIN_MM = 5.0

D_16_MM = 16.0
D_19_MM = 19.0
COCINA_ALTURAS_REL_MM = [700.0, 1050.0, 1650.0]

TUBO_E_ID = 112216

CATEGORIAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_TelephoneDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_MechanicalEquipment,
]

NOMBRES_DIAM = ["Diameter(Trade Size)", "Diameter", "Size", "Inside Diameter",
                "Outside Diameter"]


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


def group_id(el):
    try:
        g = el.GroupId
        if g is None:
            return 0
        v = g.IntegerValue if hasattr(g, "IntegerValue") else g.Value
        return int(v)
    except Exception:
        return 0


def es_miembro_grupo(el):
    g = group_id(el)
    return g != 0 and g != -1


def extremos(el):
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


def familia_y_tipo(el):
    fam = ""
    tip = ""
    try:
        if el.Symbol is not None:
            if el.Symbol.Family is not None:
                fam = el.Symbol.Family.Name
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                tip = p.AsString() or ""
    except Exception:
        pass
    return fam, tip


def param_diametro(el):
    for nombre in NOMBRES_DIAM:
        try:
            p = el.LookupParameter(nombre)
            if p is not None:
                return p
        except Exception:
            continue
    return None


def diametro_mm(el):
    p = param_diametro(el)
    if p is None:
        return None
    try:
        v = p.AsDouble() * FT_A_MM
        return round(v, 2)
    except Exception:
        return None


def mm_a_ft(mm):
    return mm / FT_A_MM


def xyz_mm(x, y, z):
    return XYZ(mm_a_ft(x), mm_a_ft(y), mm_a_ft(z))


def dist2d(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


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


def main():
    log("=" * 74)
    log("RE7_CORREGIR_RED_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    nivel = buscar_nivel(doc)
    if nivel is None:
        log("ERROR: no se encontro nivel Piso 5.")
        return 1
    nivel_id = id_de(nivel)
    z_nivel = float(nivel.Elevation) * FT_A_MM
    log("nivel=%r id=%s elevacion=%.0f mm" % (nivel.Name, nivel_id, z_nivel))

    # ---------- probe de tipos y parametro de diametro ----------
    log("")
    log("-" * 74)
    log("PROBE")
    tipos = []
    for t in FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
        nom = None
        try:
            p = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                nom = p.AsString()
        except Exception:
            pass
        size = None
        size_ro = None
        for cand in ("Size", "Diameter", "Diameter(Trade Size)"):
            try:
                pp = t.LookupParameter(cand)
                if pp is not None:
                    size = pp.AsValueString()
                    size_ro = pp.IsReadOnly
                    break
            except Exception:
                pass
        tipos.append({"id": id_de(t), "nombre": nom, "size": size, "size_readonly": size_ro})
        log("   tipo id=%-9s %-24s size=%-10s readonly=%s" % (
            id_de(t), nom, size, size_ro))

    conduits = []
    for el in FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Conduit).ToElements():
        par = extremos(el)
        if par is None:
            continue
        e0, e1 = par
        ent = {
            "el": el, "id": id_de(el), "a": e0, "b": e1,
            "grupo": es_miembro_grupo(el),
        }
        ent["vertical"] = (abs(e0[0] - e1[0]) <= 2.0 and abs(e0[1] - e1[1]) <= 2.0)
        ent["en_plenum"] = (abs(e0[2] - Z_PLENUM_MM) <= Z_TOL_MM and
                            abs(e1[2] - Z_PLENUM_MM) <= Z_TOL_MM)
        conduits.append(ent)

    p_diam = None
    for c in conduits:
        p_diam = param_diametro(c["el"])
        if p_diam is not None:
            break
    diam_ro = None
    if p_diam is not None:
        try:
            diam_ro = p_diam.IsReadOnly
        except Exception:
            diam_ro = None
    log("   conduits=%d | parametro diametro=%r readonly=%s valor_actual=%s" % (
        len(conduits), p_diam.Definition.Name if p_diam is not None else None,
        diam_ro, diametro_mm(conduits[0]["el"]) if conduits else None))

    if diam_ro:
        log("   AVISO: el diametro es de SOLO LECTURA: no se puede fijar 16/19 mm")
        log("   por instancia. Habria que crear tipos 'Conduit 1/2\"' y '3/4\"'.")
    # ---------- dispositivos ----------
    disp = []
    for cat in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
            pt = punto_real(el)
            if pt is None:
                continue
            fam, tip = familia_y_tipo(el)
            mk = valor_texto(el, ["Mark"]) or ""
            disp.append({"id": id_de(el), "pt": pt, "familia": fam, "tipo": tip,
                         "mark": mk, "apto": mk.split("|")[0] if "|" in mk else None})

    def es_datos(d):
        s = (d["familia"] + " " + d["tipo"]).lower()
        return any(k in s for k in ("comunicacion", "datos", "telephone", "data devices", "pau"))

    datos = [d for d in disp if es_datos(d)]
    log("   dispositivos=%d | datos=%d" % (len(disp), len(datos)))

    # cocinas
    coc_ids = set()
    try:
        with open(os.path.join(os.environ.get("REVITELECTRICO_ROOT", DEFAULT_ROOT) or DEFAULT_ROOT,
                               "data", "f7_cocinas_ids_v01.json")) as f:
            coc_ids = set(int(x) for x in json.load(f)["ids"])
    except Exception as ex:
        log("   AVISO: no se pudo leer f7_cocinas_ids_v01.json (%s)" % ex)
    cocinas = [d for d in disp if d["id"] in coc_ids]
    log("   dispositivos de cocina: %d" % len(cocinas))

    # ---------- TRANSACCION ----------
    diam_ok = 0
    diam_fail = 0
    datos_borrados = 0
    datos_pares = 0
    coc_borrados = 0
    coc_segmentos = 0
    coc_reconstruidas = 0
    errores = []

    trans = Transaction(doc, "RE7_CORREGIR_RED_v01")
    trans.Start()
    try:
        # ---- 1) diametros ----
        if not diam_ro and p_diam is not None:
            for c in conduits:
                el = c["el"]
                # servicio segun proximidad a dispositivo de datos
                es_dato = False
                for d in datos:
                    if dist2d(c["a"][0], c["a"][1], d["pt"][0], d["pt"][1]) <= RADIO_VERTICAL_MM:
                        es_dato = True
                        break
                destino = D_19_MM if es_dato else D_16_MM
                try:
                    p = param_diametro(el)
                    if p is None or p.IsReadOnly:
                        diam_fail += 1
                        continue
                    p.Set(mm_a_ft(destino))
                    leido = diametro_mm(el)
                    if leido is not None and abs(leido - destino) <= 0.6:
                        diam_ok += 1
                    else:
                        diam_fail += 1
                except Exception as ex:
                    diam_fail += 1
                    if len(errores) < 30:
                        errores.append({"fase": "diam", "id": c["id"], "err": str(ex)[:100]})
        else:
            log("   FASE 1 OMITIDA: diametro no escribible.")

        # ---- 2) un solo par de tubos por agrupacion de datos ----
        por_apto = defaultdict(list)
        for d in datos:
            por_apto[d["apto"] or "?"].append(d)

        for apto in sorted(por_apto.keys()):
            items = por_apto[apto]
            usados = set()
            for i in range(len(items)):
                if i in usados:
                    continue
                grupo = [items[i]]
                usados.add(i)
                for j in range(i + 1, len(items)):
                    if j in usados:
                        continue
                    if dist2d(items[i]["pt"][0], items[i]["pt"][1],
                              items[j]["pt"][0], items[j]["pt"][1]) <= CLUSTER_MM:
                        grupo.append(items[j])
                        usados.add(j)
                # verticales de la agrupacion
                vs = []
                for c in conduits:
                    if not c["vertical"]:
                        continue
                    if abs(max(c["a"][2], c["b"][2]) - Z_PLENUM_MM) > Z_TOL_MM:
                        continue  # no llega al plenum: no es un riser
                    for g in grupo:
                        if dist2d(c["a"][0], c["a"][1], g["pt"][0], g["pt"][1]) <= RADIO_VERTICAL_DATOS_MM:
                            vs.append(c)
                            break
                if len(vs) <= 2:
                    if len(vs) == 2:
                        datos_pares += 1
                    continue
                # centro de la agrupacion
                cx = sum(g["pt"][0] for g in grupo) / len(grupo)
                cy = sum(g["pt"][1] for g in grupo) / len(grupo)
                # preferir un par con misma X y ~40 mm en Y
                mejor_par = None
                mejor_cost = None
                for a_i in range(len(vs)):
                    for b_i in range(a_i + 1, len(vs)):
                        va, vb = vs[a_i], vs[b_i]
                        if abs(va["a"][0] - vb["a"][0]) > 3.0:
                            continue
                        dy = abs(va["a"][1] - vb["a"][1])
                        if dy < 25.0 or dy > 70.0:
                            continue
                        cost = dist2d(va["a"][0], va["a"][1], cx, cy)
                        if mejor_cost is None or cost < mejor_cost:
                            mejor_cost = cost
                            mejor_par = (va, vb)
                if mejor_par is None:
                    ordenados = sorted(vs, key=lambda c: dist2d(c["a"][0], c["a"][1], cx, cy))
                    mejor_par = (ordenados[0], ordenados[1]) if len(ordenados) >= 2 else None
                if mejor_par is None:
                    continue
                conservar = set([mejor_par[0]["id"], mejor_par[1]["id"]])
                for c in vs:
                    if c["id"] in conservar:
                        continue
                    if c["grupo"]:
                        errores.append({"fase": "datos", "id": c["id"],
                                        "err": "miembro de grupo, no se borra"})
                        continue
                    try:
                        doc.Delete(c["el"].Id)
                        datos_borrados += 1
                    except Exception as ex:
                        errores.append({"fase": "datos", "id": c["id"], "err": str(ex)[:100]})
                datos_pares += 1

        # ---- 3) cocinas segmentadas ----
        # agrupar cocinas por XY cercana para no crear cadenas duplicadas
        coc_usados = set()
        for i in range(len(cocinas)):
            if i in coc_usados:
                continue
            grupo = [cocinas[i]]
            coc_usados.add(i)
            for j in range(i + 1, len(cocinas)):
                if j in coc_usados:
                    continue
                if dist2d(cocinas[i]["pt"][0], cocinas[i]["pt"][1],
                          cocinas[j]["pt"][0], cocinas[j]["pt"][1]) <= CLUSTER_MM:
                    grupo.append(cocinas[j])
                    coc_usados.add(j)
            # XY del riser existente (si lo hay) para reconstruir en el mismo sitio
            x = grupo[0]["pt"][0]
            y = grupo[0]["pt"][1]
            for c in conduits:
                if not c["vertical"]:
                    continue
                if abs(max(c["a"][2], c["b"][2]) - Z_PLENUM_MM) > Z_TOL_MM:
                    continue
                cerca = False
                for g in grupo:
                    if dist2d(c["a"][0], c["a"][1], g["pt"][0], g["pt"][1]) <= CLUSTER_MM:
                        cerca = True
                        break
                if cerca:
                    x, y = c["a"][0], c["a"][1]
                    break
            z_min = min(g["pt"][2] for g in grupo)
            # borrar verticales existentes en esa XY
            for c in conduits:
                if not c["vertical"]:
                    continue
                if dist2d(c["a"][0], c["a"][1], x, y) > RADIO_MISMA_XY_MM:
                    continue
                if c["grupo"]:
                    errores.append({"fase": "cocina", "id": c["id"],
                                    "err": "miembro de grupo, no se borra"})
                    continue
                try:
                    doc.Delete(c["el"].Id)
                    coc_borrados += 1
                except Exception as ex:
                    errores.append({"fase": "cocina", "id": c["id"], "err": str(ex)[:100]})

            # cadena: z_min -> alturas -> plenum
            objetivo = [z_nivel + h for h in COCINA_ALTURAS_REL_MM]
            objetivo.append(Z_PLENUM_MM)
            cadena = [z_min]
            for z in sorted(objetivo):
                if z > z_min + 1.0:
                    cadena.append(z)
            limpia = []
            for z in cadena:
                if not limpia or abs(z - limpia[-1]) > 1.0:
                    limpia.append(z)
            hechos = 0
            for k in range(len(limpia) - 1):
                za, zb = limpia[k], limpia[k + 1]
                if abs(zb - za) < LARGO_MIN_MM:
                    continue
                try:
                    nuevo = Conduit.Create(
                        doc, ElementId(Int64(TUBO_E_ID)),
                        xyz_mm(x, y, za), xyz_mm(x, y, zb),
                        ElementId(Int64(nivel_id)))
                    hechos += 1
                    # diametro 16 mm
                    if not diam_ro:
                        pp = param_diametro(nuevo)
                        if pp is not None and not pp.IsReadOnly:
                            try:
                                pp.Set(mm_a_ft(D_16_MM))
                            except Exception:
                                pass
                except Exception as ex:
                    errores.append({"fase": "cocina_create", "apto": grupo[0]["apto"],
                                    "err": str(ex)[:120]})
            coc_segmentos += hechos
            if hechos > 0:
                coc_reconstruidas += 1

        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida, no se aplico nada.")
        log(traceback.format_exc())
        return 1

    total = len(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Conduit).ToElements())

    log("")
    log("=" * 74)
    log("RESULTADO")
    log("  1) diametros: ok=%d fallos=%d (ro=%s)" % (diam_ok, diam_fail, diam_ro))
    log("  2) datos: pares conservados=%d | verticales extra borrados=%d" % (
        datos_pares, datos_borrados))
    log("  3) cocinas: agrupaciones reconstruidas=%d | segmentos creados=%d | risers previos borrados=%d" % (
        coc_reconstruidas, coc_segmentos, coc_borrados))
    log("  conduits totales: %d" % total)
    if errores:
        log("  errores/avisos: %d" % len(errores))
        for e in errores[:15]:
            log("     %s" % e)
    log("=" * 74)

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    rep = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "tipos_conduit": tipos,
        "diametro_readonly": diam_ro,
        "resumen": {
            "diam_ok": diam_ok, "diam_fail": diam_fail,
            "datos_pares": datos_pares, "datos_borrados": datos_borrados,
            "cocinas_reconstruidas": coc_reconstruidas,
            "cocina_segmentos": coc_segmentos, "cocina_borrados": coc_borrados,
            "conduits_totales": total,
        },
        "errores": errores,
    }
    out = os.path.join(raiz, "data", "f7_corregir_red_v01.json")
    try:
        with open(out, "w") as f:
            f.write(json.dumps(rep, ensure_ascii=True, indent=1))
        log("JSON: %s" % out)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
