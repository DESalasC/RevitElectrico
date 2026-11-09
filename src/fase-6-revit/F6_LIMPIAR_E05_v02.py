# -*- coding: utf-8 -*-
"""
F6_LIMPIAR_E05_v02.py
=====================
Borra los elementos que la auditoria marco como sobrantes, sin tocar nada mas.

CORRECCION frente a v01 (corrida 2026-11-09 16:35)
--------------------------------------------------
  v01 devolvio "eliminados=0 fallos=24: no existe" porque reconstruia el
  ElementId a partir del texto guardado en el JSON:

      doc.GetElement(ElementId(5670939))   ->  None

  En Revit 2026 ese camino no resuelve el elemento. Ahora NO se reconstruye
  ningun ElementId: se indexan las instancias del documento por su id textual
  (que es justo el valor que la auditoria capturo de ellas) y se borra por
  busqueda directa en ese indice. Si aun asi no aparece, se intenta GetElement
  como respaldo y se reporta.

Que borra
---------
Lee `data/auditoria_E05_v03.json` y elimina EXCLUSIVAMENTE los id de
`candidatos_borrado`. Nunca borra familias protegidas (tablero, medidor),
aunque el JSON venga de una version anterior.

Uso
---
    exec(open(r"...\\F6_LIMPIAR_E05_v02.py").read())

    limpiar(doc)                    # simulacion
    limpiar(doc, confirmar=True)    # borra
"""
import io
import json
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    Transaction,
)

CATS = [BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
        BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_TelephoneDevices]

# Nunca borrar estas familias
FAMILIAS_PROTEGIDAS = ("distributionpanel", "medidor")


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


def _leer_json(path):
    f = io.open(path, "r", encoding="utf-8")
    try:
        return json.load(f)
    finally:
        f.close()


def _indice(doc):
    """{id textual: instancia} de todas las instancias electricas del documento."""
    idx = {}
    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    idx[_eid_txt(inst.Id)] = inst
                except Exception:
                    pass
        except Exception:
            pass
    return idx


def _variantes(txt):
    """Posibles representaciones del id para localizarlo en el indice."""
    s = str(txt).strip()
    out = [s]
    try:
        n = int(s)
        out.append(str(n))
    except Exception:
        pass
    return out


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
    print("LIMPIEZA E05 v02  |  doc: " + _safe(doc.Title))
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

    index = _indice(doc)
    print("\nInstancias electricas indexadas en el documento: {}".format(len(index)))

    resueltos = []
    no_hallados = []
    for f in candidatos:
        inst = None
        for v in _variantes(f.get("elemento_id")):
            if v in index:
                inst = index[v]
                break
        if inst is None:
            no_hallados.append(f)
        else:
            resueltos.append((f, inst))

    print("  resueltos por indice : {}".format(len(resueltos)))
    print("  no hallados          : {}".format(len(no_hallados)))

    print("\nSe eliminaran:")
    for f, inst in resueltos:
        print("   {}  {:<32} {:<18} ({:.2f},{:.2f},{:.2f})  {}".format(
            f.get("elemento_id"), _safe(f.get("familia")), _safe(f.get("tipo")),
            f.get("x", 0), f.get("y", 0), f.get("z", 0), _safe(f.get("motivo"))))

    if no_hallados:
        print("\nNO HALLADOS en el documento (no se pueden borrar):")
        for f in no_hallados[:12]:
            print("   {}  {}".format(f.get("elemento_id"), _safe(f.get("familia"))))
        print("   Ejecuta de nuevo la auditoria: el JSON puede estar desfasado.")

    if revisar:
        print("\nNO se tocaran (revisar manualmente):")
        for f in revisar[:10]:
            print("   {}  {:<32} {}".format(
                f.get("elemento_id"), _safe(f.get("familia")), _safe(f.get("motivo"))))

    if not confirmar:
        print("\nSIMULACION: no se ha borrado nada.")
        print("Ejecuta limpiar(doc, confirmar=True) para eliminar los {}.".format(
            len(resueltos)))
        return {"ok": True, "eliminados": 0, "resueltos": len(resueltos),
                "no_hallados": len(no_hallados)}

    t = Transaction(doc, "F6 - Limpiar E05 (auditoria v02)")
    t.Start()
    eliminados = 0
    fallos = []
    try:
        for f, inst in resueltos:
            try:
                doc.Delete(inst.Id)
                eliminados += 1
                print("   eliminado {}".format(f.get("elemento_id")))
            except Exception as ex:
                fallos.append({"id": f.get("elemento_id"), "motivo": _safe(ex)})
    finally:
        t.Commit()

    print("\nRESULTADO: eliminados={} fallos={} no_hallados={}".format(
        eliminados, len(fallos), len(no_hallados)))
    for fl in fallos[:10]:
        print("   - {}: {}".format(fl.get("id"), fl.get("motivo")))
    print("\nVuelve a ejecutar la auditoria para confirmar el estado.")
    return {"ok": True, "eliminados": eliminados, "fallos": fallos,
            "no_hallados": len(no_hallados)}


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    limpiar(confirmar=_c)
