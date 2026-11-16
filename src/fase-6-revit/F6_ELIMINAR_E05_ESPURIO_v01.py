# -*- coding: utf-8 -*-
"""
F6_ELIMINAR_E05_ESPURIO_v01.py
==============================
Elimina UNA instancia concreta del Apartamento Tipo E 05 sin tocar el resto.

Motivo (2026-11-09)
-------------------
De los 4 bloques 'Bala Stil Led 13W' del DXF, tres estan en su capa correcta
(ELEC-BALA LED 13 W) y el cuarto esta insertado en la capa de tuberia
'ELEC-POWER- PIPE', la unica insercion del apartamento en esa capa. No hay
lampara en esa posicion del plano: es un bloque mal insertado en el DXF.

Ese bloque quedo modelado como SONO FLEX trim en (0.527, 1.434) m sobre el
Piso 5. Este script elimina solo esa instancia.

Seguridad
---------
  * Solo considera instancias con Comments que contenga APT-E-05.
  * Solo actua dentro del radio indicado (por defecto 0.15 m) en XY.
  * Solo borra si la familia coincide.
  * Sin confirmar=True no borra nada: solo informa que encontraria.

Uso
---
    exec(open(r"...\\F6_ELIMINAR_E05_ESPURIO_v01.py").read())

    eliminar(doc)                        # simulacion
    eliminar(doc, confirmar=True)        # elimina
    eliminar(doc, x=0.527, y=1.434, familia="SONO FLEX trim", confirmar=True)
"""
import math
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Transaction,
)

FT = 0.3048

CATS = [BuiltInCategory.OST_ElectricalFixtures, BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_LightingDevices,
        BuiltInCategory.OST_DataDevices, BuiltInCategory.OST_CommunicationDevices,
        BuiltInCategory.OST_TelephoneDevices]

# Posicion de la lampara espuria, en metros sobre el Piso 5
X_DEFECTO = 0.527
Y_DEFECTO = 1.434
FAMILIA_DEFECTO = "SONO FLEX trim"
RADIO_DEFECTO = 0.15


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


def dist_xy(x1, y1, x2, y2):
    return math.hypot(x1 - x2, y1 - y2)


def _candidatas(doc, familia, x, y, radio):
    out = []
    for bic in CATS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                try:
                    cp = inst.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    c = cp.AsString() if cp is not None else ""
                except Exception:
                    c = ""
                if not (c and "APT-E-05" in c):
                    continue
                try:
                    fam = _safe(inst.Symbol.Family.Name)
                except Exception:
                    continue
                if _clave(fam) != _clave(familia):
                    continue
                try:
                    p = inst.Location.Point
                except Exception:
                    continue
                xm = p.X * FT
                ym = p.Y * FT
                zm = p.Z * FT
                d = dist_xy(xm, ym, x, y)
                if d <= radio:
                    out.append({"inst": inst, "elemento_id": _eid_txt(inst.Id),
                                "familia": fam, "x_m": round(xm, 4),
                                "y_m": round(ym, 4), "z_m": round(zm, 4),
                                "dist_m": round(d, 4)})
        except Exception:
            pass
    return out


def eliminar(doc=None, confirmar=False, x=X_DEFECTO, y=Y_DEFECTO,
             familia=FAMILIA_DEFECTO, radio=RADIO_DEFECTO):
    doc = _resolver_doc(doc)
    if doc is None:
        print("No hay documento activo. Abre un .rvt en Revit y vuelve a ejecutar.")
        return {"ok": False}

    print("=" * 70)
    print("Eliminar instancia espuria E05")
    print("  documento: " + _safe(doc.Title))
    print("  objetivo : {}  en ({:.3f}, {:.3f}) m  radio {:.2f} m".format(
        familia, x, y, radio))
    print("=" * 70)

    encontradas = _candidatas(doc, familia, x, y, radio)
    print("\nEncontradas: {}".format(len(encontradas)))
    for e in encontradas:
        print("   {}  {}  x={} y={} z={}  dist={} m".format(
            e["elemento_id"], e["familia"], e["x_m"], e["y_m"], e["z_m"], e["dist_m"]))

    if not encontradas:
        print("\nNada que eliminar. Verifica las coordenadas.")
        return {"ok": True, "eliminados": 0}

    if not confirmar:
        print("\nSIMULACION: se eliminarian {} instancia(s).".format(len(encontradas)))
        print("Ejecuta eliminar(doc, confirmar=True) para eliminarlas.")
        return {"ok": True, "eliminados": 0, "candidatas": len(encontradas)}

    t = Transaction(doc, "F6 - Eliminar E05 espurio")
    t.Start()
    eliminados = 0
    try:
        for e in encontradas:
            try:
                doc.Delete(e["inst"].Id)
                eliminados += 1
                print("   eliminada {}".format(e["elemento_id"]))
            except Exception as ex:
                print("   fallo al eliminar {}: {}".format(
                    e["elemento_id"], _safe(ex)))
    finally:
        t.Commit()

    print("\nRESULTADO: eliminados={}".format(eliminados))
    return {"ok": True, "eliminados": eliminados}


if __name__ == "__main__":
    try:
        _c = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _c = False
    eliminar(confirmar=_c)
