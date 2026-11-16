# -*- coding: utf-8 -*-
"""
F6_DIAGNOSTICO_E05_v03.py
=========================
Diagnostico SOLO LECTURA. No crea, no borra, no mueve nada.

CORRECCIONES frente a v02 (confirmadas por el volcado del 2026-11-09):

  1. CODIFICACION. IronPython 2.7 leia los .json como bytes: 'Estándar' llegaba
     como 'EstÃ¡ndar' y las familias con acento no resolvian. Ahora io.open UTF-8.
  2. SIMBOLOS. Family.GetFamilySymbolIds() devuelve ISet<ElementId> y la
     iteracion directa devolvia vacio ("Disponibles: []" en todos los errores).
     Ahora se usan tres caminos: enumerador .NET, colector FamilySymbol por
     FamilyId y colector por nombre de familia.

Secciones:
  A. Niveles del documento.
  B. Inventario real de familias y simbolos por categoria.
  C. Instancias E05 con ElementId, familia, tipo, host, Z.
  D. Parametros de nivel por instancia (existe / escribible / valor).
  E. Verificacion del mapeo config/mapeo_E05_v01.json contra el documento:
     por cada bloque dice si la familia y el simbolo EXISTEN de verdad.

Salidas (UTF-8):
  data/diagnostico_E05_familias_v03.json
  data/diagnostico_E05_niveles_v03.json
  data/diagnostico_E05_mapeo_v03.json

Uso:
    # basta con esto: el script resuelve el documento activo por si mismo
    exec(open(r"...\\F6_DIAGNOSTICO_E05_v03.py").read())
    diagnosticar()

    # o, si se prefiere, pasar el documento explicitamente
    diagnosticar(__revit__.ActiveUIDocument.Document)
"""
import io
import json
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Family,
    FamilySymbol,
    FilteredElementCollector,
    Level,
)

FT = 0.3048  # pies -> metros

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
        f = io.open(path, "w", encoding="utf-8")
        try:
            json.dump(obj, f, indent=2, ensure_ascii=True)
        finally:
            f.close()
        print("Guardado: " + path)
    except Exception as ex:
        print("No se pudo guardar {}: {}".format(path, _safe(ex)))


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


def _simbolos_de_familia(doc, fam):
    """FamilySymbol de la familia. Robusto en IronPython 2.7 / Revit 2026."""
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


