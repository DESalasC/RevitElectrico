# -*- coding: utf-8 -*-
"""
F6_DIAGNOSTICO_E05_v04.py
=========================
Diagnostico SOLO LECTURA. No crea, no borra, no mueve nada.

Objetivo: cerrar las dos incognitas que quedaron abiertas el 2026-11-09.

  1. SIMBOLOS. Compara TRES metodos de enumeracion por familia y dice cual
     devuelve resultados:
        a) Family.GetFamilySymbolIds()
        b) FilteredElementCollector.OfClass(<clase de un simbolo conocido>)
        c) WhereElementIsElementType() + .Family + SYMBOL_NAME_PARAM
     Ademas verifica cada pareja familia/simbolo del mapeo.

  2. PARAMETROS DE NIVEL. Vuelca TODOS los parametros de una instancia E05
     (nombre, BuiltInParameter, StorageType, escribible, valor). Asi se ve de
     una vez si "Schedule Level" es escribible o no y por que.

Secciones:
  A. Niveles del documento (metros y pies).
  B. Comparativa de los tres metodos de simbolos, por familia.
  C. Instancias E05 (ElementId, familia, tipo, host, Z).
  D. Volcado completo de parametros de una instancia (los de nivel primero).
  E. Verificacion del mapeo config/mapeo_E05_v01.json.

Salidas (JSON ASCII en binario):
  data/diagnostico_E05_simbolos_v04.json
  data/diagnostico_E05_parametros_v04.json

Uso:
    exec(open(r"...\\F6_DIAGNOSTICO_E05_v04.py").read())
    diagnosticar()
"""
import io
import json
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Family,
    FilteredElementCollector,
    Level,
)

FT = 0.3048

CATS_ELECTRICAS = [
    ("ElectricalFixtures", BuiltInCategory.OST_ElectricalFixtures),
    ("ElectricalEquipment", BuiltInCategory.OST_ElectricalEquipment),
    ("LightingFixtures", BuiltInCategory.OST_LightingFixtures),
    ("LightingDevices", BuiltInCategory.OST_LightingDevices),
    ("DataDevices", BuiltInCategory.OST_DataDevices),
    ("CommunicationDevices", BuiltInCategory.OST_CommunicationDevices),
    ("TelephoneDevices", BuiltInCategory.OST_TelephoneDevices),
]

CANDIDATOS_NIVEL_NOMBRES = (
    "SCHEDULE_LEVEL_PARAM",
    "FAMILY_LEVEL_PARAM",
    "RBS_START_LEVEL_PARAM",
    "LEVEL_PARAM",
    "INSTANCE_REFERENCE_LEVEL_PARAM",
)


# --------------------------------------------------------------------------

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
        print("Guardado: " + path)
        return True
    except Exception as ex:
        print("No se pudo guardar {}: {}".format(path, _safe(ex)))
        return False


def _leer_json(path):
    f = io.open(path, "r", encoding="utf-8")
    try:
        return json.load(f)
    finally:
        f.close()


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


# --------------------------------------------------------------------------
# Tres metodos de enumeracion de simbolos
# --------------------------------------------------------------------------

def _metodo_a(doc, fam):
    """Family.GetFamilySymbolIds()"""
    out = {}
    try:
        ids = fam.GetFamilySymbolIds()
        n = 0
        try:
            it = ids.GetEnumerator()
            while it.MoveNext():
                n += 1
                s = doc.GetElement(it.Current)
                if s is not None:
                    out[_clave(_nombre_tipo(s))] = _safe(_nombre_tipo(s))
        except Exception:
            n = -1
        if n <= 0:
            try:
                for sid in ids:
                    s = doc.GetElement(sid)
                    if s is not None:
                        out[_clave(_nombre_tipo(s))] = _safe(_nombre_tipo(s))
            except Exception:
                pass
    except Exception:
        pass
    return out


def _metodo_b(doc, fam):
    """Collector de la clase de un simbolo conocido de esa familia, por FamilyId."""
    out = {}
    try:
        base = None
        for inst in FilteredElementCollector(doc).OfClass(Family).ToElements():
            if _clave(inst.Name) == _clave(fam.Name):
                base = inst
                break
        if base is None:
            base = fam
        fid = _eid_txt(base.Id)
        ref = None
        # tomar la clase real de un tipo de esa familia
        for e in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
            et = None
            try:
                et = e.Family
            except Exception:
                et = None
            if et is None:
                continue
            if _eid_txt(et.Id) == fid:
                ref = type(e)
                break
        if ref is None:
            return out
        for e in FilteredElementCollector(doc).OfClass(ref).ToElements():
            try:
                if _eid_txt(e.Family.Id) == fid:
                    out[_clave(_nombre_tipo(e))] = _safe(_nombre_tipo(e))
            except Exception:
                pass
    except Exception:
        pass
    return out


