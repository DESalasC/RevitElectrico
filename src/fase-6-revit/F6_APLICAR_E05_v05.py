# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_v05.py
=====================
Aplica los 47 dispositivos reales de E 05 con el mapeo corregido
(config/mapeo_E05_v01.json) sobre las caras reales de sus anfitriones.

CORRECCIONES frente a v04 (evidencia del volcado del 2026-11-09 14:28):

  1. SIMBOLOS, ENFOQUE NUEVO. Ni Family.GetFamilySymbolIds() ni
     FilteredElementCollector.OfClass(FamilySymbol) devolvieron nada en
     IronPython 2.7 / Revit 2026 ("la familia no expone simbolos").
     Ahora el mapa de tipos se construye recorriendo
     FilteredElementCollector(doc).WhereElementIsElementType() y filtrando por
     duck-typing: todo ElementType con .Family. El nombre del tipo se lee con
     BuiltInParameter.SYMBOL_NAME_PARAM (no con .Name, que salia vacio).
     Los metodos antiguos quedan como respaldo.

  2. ESCRITURA DE JSON. json.dump sobre io.open("w", encoding="utf-8") fallaba
     con "'unknown' codec can't decode byte 0xe9" al haber cadenas no ASCII.
     Ahora se serializa con ensure_ascii=True y se escribe en BINARIO.

  3. DOCUMENTO OPCIONAL. aplicar() sin argumentos resuelve el documento activo,
     para que no falle con NameError en la pyRevit Python Shell.

  4. Se mantienen de v04: exclusiones antes de buscar regla, guarda de unidades
     (pies/metros), cascada de parametros de nivel y doc.Regenerate() previo.

Sobrecarga correcta de creacion:
    NewFamilyInstance(Face, XYZ location, XYZ referenceDir, FamilySymbol)

Uso:
    exec(open(r"...\\F6_APLICAR_E05_v05.py").read())
    aplicar(confirmar=False)   # valida, no crea nada
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

CANDIDATOS_NIVEL_NOMBRES = (
    "SCHEDULE_LEVEL_PARAM",
    "FAMILY_LEVEL_PARAM",
    "RBS_START_LEVEL_PARAM",
    "LEVEL_PARAM",
    "INSTANCE_REFERENCE_LEVEL_PARAM",
)


# --------------------------------------------------------------------------
# Utilidades basicas
# --------------------------------------------------------------------------

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
    """Escribe JSON ASCII en binario: evita el fallo de codec de io.open en texto."""
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
# Familias y tipos  (enfoque robusto)
# --------------------------------------------------------------------------

def _nombre_tipo(e):
    """Nombre del tipo. SYMBOL_NAME_PARAM primero; .Name como respaldo."""
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


def _mapa_familias(doc):
    """{clave_familia: {'family': fam, 'id': str, 'name': str}}"""
    out = {}
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            k = _clave(fam.Name)
        except Exception:
            continue
        if not k:
            continue
        out[k] = {"family": fam, "id": _eid_txt(fam.Id), "name": _safe(fam.Name)}
    return out


def _tipos_por_familia(doc):
    """{clave_familia: {clave_tipo: symbol}}

    Recorre TODOS los tipos del documento y se queda con los que tienen
    .Family. No usa GetFamilySymbolIds ni OfClass(FamilySymbol): ambos
    devolvieron vacio en IronPython 2.7 / Revit 2026.
    """
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
        try:
            kf = _clave(fam.Name)
        except Exception:
            continue
        if not kf:
            continue
        ks = _clave(_nombre_tipo(e))
        if not ks:
            continue
        out.setdefault(kf, {})[ks] = e
    return out, total


def _tipos_metodo_antiguo(doc, fam):
    """Respaldo: GetFamilySymbolIds + OfClass(FamilySymbol). Solo diagnostico."""
    syms = {}
    try:
        ids = fam.GetFamilySymbolIds()
        try:
            it = ids.GetEnumerator()
            while it.MoveNext():
                s = doc.GetElement(it.Current)
                if s is not None:
                    syms[_clave(_nombre_tipo(s))] = s
        except Exception:
            for sid in ids:
                s = doc.GetElement(sid)
                if s is not None:
                    syms[_clave(_nombre_tipo(s))] = s
    except Exception:
        pass
    return syms


