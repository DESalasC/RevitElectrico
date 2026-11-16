# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_v18.py
=====================
Aplica los dispositivos del Apartamento Tipo E 05 sobre las caras reales de sus
anfitriones.

CUARTO INTENTO PARA CIELORRASO (v18)
------------------------------------
  En v17 las 8 lamparas volvieron a fallar con "sin cara de anfitrion" aunque el
  diagnostico mostraba 43 techos cubriendo el punto y cotas que incluian 15.84 m
  (la del Piso 5). El codigo de techo era identico a v16, donde si funcionaba.

  La causa mas probable es que la normal de la cara inferior del cielorraso
  venga invertida y el filtro n.Z <= -0.7 la descartara. Por eso se añade un
  cuarto intento que busca caras horizontales a la MISMA cota objetivo
  (z_ft +- 0.30 m) sin exigir el sentido de la normal.

  Orden completo para anfitrion techo:
    1) cara hacia abajo, tolerancia 0.80 m
    2) cara hacia abajo, tolerancia 1.80 m
    3) cara hacia abajo, entre 1.90 y 3.40 m sobre el nivel
    4) cara horizontal a la cota objetivo, sin exigir sentido de la normal

Uso
---
    exec(open(r"...\\F6_APLICAR_E05_v18.py").read())

    aplicar(confirmar=False)   # valida. NO borra, NO crea
    aplicar(confirmar=True)    # aplica
