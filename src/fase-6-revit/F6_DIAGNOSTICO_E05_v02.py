# -*- coding: utf-8 -*-
"""
F6_DIAGNOSTICO_E05_v02.py
=========================
Diagnostico SOLO LECTURA. No crea, no borra, no mueve nada.

Responde estas preguntas:
  1. Que familias y simbolos existen REALMENTE en el documento (inventario vivo).
  2. Que instancias E05 hay: ElementId visible, familia, tipo, host, nivel, Z.
  3. Que parametros de nivel existen en esas instancias y si son escribibles
     (para resolver el problema de "Schedule Level" vacio).
  4. Que muros y techos hay cerca de cada lampara (para el caso de las balas
     que cayeron sobre un muro en vez del cielorraso).

Salidas:
  data/diagnostico_E05_familias_v02.json
  data/diagnostico_E05_niveles_v02.json

Uso en pyRevit Python Shell:
    exec(open(r"...\\F6_DIAGNOSTICO_E05_v02.py").read())
    diagnosticar(doc)
"""
import json
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Family,
    FilteredElementCollector,
    Level,
)

FT = 0.3048  # pies -> metros

CATS_INTERES = [
    ("ElectricalFixtures", BuiltInCategory.OST_ElectricalFixtures),
    ("ElectricalEquipment", BuiltInCategory.OST_ElectricalEquipment),
    ("LightingFixtures", BuiltInCategory.OST_LightingFixtures),
    ("LightingDevices", BuiltInCategory.OST_LightingDevices),
    ("DataDevices", BuiltInCategory.OST_DataDevices),
    ("CommunicationDevices", BuiltInCategory.OST_CommunicationDevices),
    ("TelephoneDevices", BuiltInCategory.OST_TelephoneDevices),
    ("Walls", BuiltInCategory.OST_Walls),
    ("Ceilings", BuiltInCategory.OST_Ceilings),
]

# Candidatos de parametro de nivel, en orden de preferencia.
# Se resuelven de forma PEREZOSA: no todos los BuiltInParameter existen en todas
# las versiones de Revit (ELEM_REFERENCE_LEVEL_PARAM no existe en Revit 2026 y
# provocaba AttributeError al importar el modulo, antes de ejecutar nada).
CANDIDATOS_NIVEL_NOMBRES = (
    "SCHEDULE_LEVEL_PARAM",
    "FAMILY_LEVEL_PARAM",
    "RBS_START_LEVEL_PARAM",
    "LEVEL_PARAM",
    "INSTANCE_REFERENCE_LEVEL_PARAM",
)


def _bips_nivel():
    """[(nombre, BuiltInParameter)] de los que existan realmente."""
    out = []
    for nm in CANDIDATOS_NIVEL_NOMBRES:
        try:
            out.append((nm, getattr(BuiltInParameter, nm)))
        except Exception:
            pass
    return out


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
    """ElementId en formato visible de Revit 2025+ (p.ej. 17RgmcKb1AhOscNgPvZfU)."""
    try:
        return str(eid)
    except Exception:
        return "?"


def _host_info(inst):
    try:
        h = inst.Host
        if h is None:
            return None, None
        try:
            cat = h.Category.Name
        except Exception:
            cat = "?"
        return _safe(h.Name), _safe(cat)
    except Exception:
        return None, None


def _valor_param(inst, bip):
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


def _bbox_metros(el):
    try:
        bb = el.get_BoundingBox(None)
        if bb is None:
            return None
        return {
            "x_min": round(bb.Min.X * FT, 3), "x_max": round(bb.Max.X * FT, 3),
            "y_min": round(bb.Min.Y * FT, 3), "y_max": round(bb.Max.Y * FT, 3),
            "z_min": round(bb.Min.Z * FT, 3), "z_max": round(bb.Max.Z * FT, 3),
        }
    except Exception:
        return None