def _resolver(familias, tipos, nombre_fam, nombre_sym):
    """Devuelve (symbol, error). SIN fallback al primer simbolo."""
    kf = _clave(nombre_fam)

    entrada = familias.get(kf)
    if entrada is None:
        cands = [k for k in familias.keys() if kf and (kf in k or k in kf)]
        if len(cands) == 1:
            entrada = familias[cands[0]]
            kf = cands[0]
    if entrada is None:
        return None, "familia no encontrada en el documento: " + str(nombre_fam)

    syms = tipos.get(kf) or {}
    if not syms:
        return None, ("la familia '{}' no tiene tipos cargados".format(entrada["name"]))

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
    """(nombre_ok, [(nombre, escribible)])."""
    info = []
    for nombre, bip in _bips_nivel():
        try:
            p = inst.get_Parameter(bip)
        except Exception:
            continue
        if p is None:
            continue
        try:
            escribible = not p.IsReadOnly
        except Exception:
            escribible = False
        info.append((nombre, escribible))
        if escribible:
            try:
                p.Set(nivel_id)
                return nombre, info
            except Exception:
                pass
    return "", info


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
# Principal
# --------------------------------------------------------------------------

def aplicar(doc=None, confirmar=False,
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_mapeo="config/mapeo_E05_v01.json",
            json_out="data/resultado_E05_v05.json"):
    doc = _resolver_doc(doc)
    if doc is None:
        print("No hay documento activo. Abre un .rvt en Revit y vuelve a ejecutar.")
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
    print("E05 v05  |  doc: " + _safe(doc.Title))
    print("Nivel: {}  elev={:.4f} m  ({:.4f} ft)".format(
        _safe(nivel.Name), elevacion_m, nivel.Elevation))
    print("=" * 72)
    if aviso_unidades:
        print(aviso_unidades)
        print("")
    if sospechosos:
        print("AVISO: z_local_m implausible (>6 m): {}".format(sospechosos[:5]))
        print("")

    familias = _mapa_familias(doc)
    tipos, n_tipos = _tipos_por_familia(doc)
    print("Inventario: {} familias, {} tipos con .Family, {} familias con tipos".format(
        len(familias), n_tipos, len(tipos)))

    # ---------------- 1. Validacion previa ----------------
    dispositivos = []
    errores_mapeo = []
    excluidos = []

    for d in data.get("dispositivos") or []:
        bloque = d.get("nombre_bloque_hijo")

        if bloque in excluir:
            excluidos.append(bloque)
            continue

        regla = mapa_disp.get(bloque)
        if regla is None:
            errores_mapeo.append({"bloque": bloque, "motivo": "sin regla en el mapeo"})
            continue
        if not regla.get("modelar", True):
            excluidos.append(bloque)
            continue

        sym, err = _resolver(familias, tipos, regla.get("familia"), regla.get("simbolo"))
        if sym is None:
            errores_mapeo.append({"bloque": bloque, "motivo": err})
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

        dispositivos.append({"d": d, "sym": sym, "es_techo": es_techo,
                             "familia": _safe(regla.get("familia")),
                             "simbolo": _safe(_nombre_tipo(sym))})

    print("\nVALIDACION DE MAPEO")
    print("  en transferencia              : {}".format(len(data.get("dispositivos") or [])))
    print("  con familia+simbolo resueltos : {}".format(len(dispositivos)))
    print("  excluidos (marcadores)        : {} {}".format(
        len(excluidos), sorted(set(excluidos))))
    print("  errores de mapeo              : {}".format(len(errores_mapeo)))

    if errores_mapeo:
        print("\n  DETALLE DE ERRORES (no se creara nada):")
        vistos = {}
        for e in errores_mapeo:
            k = (e["bloque"], e["motivo"])
            vistos[k] = vistos.get(k, 0) + 1
        for (bloque, motivo), cnt in sorted(vistos.items()):
            print("   - {:<24} x{:<3} {}".format(bloque, cnt, motivo))
        _guardar(json_out, {"ok": False, "fase": "validacion_mapeo",
                            "errores_mapeo": errores_mapeo, "excluidos": excluidos})
        print("\nABORTADO: corrige el mapeo y vuelve a ejecutar.")
        return {"ok": False, "errores_mapeo": errores_mapeo}

    # ---------------- 2. Instancias previas ----------------
    previas = _instancias_e05(doc)
    res = {"modo": "aplicar" if confirmar else "simulacion",
           "documento": _safe(doc.Title), "nivel": _safe(nivel.Name),
           "nivel_elev_m": round(elevacion_m, 4),
           "nivel_elev_ft": round(nivel.Elevation, 4),
           "aviso_unidades": aviso_unidades,
           "dispositivos": len(dispositivos), "eliminados": 0,
           "creados": 0, "con_host": 0, "sin_host": 0,
           "nivel_asignado_por": {}, "nivel_params": {}, "por_metodo": {},
           "fallos": [], "detalle": [], "excluidos": sorted(set(excluidos))}

    print("\nInstancias E05 previas con APT-E-05-P5: {}".format(len(previas)))
    if confirmar and previas:
        t = Transaction(doc, "F6 - Limpiar E05 v05")
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

    # ---------------- 3. Cara de anfitrion ----------------
    muros = []
    for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType():
        try:
            if _eid_int(w.LevelId) != _eid_int(nivel.Id):
                continue
            muros.append(w)
        except Exception:
            pass
    techos = list(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType())
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
                                  "motivo": "sin cara de anfitrion"})
            continue
        item["cara"] = elegido[1]
        item["punto"] = elegido[2]
        item["host"] = elegido[3]
        item["dir"] = XYZ(1, 0, 0) if item["es_techo"] else XYZ(0, 0, 1)
        planes.append(item)

    print("Con cara de anfitrion: {} / {}   sin cara: {}".format(
        len(planes), len(dispositivos), len(dispositivos) - len(planes)))

    if not confirmar:
        print("\nSIMULACION: mapeo y caras validados. No se ha creado nada.")
        print("Ejecuta aplicar(confirmar=True) para aplicar.")
        _guardar(json_out, res)
        return res

    # ---------------- 4. Creacion ----------------
    t = Transaction(doc, "F6 - Crear E05 v05")
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

                inst = None
                metodo = ""
                err = ""
                try:
                    inst = doc.Create.NewFamilyInstance(item["cara"], item["punto"],
                                                       item["dir"], sym)
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

                try:
                    doc.Regenerate()
                except Exception:
                    pass

                nivel_con, info_niv = _asignar_nivel(inst, nivel.Id)
                for nm, esc in info_niv:
                    k = "{} (escribible={})".format(nm, esc)
                    res["nivel_params"][k] = res["nivel_params"].get(k, 0) + 1
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
                    "z_m": round(float(d["z_local_m"]) + elevacion_m, 3),
                })
            except Exception as ex:
                res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                      "motivo": _safe(ex)})
    finally:
        t.Commit()

    _guardar(json_out, res)

    print("\n" + "=" * 72)
    print("RESULTADO: creados={} con_host={} sin_host={} fallos={}".format(
        res["creados"], res["con_host"], res["sin_host"], len(res["fallos"])))
    print("Metodos        : " + str(res["por_metodo"]))
    print("Nivel asignado : " + str(res["nivel_asignado_por"]))
    print("Params nivel   : " + str(res["nivel_params"]))
    if res["fallos"]:
        print("\nFALLOS:")
        for fl in res["fallos"][:20]:
            print("  - {}: {}".format(fl.get("bloque"), fl.get("motivo")))
    print("Detalle por dispositivo en: " + json_out)
    print("=" * 72)
    return res


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    aplicar(confirmar=_c)
