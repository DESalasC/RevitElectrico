# -*- coding: utf-8 -*-
"""
RE7_BORRAR_SIN_LOCATION_v01.py

Borra los dispositivos electricos SIN Location utilizable (ni LocationPoint
ni LocationCurve), solicitado por el operador tras la aplicacion de Marks.

Salvaguardas:
  * Antes de borrar, escribe la lista completa a
    data/f7_sin_location_borrados_v01.json (trazabilidad aunque se pierda
    el modelo sin guardar).
  * Si el numero de candidatos supera MAX_ESPERADO (50), ABORTA sin borrar:
    el operador aprobo ~33, no una purga masiva.
  * Solo actua sobre las 6 categorias electricas del proyecto.
  * Todo en UNA transaccion; si algo falla, RollBack.
  * Verifica despues que los elementos ya no existen.

Entorno: pyRevit IronPython 2.7
"""
import datetime
import json
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
    Transaction,
)
from System import Int64

VERSION = "v01_borrar_sin_location"
FT_A_MM = 304.8
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
MAX_ESPERADO = 50

CATEGORIAS = [
    ("ElectricalFixtures", BuiltInCategory.OST_ElectricalFixtures),
    ("LightingFixtures", BuiltInCategory.OST_LightingFixtures),
    ("DataDevices", BuiltInCategory.OST_DataDevices),
    ("TelephoneDevices", BuiltInCategory.OST_TelephoneDevices),
    ("CommunicationDevices", BuiltInCategory.OST_CommunicationDevices),
    ("MechanicalEquipment", BuiltInCategory.OST_MechanicalEquipment),
]


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


def nombre_familia(el):
    try:
        if el.Symbol is not None and el.Symbol.Family is not None:
            return el.Symbol.Family.Name
    except Exception:
        pass
    return None


def nombre_tipo(el):
    try:
        if el.Symbol is not None:
            p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p is not None:
                return p.AsString()
    except Exception:
        pass
    return None


def nombre_nivel(el):
    try:
        lid = el.LevelId
        if lid is not None and lid.IntegerValue > 0:
            lvl = el.Document.GetElement(lid)
            if lvl is not None:
                return lvl.Name
    except Exception:
        pass
    return None


def host_id(el):
    try:
        h = el.Host
        if h is not None:
            return id_de(h)
    except Exception:
        pass
    return None


def bbox_mm(el):
    try:
        bb = el.get_BoundingBox(None)
        if bb is None:
            return None
        return {
            "min": [round(bb.Min.X * FT_A_MM, 1), round(bb.Min.Y * FT_A_MM, 1),
                    round(bb.Min.Z * FT_A_MM, 1)],
            "max": [round(bb.Max.X * FT_A_MM, 1), round(bb.Max.Y * FT_A_MM, 1),
                    round(bb.Max.Z * FT_A_MM, 1)],
        }
    except Exception:
        return None


def group_id(el):
    """Devuelve el id del grupo al que pertenece el elemento, o 0 si no tiene."""
    try:
        g = el.GroupId
        if g is None:
            return 0
        v = g.IntegerValue if hasattr(g, "IntegerValue") else g.Value
        return int(v)
    except Exception:
        return 0


def es_miembro_de_grupo(el):
    return group_id(el) != 0 and group_id(el) != -1


def tiene_location(el):
    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            return True
        if isinstance(loc, LocationCurve):
            return True
    except Exception:
        pass
    return False