"""
import io
import json
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Family,
    FilteredElementCollector,
    GeometryInstance,
    HostObjectUtils,
    Level,
    Options,
    ShellLayerType,
    Solid,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import Structure

FT = 3.280839895
TOL_MURO_M = 2.50
TOL_TECHO_M = 0.80
ALTURA_CIELORRASO_M = 2.60

CATS = [BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
        BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_TelephoneDevices]

CANDIDATOS_NIVEL_NOMBRES = (
    "SCHEDULE_LEVEL_PARAM",
    "FAMILY_LEVEL_PARAM",
    "RBS_START_LEVEL_PARAM",
    "LEVEL_PARAM",
    "INSTANCE_REFERENCE_LEVEL_PARAM",
)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

_ERRORES_CARAS = []


def _registrar_error_cara(host, ex):
    """Guarda el error de geometria para que no falle en silencio."""
    if len(_ERRORES_CARAS) >= 8:
        return
    try:
        nm = _safe(host.Name)
    except Exception:
        nm = "?"
    _ERRORES_CARAS.append("{}: {}".format(nm, _safe(ex)))


# Nombres candidatos del metodo de geometria, en orden de preferencia.
# El correcto en el API de Revit es 'get_Geometry' (g minuscula). Se prueban
# todos para no depender de recordarlo: v09 uso 'get_geometry' y v10/v11
# usaron 'GetGeometry', y ninguno existe.
_METODOS_GEOMETRIA = ("get_Geometry", "GetGeometry", "get_geometry")


_GEOMETRIA_OK = []


def _geometria(host):
    """Devuelve la geometria del host probando los nombres del metodo."""
    errores = []
    for nombre in _METODOS_GEOMETRIA:
        try:
            fn = getattr(host, nombre)
        except Exception:
            continue
        if not callable(fn):
            continue
        try:
            opts = Options()
            opts.ComputeReferences = True
            geo = fn(opts)
        except Exception as ex:
            errores.append("{}: {}".format(nombre, _safe(ex)))
            continue
        if not _GEOMETRIA_OK:
            _GEOMETRIA_OK.append(nombre)
        return geo
    if errores:
        try:
            nm = _safe(host.Name)
        except Exception:
            nm = "?"
        _ERRORES_CARAS.append("{}: {}".format(nm, " | ".join(errores)))
    else:
        _registrar_error_cara(host, Exception("ningun metodo de geometria disponible"))
    return None


def _resolver_doc(doc):
    if doc is not None:
        return doc
    try:
        uidoc = __revit__.ActiveUIDocument  # noqa: F821
        return uidoc.Document if uidoc is not None else None
    except Exception:
        return None


def _bips_nivel():
    out = []
    for nm in CANDIDATOS_NIVEL_NOMBRES:
        try:
            out.append((nm, getattr(BuiltInParameter, nm)))
        except Exception:
            pass
    return out


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


# --------------------------------------------------------------------------
# Familias y tipos
# --------------------------------------------------------------------------

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
        v = e.Name
        if v:
            return v
    except Exception:
        pass
    return ""


def _placement(fam):
    try:
        return _safe(fam.FamilyPlacementType)
    except Exception:
        return "?"


def _mapa_familias(doc):
    out = {}
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            k = _clave(fam.Name)
        except Exception:
            continue
        if not k:
            continue
        out[k] = {"family": fam, "id": _eid_txt(fam.Id),
                  "name": _safe(fam.Name), "placement": _placement(fam)}
    return out


def _tipos_por_familia(doc):
    """{clave_familia: {clave_tipo: symbol}} recorriendo WhereElementIsElementType."""
    out = {}
    total = 0
    try:
        tipos = FilteredElementCollector(doc).WhereElementIsElementType().ToElements()
    except Exception:
        tipos = []
    for e in tipos:
        total += 1
        try:
            fam = e.Family
        except Exception:
            continue
        if fam is None:
            continue
        kf = _clave(fam.Name)
        ks = _clave(_nombre_tipo(e))
        if kf and ks:
            out.setdefault(kf, {})[ks] = e
    return out, total


def _resolver(familias, tipos, nombre_fam, nombre_sym):
    kf = _clave(nombre_fam)
    entrada = familias.get(kf)
    if entrada is None:
        cands = [k for k in familias.keys() if kf and (kf in k or k in kf)]
        if len(cands) == 1:
            entrada = familias[cands[0]]
            kf = cands[0]
    if entrada is None:
        # Sugerir familias parecidas para diagnosticar rapido
        pistas = []
        try:
            piezas = [p for p in ["interruptor", "toma", "pulsador", "timbre",
                                  "ventilador", "sono", "combo"] if p in kf]
            for k, v in familias.items():
                if any(p in k for p in piezas):
                    pistas.append(v["name"])
        except Exception:
            pass
        msg = "familia no encontrada en el documento: " + str(nombre_fam)
        if pistas:
            msg = msg + ". Familias parecidas cargadas: " + str(sorted(pistas)[:12])
        return None, msg

    syms = tipos.get(kf) or {}
    if not syms:
        return None, "la familia '{}' no tiene tipos cargados".format(entrada["name"])

    ks = _clave(nombre_sym)
    sym = syms.get(ks)
    if sym is None:
        cands = [k for k in syms.keys() if ks and (ks in k or k in ks)]
        if len(cands) == 1:
            sym = syms[cands[0]]
    if sym is None:
        return None, "simbolo '{}' no existe en '{}'. Disponibles: {}".format(
            nombre_sym, entrada["name"], sorted(syms.keys()))
    return sym, ""


# --------------------------------------------------------------------------
# Geometria
# --------------------------------------------------------------------------

def _dist_curva(w, x, y):
    try:
        c = w.Location.Curve
        r = c.Project(XYZ(x, y, 0))
        p = r.XYZPoint
        return math.hypot(p.X - x, p.Y - y)
    except Exception:
        return 999.0


def _caras_laterales(wall, punto):
    """Caras laterales (paramentos) del muro: excluye remates de extremos."""
    salida = []
    refs = []
    for lado in (ShellLayerType.Exterior, ShellLayerType.Interior):
        try:
            refs.extend(list(HostObjectUtils.GetSideFaces(wall, lado)))
        except Exception:
            pass
    for r in refs:
        try:
            f = wall.GetGeometryObjectFromReference(r)
        except Exception:
            continue
        if f is None:
            continue
        try:
            pr = f.Project(punto)
            if pr is None:
                continue
            n = f.ComputeNormal(pr.UVPoint)
            if abs(n.Z) > 0.3:
                continue
            salida.append((pr.Distance, f, pr.XYZPoint))
        except Exception:
            pass
    return salida


def _caras(host, punto, es_techo, tol_m=None):
    tol = (TOL_TECHO_M if tol_m is None else tol_m) * FT
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
                        if abs(pr.XYZPoint.Z - punto.Z) > tol:
                            continue
                    else:
                        if abs(n.Z) > 0.3:
                            continue
                    salida.append((pr.Distance, f, pr.XYZPoint))
                except Exception:
                    pass
        except Exception:
            pass

    geo = _geometria(host)
    if geo is None:
        return salida

    try:
        for g in geo:
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
    except Exception as ex:
        _registrar_error_cara(host, ex)
    return salida


def _caras_rango(host, punto, z_lo_ft, z_hi_ft, exigir_abajo=True):
    """Caras horizontales cuya cota cae dentro de [z_lo_ft, z_hi_ft].

    exigir_abajo=True  -> solo caras con normal hacia abajo (n.Z <= -0.7)
    exigir_abajo=False -> cualquier cara horizontal (|n.Z| >= 0.7), sin importar
                          el sentido. Sirve cuando la normal del cielorraso
                          viene invertida y se rechazaba una cara valida.
    """
    salida = []
    geo = _geometria(host)
    if geo is None:
        return salida

    def tratar_solid(sol):
        try:
            for f in sol.Faces:
                try:
                    pr = f.Project(punto)
                    if pr is None:
                        continue
                    n = f.ComputeNormal(pr.UVPoint)
                    if exigir_abajo:
                        if n.Z > -0.7:
                            continue
                    else:
                        if abs(n.Z) < 0.7:
                            continue
                    if not (z_lo_ft <= pr.XYZPoint.Z <= z_hi_ft):
                        continue
                    salida.append((pr.Distance, f, pr.XYZPoint))
                except Exception:
                    pass
        except Exception:
            pass

    try:
        for g in geo:
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


def _z_objetivo_m(d, es_techo, z_mapa=None):
    """Altura local de montaje en metros.

    Prioridad:
      1) z_local_m del MAPEO (regla por bloque), si existe.
      2) z_local_m del JSON.
      3) lampara forzada a techo con altura de muro -> altura de cielorraso.
    Devuelve (z_m, ajustado) donde ajustado indica que se cambio respecto al JSON.
    """
    try:
        z_json = float(d.get("z_local_m"))
    except Exception:
        z_json = None

    if z_mapa is not None:
        try:
            z = float(z_mapa)
            return z, (z_json is None or abs(z - z_json) > 1e-6)
        except Exception:
            pass

    if z_json is None:
        return (ALTURA_CIELORRASO_M if es_techo else 0.30), True
    if es_techo and z_json < 2.0:
        return ALTURA_CIELORRASO_M, True
    return z_json, False


def _instancias_e05(doc, fam_ids=None):
    """Instancias de E 05 ya colocadas.

    Si se pasan fam_ids, se recorre el documento completo y se filtra por Id de
    familia: asi se detectan familias que no estan en CATS (por ejemplo
    Keypad-Lutron-Homeworks_Sunnata). Sin fam_ids se usa el recorrido por
    categorias electricas.
    """
    if fam_ids:
        out = []
        try:
            for inst in FilteredElementCollector(doc).WhereElementIsNotElementType():
                try:
                    cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = cp.AsString() if cp is not None else ""
                except Exception:
                    c = ""
                if not (c and "APT-E-05-P5" in c):
                    continue
                try:
                    if _eid_txt(inst.Symbol.Family.Id) in fam_ids:
                        out.append(inst)
                except Exception:
                    pass
            return out
        except Exception:
            pass

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


def _referencia_nivel(doc, familia_nombre):
    """Instancia de referencia (F 01/F 02) de la misma familia, con sus params de nivel."""
    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    if _safe(inst.Symbol.Family.Name) != familia_nombre:
                        continue
                    p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = p.AsString() if p is not None else ""
                except Exception:
                    continue
                if c and "APT-E-05" in c:
                    continue
                filas = []
                for nm, bip in _bips_nivel():
                    try:
                        pr = inst.get_Parameter(bip)
                    except Exception:
                        pr = None
                    if pr is None:
                        continue
                    try:
                        v = pr.AsValueString()
                    except Exception:
                        v = None
                    try:
                        esc = not pr.IsReadOnly
                    except Exception:
                        esc = None
                    filas.append({"nombre": nm, "escribible": esc,
                                  "valor": _safe(v) if v is not None else None})
                hname = ""
                try:
                    if inst.Host is not None:
                        hname = _safe(inst.Host.Name)
                except Exception:
                    pass
                return {"elemento_id": _eid_txt(inst.Id), "familia": familia_nombre,
                        "host": hname, "nivel": filas}
        except Exception:
            pass
    return None


# --------------------------------------------------------------------------
# Unidades
# --------------------------------------------------------------------------

def _revisar_unidades_elevacion(data, nivel):
    viva = nivel.Elevation * 0.3048
    decl = data.get("elevacion_nivel_m")
    if decl is None:
        return viva, ""
    try:
        decl = float(decl)
    except Exception:
        return viva, ""
    if abs(decl - viva) <= 0.05:
        return viva, ""
    if abs(decl * 0.3048 - viva) <= 0.05:
        return viva, ("AVISO UNIDADES: 'elevacion_nivel_m'={} esta en PIES, no en metros "
                      "({} ft = {:.4f} m). Se usa la elevacion viva: {:.4f} m.").format(
                          decl, decl, decl * 0.3048, viva)
    return viva, ("AVISO: 'elevacion_nivel_m'={} no coincide con la viva {:.4f} m "
                  "(ni metros ni pies). Se usa la viva.").format(decl, viva)


def _revisar_unidades_z_local(dispositivos):
    raros = []
    for d in dispositivos:
        try:
            z = float(d.get("z_local_m"))
        except Exception:
            continue
        if z > 6.0:
            raros.append((d.get("nombre_bloque_hijo"), z))
    return raros


# --------------------------------------------------------------------------
# Medicion final (despues del commit)
# --------------------------------------------------------------------------

def _fam_ids_en_uso(familias, dispositivos):
    """Ids de las familias usadas por los dispositivos a modelar."""
    out = set()
    for item in dispositivos:
        try:
            e = familias.get(_clave(item["familia"]))
            if e is not None:
                out.add(e["id"])
        except Exception:
            pass
    return out


def _medir(inst):
    """(host_nombre, level_id, schedule_level) en el estado ya confirmado."""
    hname = ""
    try:
        if inst.Host is not None:
            hname = _safe(inst.Host.Name)
    except Exception:
        pass
    lvl = "?"
    try:
        lvl = _eid_txt(inst.LevelId)
    except Exception:
        pass
    sched = ""
    try:
        sp = inst.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM)
        if sp is not None:
            sched = _safe(sp.AsValueString())
    except Exception:
        pass
    return hname, lvl, sched


# --------------------------------------------------------------------------
# Principal
# --------------------------------------------------------------------------

def aplicar(doc=None, confirmar=False, metodo="face",
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_mapeo="config/mapeo_E05_v01.json",
            json_out="data/resultado_E05_v18.json"):
    doc = _resolver_doc(doc)
    if doc is None:
        print("No hay documento activo. Abre un .rvt en Revit y vuelve a ejecutar.")
        return {"ok": False}

    metodo = (metodo or "face").lower()
    if metodo not in ("face", "hostnivel"):
        print("Metodo desconocido '{}': usa 'face' o 'hostnivel'.".format(metodo))
        return {"ok": False}

    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_mapeo):
        json_mapeo = os.path.join(root, json_mapeo)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    data = _leer_json(json_in)
    mapeo = _leer_json(json_mapeo)
    mapa_disp = mapeo.get("dispositivos") or {}
    excluir = mapeo.get("excluir") or {}
    excluir_capa = mapeo.get("excluir_por_bloque_y_capa") or {}

    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _clave(lv.Name) == _clave(data.get("nivel", "Piso 5")):
            nivel = lv
            break
    if nivel is None:
        print("Nivel no encontrado: " + str(data.get("nivel")))
        return {"ok": False}

    elevacion_m, aviso_unidades = _revisar_unidades_elevacion(data, nivel)
    sospechosos = _revisar_unidades_z_local(data.get("dispositivos") or [])

    print("=" * 72)
    print("E05 v18  |  doc: " + _safe(doc.Title))
    print("Nivel: {}  elev={:.4f} m   metodo={}".format(
        _safe(nivel.Name), elevacion_m, metodo))
    print("=" * 72)
    if aviso_unidades:
        print(aviso_unidades)
    if sospechosos:
        print("AVISO: z_local_m implausible (>6 m): {}".format(sospechosos[:5]))

    familias = _mapa_familias(doc)
    tipos, n_tipos = _tipos_por_familia(doc)
    print("Inventario: {} familias, {} tipos, {} familias con tipos".format(
        len(familias), n_tipos, len(tipos)))

    # ---------------- 1. Validacion previa ----------------
    dispositivos = []
    errores = []
    excluidos = []

    for d in data.get("dispositivos") or []:
        bloque = d.get("nombre_bloque_hijo")
        if bloque in excluir:
            excluidos.append(bloque)
            continue
        capa = d.get("capa") or ""
        capas_bloqueadas = excluir_capa.get(bloque) or []
        if capa in capas_bloqueadas:
            excluidos.append("{} [{}]".format(bloque, capa))
            continue
        regla = mapa_disp.get(bloque)
        if regla is None:
            errores.append({"bloque": bloque, "motivo": "sin regla en el mapeo"})
            continue
        if not regla.get("modelar", True):
            excluidos.append(bloque)
            continue
        sym, err = _resolver(familias, tipos, regla.get("familia"), regla.get("simbolo"))
        if sym is None:
            errores.append({"bloque": bloque, "motivo": err})
            continue
        anf = regla.get("anfitrion")
        if anf:
            es_techo = (anf in ("techo", "ceiling"))
        else:
            a_json = (d.get("anfitrion") or "").lower()
            if a_json == "ceiling":
                es_techo = True
            elif a_json in ("muro", "wall"):
                es_techo = False
            else:
                es_techo = float(d["z_local_m"]) >= 2.0
        entry = familias.get(_clave(regla.get("familia")))
        dispositivos.append({"d": d, "sym": sym, "es_techo": es_techo,
                             "familia": _safe(regla.get("familia")),
                             "simbolo": _safe(_nombre_tipo(sym)),
                             "z_mapa": regla.get("z_local_m"),
                             "placement": entry["placement"] if entry else "?"})

    print("\nVALIDACION: {} de {} resueltos, {} excluidos, {} errores".format(
        len(dispositivos), len(data.get("dispositivos") or []),
        len(excluidos), len(errores)))
    if errores:
        vistos = {}
        for e in errores:
            vistos[(e["bloque"], e["motivo"])] = vistos.get((e["bloque"], e["motivo"]), 0) + 1
        for (b, m), c in sorted(vistos.items()):
            print("   - {:<24} x{:<3} {}".format(b, c, m))
        _guardar(json_out, {"ok": False, "fase": "validacion_mapeo", "errores": errores})
        print("\nABORTADO.")
        return {"ok": False, "errores_mapeo": errores}

    # ---------------- 2. Previas ----------------
    previas = _instancias_e05(doc, _fam_ids_en_uso(familias, dispositivos))
    res = {"modo": "aplicar" if confirmar else "simulacion", "metodo": metodo,
           "documento": _safe(doc.Title), "nivel": _safe(nivel.Name),
           "nivel_elev_m": round(elevacion_m, 4),
           "aviso_unidades": aviso_unidades,
           "dispositivos": len(dispositivos), "eliminados": 0, "creados": 0,
           "con_host": 0, "sin_host": 0, "con_nivel_valido": 0,
           "schedule_con_valor": 0, "schedule_vacio": 0,
           "por_metodo": {}, "por_placement": {},
           "desplazamiento": {"max_m": 0.0, "grandes": []},
           "fallos": [], "detalle": [], "excluidos": sorted(set(excluidos))}

    print("Instancias E05 previas: {} (no se borra nada hasta validar las caras)".format(
        len(previas)))

    # ---------------- 3. Anfitriones ----------------
    muros = []
    for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType():
        try:
            if _eid_int(w.LevelId) != _eid_int(nivel.Id):
                continue
            bb = w.get_BoundingBox(None)
            if bb is None:
                continue
            muros.append((w, bb.Min.Z, bb.Max.Z))
        except Exception:
            pass
    techos = list(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType())
    print("Muros en el nivel: {}   Techos: {}".format(len(muros), len(techos)))

    planes = []
    ajustes_z = []
    for item in dispositivos:
        d = item["d"]
        x_ft = float(d["x_revit_ft"])
        y_ft = float(d["y_revit_ft"])
        z_m, ajustado = _z_objetivo_m(d, item["es_techo"], item.get("z_mapa"))
        if ajustado:
            ajustes_z.append({"bloque": d.get("nombre_bloque_hijo"),
                              "z_json_m": float(d["z_local_m"]), "z_usada_m": z_m})
        z_ft = nivel.Elevation + z_m * FT
        punto = XYZ(x_ft, y_ft, z_ft)
        item["z_m"] = z_m

        elegido = None
        cubren = []
        if item["es_techo"]:
            for techo in techos:
                bb = techo.get_BoundingBox(None)
                if bb is None:
                    continue
                if not (bb.Min.X - 0.5 <= x_ft <= bb.Max.X + 0.5 and
                        bb.Min.Y - 0.5 <= y_ft <= bb.Max.Y + 0.5):
                    continue
                cubren.append((techo, bb))
            for tol in (TOL_TECHO_M, 1.80):
                for techo, bb in cubren:
                    for dist, f, pt in _caras(techo, punto, True, tol):
                        if elegido is None or dist < elegido[0]:
                            elegido = (dist, f, pt, techo)
                if elegido is not None:
                    break
            if elegido is None:
                # tercer intento: cualquier cara hacia abajo en el rango real
                # de un falso techo (1.90 a 3.40 m sobre el nivel)
                z_lo = nivel.Elevation + 1.90 * FT
                z_hi = nivel.Elevation + 3.40 * FT
                for techo, bb in cubren:
                    for dist, f, pt in _caras_rango(techo, punto, z_lo, z_hi):
                        if elegido is None or dist < elegido[0]:
                            elegido = (dist, f, pt, techo)
            if elegido is None:
                # cuarto intento: la MISMA cota, sin exigir normal hacia abajo
                # (hay cielorrasos cuya normal viene invertida)
                z_lo = z_ft - 0.30 * FT
                z_hi = z_ft + 0.30 * FT
                for techo, bb in cubren:
                    for dist, f, pt in _caras_rango(techo, punto, z_lo, z_hi, False):
                        if elegido is None or dist < elegido[0]:
                            elegido = (dist, f, pt, techo)
        else:
            # solo muros cuya extension vertical cubre la cota del dispositivo
            cand = []
            for (w, zmin, zmax) in muros:
                if zmin - 0.10 <= z_ft <= zmax + 0.10:
                    cand.append((_dist_curva(w, x_ft, y_ft), w))
            for dist_w, w in sorted(cand)[:10]:
                if dist_w > TOL_MURO_M * FT:
                    continue
                # 1) solo paramentos laterales (sin remates)
                for dist, f, pt in _caras_laterales(w, punto):
                    if elegido is None or dist < elegido[0]:
                        elegido = (dist, f, pt, w)
                # 2) respaldo: cualquier cara vertical del muro
                if elegido is None:
                    for dist, f, pt in _caras(w, punto, False):
                        if elegido is None or dist < elegido[0]:
                            elegido = (dist, f, pt, w)

        if elegido is None:
            fallo = {"bloque": d.get("nombre_bloque_hijo"),
                     "anfitrion": "techo" if item["es_techo"] else "muro",
                     "motivo": "sin cara de anfitrion",
                     "z_objetivo_m": round(z_ft * 0.3048, 3)}
            if item["es_techo"]:
                fallo["techos_que_cubren"] = len(cubren)
                fallo["cotas_techos_m"] = sorted(
                    set(round(bb.Max.Z * 0.3048, 2) for _, bb in cubren))[:6]
            res["fallos"].append(fallo)
            continue
        item["cara"] = elegido[1]
        item["punto"] = elegido[2]
        item["host"] = elegido[3]
        item["dir"] = XYZ(1, 0, 0) if item["es_techo"] else XYZ(0, 0, 1)
        try:
            item["desplazamiento_m"] = round(
                math.hypot(elegido[2].X - x_ft, elegido[2].Y - y_ft) * 0.3048, 3)
        except Exception:
            item["desplazamiento_m"] = None
        planes.append(item)

    print("Con cara de anfitrion: {} / {}   sin cara: {}".format(
        len(planes), len(dispositivos), len(dispositivos) - len(planes)))
    if _GEOMETRIA_OK:
        print("Metodo de geometria confirmado: {}()".format(_GEOMETRIA_OK[0]))
    res["metodo_geometria"] = _GEOMETRIA_OK[0] if _GEOMETRIA_OK else ""
    if _ERRORES_CARAS:
        print("ERRORES AL LEER GEOMETRIA ({}):".format(len(_ERRORES_CARAS)))
        for e in _ERRORES_CARAS:
            print("   - " + e)
    if ajustes_z:
        grupos = {}
        for a in ajustes_z:
            grupos[a["bloque"]] = "{:.2f} -> {:.2f} m".format(
                a["z_json_m"], a["z_usada_m"])
        print("Altura ajustada en {} dispositivos: {}".format(
            len(ajustes_z), grupos))
    res["ajustes_z"] = ajustes_z

    fallos_techo = [f for f in res["fallos"] if f.get("anfitrion") == "techo"]
    if fallos_techo:
        print("\nDETALLE DE FALLOS EN TECHO:")
        for f in fallos_techo[:10]:
            print("   {:<22} z_obj={} techos_que_cubren={} cotas={}".format(
                f.get("bloque"), f.get("z_objetivo_m"),
                f.get("techos_que_cubren"), f.get("cotas_techos_m")))

    if not planes:
        print("\nABORTADO: no se encontro ninguna cara de anfitrion.")
        print("NO se ha borrado ninguna instancia existente.")
        _guardar(json_out, res)
        return res

    if not confirmar:
        print("\nSIMULACION: {} dispositivos con cara de anfitrion.".format(len(planes)))
        print("Se borrarian {} instancias previas y se crearian {}.".format(
            len(previas), len(planes)))
        print("Nada se ha modificado. Ejecuta aplicar(confirmar=True) para aplicar.")
        _guardar(json_out, res)
        return res

    # ---------------- 4. Borrado de previas (solo con caras validadas) ----------------
    if previas:
        print("\nBorrando {} instancias previas...".format(len(previas)))
        t = Transaction(doc, "F6 - Limpiar E05 v18")
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

    # ---------------- 5. Creacion ----------------
    creadas = []
    t = Transaction(doc, "F6 - Crear E05 v18 ({})".format(metodo))
    t.Start()
    try:
        for item in planes:
            d = item["d"]
            try:
                sym = item["sym"]
                try:
                    if not sym.IsActive:
                        sym.Activate()
                        doc.Regenerate()
                except Exception:
                    pass

                intentos = []
                if metodo == "face":
                    intentos = ["Face", "HostNivel", "HostElem", "Nivel"]
                else:
                    intentos = ["HostNivel", "Face", "HostElem", "Nivel"]

                inst = None
                usado = ""
                err = ""
                for nombre in intentos:
                    if inst is not None:
                        break
                    try:
                        if nombre == "Face":
                            inst = doc.Create.NewFamilyInstance(item["cara"], item["punto"],
                                                               item["dir"], sym)
                        elif nombre == "HostNivel":
                            if item["host"] is None:
                                continue
                            inst = doc.Create.NewFamilyInstance(item["punto"], sym, item["host"],
                                                               nivel,
                                                               Structure.StructuralType.NonStructural)
                        elif nombre == "HostElem":
                            if item["host"] is None:
                                continue
                            inst = doc.Create.NewFamilyInstance(item["punto"], sym, item["host"],
                                                               Structure.StructuralType.NonStructural)
                        else:
                            inst = doc.Create.NewFamilyInstance(item["punto"], sym, nivel,
                                                               Structure.StructuralType.NonStructural)
                        if inst is not None:
                            usado = nombre
                    except Exception as ex:
                        err = err + " | " + nombre + ": " + _safe(ex)
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

                res["por_metodo"][usado] = res["por_metodo"].get(usado, 0) + 1
                res["por_placement"][item["placement"]] = \
                    res["por_placement"].get(item["placement"], 0) + 1
                res["creados"] += 1
                creadas.append(inst)
                res["detalle"].append({
                    "elemento_id": _eid_txt(inst.Id),
                    "bloque": d.get("nombre_bloque_hijo"),
                    "familia": item["familia"],
                    "simbolo": item["simbolo"],
                    "placement_type": item["placement"],
                    "anfitrion": "techo" if item["es_techo"] else "muro",
                    "metodo": usado,
                    "x_m": round(float(d["x_revit_ft"]) * 0.3048, 3),
                    "y_m": round(float(d["y_revit_ft"]) * 0.3048, 3),
                    "z_m": round(item["punto"].Z * 0.3048, 3),
                    "z_objetivo_m": round(item["z_m"] + elevacion_m, 3),
                    "desplazamiento_m": item.get("desplazamiento_m"),
                })
            except Exception as ex:
                res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                      "motivo": _safe(ex)})
    finally:
        t.Commit()

    # ---------------- 5. Medicion final ----------------
    try:
        doc.Regenerate()
    except Exception:
        pass

    for inst, fila in zip(creadas, res["detalle"]):
        try:
            hname, lvl, sched = _medir(inst)
        except Exception:
            hname, lvl, sched = "", "?", ""
        fila["host"] = hname
        fila["level_id"] = lvl
        fila["schedule_level"] = sched
        if hname:
            res["con_host"] += 1
        else:
            res["sin_host"] += 1
        if lvl not in ("?", "None", "-1"):
            res["con_nivel_valido"] += 1
        if sched:
            res["schedule_con_valor"] += 1
        else:
            res["schedule_vacio"] += 1

    # ---------------- 6. Referencia F 01 / F 02 ----------------
    for f in res["detalle"]:
        dsp = f.get("desplazamiento_m")
        if dsp is None:
            continue
        if dsp > res["desplazamiento"]["max_m"]:
            res["desplazamiento"]["max_m"] = dsp
        if dsp > 0.35:
            res["desplazamiento"]["grandes"].append(
                {"elemento_id": f.get("elemento_id"), "bloque": f.get("bloque"),
                 "familia": f.get("familia"), "desplazamiento_m": dsp})
    refs = {}
    for item in planes:
        fam = item["familia"]
        if fam in refs:
            continue
        try:
            refs[fam] = _referencia_nivel(doc, fam)
        except Exception:
            refs[fam] = None
    res["referencia_nivel"] = refs

    _guardar(json_out, res)

    print("\n" + "=" * 72)
    print("RESULTADO (medido despues del commit)")
    print("  creados        : {}   fallos: {}".format(res["creados"], len(res["fallos"])))
    print("  con_host       : {}   sin_host: {}".format(res["con_host"], res["sin_host"]))
    print("  nivel valido   : {}".format(res["con_nivel_valido"]))
    print("  schedule valor : {}   vacio: {}".format(
        res["schedule_con_valor"], res["schedule_vacio"]))
    print("  metodos        : " + str(res["por_metodo"]))
    print("  placement      : " + str(res["por_placement"]))
    print("  desplaz. max   : {:.3f} m".format(res["desplazamiento"]["max_m"]))
    if res["desplazamiento"]["grandes"]:
        print("  ajustes >0.35 m ({}):".format(len(res["desplazamiento"]["grandes"])))
        for g in res["desplazamiento"]["grandes"]:
            print("     {}  {:<22} {}  {:.3f} m".format(
                g["elemento_id"], g["bloque"], g["familia"], g["desplazamiento_m"]))

    por_fam = {}
    for f in res["detalle"]:
        k = f.get("familia", "?")
        d2 = por_fam.setdefault(k, {"n": 0, "host": 0, "sched": 0})
        d2["n"] += 1
        if f.get("host"):
            d2["host"] += 1
        if f.get("schedule_level"):
            d2["sched"] += 1
    print("\n  {:<32} {:>4} {:>7} {:>8}".format("Familia", "n", "host", "sched"))
    for k in sorted(por_fam):
        d2 = por_fam[k]
        print("  {:<32} {:>4} {:>7} {:>8}".format(k, d2["n"], d2["host"], d2["sched"]))

    print("\nREFERENCIA F 01 / F 02 (host / Schedule Level):")
    for fam in sorted(refs.keys()):
        r = refs[fam]
        if r is None:
            print("   {:<32} (sin referencia)".format(fam))
            continue
        sched = ""
        for f in r["nivel"]:
            if f["nombre"] == "SCHEDULE_LEVEL_PARAM":
                sched = f["valor"] or ""
        print("   {:<32} host={:<26} sched={}".format(
            fam, (r["host"] or "(sin host)")[:26], sched or "(vacio)"))

    if res["fallos"]:
        print("\nFALLOS:")
        for fl in res["fallos"][:20]:
            print("  - {}: {}".format(fl.get("bloque"), fl.get("motivo")))
    print("Detalle en: " + json_out)
    print("=" * 72)
    return res


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    aplicar(confirmar=_c)
