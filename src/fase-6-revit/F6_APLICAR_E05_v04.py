# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_v04.py
=====================
Aplica los 47 dispositivos reales de E 05 con el mapeo corregido
(config/mapeo_E05_v01.json) sobre las caras reales de sus anfitriones.

CORRECCIONES frente a v03 (todas confirmadas por el diagnostico del 2026-11-09):

  1. CODIFICACION. IronPython 2.7 lee los .json como bytes, no como UTF-8.
     'Estándar' llegaba como 'EstÃ¡ndar' y 'M_Toma de teléfono - Datos' como
     'M_Toma de telÃ©fono - Datos', asi que NINGUNA familia ni simbolo resolvia.
     Ahora todos los JSON se leen con io.open(..., encoding="utf-8").

  2. SIMBOLOS. Family.GetFamilySymbolIds() devuelve ISet<ElementId> y en
     IronPython 2.7 la iteracion directa devolvia vacio: todos los errores
     decian "Disponibles: []". Ahora se usan tres caminos (enumerador .NET,
     colector FamilySymbol por FamilyId, colector por nombre de familia).

  3. EXCLUSIONES. Los marcadores de conductores se comprobaban DESPUES de
     buscar la regla, asi que 2F2N1T1R salia como "sin regla". Ahora se
     comprueban primero.

  4. SCHEDULE LEVEL. El diagnostico confirma que el parametro existe y es
     escribible (escribible=True), pero se leia viva la instancia recien
     creada. Ahora se hace doc.Regenerate() antes de asignarlo.

  5. GUARDA DE UNIDADES. El JSON de transferencia guardaba la elevacion del
     nivel en PIES bajo la clave 'elevacion_nivel_m' (43.3727 ft = 13.219999 m).
     Ademas 'z_abs_m' sumaba pies de nivel + metros locales. Ahora el valor
     autoritativo es SIEMPRE nivel.Elevation del documento y, si el JSON
     discrepa, se detecta si venia en pies y se avisa en consola y en el JSON
     de salida. Tambien se avisa si algun 'z_local_m' parece estar en pies.

Sobrecarga correcta de creacion:
    NewFamilyInstance(Face, XYZ location, XYZ referenceDir, FamilySymbol)
(NewFamilyInstance(Reference, XYZ, FamilySymbol) NO existe: de ahi el antiguo
"expected Line, got Reference".)

Uso:
    # basta con esto: el script resuelve el documento activo por si mismo
    exec(open(r"...\\F6_APLICAR_E05_v04.py").read())
    aplicar(confirmar=False)

    # o, si se prefiere, pasar el documento explicitamente
    aplicar(__revit__.ActiveUIDocument.Document, confirmar=True)
