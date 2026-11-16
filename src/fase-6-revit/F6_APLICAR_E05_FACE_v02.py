# -*- coding: utf-8 -*-
"""
F6_APLICAR_E05_FACE_v02.py
==========================
Coloca los 49 dispositivos de E 05 sobre las caras reales de sus anfitriones.

SOBRECARGA CORRECTA (la que funciona):
    NewFamilyInstance(Face, XYZ location, XYZ referenceDir, FamilySymbol)

El error "expected Line, got Reference" de las v02/v03/v04 se debia a que
NewFamilyInstance(Reference, XYZ, FamilySymbol) NO existe como overload: Python
resolvia contra NewFamilyInstance(Line, ...) y fallaba.

Anfitrion por dispositivo:
  * d["anfitrion"] == "ceiling"  -> cara inferior del Compound Ceiling
  * d["anfitrion"] == "muro"     -> cara lateral del muro
  * si falta el campo -> z_local_m >= 2.0 => techo, si no muro

Direccion de referencia (referenceDir):
  * muro  -> (0,0,1)   => HandOrientation vertical, como F 01 / F 02
  * techo -> (1,0,0)

Cascada de creacion por dispositivo (se reporta el metodo usado):
  1. Face     : NewFamilyInstance(Face, XYZ, XYZ, FamilySymbol)
  2. HostElem : NewFamilyInstance(XYZ, FamilySymbol, Element host, StructuralType)
  3. Nivel    : NewFamilyInstance(XYZ, FamilySymbol, Level, StructuralType)  [Host=None]

Solo elimina instancias con Comments APT-E-05-P5. No toca F 01 ni F 02.

Uso:
    aplicar(doc, confirmar=False)   # simulacion con diagnostico
    aplicar(doc, confirmar=True)    # aplica
"""
import json
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
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


def _eid(e):
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


def _norm(t):
    if t is None:
        return ""
    try:
        t = unicode(t)  # noqa: F821
    except Exception:
        t = str(t)
    import unicodedata
    try:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return "".join(c for c in t if ord(c) < 128).strip().lower()


def _familia(doc, nombre):
    from Autodesk.Revit.DB import Family
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        if _norm(fam.Name) == _norm(nombre):
            return fam
    return None


def _simbolo(doc, fam, nombre):
    objetivo = _norm(nombre)
    syms = []
    for sid in fam.GetFamilySymbolIds():
        try:
            s = doc.GetElement(sid)
            p = s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            syms.append((sid, (p.AsString() if p is not None else "") or ""))
        except Exception:
            pass
    for sid, n in syms:
        if _norm(n) == objetivo:
            return doc.GetElement(sid)
    for sid, n in syms:
        nn = _norm(n)
        if objetivo and (objetivo in nn or nn in objetivo):
            return doc.GetElement(sid)
    return doc.GetElement(syms[0][0]) if syms else None


def _dist_curva(w, x, y):
    try:
        c = w.Location.Curve
        r = c.Project(XYZ(x, y, 0))
        p = r.XYZPoint
        return math.hypot(p.X - x, p.Y - y)
    except Exception:
        return 999.0


def _caras(host, punto, es_techo):
    """Devuelve [(dist, Face, XYZPoint)] de las caras validas del host."""
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


def _marcar(inst, nivel):
    """Comments + Schedule Level."""
    try:
        cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if cp is not None and not cp.IsReadOnly:
            cp.Set("APT-E-05-P5")
    except Exception:
        pass
    ok_nivel = False
    try:
        sp = inst.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM)
        if sp is not None and not sp.IsReadOnly:
            sp.Set(nivel.Id)
            ok_nivel = True
    except Exception:
        pass
    return ok_nivel


def _crear(doc, cara, punto, dir_ref, sym, host, nivel):
    """Cascada de creacion. Devuelve (instancia, metodo, error)."""
    errores = []
    # 1. Face (4 argumentos) -> correcto para face-based
    if cara is not None:
        try:
            inst = doc.Create.NewFamilyInstance(cara, punto, dir_ref, sym)
            if inst is not None:
                return inst, "Face", ""
        except Exception as ex:
            errores.append("Face: " + _safe(ex))
    # 2. Host element (4 argumentos: XYZ, FamilySymbol, Element, StructuralType)
    if host is not None:
        try:
            inst = doc.Create.NewFamilyInstance(punto, sym, host,
                                               Structure.StructuralType.NonStructural)
            if inst is not None:
                return inst, "HostElem", ""
        except Exception as ex:
            errores.append("HostElem: " + _safe(ex))
    # 3. Nivel (work-plane based) -> queda Host=None
    try:
        inst = doc.Create.NewFamilyInstance(punto, sym, nivel,
                                           Structure.StructuralType.NonStructural)
        if inst is not None:
            return inst, "Nivel", ""
    except Exception as ex:
        errores.append("Nivel: " + _safe(ex))
    return None, "", " | ".join(errores)