def _metodo_c(doc, fam):
    """WhereElementIsElementType + .Family + SYMBOL_NAME_PARAM"""
    out = {}
    try:
        fid = _eid_txt(fam.Id)
        fn = _clave(fam.Name)
        for e in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
            try:
                f = e.Family
            except Exception:
                continue
            if f is None:
                continue
            if _eid_txt(f.Id) != fid and _clave(f.Name) != fn:
                continue
            out[_clave(_nombre_tipo(e))] = _safe(_nombre_tipo(e))
    except Exception:
        pass
    return out


def _tipos_global(doc):
    out = {}
    n = 0
    for e in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
        n += 1
        try:
            f = e.Family
        except Exception:
            continue
        if f is None:
            continue
        kf = _clave(f.Name)
        ks = _clave(_nombre_tipo(e))
        if kf and ks:
            out.setdefault(kf, {})[ks] = e
    return out, n


# --------------------------------------------------------------------------

def diagnosticar(doc=None,
                 json_simbolos="data/diagnostico_E05_simbolos_v04.json",
                 json_parametros="data/diagnostico_E05_parametros_v04.json",
                 json_cfg="config/mapeo_E05_v01.json"):
    doc = _resolver_doc(doc)
    if doc is None:
        print("No hay documento activo. Abre un .rvt en Revit y vuelve a ejecutar.")
        return None

    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    if not os.path.isabs(json_simbolos):
        json_simbolos = os.path.join(root, json_simbolos)
    if not os.path.isabs(json_parametros):
        json_parametros = os.path.join(root, json_parametros)
    if not os.path.isabs(json_cfg):
        json_cfg = os.path.join(root, json_cfg)

    print("=" * 74)
    print("DIAGNOSTICO E05 v04  --  doc: " + _safe(doc.Title))
    print("=" * 74)

    # ---------------- A. Niveles ----------------
    niveles = []
    for lv in FilteredElementCollector(doc).OfClass(Level):
        niveles.append({"nombre": _safe(lv.Name),
                        "elev_m": round(lv.Elevation * FT, 4),
                        "elev_ft": round(lv.Elevation, 4)})
    niveles.sort(key=lambda x: x["elev_m"])
    print("\nA. NIVELES ({}):".format(len(niveles)))
    for nv in niveles:
        print("   {:<44} {:>9.4f} m  ({:>10.4f} ft)".format(
            nv["nombre"], nv["elev_m"], nv["elev_ft"]))

    # ---------------- B. Comparativa de metodos ----------------
    tipos, n_tipos = _tipos_global(doc)
    print("\nB. ENUMERACION DE SIMBOLOS")
    print("   Tipos totales en el documento : {}".format(n_tipos))
    print("   Familias con tipos (metodo c) : {}".format(len(tipos)))

    cfg = None
    try:
        cfg = _leer_json(json_cfg)
    except Exception as ex:
        print("   No se pudo leer el mapeo: " + _safe(ex))

    fams_objetivo = {}
    if cfg:
        for bloque, regla in sorted((cfg.get("dispositivos") or {}).items()):
            fams_objetivo[regla.get("familia")] = True
    mapa_fam = {}
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            mapa_fam[_clave(fam.Name)] = fam
        except Exception:
            pass

    print("\n   {:<30} {:>6} {:>6} {:>6}   {}".format(
        "Familia", "a_ids", "b_cls", "c_glob", "c -> tipos"))
    comparativa = []
    for nombre_fam in sorted(fams_objetivo.keys()):
        fam = mapa_fam.get(_clave(nombre_fam))
        if fam is None:
            print("   {:<30} {:>6} {:>6} {:>6}   FAMILIA NO ENCONTRADA".format(
                _safe(nombre_fam), "-", "-", "-"))
            continue
        a = _metodo_a(doc, fam)
        b = _metodo_b(doc, fam)
        c = tipos.get(_clave(fam.Name)) or {}
        lista_c = sorted(_safe(_nombre_tipo(v)) for v in c.values())
        print("   {:<30} {:>6} {:>6} {:>6}   {}".format(
            _safe(nombre_fam), len(a), len(b), len(c),
            lista_c[:4] if lista_c else "(vacio)"))
        comparativa.append({"familia": _safe(nombre_fam),
                            "a_ids": sorted(a.values()),
                            "b_clase": sorted(b.values()),
                            "c_global": lista_c})

    # ---------------- C. Instancias E05 ----------------
    instancias = []
    for etiqueta, bic in CATS_ELECTRICAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = p.AsString() if p is not None else ""
                except Exception:
                    c = ""
                if not (c and "APT-E-05" in c):
                    continue
                try:
                    pt = inst.Location.Point
                    pos = (round(pt.X * FT, 3), round(pt.Y * FT, 3), round(pt.Z * FT, 3))
                except Exception:
                    pos = (None, None, None)
                hname = ""
                try:
                    if inst.Host is not None:
                        hname = _safe(inst.Host.Name)
                except Exception:
                    pass
                try:
                    tipo = _safe(_nombre_tipo(inst.Symbol))
                except Exception:
                    tipo = ""
                instancias.append({"elemento_id": _eid_txt(inst.Id),
                                   "categoria": etiqueta,
                                   "familia": _safe(inst.Symbol.Family.Name),
                                   "tipo": tipo, "host": hname,
                                   "x_m": pos[0], "y_m": pos[1], "z_m": pos[2]})
        except Exception:
            pass

    print("\nC. INSTANCIAS E05: {}".format(len(instancias)))
    for m in instancias:
        print("   {:<10} {:<28} {:<26} z={:<7} {}".format(
            str(m["elemento_id"]), m["familia"][:28],
            str(m["host"])[:26], str(m["z_m"]), m["tipo"]))

    # ---------------- D. Volcado completo de parametros ----------------
    print("\nD. PARAMETROS DE UNA INSTANCIA E05 (todos los de nivel/elevacion):")
    volcado = []
    muestra = None
    for bic in CATS_ELECTRICAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = p.AsString() if p is not None else ""
                except Exception:
                    c = ""
                if c and "APT-E-05" in c:
                    muestra = inst
                    break
        except Exception:
            pass
        if muestra is not None:
            break

    if muestra is not None:
        print("   {}  {}".format(_eid_txt(muestra.Id),
                                 _safe(muestra.Symbol.Family.Name)))
        interesantes = ("level", "nivel", "elevation", "elevacion", "altura")
        try:
            for pr in muestra.Parameters:
                try:
                    d = pr.Definition
                    nm = _safe(d.Name)
                except Exception:
                    continue
                low = nm.lower()
                if not any(k in low for k in interesantes):
                    continue
                try:
                    bip = str(d.BuiltInParameter)
                except Exception:
                    bip = "?"
                try:
                    esc = not pr.IsReadOnly
                except Exception:
                    esc = None
                try:
                    st = str(pr.StorageType)
                except Exception:
                    st = "?"
                try:
                    val = pr.AsValueString()
                except Exception:
                    val = None
                fila = {"nombre": nm, "builtin": bip, "storage": st,
                        "escribible": esc, "valor": _safe(val) if val is not None else None}
                volcado.append(fila)
                print("      {:<32} bip={:<28} tipo={:<10} escribible={:<6} valor={}".format(
                    nm, bip, st, str(esc), str(fila["valor"])))
        except Exception as ex:
            print("      error recorriendo parametros: " + _safe(ex))
    else:
        print("   (no hay instancias E05 para muestrear)")

    # ---------------- E. Verificacion del mapeo ----------------
    print("\nE. VERIFICACION DEL MAPEO:")
    ok, fallas = 0, 0
    detalle_mapeo = []
    if cfg:
        for bloque in sorted((cfg.get("dispositivos") or {}).keys()):
            regla = cfg["dispositivos"][bloque]
            fam_ped = regla.get("familia")
            sym_ped = regla.get("simbolo")
            kf = _clave(fam_ped)
            fam = mapa_fam.get(kf)
            if fam is None:
                print("   FALLA  {:<24} familia '{}' no existe".format(bloque, fam_ped))
                fallas += 1
                detalle_mapeo.append({"bloque": bloque, "estado": "familia ausente"})
                continue
            syms = tipos.get(_clave(fam.Name)) or {}
            if not syms:
                print("   FALLA  {:<24} familia '{}' sin tipos".format(bloque, fam_ped))
                fallas += 1
                detalle_mapeo.append({"bloque": bloque, "estado": "sin tipos"})
                continue
            ks = _clave(sym_ped)
            if ks in syms:
                print("   OK     {:<24} {} -> {}".format(
                    bloque, _safe(fam.Name), _safe(_nombre_tipo(syms[ks]))))
                ok += 1
                detalle_mapeo.append({"bloque": bloque, "estado": "ok",
                                      "simbolo": _safe(_nombre_tipo(syms[ks]))})
            else:
                print("   FALLA  {:<24} simbolo '{}' no esta en {}. Disponibles: {}".format(
                    bloque, sym_ped, _safe(fam.Name),
                    sorted(_safe(_nombre_tipo(v)) for v in syms.values())))
                fallas += 1
                detalle_mapeo.append({"bloque": bloque, "estado": "simbolo ausente",
                                      "disponibles": sorted(_safe(_nombre_tipo(v))
                                                            for v in syms.values())})
        print("\n   RESUMEN: {} OK / {} fallas".format(ok, fallas))

    _guardar(json_simbolos, {"documento": _safe(doc.Title), "niveles": niveles,
                             "tipos_totales": n_tipos,
                             "comparativa_metodos": comparativa,
                             "instancias": instancias,
                             "mapeo": detalle_mapeo,
                             "ok": ok, "fallas": fallas})
    _guardar(json_parametros, {"documento": _safe(doc.Title), "parametros": volcado})

    print("\n" + "=" * 74)
    print("FIN DIAGNOSTICO (nada fue modificado)")
    print("=" * 74)
    return {"ok": ok, "fallas": fallas}


if __name__ == "__main__":
    diagnosticar()