"""
import io
import json
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Family,
    FamilySymbol,
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


def _bips_nivel():
    out = []
    for nm in CANDIDATOS_NIVEL_NOMBRES:
        try:
            out.append((nm, getattr(BuiltInParameter, nm)))
        except Exception:
            pass
    return out


def _resolver_doc(doc):
    """Devuelve el documento activo. Evita el NameError si 'doc' no existe.

    En la pyRevit Python Shell las variables se pierden al reiniciarse la sesion,
    asi que llamar aplicar(doc, ...) sin haber definido doc fallaba con
    NameError. Ahora el documento es opcional.
    """
    if doc is not None:
        return doc
    try:
        uiapp = __revit__  # noqa: F821
        uidoc = uiapp.ActiveUIDocument
        if uidoc is None:
            return None
        return uidoc.Document
    except Exception:
        return None


def _elevacion_viva_m(nivel):
    return nivel.Elevation * 0.3048


def _revisar_unidades_elevacion(data, nivel):
    """Compara la elevacion declarada en el JSON con la viva del documento.

    Devuelve (elevacion_m, aviso). La elevacion autoritativa es SIEMPRE la del
    documento: Revit guarda las alturas en pies y aqui se pasan a metros.
    Detecta el error historico de tener pies guardados bajo clave '_m'.
    """
    viva = _elevacion_viva_m(nivel)
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
                      "({} ft = {:.4f} m). Se usa la elevacion viva del nivel: {:.4f} m.").format(
                          decl, decl, decl * 0.3048, viva)
    return viva, ("AVISO: 'elevacion_nivel_m'={} no coincide con la elevacion viva "
                  "{:.4f} m, ni como metros ni como pies. Se usa la viva.").format(decl, viva)


def _revisar_unidades_z_local(dispositivos):
    """Avisa si algun z_local_m resulta implausible (posible pies)."""
    raros = []
    for d in dispositivos:
        try:
            z = float(d.get("z_local_m"))
        except Exception:
            continue
        if z > 6.0:
            raros.append((d.get("nombre_bloque_hijo"), z))
    return raros


def _leer_json(path):
    """Lee JSON como UTF-8. IronPython 2.7 necesita io.open explicito."""
    f = io.open(path, "r", encoding="utf-8")
    try:
        return json.load(f)
    finally:
        f.close()


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
    """Clave robusta: solo alfanumericos en minuscula, sin acentos ni simbolos."""
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
# Familias y simbolos
# --------------------------------------------------------------------------

def _mapa_familias(doc):
    out = {}
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            k = _clave(fam.Name)
            fid = _eid_txt(fam.Id)
        except Exception:
            continue
        if k:
            out[k] = {"family": fam, "id": fid, "name": _safe(fam.Name)}
    return out


def _simbolos_de_familia(doc, fam):
    """Lista de FamilySymbol. Robusto en IronPython 2.7 / Revit 2026."""
    out = []
    vistos = {}

    def agregar(s):
        if s is None:
            return
        try:
            k = _eid_txt(s.Id)
        except Exception:
            return
        if k in vistos:
            return
        vistos[k] = True
        out.append(s)

    # 1) ISet<ElementId> con enumerador .NET explicito
    try:
        ids = fam.GetFamilySymbolIds()
        enumerado = False
        try:
            it = ids.GetEnumerator()
            while it.MoveNext():
                enumerado = True
                try:
                    agregar(doc.GetElement(it.Current))
                except Exception:
                    pass
        except Exception:
            pass
        if not enumerado:
            try:
                for sid in ids:
                    agregar(doc.GetElement(sid))
            except Exception:
                pass
    except Exception:
        pass

    fid = _eid_txt(getattr(fam, "Id", None))
    fnombre = _clave(getattr(fam, "Name", ""))

    # 2) Colector de FamilySymbol filtrado por FamilyId
    if not out:
        try:
            for s in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
                try:
                    if fid and fid != "None" and _eid_txt(s.Family.Id) == fid:
                        agregar(s)
                except Exception:
                    pass
        except Exception:
            pass

    # 3) Colector de FamilySymbol filtrado por nombre de familia
    if not out and fnombre:
        try:
            for s in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
                try:
                    if _clave(s.Family.Name) == fnombre:
                        agregar(s)
                except Exception:
                    pass
        except Exception:
            pass

    return out


def _mapa_simbolos(doc, fam):
    out = {}
    for s in _simbolos_de_familia(doc, fam):
        try:
            out[_clave(s.Name)] = s
        except Exception:
            pass
    return out


def _resolver(doc, familias, nombre_fam, nombre_sym):
    """Devuelve (symbol, error). SIN fallback al primer simbolo."""
    kf = _clave(nombre_fam)
    entrada = familias.get(kf)
    if entrada is None:
        cands = [k for k in familias.keys() if kf and (kf in k or k in kf)]
        if len(cands) == 1:
            entrada = familias[cands[0]]
    if entrada is None:
        return None, "familia no encontrada: " + str(nombre_fam)

    fam = entrada["family"]
    syms = _mapa_simbolos(doc, fam)
    if not syms:
        return None, "la familia '{}' no expone simbolos (GetFamilySymbolIds vacio)".format(
            entrada["name"])

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
    """Cascada de parametros de nivel. Devuelve (nombre_ok, [(nombre, escribible)])."""
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
# Principal
# --------------------------------------------------------------------------

def aplicar(doc=None, confirmar=False,
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_mapeo="config/mapeo_E05_v01.json",
            json_out="data/resultado_E05_v04.json"):
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

    print("=" * 70)
    print("E05 v04  |  doc: " + _safe(doc.Title))
    print("Nivel: {}  elev={:.4f} m  ({:.4f} ft)".format(
        _safe(nivel.Name), elevacion_m, nivel.Elevation))
    print("=" * 70)
    if aviso_unidades:
        print(aviso_unidades)
        print("")
    if sospechosos:
        print("AVISO: z_local_m implausible (>6 m), posible valor en pies:")
        for b, z in sospechosos[:10]:
            print("   - {:<24} z_local_m={}".format(b, z))
        print("")

    familias = _mapa_familias(doc)
    print("Familias cargadas en el documento: {}".format(len(familias)))

    # ---------------- 1. Validacion previa del mapeo ----------------
    dispositivos = []
    errores_mapeo = []
    excluidos = []

    for d in data.get("dispositivos") or []:
        bloque = d.get("nombre_bloque_hijo")

        # (a) exclusion explicita PRIMERO
        if bloque in excluir:
            excluidos.append(bloque)
            continue

        # (b) regla de mapeo
        regla = mapa_disp.get(bloque)
        if regla is None:
            errores_mapeo.append({"bloque": bloque, "motivo": "sin regla en mapeo_E05_v01.json"})
            continue
        if not regla.get("modelar", True):
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
           "z_local_sospechosos": [{"bloque": b, "z_local_m": z} for b, z in sospechosos],
           "dispositivos": len(dispositivos), "eliminados": 0,
           "creados": 0, "con_host": 0, "sin_host": 0,
           "nivel_asignado_por": {}, "nivel_params": {}, "por_metodo": {},
           "fallos": [], "detalle": [], "excluidos": sorted(set(excluidos))}

    print("\nInstancias E05 previas con APT-E-05-P5: {}".format(len(previas)))
    if confirmar and previas:
        t = Transaction(doc, "F6 - Limpiar E05 v04")
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
        print("\nSIMULACION: mapeo y caras validados. No se ha creado nada.")
        print("Ejecuta con confirmar=True para aplicar.")
        _guardar(json_out, res)
        return res

    # ---------------- 4. Creacion ----------------
    t = Transaction(doc, "F6 - Crear E05 v04")
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

                # Regenerar para que el parametro de nivel exista ya en la instancia
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
                    "z_m": round(float(d["z_local_m"]) + nivel.Elevation * 0.3048, 3),
                })
            except Exception as ex:
                res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                      "motivo": _safe(ex)})
    finally:
        t.Commit()

    _guardar(json_out, res)

    print("\n" + "=" * 70)
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
    print("=" * 70)
    return res


def _guardar(path, obj):
    try:
        f = io.open(path, "w", encoding="utf-8")
        try:
            json.dump(obj, f, indent=2, ensure_ascii=True)
        finally:
            f.close()
    except Exception as ex:
        print("No se pudo guardar {}: {}".format(path, _safe(ex)))


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    aplicar(confirmar=_c)