def aplicar(doc, confirmar=False,
            json_in="data/E05_transferencia_panel_ancla_v03.json",
            json_out="data/resultado_E05_face_v02.json"):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    data = json.load(open(json_in, "r"))
    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _norm(lv.Name) == _norm(data.get("nivel", "Piso 5")):
            nivel = lv
            break
    if nivel is None:
        print("Nivel no encontrado: " + str(data.get("nivel")))
        return {"ok": False}

    res = {"modo": "aplicar" if confirmar else "simulacion",
           "documento": _safe(doc.Title),
           "nivel": _safe(nivel.Name),
           "nivel_elev_m": round(nivel.Elevation * 0.3048, 4),
           "dispositivos": len(data.get("dispositivos") or []),
           "con_cara": 0, "sin_cara": 0, "creados": 0, "eliminados": 0,
           "con_host": 0, "sin_host": 0, "con_schedule_level": 0,
           "por_metodo": {}, "fallos": []}

    # ---------- Diagnostico previo ----------
    previas = _instancias_e05(doc)
    print("DIAGNOSTICO: instancias E05 previas = {}".format(len(previas)))
    for inst in previas[:5]:
        try:
            print("  ID {} fam={} host={} level={} z_m={}".format(
                inst.Id, _safe(inst.Symbol.Family.Name),
                _safe(inst.Host.Name if inst.Host is not None else "None"),
                _safe(inst.LevelId),
                round(inst.Location.Point.Z * 0.3048, 3)))
        except Exception as ex:
            print("  ID {} (sin punto: {})".format(inst.Id, _safe(ex)))

    if confirmar and previas:
        t = Transaction(doc, "F6 - Limpiar E05 face v02")
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
        print("LIMPIEZA: eliminadas={}".format(res["eliminados"]))

    # ---------- Recoleccion de hosts ----------
    muros = []
    for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType():
        try:
            if _eid(w.LevelId) != _eid(nivel.Id):
                continue
            muros.append(w)
        except Exception:
            pass
    techos = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType())
    print("DIAGNOSTICO: muros Piso 5={} techos totales={}".format(len(muros), len(techos)))

    # ---------- Resolucion de cara por dispositivo ----------
    planes = []
    for d in data.get("dispositivos") or []:
        x_ft = float(d["x_revit_ft"])
        y_ft = float(d["y_revit_ft"])
        z_local = float(d["z_local_m"])
        z_ft = nivel.Elevation + z_local * FT
        punto = XYZ(x_ft, y_ft, z_ft)

        anf = _norm(d.get("anfitrion"))
        if anf == "ceiling":
            es_techo = True
        elif anf in ("muro", "wall"):
            es_techo = False
        else:
            es_techo = z_local >= 2.0

        elegido = None
        host_el = None
        if es_techo:
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
            cercanos = sorted((_dist_curva(w, x_ft, y_ft), w) for w in muros)[:10]
            for dist_w, w in cercanos:
                if dist_w > TOL_MURO_M * FT:
                    continue
                for dist, f, pt in _caras(w, punto, False):
                    if elegido is None or dist < elegido[0]:
                        elegido = (dist, f, pt, w)

        if elegido is None:
            res["sin_cara"] += 1
            res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                  "anfitrion": "techo" if es_techo else "muro",
                                  "motivo": "sin cara de host"})
            continue
        res["con_cara"] += 1
        host_el = elegido[3]
        dir_ref = XYZ(1, 0, 0) if es_techo else XYZ(0, 0, 1)
        planes.append({"d": d, "cara": elegido[1], "punto": elegido[2],
                       "dir": dir_ref, "host": host_el,
                       "tipo": "techo" if es_techo else "muro"})

    print("SIMULACION: dispositivos={} con_cara={} sin_cara={}".format(
        res["dispositivos"], res["con_cara"], res["sin_cara"]))
    if not confirmar:
        return res

    # ---------- Creacion ----------
    t = Transaction(doc, "F6 - Crear E05 sobre caras v02")
    t.Start()
    try:
        for p in planes:
            d = p["d"]
            try:
                fam = _familia(doc, d.get("familia_revit"))
                if fam is None:
                    res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                          "motivo": "familia no encontrada: " + str(d.get("familia_revit"))})
                    continue
                sym = _simbolo(doc, fam, d.get("simbolo"))
                if sym is None:
                    res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                          "motivo": "simbolo no encontrado: " + str(d.get("simbolo"))})
                    continue
                if not sym.IsActive:
                    try:
                        sym.Activate()
                        doc.Regenerate()
                    except Exception:
                        pass

                inst, metodo, err = _crear(doc, p["cara"], p["punto"], p["dir"],
                                           sym, p["host"], nivel)
                if inst is None:
                    res["fallos"].append({"bloque": d.get("nombre_bloque_hijo"),
                                          "anfitrion": p["tipo"], "motivo": err})
                    continue

                if _marcar(inst, nivel):
                    res["con_schedule_level"] += 1

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

    print("RESULTADO: creados={} con_host={} sin_host={} schedule_level={} fallos={}".format(
        res["creados"], res["con_host"], res["sin_host"],
        res["con_schedule_level"], len(res["fallos"])))
    print("METODOS: " + str(res["por_metodo"]))
    return res


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    aplicar(__revit__.ActiveUIDocument.Document, confirmar=_c)  # noqa: F821
