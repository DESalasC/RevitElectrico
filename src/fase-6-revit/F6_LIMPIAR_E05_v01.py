# -*- coding: utf-8 -*-
"""
F6_LIMPIAR_E05_v01.py
=====================
Borra los elementos que la auditoria marco como sobrantes, sin tocar nada mas.

Que borra
---------
Lee `data/auditoria_E05_v03.json` (que genera F6_AUDITAR_E05_v03.py) y elimina
EXCLUSIVAMENTE los ElementId de:

    candidatos_borrado   -> duplicados y familias fuera del mapeo

NO borra:
    * los 'faltantes' (no existen)
    * los de 'revisar_manualmente' (requieren criterio humano)
    * las 'anclas' (tablero y medidor)
    * nada de F 01 ni F 02

Por que asi y no con un filtro generico
---------------------------------------
Tras varias corridas quedaron instancias con familias viejas
(M_Pulsador - Interruptor) y duplicados de la misma familia. Borrar por
"Comments = APT-E-05-P5" arrastraria tambien las instancias correctas. Por eso
el borrado es por lista explicita de Ids, revisada antes de ejecutar.

Uso
---
    exec(open(r"...\\F6_LIMPIAR_E05_v01.py").read())

    limpiar(doc)                    # simulacion: solo informa
    limpiar(doc, confirmar=True)    # borra

Si has vuelto a auditar y el JSON cambio, vuelve a ejecutar el script: lee el
archivo en cada llamada.
"""
import io
import json
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    Transaction,
)

# Nunca borrar estas familias, aunque aparezcan en la lista de candidatos
# (el JSON de auditoria puede ser de una version anterior con la clasificacion
# equivocada, como paso el 2026-11-09 con el tablero).
FAMILIAS_PROTEGIDAS = ("distributionpanel", "medidor")


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


def _leer_json(path):
    f = io.open(path, "r", encoding="utf-8")
    try:
        return json.load(f)
    finally:
        f.close()


def _eid_int(txt):
    """Convierte el id textual del JSON a entero para construir ElementId."""
    try:
        return int(str(txt))
    except Exception:
        return None


def limpiar(doc=None, confirmar=False,
            json_auditoria="data/auditoria_E05_v03.json"):
    doc = _resolver_doc(doc)
    if doc is None:
        print("No hay documento activo.")
        return None

    root = os.environ.get("REVITELECTRICO_ROOT") or os.path.abspath(".")
    if not os.path.isabs(json_auditoria):
        json_auditoria = os.path.join(root, json_auditoria)

    if not os.path.exists(json_auditoria):
        print("No existe el informe de auditoria: " + json_auditoria)
        print("Ejecuta primero F6_AUDITAR_E05_v03.py -> auditar(doc)")
        return None

    aud = _leer_json(json_auditoria)
    candidatos = aud.get("candidatos_borrado") or []
    revisar = aud.get("revisar_manualmente") or []

    # Guarda: nunca borrar anclas ni familias protegidas
    bloqueados = []
    filtrados = []
    for f in candidatos:
        kf = _clave(f.get("familia"))
        if any(p in kf for p in FAMILIAS_PROTEGIDAS):
            bloqueados.append(f)
        else:
            filtrados.append(f)
    candidatos = filtrados

    print("=" * 74)
    print("LIMPIEZA E05 v01  |  doc: " + _safe(doc.Title))
    print("  candidatos a borrar   : {}".format(len(candidatos)))
    print("  a revisar (no se toca): {}".format(len(revisar)))
    if bloqueados:
        print("  PROTEGIDOS y omitidos : {}".format(len(bloqueados)))
        for f in bloqueados:
            print("     {} {} (ancla, no se borra)".format(
                f.get("elemento_id"), _safe(f.get("familia"))))
    print("=" * 74)

    if not candidatos:
        print("\nNada que borrar. La auditoria no marco candidatos.")
        return {"ok": True, "eliminados": 0}

    print("\nSe eliminaran:")
    for f in candidatos:
        print("   {}  {:<32} {:<18} ({:.2f},{:.2f},{:.2f})  {}".format(
            f.get("elemento_id"), _safe(f.get("familia")), _safe(f.get("tipo")),
            f.get("x", 0), f.get("y", 0), f.get("z", 0), _safe(f.get("motivo"))))

    if revisar:
        print("\nNO se tocaran (revisar manualmente):")
        for f in revisar[:10]:
            print("   {}  {:<32} {}".format(
                f.get("elemento_id"), _safe(f.get("familia")), _safe(f.get("motivo"))))

    if not confirmar:
        print("\nSIMULACION: no se ha borrado nada.")
        print("Ejecuta limpiar(doc, confirmar=True) para eliminar los {}.".format(
            len(candidatos)))
        return {"ok": True, "eliminados": 0, "candidatos": len(candidatos)}

    from Autodesk.Revit.DB import ElementId

    t = Transaction(doc, "F6 - Limpiar E05 (auditoria)")
    t.Start()
    eliminados = 0
    fallos = []
    try:
        cats_electricas = (
            BuiltInCategory.OST_ElectricalFixtures,
            BuiltInCategory.OST_ElectricalEquipment,
            BuiltInCategory.OST_LightingFixtures,
            BuiltInCategory.OST_LightingDevices,
            BuiltInCategory.OST_DataDevices,
            BuiltInCategory.OST_CommunicationDevices,
            BuiltInCategory.OST_TelephoneDevices,
        )
        ids_electricas = [int(c) for c in cats_electricas]
        for f in candidatos:
            n = _eid_int(f.get("elemento_id"))
            if n is None:
                fallos.append({"id": f.get("elemento_id"), "motivo": "id no numerico"})
                continue
            try:
                el = doc.GetElement(ElementId(System.Int64(n)))
            except Exception:
                el = None
            if el is None:
                fallos.append({"id": f.get("elemento_id"), "motivo": "no existe"})
                continue
            # Guardia: categoria eléctrica, apartamento E 05, nunca F 01 ni F 02
            try:
                bic_int = el.Category.Id.IntegerValue if el.Category is not None else -1
            except Exception:
                bic_int = -1
            p_comments = el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            comentarios = p_comments.AsString() if p_comments is not None else ""
            es_electrica = bic_int in ids_electricas
            es_e05 = ("E-05" in comentarios) or ("APT-E-05" in comentarios)
            es_f01_f02 = ("F 01" in comentarios) or ("F 02" in comentarios)
            if not es_electrica or not es_e05 or es_f01_f02:
                fallos.append({
                    "id": f.get("elemento_id"),
                    "motivo": "guardia: electrica={} e05={} f01f02={}".format(
                        es_electrica, es_e05, es_f01_f02),
                })
                continue
            try:
                doc.Delete(el.Id)
                eliminados += 1
                print("   eliminado {}".format(f.get("elemento_id")))
            except Exception as ex:
                fallos.append({"id": f.get("elemento_id"), "motivo": _safe(ex)})
    finally:
        t.Commit()

    print("\nRESULTADO: eliminados={} fallos={}".format(eliminados, len(fallos)))
    if fallos:
        for fl in fallos[:10]:
            print("   - {}: {}".format(fl.get("id"), fl.get("motivo")))
    print("\nVuelve a ejecutar la auditoria para confirmar el estado.")
    return {"ok": True, "eliminados": eliminados, "fallos": fallos}


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    limpiar(confirmar=_c)
