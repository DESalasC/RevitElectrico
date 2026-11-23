# -*- coding: utf-8 -*-
"""
DIAGNOSTICAR_FAMILIAS_V01.py
Imprime los nombres de familia reales de dispositivos electricos en Revit.
Ayuda a corregir el mapeo DXF -> Revit en el script de ruteo F7.
"""
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    XYZ,
)
from System import Int64

FT_A_MM = 304.8


def id_de(elemento):
    eid_val = elemento.Id
    if hasattr(eid_val, "IntegerValue"):
        return int(eid_val.IntegerValue)
    return int(eid_val.Value)


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


def main():
    doc = obtener_doc()
    if doc is None:
        print("ERROR: no hay documento activo.")
        return 1

    cat = BuiltInCategory.OST_ElectricalFixtures
    dispositivos = []
    for el in FilteredElementCollector(doc).OfCategory(cat).ToElements():
        try:
            loc = el.Location
            if loc is None:
                continue
            pt = None
            try:
                pt = loc.Point
            except Exception:
                continue
            if pt is None:
                continue

            # Nombre de familia via SYMBOL_NAME_PARAM
            nombre_simbolo = ""
            try:
                sym = el.Symbol
                if sym is not None:
                    p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                    if p is not None:
                        nombre_simbolo = p.AsString() or ""
                    else:
                        nombre_simbolo = "NO_PARAM"
            except Exception:
                nombre_simbolo = "ERROR"

            # Nombre de familia via Family.Name
            nombre_familia = ""
            try:
                sym = el.Symbol
                if sym is not None and hasattr(sym, "Family"):
                    nombre_familia = sym.Family.Name
            except Exception:
                nombre_familia = "ERROR"

            dispositivos.append({
                "id": id_de(el),
                "x_mm": round(pt.X * FT_A_MM, 1),
                "y_mm": round(pt.Y * FT_A_MM, 1),
                "z_mm": round(pt.Z * FT_A_MM, 1),
                "simbolo": nombre_simbolo,
                "familia": nombre_familia,
                "nombre": el.Name,
            })
        except Exception:
            continue

    print("Total dispositivos electricos: %d" % len(dispositivos))
    print()
    print("=== Nombres de simbolo (SYMBOL_NAME_PARAM) ===")
    from collections import Counter
    c = Counter(d["simbolo"] for d in dispositivos)
    for nombre, n in c.most_common():
        print("  %-40s %d" % (nombre, n))

    print()
    print("=== Nombres de familia (Family.Name) ===")
    c2 = Counter(d["familia"] for d in dispositivos)
    for nombre, n in c2.most_common():
        print("  %-40s %d" % (nombre, n))

    print()
    print("=== Muestra de dispositivos con coords ===")
    for d in dispositivos[:10]:
        print("  id=%d x=%.1f y=%.1f z=%.1f simbolo=%r familia=%r" % (
            d["id"], d["x_mm"], d["y_mm"], d["z_mm"], d["simbolo"], d["familia"]))

    print()
    print("=== Dispositivos por rango F17 (X 7000-10500, Y 1000-8500) ===")
    f17 = [d for d in dispositivos if 7000 <= d["x_mm"] <= 10500 and 1000 <= d["y_mm"] <= 8500]
    print("  Total F17: %d" % len(f17))
    c3 = Counter(d["simbolo"] for d in f17)
    for nombre, n in c3.most_common():
        print("    %-40s %d" % (nombre, n))

    print()
    print("=== Dispositivos por rango F18 (X 7000-10500, Y 9000-16500) ===")
    f18 = [d for d in dispositivos if 7000 <= d["x_mm"] <= 10500 and 9000 <= d["y_mm"] <= 16500]
    print("  Total F18: %d" % len(f18))
    c4 = Counter(d["simbolo"] for d in f18)
    for nombre, n in c4.most_common():
        print("    %-40s %d" % (nombre, n))

    return 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    import traceback
    traceback.print_exc()
    raise SystemExit(1)
