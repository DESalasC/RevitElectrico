# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_v03.py
=====================
Aplica los 49 dispositivos de E 05 usando el mapeo corregido
(config/mapeo_E05_v01.json) sobre las caras reales de sus anfitriones.

Correcciones frente a FACE v02:
  * VALIDACION PREVIA: resuelve familia + simbolo de TODOS los dispositivos
    antes de crear nada. Si alguna pareja no existe, aborta y lista los errores.
    Ya no se cae al "primer simbolo" de la familia (eso hacia que todos los
    interruptores salieran como M_Interruptor -> Ventilador).
  * MAPEO EXTERNO: familia/simbolo/anfitrion salen de config/mapeo_E05_v01.json,
    no del JSON de transferencia (que traia 'Estandar' y anfitriones erroneos).
  * ANFITRION FORZADO: las Bala Stil Led van siempre a cielorraso.
  * SCHEDULE LEVEL: cascada de parametros (SCHEDULE_LEVEL_PARAM ->
    FAMILY_LEVEL_PARAM -> RBS_START_LEVEL_PARAM -> ELEM_REFERENCE_LEVEL_PARAM).
    Se reporta cual funciono.
  * REPORTE CON ElementId por dispositivo, para poder correlacionar con lo que
    se ve en Revit.
  * EXCLUSIONES: los marcadores de conductores (2F2N1T1R, 1FTN, ...) no se
    modelan.

Uso:
    aplicar(doc, confirmar=False)   # simulacion + validacion de mapeo
    aplicar(doc, confirmar=True)    # aplica
