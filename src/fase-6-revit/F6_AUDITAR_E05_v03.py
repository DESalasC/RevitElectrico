# -*- coding: utf-8 -*-
"""
F6_AUDITAR_E05_v03.py
=====================
Auditoria COMPLETA y de SOLO LECTURA del Apartamento Tipo E 05.

CORRECCIONES frente a v02 (corrida 2026-11-09 16:27)
----------------------------------------------------
  1. TOLERANCIA DE EMPAREJAMIENTO. v02 usaba 0.30 m, pero el aplicador pega los
     dispositivos al muro y los desplaza hasta 0.66 m. Por eso reportaba 31
     sobrantes y 7 faltantes que eran los MISMOS objetos bien colocados.
     Ahora el emparejamiento usa 0.90 m y se reporta la distancia de cada uno,
     marcando como 'ajuste' los que superan 0.35 m.
  2. ANCLAS SEPARADAS. El tablero (E_Distribution Panel) y el medidor estan en la
     zona pero NO son dispositivos del apartamento: son el ancla. Se listan
     aparte y no cuentan como huerfanos ni como familias obsoletas.
  3. CANDIDATOS DE BORRADO. Se construye la lista concreta de ElementId a
     eliminar: familias fuera del mapeo, duplicados y sobrantes. La usa
     F6_LIMPIAR_E05_v01.py.

Secciones
---------
  A. Esperados / B. Encontrados / C. Emparejamiento / D. Huerfanos
  E. Familias fuera del mapeo / F. Cotas Z / G. Candidatos a borrado

Uso
---
    exec(open(r"...\\F6_AUDITAR_E05_v03.py").read())
    auditar(doc)
"""
import io
import json
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Level,
)

FT = 0.3048

CATS = [BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
        BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_TelephoneDevices]

TOL_XY_M = 0.90      # emparejamiento: incluye el ajuste al muro (hasta 0.66 m)
TOL_DUP_M = 0.08     # para considerar duplicado
TOL_AJUSTE_M = 0.35  # a partir de aqui se reporta como ajuste al paramento
MARGEN_ZONA_M = 1.00
Z_BANDA_M = (0.10, 3.10)   # relativo a la elevacion del nivel

# Familias que son el ancla del apartamento, no dispositivos a modelar.
# Se comparan con clave normalizada (sin espacios, en minuscula): comparar
# "distribution panel" con espacios contra "edistributionpanel" nunca coincidia,
# y el tablero acababa en la lista de candidatos a borrado.
FAMILIAS_ANCLA_CLAVES = ("distributionpanel", "medidor")


def _resolver_doc(doc):
    if doc is not None:
        return doc
    try:
        uidoc = __revit__.ActiveUIDocument  # noqa: F821
        return uidoc.Document if uidoc is not None else None
    except Exception:
        return None


def _safe(v):
    if v is None:
        return ""
    try:
        s = str(v)
    except Exception:
        return "?"
    out = []
    for c in s:
        try:
            c.encode("ascii")
            out.append(c)
        except Exception:
            out.append("_")
    return "".join(out)


def _eid_txt(eid):
    try:
        return str(eid)
    except Exception:
        return "?"


def _clave(t):
    if t is None:
        return ""
    try:
        s = unicode(t)  # noqa: F821
    except Exception:
        s = str(t)
    import unicodedata
    try:
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return "".join(c.lower() for c in s if c.isalpha() or c.isdigit())


def _leer_json(path):
    f = io.open(path, "r", encoding="utf-8")
    try:
        return json.load(f)
    finally:
        f.close()


def _guardar(path, obj):
    try:
        txt = json.dumps(obj, indent=2, ensure_ascii=True)
        try:
            datos = txt.encode("ascii", "replace")
        except Exception:
            datos = txt
        f = io.open(path, "wb")
        try:
            f.write(datos)
        finally:
            f.close()
        return True
    except Exception as ex:
        print("No se pudo guardar {}: {}".format(path, _safe(ex)))
        return False


def _nombre_tipo(e):
    try:
        p = e.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    try:
        return e.Name or ""
    except Exception:
        return ""