def diagnosticar(doc, json_familias="data/diagnostico_E05_familias_v02.json",
                 json_niveles="data/diagnostico_E05_niveles_v02.json"):
    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    if not os.path.isabs(json_familias):
        json_familias = os.path.join(root, json_familias)
    if not os.path.isabs(json_niveles):
        json_niveles = os.path.join(root, json_niveles)

    print("=" * 70)
    print("DIAGNOSTICO E05 v02  --  documento: " + _safe(doc.Title))
    print("=" * 70)

    # ---------- 1. Niveles del documento ----------
    niveles = []
    for lv in FilteredElementCollector(doc).OfClass(Level):
        niveles.append({"nombre": _safe(lv.Name),
                        "elevacion_m": round(lv.Elevation * FT, 4),
                        "id": _eid_txt(lv.Id)})
    niveles.sort(key=lambda x: x["elevacion_m"])
    print("\nNIVELES ({}):".format(len(niveles)))
    for nv in niveles:
        print("  {:<28} {:>10.4f} m   id={}".format(nv["nombre"], nv["elevacion_m"], nv["id"]))

    # ---------- 2. Inventario vivo de familias y simbolos ----------
    inventario = {}
    todas_las_familias = list(FilteredElementCollector(doc).OfClass(Family).ToElements())

    for etiqueta, bic in CATS_INTERES:
        if etiqueta in ("Walls", "Ceilings"):
            continue
        inst_por_fam = {}
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    fn = _safe(inst.Symbol.Family.Name)
                except Exception:
                    continue
                inst_por_fam[fn] = inst_por_fam.get(fn, 0) + 1
        except Exception:
            pass

        fams = {}
        for fam in todas_las_familias:
            try:
                cat_name = _safe(fam.FamilyCategory.Name) if fam.FamilyCategory is not None else ""
            except Exception:
                cat_name = ""
            fn = _safe(fam.Name)
            if cat_name != etiqueta and fn not in inst_por_fam:
                continue
            simbolos = []
            for sid in fam.GetFamilySymbolIds():
                try:
                    simbolos.append(_safe(doc.GetElement(sid).Name))
                except Exception:
                    pass
            if not simbolos:
                continue
            fams[fn] = {"simbolos": sorted(simbolos),
                        "instancias": inst_por_fam.get(fn, 0)}
        if fams:
            inventario[etiqueta] = fams

    print("\nINVENTARIO DE FAMILIAS Y SIMBOLOS:")
    for cat in sorted(inventario.keys()):
        print("  --- {} ---".format(cat))
        for fam in sorted(inventario[cat].keys()):
            info = inventario[cat][fam]
            print("    {:<45} inst={:<4} simbolos={}".format(
                fam, info["instancias"], info["simbolos"]))

    fam_out = {
        "documento": _safe(doc.Title),
        "niveles": niveles,
        "inventario": inventario,
    }
    try:
        f = open(json_familias, "w")
        try:
            json.dump(fam_out, f, indent=2)
        finally:
            f.close()
        print("\nGuardado: " + json_familias)
    except Exception as ex:
        print("No se pudo guardar familias: " + _safe(ex))

    # ---------- 3. Instancias E05 + parametros de nivel ----------
    marcas = []
    for etiqueta, bic in CATS_INTERES:
        if etiqueta in ("Walls", "Ceilings"):
            continue
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
                hname, hcat = _host_info(inst)
                niveles_inst = {}
                for nm, bip in _bips_nivel():
                    existe, escribible, valor = _valor_param(inst, bip)
                    niveles_inst[nm] = {"existe": existe, "escribible": escribible, "valor": valor}
                try:
                    tipo = _safe(inst.Symbol.Name)
                except Exception:
                    tipo = ""
                try:
                    tipo = tipo + " | " + _safe(inst.Name)
                except Exception:
                    pass
                marcas.append({
                    "elemento_id": _eid_txt(inst.Id),
                    "unique_id": _safe(inst.UniqueId),
                    "categoria": etiqueta,
                    "familia": _safe(inst.Symbol.Family.Name),
                    "tipo": tipo,
                    "comment": _safe(c),
                    "x_m": pos[0], "y_m": pos[1], "z_m": pos[2],
                    "host": hname,
                    "host_categoria": hcat,
                    "nivel_parametros": niveles_inst,
                })
        except Exception:
            pass

    print("\nINSTANCIAS E05 ENCONTRADAS: {}".format(len(marcas)))
    print("  {:<26} {:<28} {:<22} {:<8} {}".format("ElementId", "Familia", "Host", "Z(m)", "Tipo"))
    for m in marcas:
        print("  {:<26} {:<28} {:<22} {:<8} {}".format(
            m["elemento_id"], m["familia"], str(m["host"])[:20], str(m["z_m"]), str(m["tipo"])[:40]))

    # ---------- 4. Parametros que contienen "level"/"nivel" en 3 instancias ----------
    detalle_params = []
    for inst in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalFixtures).WhereElementIsNotElementType():
        try:
            p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            c = p.AsString() if p is not None else ""
        except Exception:
            c = ""
        if not (c and "APT-E-05" in c):
            continue
        fila = {"elemento_id": _eid_txt(inst.Id),
                "familia": _safe(inst.Symbol.Family.Name), "parametros": []}
        try:
            for pr in inst.Parameters:
                try:
                    nm = _safe(pr.Definition.Name)
                except Exception:
                    continue
                low = nm.lower()
                if "level" not in low and "nivel" not in low:
                    continue
                try:
                    val = pr.AsValueString()
                except Exception:
                    val = None
                fila["parametros"].append({
                    "nombre": nm,
                    "escribible": (not pr.IsReadOnly),
                    "valor": _safe(val) if val is not None else None,
                })
        except Exception:
            pass
        detalle_params.append(fila)
        if len(detalle_params) >= 3:
            break

    print("\nPARAMETROS DE NIVEL (muestra {} instancias):".format(len(detalle_params)))
    for fila in detalle_params:
        print("  {}  {}".format(fila["elemento_id"], fila["familia"]))
        if not fila["parametros"]:
            print("     (ningun parametro con 'level'/'nivel')")
        for prm in fila["parametros"]:
            print("     {:<32} escribible={:<6} valor={}".format(
                prm["nombre"], str(prm["escribible"]), str(prm["valor"])))

    niv_out = {
        "documento": _safe(doc.Title),
        "niveles": niveles,
        "instancias_E05": marcas,
        "parametros_nivel_muestra": detalle_params,
        "candidatos_nivel_probados": [nm for nm, _ in _bips_nivel()],
    }
    try:
        f = open(json_niveles, "w")
        try:
            json.dump(niv_out, f, indent=2)
        finally:
            f.close()
        print("\nGuardado: " + json_niveles)
    except Exception as ex:
        print("No se pudo guardar niveles: " + _safe(ex))

    print("\n" + "=" * 70)
    print("FIN DIAGNOSTICO (nada fue modificado)")
    print("=" * 70)
    return niv_out


if __name__ == "__main__":
    diagnosticar(__revit__.ActiveUIDocument.Document)  # noqa: F821