def main():
    log("=" * 70)
    log("RE7_BORRAR_SIN_LOCATION_%s" % VERSION)
    log("utc=%s" % datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    doc = obtener_doc()
    if doc is None:
        log("ERROR: no hay documento activo.")
        return 1
    log("documento=%r" % doc.Title)

    candidatos = []
    por_cat = defaultdict(int)
    for (nombre_cat, bic) in CATEGORIAS:
        for el in FilteredElementCollector(doc).OfCategory(bic).ToElements():
            if tiene_location(el):
                continue
            d = {
                "id": id_de(el),
                "categoria": nombre_cat,
                "familia": nombre_familia(el),
                "tipo": nombre_tipo(el),
                "mark": valor_texto(el, ["Mark"]),
                "comment": valor_texto(el, ["Comments"]),
                "nivel": nombre_nivel(el),
                "host_id": host_id(el),
                "group_id": group_id(el),
                "es_miembro_de_grupo": es_miembro_de_grupo(el),
                "bbox": bbox_mm(el),
            }
            candidatos.append(d)
            por_cat[nombre_cat] += 1

    log("Candidatos sin Location: %d" % len(candidatos))
    en_grupo = [d for d in candidatos if d["es_miembro_de_grupo"]]
    log("De ellos, MIEMBROS DE GRUPO (NO se borran): %d" % len(en_grupo))
    for d in en_grupo:
        log("   GRUPO id=%-9s grupo=%-9s %-22s %-20s" % (
            d["id"], d["group_id"], d["categoria"], (d["tipo"] or "-")[:20]))
    log("Por categoria: %s" % dict(por_cat))
    for d in candidatos:
        log("   id=%-9s %-22s %-24s %-20s nivel=%-7s host=%s grupo=%s bb=%s mark=%r" % (
            d["id"], d["categoria"], (d["familia"] or "-")[:24],
            (d["tipo"] or "-")[:20], d["nivel"] or "-", d["host_id"],
            d["group_id"], "si" if d["bbox"] else "no", d["mark"]))

    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip() or DEFAULT_ROOT
    lista_path = os.path.join(raiz, "data", "f7_sin_location_borrados_v01.json")
    lista = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "aviso": "Lista de dispositivos sin Location ANTES de borrar",
        "total": len(candidatos),
        "por_categoria": dict(por_cat),
        "dispositivos": candidatos,
    }
    try:
        with open(lista_path, "w") as f:
            f.write(json.dumps(lista, ensure_ascii=True, indent=1))
        log("Lista guardada ANTES de borrar: %s" % lista_path)
    except Exception as ex:
        log("ERROR guardando la lista: %s" % ex)
        log("Se aborta el borrado para no perder trazabilidad.")
        return 1

    if not candidatos:
        log("No hay dispositivos sin Location. Nada que borrar.")
        return 0

    if len(candidatos) > MAX_ESPERADO:
        log("")
        log("ABORTADO: %d candidatos supera el maximo esperado (%d)." % (
            len(candidatos), MAX_ESPERADO))
        log("Revisa la lista antes de continuar; no se borro nada.")
        return 1

    borrables = [d for d in candidatos if not d["es_miembro_de_grupo"]]
    log("")
    log("Aptos para borrar (sin grupo): %d de %d" % (len(borrables), len(candidatos)))
    if len(borrables) != len(candidatos):
        log("Los %d miembros de grupo quedan intactos por seguridad." % (
            len(candidatos) - len(borrables)))
    if not borrables:
        log("No hay elementos borrables (todos son miembros de grupo). Se aborta.")
        return 1

    borrados = 0
    fallos = []
    trans = Transaction(doc, "RE7_BORRAR_SIN_LOCATION_v01")
    trans.Start()
    try:
        for d in borrables:
            try:
                el = doc.GetElement(ElementId(Int64(d["id"])))
                if el is None:
                    fallos.append({"id": d["id"], "error": "desaparecio antes de borrar"})
                    continue
                if es_miembro_de_grupo(el):
                    fallos.append({"id": d["id"], "error": "es miembro de grupo (guard)"})
                    continue
                doc.Delete(el.Id)
                borrados += 1
            except Exception as ex:
                fallos.append({"id": d["id"], "error": str(ex)[:150]})
        trans.Commit()
        log("Transaccion COMMIT.")
    except Exception:
        trans.RollBack()
        log("ERROR: transaccion revertida, no se borro nada.")
        log(traceback.format_exc())
        return 1

    quedan = [d["id"] for d in borrables
              if doc.GetElement(ElementId(Int64(d["id"]))) is not None]

    log("")
    log("=" * 70)
    log("Borrados: %d | fallos: %d | siguen existiendo: %d" % (
        borrados, len(fallos), len(quedan)))
    for f in fallos:
        log("   FALLO id=%s: %s" % (f["id"], f["error"]))
    if quedan:
        log("   SIGUEN EXISTIENDO: %s" % quedan)
    log("=" * 70)

    reporte = {
        "version": VERSION,
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "resumen": {
            "candidatos": len(candidatos),
            "borrados": borrados,
            "fallos": len(fallos),
            "siguen_existiendo": len(quedan),
        },
        "fallos": fallos,
        "siguen_existiendo": quedan,
    }
    out_path = os.path.join(raiz, "data", "f7_borrar_sin_location_v01.json")
    try:
        with open(out_path, "w") as f:
            f.write(json.dumps(reporte, ensure_ascii=True, indent=1))
        log("JSON: %s" % out_path)
    except Exception as ex:
        log("ERROR guardando JSON: %s" % ex)

    return 0 if (borrados == len(borrables) and not quedan) else 1


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    log("EXCEPCION NO CONTROLADA:")
    log(traceback.format_exc())
    raise SystemExit(1)