"""
import json
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Family,
    FilteredElementCollector,
    GeometryInstance,
    Level,
    Options,
    Solid,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import Structure

FT = 3.280839895
TOL_MURO_M = 2.50
TOL_TECHO_M = 0.80

CATS = [BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
        BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_TelephoneDevices]

# Candidatos de parametro de nivel. Resolucion PEREZOSA: no todos los
# BuiltInParameter existen en todas las versiones de Revit.
CANDIDATOS_NIVEL_NOMBRES = (
    "SCHEDULE_LEVEL_PARAM",
    "FAMILY_LEVEL_PARAM",
    "RBS_START_LEVEL_PARAM",
    "LEVEL_PARAM",
    "INSTANCE_REFERENCE_LEVEL_PARAM",
)


def _bips_nivel():
    out = []
    for nm in CANDIDATOS_NIVEL_NOMBRES:
        try:
            out.append((nm, getattr(BuiltInParameter, nm)))
        except Exception:
            pass
    return out


def _eid_txt(eid):
    try:
        return str(eid)
    except Exception:
        return "?"


def _eid_int(e):
    for a in ("Value", "IntegerValue"):
        try:
            return int(getattr(e, a))
        except Exception:
            pass
    try:
        return int(e)
    except Exception:
        return None


def _safe(v):
    try:
        s = str(v)
    except Exception:
        return "?"
    out = ""
    for c in s:
        try:
            c.encode("ascii")
            out += c
        except Exception:
            out += "_"
    return out


def _clave(t):
    """Clave robusta: solo alfanumericos en minuscula, sin acentos ni simbolos.

    Asi 'Estándar', 'Est_ndar' y 'ESTANDAR' colapsan a 'estandar', y
    '_SONO FLEX 200 trim' colapsa a 'sonoflex200trim'.
    """
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
    out = []
    for c in s:
        if c.isalpha() or c.isdigit():
            out.append(c.lower())
    return "".join(out)


# --------------------------------------------------------------------------
# Resolucion de familias y simbolos
# --------------------------------------------------------------------------

def _mapa_familias(doc):
    """{clave_familia: Family}"""
    out = {}
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            k = _clave(fam.Name)
        except Exception:
            continue
        if k:
            out[k] = fam
    return out


def _mapa_simbolos(doc, fam):
    """{clave_simbolo: FamilySymbol}"""
    out = {}
    try:
        for sid in fam.GetFamilySymbolIds():
            try:
                s = doc.GetElement(sid)
                out[_clave(s.Name)] = s
            except Exception:
                pass
    except Exception:
        pass
    return out


def _resolver(doc, familias, nombre_fam, nombre_sym):
    """Devuelve (symbol, error). Sin fallback al primer simbolo."""
    kf = _clave(nombre_fam)
    fam = familias.get(kf)
    if fam is None:
        # segundo intento: coincidencia parcial unica
        cands = [k for k in familias.keys() if kf and (kf in k or k in kf)]
        if len(cands) == 1:
            fam = familias[cands[0]]
    if fam is None:
        return None, "familia no encontrada: " + str(nombre_fam)
    syms = _mapa_simbolos(doc, fam)
    ks = _clave(nombre_sym)
    sym = syms.get(ks)
    if sym is None:
        cands = [k for k in syms.keys() if ks and (ks in k or k in ks)]
        if len(cands) == 1:
            sym = syms[cands[0]]
    if sym is None:
        return None, "simbolo '{}' no existe en '{}'. Disponibles: {}".format(
            nombre_sym, nombre_fam, sorted(syms.keys()))
    return sym, ""


# --------------------------------------------------------------------------
# Geometria de anfitriones
# --------------------------------------------------------------------------

def _dist_curva(w, x, y):
    try:
        c = w.Location.Curve
        r = c.Project(XYZ(x, y, 0))
        p = r.XYZPoint
        return math.hypot(p.X - x, p.Y - y)
    except Exception:
        return 999.0


def _caras(host, punto, es_techo):
    opts = Options()
    opts.ComputeReferences = True
    salida = []

    def tratar_solid(sol):
        try:
            for f in sol.Faces:
                try:
                    pr = f.Project(punto)
                    if pr is None:
                        continue
                    n = f.ComputeNormal(pr.UVPoint)
                    if es_techo:
                        if n.Z > -0.7:
                            continue
                        if abs(pr.XYZPoint.Z - punto.Z) > TOL_TECHO_M * FT:
                            continue
                    else:
                        if abs(n.Z) > 0.3:
                            continue
                    salida.append((pr.Distance, f, pr.XYZPoint))
                except Exception:
                    pass
        except Exception:
            pass

    try:
        for g in host.get_Geometry(opts):
            if g is None:
                continue
            if isinstance(g, Solid):
                tratar_solid(g)
            elif isinstance(g, GeometryInstance):
                try:
                    for gg in g.GetInstanceGeometry():
                        if isinstance(gg, Solid):
                            tratar_solid(gg)
                except Exception:
                    pass
    except Exception:
        pass
    return salida


def _asignar_nivel(inst, nivel_id):
    """Cascada de parametros de nivel. Devuelve el nombre del que funciono o ''."""
    for nombre, bip in _bips_nivel():
        try:
            p = inst.get_Parameter(bip)
            if p is None or p.IsReadOnly:
                continue
            p.Set(nivel_id)
            return nombre
        except Exception:
            pass
    return ""


def _instancias_e05(doc):
    out = []
    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = p.AsString() if p is not None else ""
                except Exception:
                    c = ""
                if c and "APT-E-05-P5" in c:
                    out.append(inst)
        except Exception:
            pass
    return out


# --------------------------------------------------------------------------
# Principal
# --------------------------------------------------------------------------

def aplicar(doc, confirmar=False,
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_mapeo="config/mapeo_E05_v01.json",
            json_out="data/resultado_E05_v03.json"):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_mapeo):
        json_mapeo = os.path.join(root, json_mapeo)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    data = json.load(open(json_in, "r"))
    mapeo = json.load(open(json_mapeo, "r"))
    mapa_disp = mapeo.get("dispositivos") or {}
    excluir = mapeo.get("excluir") or {}

    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _clave(lv.Name) == _clave(data.get("nivel", "Piso 5")):
            nivel = lv
            break
    if nivel is None:
        print("Nivel no encontrado: " + str(data.get("nivel")))
        return {"ok": False}

    print("=" * 70)
    print("E05 v03  |  doc: " + _safe(doc.Title))
    print("Nivel: {}  elev={:.4f} m".format(_safe(nivel.Name), nivel.Elevation * 0.3048))
    print("=" * 70)

    familias = _mapa_familias(doc)

    # ------------------------------------------------------------------
    # 1. VALIDACION PREVIA DEL MAPEO  (no crea nada)
    # ------------------------------------------------------------------
    dispositivos = []
    errores_mapeo = []
    excluidos = []

    for d in data.get("dispositivos") or []:
        bloque = d.get("nombre_bloque_hijo")
        regla = mapa_disp.get(bloque)
        if regla is None:
            errores_mapeo.append({"bloque": bloque, "motivo": "sin regla en mapeo_E05_v01.json"})
            continue
        if not regla.get("modelar", True):
            excluidos.append(bloque)
            continue
        if regla.get("familia") in excluir:
            excluidos.append(bloque)
            continue

        sym, err = _resolver(doc, familias, regla.get("familia"), regla.get("simbolo"))
        if sym is None:
            errores_mapeo.append({"bloque": bloque, "motivo": err})
            continue

        anf = regla.get("anfitrion")
        if anf:
            es_techo = (anf == "techo" or anf == "ceiling")
        else:
            a_json = (d.get("anfitrion") or "").lower()
            if a_json == "ceiling":
                es_techo = True
            elif a_json in ("muro", "wall"):
                es_techo = False
            else:
                es_techo = float(d["z_local_m"]) >= 2.0

        dispositivos.append({"d": d, "sym": sym, "es_techo": es_techo,
                             "familia": regla.get("familia"),
                             "simbolo": _safe(sym.Name)})

    print("\nVALIDACION DE MAPEO")
    print("  dispositivos en transferencia : {}".format(len(data.get("dispositivos") or [])))
    print("  con familia+simbolo resueltos : {}".format(len(dispositivos)))
    print("  excluidos (marcadores)        : {} {}".format(len(excluidos), sorted(set(excluidos))))
    print("  errores de mapeo              : {}".format(len(errores_mapeo)))
    if errores_mapeo:
        print("\n  DETALLE DE ERRORES (no se creara nada):")
        vistos = {}
        for e in errores_mapeo:
            k = (e["bloque"], e["motivo"])
            vistos[k] = vistos.get(k, 0) + 1
        for (bloque, motivo), cnt in sorted(vistos.items()):
            print("   - {:<24} x{:<3} {}".format(bloque, cnt, motivo))
        try:
            f = open(json_out, "w")
            try:
                json.dump({"ok": False, "fase": "validacion_mapeo",
                           "errores_mapeo": errores_mapeo, "excluidos": excluidos},
                          f, indent=2)
            finally:
                f.close()
        except Exception:
            pass
        print("\nABORTADO: corrige el mapeo y vuelve a ejecutar.")
        return {"ok": False, "errores_mapeo": errores_mapeo}

    # ------------------------------------------------------------------
    # 2. Instancias previas E05
    # ------------------------------------------------------------------
    previas = _instancias_e05(doc)
    res = {"modo": "aplicar" if confirmar else "simulacion",
           "documento": _safe(doc.Title), "nivel": _safe(nivel.Name),
           "dispositivos": len(dispositivos), "eliminados": 0,
           "creados": 0, "con_host": 0, "sin_host": 0,
           "nivel_asignado_por": {}, "por_metodo": {}, "fallos": [],
           "detalle": [], "excluidos": sorted(set(excluidos))}

    print("\nInstancias E05 previas: {}".format(len(previas)))
    if confirmar and previas:
        t = Transaction(doc, "F6 - Limpiar E05 v03")
        t.Start()
        try:
            for inst in previas:
                try:
                    doc.Delete(inst.Id)
                    res["eliminados"] += 1
                except Exception:
                    pass
        finally:
            t.Commit()
        print("Eliminadas: {}".format(res["eliminados"]))

    # ------------------------------------------------------------------
    # 3. Resolucion de cara de anfitrion
    # ------------------------------------------------------------------
    muros = []
    for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType():
        try:
            if _eid_int(w.LevelId) != _eid_int(nivel.Id):
                continue
            muros.append(w)
        except Exception:
            pass
    techos = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType())
    print("Muros en el nivel: {}   Techos: {}".format(len(muros), len(techos)))

    planes = []
    for item in dispositivos:
        d = item["d"]
        x_ft = float(d["x_revit_ft"])
        y_ft = float(d["y_revit_ft"])
        z_ft = nivel.Elevation + float(d["z_local_m"]) * FT
        punto = XYZ(x_ft, y_ft, z_ft)

        elegido = None
        if item["es_techo"]:
            for techo in techos:
                bb = techo.get_BoundingBox(None)
                if bb is None:
                    continue
                if not (bb.Min.X - 0.5 <= x_ft <= bb.Max.X + 0.5 and
                        bb.Min.Y - 0.5 <= y_ft <= bb.Max.Y + 0.5):
                    continue
                for dist, f, pt in _caras(techo, punto, True):
                    if elegido is None or dist < elegido[0]:
                        elegido = (dist, f, pt, techo)
        else:
            for dist_w, w in sorted((_dist_curva(w, x_ft, y_ft), w) for w in muros)[:10]:
                if dist_w > TOL_MURO_M * FT:
                    continue
                for dist, f, pt in _caras(w, punto, False):
                    if elegido is None or dist < elegido[0]:
                        elegido = (dist, f, pt, w)

        if elegido is None:
            res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                  "anfitrion": "techo" if item["es_techo"] else "muro",
                                  "motivo": "sin cara de anfitrion",
                                  "x_m": round(x_ft * 0.3048, 3),
                                  "y_m": round(y_ft * 0.3048, 3),
                                  "z_m": round(z_ft * 0.3048, 3)})
            continue
        item["cara"] = elegido[1]
        item["punto"] = elegido[2]
        item["host"] = elegido[3]
        item["dir"] = XYZ(1, 0, 0) if item["es_techo"] else XYZ(0, 0, 1)
        planes.append(item)

    print("Con cara de anfitrion: {} / {}   sin cara: {}".format(
        len(planes), len(dispositivos), len(dispositivos) - len(planes)))

    if not confirmar:
        print("\nSIMULACION: valida el mapeo y las caras. No se ha creado nada.")
        print("Ejecuta con confirmar=True para aplicar.")
        return res

    # ------------------------------------------------------------------
    # 4. Creacion
    # ------------------------------------------------------------------
    t = Transaction(doc, "F6 - Crear E05 v03")
    t.Start()
    try:
        for item in planes:
            d = item["d"]
            sym = item["sym"]
            try:
                if not sym.IsActive:
                    try:
                        sym.Activate()
                        doc.Regenerate()
                    except Exception:
                        pass

                inst = None
                metodo = ""
                err = ""
                try:
                    inst = doc.Create.NewFamilyInstance(item["cara"], item["punto"], item["dir"], sym)
                    metodo = "Face"
                except Exception as ex1:
                    err = _safe(ex1)
                if inst is None:
                    try:
                        inst = doc.Create.NewFamilyInstance(item["punto"], sym, item["host"],
                                                           Structure.StructuralType.NonStructural)
                        metodo = "HostElem"
                    except Exception as ex2:
                        err = err + " | " + _safe(ex2)
                if inst is None:
                    try:
                        inst = doc.Create.NewFamilyInstance(item["punto"], sym, nivel,
                                                           Structure.StructuralType.NonStructural)
                        metodo = "Nivel"
                    except Exception as ex3:
                        err = err + " | " + _safe(ex3)
                if inst is None:
                    res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                          "motivo": err})
                    continue

                try:
                    cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cp is not None and not cp.IsReadOnly:
                        cp.Set("APT-E-05-P5")
                except Exception:
                    pass

                nivel_con = _asignar_nivel(inst, nivel.Id)
                if nivel_con:
                    res["nivel_asignado_por"][nivel_con] = \
                        res["nivel_asignado_por"].get(nivel_con, 0) + 1

                con_host = False
                try:
                    con_host = inst.Host is not None
                except Exception:
                    con_host = False
                if con_host:
                    res["con_host"] += 1
                else:
                    res["sin_host"] += 1

                res["por_metodo"][metodo] = res["por_metodo"].get(metodo, 0) + 1
                res["creados"] += 1

                hname = ""
                try:
                    if inst.Host is not None:
                        hname = _safe(inst.Host.Name)
                except Exception:
                    pass
                res["detalle"].append({
                    "elemento_id": _eid_txt(inst.Id),
                    "bloque": d.get("nombre_bloque_hijo"),
                    "familia": item["familia"],
                    "simbolo": item["simbolo"],
                    "anfitrion": "techo" if item["es_techo"] else "muro",
                    "host": hname,
                    "metodo": metodo,
                    "nivel_param": nivel_con,
                    "x_m": round(float(d["x_revit_ft"]) * 0.3048, 3),
                    "y_m": round(float(d["y_revit_ft"]) * 0.3048, 3),
                    "z_m": round(float(d["z_local_m"]) + nivel.Elevation * 0.3048, 3),
                })
            except Exception as ex:
                res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                      "motivo": _safe(ex)})
    finally:
        t.Commit()

    try:
        f = open(json_out, "w")
        try:
            json.dump(res, f, indent=2)
        finally:
            f.close()
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("RESULTADO: creados={} con_host={} sin_host={} fallos={}".format(
        res["creados"], res["con_host"], res["sin_host"], len(res["fallos"])))
    print("Metodos        : " + str(res["por_metodo"]))
    print("Nivel asignado : " + str(res["nivel_asignado_por"]))
    if res["fallos"]:
        print("\nFALLOS:")
        for fl in res["fallos"][:20]:
            print("  - {}: {}".format(fl.get("bloque"), fl.get("motivo")))
    print("Detalle por dispositivo en: " + json_out)
    print("=" * 70)
    return res


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    aplicar(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