def _esperados(data, mapeo):
    """Lista de dispositivos que deberian existir, segun JSON + mapeo."""
    disp = mapeo.get("dispositivos") or {}
    excl = mapeo.get("excluir") or {}
    excl_capa = mapeo.get("excluir_por_bloque_y_capa") or {}
    out = []
    for d in data.get("dispositivos") or []:
        b = d.get("nombre_bloque_hijo")
        if b in excl:
            continue
        if (d.get("capa") or "") in (excl_capa.get(b) or []):
            continue
        regla = disp.get(b)
        if regla is None or not regla.get("modelar", True):
            continue
        z_local = regla.get("z_local_m")
        if z_local is None:
            z_local = d["z_local_m"]
        z_local = float(z_local)
        # Misma regla que el aplicador: lampara forzada a techo con altura de
        # muro -> altura de cielorraso. Sin esto el informe compara 3 lamparas
        # Bala Stil Led 13W contra 13.52 cuando deben estar a 15.82.
        anf_regla = (regla.get("anfitrion") or "").lower()
        es_techo = anf_regla in ("techo", "ceiling")
        if not anf_regla:
            a_json = (d.get("anfitrion") or "").lower()
            if a_json == "ceiling":
                es_techo = True
            elif a_json in ("muro", "wall"):
                es_techo = False
            else:
                es_techo = z_local >= 2.0
        if es_techo and z_local < 2.0:
            z_local = 2.60

        out.append({
            "bloque": b,
            "familia": _safe(regla.get("familia")),
            "simbolo": _safe(regla.get("simbolo")),
            "anfitrion": regla.get("anfitrion") or d.get("anfitrion"),
            "x": float(d["x_revit_m"]),
            "y": float(d["y_revit_m"]),
            "z_local": z_local,
        })
    return out