def _resolver_doc(doc):
    """Devuelve el documento activo. Evita el NameError si 'doc' no existe.

    En la pyRevit Python Shell las variables se pierden al reiniciarse la sesion,
    asi que llamar diagnosticar(doc) sin haber definido doc fallaba con
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


def _param(inst, bip):
    """(existe, escribible, valor_legible)"""
    try:
        p = inst.get_Parameter(bip)
        if p is None:
            return False, False, None
        try:
            v = p.AsValueString()
        except Exception:
            v = None
        if v is None:
            try:
                e = p.AsElementId()
                v = _eid_txt(e) if e is not None else None
            except Exception:
                v = None
        return True, (not p.IsReadOnly), v
    except Exception:
        return False, False, None


def diagnosticar(doc=None,
                 json_familias="data/diagnostico_E05_familias_v03.json",
                 json_niveles="data/diagnostico_E05_niveles_v03.json",
                 json_mapeo="data/diagnostico_E05_mapeo_v03.json",
                 json_cfg="config/mapeo_E05_v01.json"):
    doc = _resolver_doc(doc)
    if doc is None:
        print("No hay documento activo. Abre un .rvt en Revit y vuelve a ejecutar.")
        return None

    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    rutas = {}
    for k, v in (("fam", json_familias), ("niv", json_niveles),
                 ("map", json_mapeo), ("cfg", json_cfg)):
        rutas[k] = v if os.path.isabs(v) else os.path.join(root, v)

    print("=" * 72)
    print("DIAGNOSTICO E05 v03  --  documento: " + _safe(doc.Title))
    print("=" * 72)

    # ---------------- A. Niveles ----------------
    niveles = []
    for lv in FilteredElementCollector(doc).OfClass(Level):
        niveles.append({"nombre": _safe(lv.Name),
                        "elevacion_m": round(lv.Elevation * FT, 4),
                        "id": _eid_txt(lv.Id)})
    niveles.sort(key=lambda x: x["elevacion_m"])
    print("\nA. NIVELES ({}):".format(len(niveles)))
    for nv in niveles:
        print("   {:<44} {:>9.4f} m   id={}".format(
            nv["nombre"], nv["elevacion_m"], nv["id"]))

    # ---------------- B. Inventario ----------------
    inst_por_fam = {}
    for etiqueta, bic in CATS_ELECTRICAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    fn = _safe(inst.Symbol.Family.Name)
                except Exception:
                    continue
                inst_por_fam[fn] = inst_por_fam.get(fn, 0) + 1
        except Exception:
            pass

    inventario = {}
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            cat_name = _safe(fam.FamilyCategory.Name) if fam.FamilyCategory is not None else ""
            fn = _safe(fam.Name)
        except Exception:
            continue
        nombres_cat = [e for e, _ in CATS_ELECTRICAS]
        if cat_name not in nombres_cat and fn not in inst_por_fam:
            continue
        simbolos = []
        for s in _simbolos_de_familia(doc, fam):
            try:
                simbolos.append(_safe(s.Name))
            except Exception:
                pass
        if not simbolos:
            continue
        if cat_name not in inventario:
            inventario[cat_name] = {}
        inventario[cat_name][fn] = {
            "simbolos": sorted(simbolos),
            "instancias": inst_por_fam.get(fn, 0),
        }

    print("\nB. INVENTARIO DE FAMILIAS Y SIMBOLOS:")
    for cat in sorted(inventario.keys()):
        print("   --- {} ---".format(cat))
        for fam in sorted(inventario[cat].keys()):
            info = inventario[cat][fam]
            print("     {:<42} inst={:<4} {}".format(
                fam, info["instancias"], info["simbolos"]))

    _guardar(rutas["fam"], {"documento": _safe(doc.Title),
                            "niveles": niveles, "inventario": inventario})

    # ---------------- C. Instancias E05 ----------------
    marcas = []
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
                hname, hcat = None, None
                try:
                    h = inst.Host
                    if h is not None:
                        hname = _safe(h.Name)
                        hcat = _safe(h.Category.Name)
                except Exception:
                    pass
                niveles_inst = {}
                for nm, bip in _bips_nivel():
                    existe, esc, val = _param(inst, bip)
                    if existe:
                        niveles_inst[nm] = {"escribible": esc, "valor": val}
                try:
                    tipo = _safe(inst.Symbol.Name)
                except Exception:
                    tipo = ""
                marcas.append({
                    "elemento_id": _eid_txt(inst.Id),
                    "categoria": etiqueta,
                    "familia": _safe(inst.Symbol.Family.Name),
                    "tipo": tipo,
                    "comment": _safe(c),
                    "x_m": pos[0], "y_m": pos[1], "z_m": pos[2],
                    "host": hname, "host_categoria": hcat,
                    "nivel_parametros": niveles_inst,
                })
        except Exception:
            pass

    print("\nC. INSTANCIAS E05: {}".format(len(marcas)))
    for m in marcas:
        niv = ""
        for k, v in (m["nivel_parametros"] or {}).items():
            if v.get("escribible"):
                niv = "{}={}".format(k, v.get("valor"))
                break
        print("   {:<10} {:<26} {:<26} z={:<7} {:<22} {}".format(
            str(m["elemento_id"]), m["familia"][:26], str(m["host"])[:26],
            str(m["z_m"]), m["tipo"][:22], niv))

    # ---------------- D. Parametros de nivel ----------------
    print("\nD. PARAMETROS DE NIVEL (una muestra por familia):")
    vistas = {}
    for m in marcas:
        if m["familia"] in vistas:
            continue
        vistas[m["familia"]] = m
        print("   {}  {}".format(m["elemento_id"], m["familia"]))
        if not m["nivel_parametros"]:
            print("      (ninguno)")
        for k, v in sorted(m["nivel_parametros"].items()):
            print("      {:<30} escribible={:<6} valor={}".format(
                k, str(v["escribible"]), str(v["valor"])))

    _guardar(rutas["niv"], {"documento": _safe(doc.Title), "niveles": niveles,
                            "instancias_E05": marcas,
                            "candidatos_nivel_probados": [n for n, _ in _bips_nivel()]})

    # ---------------- E. Verificacion del mapeo ----------------
    print("\nE. VERIFICACION DEL MAPEO (config/mapeo_E05_v01.json):")
    mapa_fam = {}
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            k = _clave(fam.Name)
        except Exception:
            continue
        if k:
            mapa_fam[k] = fam

    resumen = {"ok": [], "errores": []}
    try:
        cfg = _leer_json(rutas["cfg"])
    except Exception as ex:
        print("   No se pudo leer el mapeo: " + _safe(ex))
        cfg = None

    if cfg:
        for bloque in sorted((cfg.get("dispositivos") or {}).keys()):
            regla = cfg["dispositivos"][bloque]
            fam_ped = regla.get("familia")
            sym_ped = regla.get("simbolo")
            fam = mapa_fam.get(_clave(fam_ped))
            if fam is None:
                msg = "familia '{}' NO existe en el documento".format(fam_ped)
                resumen["errores"].append({"bloque": bloque, "motivo": msg})
                print("   FALLA  {:<24} {}".format(bloque, msg))
                continue
            syms = {}
            for s in _simbolos_de_familia(doc, fam):
                try:
                    syms[_clave(s.Name)] = s
                except Exception:
                    pass
            if not syms:
                msg = "la familia '{}' no expone simbolos".format(fam_ped)
                resumen["errores"].append({"bloque": bloque, "motivo": msg})
                print("   FALLA  {:<24} {}".format(bloque, msg))
                continue
            ks = _clave(sym_ped)
            if ks in syms:
                resumen["ok"].append({"bloque": bloque, "familia": _safe(fam.Name),
                                      "simbolo": _safe(syms[ks].Name)})
                print("   OK     {:<24} {} -> {}".format(
                    bloque, _safe(fam.Name), _safe(syms[ks].Name)))
            else:
                msg = "simbolo '{}' no existe en '{}'. Disponibles: {}".format(
                    sym_ped, _safe(fam.Name), sorted(_safe(s.Name) for s in syms.values()))
                resumen["errores"].append({"bloque": bloque, "motivo": msg})
                print("   FALLA  {:<24} {}".format(bloque, msg))

        excl = cfg.get("excluir") or {}
        if excl:
            print("\n   Excluidos (no se modelan): " + ", ".join(sorted(excl.keys())))

        print("\n   RESUMEN: {} OK / {} fallas".format(
            len(resumen["ok"]), len(resumen["errores"])))

    _guardar(rutas["map"], {"documento": _safe(doc.Title),
                            "ok": resumen["ok"], "errores": resumen["errores"]})

    print("\n" + "=" * 72)
    print("FIN DIAGNOSTICO (nada fue modificado)")
    print("=" * 72)
    return resumen


if __name__ == "__main__":
    diagnosticar()