def auditar(doc=None,
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_mapeo="config/mapeo_E05_v01.json",
            json_out="data/auditoria_E05_v03.json"):
    doc = _resolver_doc(doc)
    if doc is None:
        print("No hay documento activo.")
        return None

    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    for k in ("json_in", "json_mapeo", "json_out"):
        pass
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_mapeo):
        json_mapeo = os.path.join(root, json_mapeo)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    data = _leer_json(json_in)
    mapeo = _leer_json(json_mapeo)
    esperados = _esperados(data, mapeo)

    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _clave(lv.Name) == _clave(data.get("nivel", "Piso 5")):
            nivel = lv
            break
    elev_m = (nivel.Elevation * FT) if nivel is not None else 0.0

    # ---------- zona del apartamento ----------
    xs = [e["x"] for e in esperados] or [0.0]
    ys = [e["y"] for e in esperados] or [0.0]
    env = (min(xs) - MARGEN_ZONA_M, max(xs) + MARGEN_ZONA_M,
           min(ys) - MARGEN_ZONA_M, max(ys) + MARGEN_ZONA_M)
    z_lo = elev_m + Z_BANDA_M[0]
    z_hi = elev_m + Z_BANDA_M[1]

    print("=" * 74)
    print("AUDITORIA E05 v03  |  doc: " + _safe(doc.Title))
    print("Nivel {}  elev={:.4f} m".format(_safe(data.get("nivel")), elev_m))
    print("Zona X [{:.2f}, {:.2f}]  Y [{:.2f}, {:.2f}]  Z [{:.2f}, {:.2f}] m".format(
        env[0], env[1], env[2], env[3], z_lo, z_hi))
    print("=" * 74)

    # ---------- A ----------
    print("\nA. ESPERADOS: {}".format(len(esperados)))
    fam_esp = {}
    for e in esperados:
        fam_esp[e["familia"]] = fam_esp.get(e["familia"], 0) + 1
    for k in sorted(fam_esp):
        print("   {:<36} {}".format(k, fam_esp[k]))

    # ---------- recoleccion ----------
    encontrados = []   # con comentario APT-E-05
    huerfanos = []     # en la zona, sin comentario
    anclas = []        # tablero / medidor: no son dispositivos
    vistas = {}

    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    coment = cp.AsString() if cp is not None else ""
                except Exception:
                    coment = ""
                try:
                    pt = inst.Location.Point
                except Exception:
                    continue
                xm = pt.X * FT
                ym = pt.Y * FT
                zm = pt.Z * FT
                if not (env[0] <= xm <= env[1] and env[2] <= ym <= env[3]):
                    continue
                if not (z_lo <= zm <= z_hi):
                    continue
                try:
                    fam = _safe(inst.Symbol.Family.Name)
                    tip = _safe(_nombre_tipo(inst.Symbol))
                except Exception:
                    fam, tip = "?", "?"
                fila = {"elemento_id": _eid_txt(inst.Id), "familia": fam, "tipo": tip,
                        "x": round(xm, 3), "y": round(ym, 3), "z": round(zm, 3),
                        "comentario": _safe(coment)}
                es_ancla = any(a in _clave(fam) for a in FAMILIAS_ANCLA_CLAVES)
                if es_ancla:
                    anclas.append(fila)
                elif coment and "APT-E-05" in coment:
                    encontrados.append(fila)
                else:
                    try:
                        if inst.Category is not None:
                            fila["categoria"] = _safe(inst.Category.Name)
                    except Exception:
                        pass
                    huerfanos.append(fila)
        except Exception:
            pass

    print("\nB. ENCONTRADOS con APT-E-05-P5: {}".format(len(encontrados)))

    # ---------- C: emparejamiento ----------
    usados = {}
    ok, faltan, dups = [], [], []
    for i, e in enumerate(esperados):
        cands = []
        for j, f in enumerate(encontrados):
            if j in usados:
                continue
            if _clave(f["familia"]) != _clave(e["familia"]):
                continue
            d = math.hypot(f["x"] - e["x"], f["y"] - e["y"])
            if d <= TOL_XY_M:
                cands.append((d, j))
        if not cands:
            faltan.append(e)
            continue
        cands.sort()
        d, j = cands[0]
        usados[j] = True
        ok.append({"bloque": e["bloque"], "elemento_id": encontrados[j]["elemento_id"],
                   "dist": round(d, 3), "z": encontrados[j]["z"]})
        if len(cands) > 1 and cands[1][0] <= TOL_DUP_M:
            dups.append({"bloque": e["bloque"], "elemento_id": encontrados[j]["elemento_id"],
                         "otro": encontrados[cands[1][1]]["elemento_id"]})
    sobrantes = [f for j, f in enumerate(encontrados) if j not in usados]

    print("   emparejados OK : {}".format(len(ok)))
    print("   FALTANTES      : {}".format(len(faltan)))
    print("   SOBRANTES      : {}".format(len(sobrantes)))
    print("   DUPLICADOS     : {}".format(len(dups)))
    ajustes = [o for o in ok if o["dist"] > TOL_AJUSTE_M]
    print("   ajuste >{:.2f} m : {}".format(TOL_AJUSTE_M, len(ajustes)))
    if ajustes:
        for o in sorted(ajustes, key=lambda t: -t["dist"])[:8]:
            print("      {}  {:<22} {:.3f} m".format(
                o["elemento_id"], o["bloque"], o["dist"]))
    if faltan:
        print("\n   FALTANTES:")
        agr = {}
        for e in faltan:
            agr[e["bloque"]] = agr.get(e["bloque"], 0) + 1
        for k in sorted(agr):
            print("      {:<24} x{}".format(k, agr[k]))
    if sobrantes:
        print("\n   SOBRANTES (con comentario pero sin objetivo):")
        for f in sobrantes[:12]:
            print("      {}  {:<30} {:<18} ({:.2f},{:.2f},{:.2f})".format(
                f["elemento_id"], f["familia"], f["tipo"], f["x"], f["y"], f["z"]))

    # ---------- D: huerfanos ----------
    print("\nD. HUERFANOS en la zona (sin comentario APT-E-05): {}".format(len(huerfanos)))
    if huerfanos:
        agr = {}
        for f in huerfanos:
            k = (f["familia"], f["tipo"])
            agr[k] = agr.get(k, 0) + 1
        for (fam, tip) in sorted(agr):
            print("      {:<34} {:<22} x{}".format(fam, tip, agr[(fam, tip)]))

    if anclas:
        print("\n   ANCLAS en la zona (no son dispositivos, no se tocan):")
        for f in anclas:
            print("      {}  {:<30} {:<16} z={}".format(
                f["elemento_id"], f["familia"], f["tipo"], f["z"]))

    # ---------- E: familias obsoletas ----------
    en_mapeo = set(_clave(e["familia"]) for e in esperados)
    obsoletas = {}
    for f in huerfanos + encontrados:
        if _clave(f["familia"]) not in en_mapeo:
            k = f["familia"]
            obsoletas[k] = obsoletas.get(k, 0) + 1
    print("\nE. FAMILIAS FUERA DEL MAPEO (restos de corridas anteriores):")
    if obsoletas:
        for k in sorted(obsoletas):
            print("      {:<38} x{}".format(k, obsoletas[k]))
    else:
        print("      (ninguna)")

    # ---------- F: distribucion Z ----------
    print("\nF. DISTRIBUCION DE COTAS Z:")
    cotas = {}
    for f in encontrados + huerfanos:
        k = round(f["z"], 2)
        cotas[k] = cotas.get(k, 0) + 1
    esperadas_z = {}
    for e in esperados:
        k = round(elev_m + e["z_local"], 2)
        esperadas_z[k] = esperadas_z.get(k, 0) + 1
    for k in sorted(set(list(cotas.keys()) + list(esperadas_z.keys()))):
        print("      z={:<7} hay={:<4} esperado={}".format(
            k, cotas.get(k, 0), esperadas_z.get(k, 0)))

    res = {"documento": _safe(doc.Title), "elev_m": round(elev_m, 4),
           "esperados": len(esperados), "encontrados": len(encontrados),
           "ok": len(ok), "faltantes": faltan, "sobrantes": sobrantes,
           "duplicados": dups, "huerfanos": huerfanos, "anclas": anclas,
           "familias_obsoletas": obsoletas,
           "detalle_ok": ok, "ajustes_mayores": ajustes}

    # ---------- G: candidatos de borrado ----------
    # Reglas:
    #   * familia que NO esta en el mapeo  -> sobra (resto de corridas viejas)
    #   * familia esperada y con un esperado cerca -> duplicado
    #   * familia esperada pero lejos de todo esperado -> revisar a mano
    fam_esperadas = set(_clave(e["familia"]) for e in esperados)
    candidatos = []
    revisar = []
    for f in sobrantes:
        kf = _clave(f["familia"])
        if kf not in fam_esperadas:
            f["motivo"] = "familia fuera del mapeo (resto de corridas anteriores)"
            candidatos.append(f)
            continue
        mismo = [e for e in esperados if _clave(e["familia"]) == kf]
        cerca = min([math.hypot(f["x"] - e["x"], f["y"] - e["y"]) for e in mismo] or [99.0])
        if cerca <= 1.50:
            f["motivo"] = "duplicado (esperado de la misma familia a {:.2f} m)".format(cerca)
            candidatos.append(f)
        else:
            f["motivo"] = "sin esperado de la misma familia cerca ({:.2f} m)".format(cerca)
            revisar.append(f)
    for f in huerfanos:
        kf = _clave(f["familia"])
        if kf not in fam_esperadas:
            f["motivo"] = "sin comentario y familia fuera del mapeo"
            candidatos.append(f)
        else:
            f["motivo"] = "sin comentario (puede faltar la marca)"
            revisar.append(f)

    res["candidatos_borrado"] = candidatos
    res["revisar_manualmente"] = revisar

    print("\nG. CANDIDATOS A BORRADO: {}".format(len(candidatos)))
    if candidatos:
        agr = {}
        for f in candidatos:
            k = (f["familia"], f["motivo"])
            agr[k] = agr.get(k, 0) + 1
        for (fam, mot) in sorted(agr):
            print("      {:<34} x{:<3} {}".format(fam, agr[(fam, mot)], mot))
        print("      (revisa la simulacion de F6_LIMPIAR_E05_v01 antes de borrar)")
    else:
        print("      (ninguno)")
    if revisar:
        print("\n   REVISAR MANUALMENTE: {}".format(len(revisar)))
        for f in revisar[:10]:
            print("      {}  {:<30} ({:.2f},{:.2f},{:.2f})  {}".format(
                f["elemento_id"], f["familia"], f["x"], f["y"], f["z"], f["motivo"]))
    _guardar(json_out, res)

    print("\n" + "=" * 74)
    veredicto = "LIMPIO" if (not faltan and not candidatos and not revisar) \
        else "REQUIERE LIMPIEZA"
    print("VEREDICTO: {}".format(veredicto))
    print("Detalle en: " + json_out)
    print("=" * 74)
    return res


if __name__ == "__main__":
    auditar()
