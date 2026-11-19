# -*- coding: utf-8 -*-
"""
test_minimo_wrapper.py
======================
Script minimo para validar que MiAddin.dll carga y PlaceFaceBased funciona.
Probar ANTES de masificar.

Uso en pyRevit Python Shell (Revit 2026):
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\test_minimo_wrapper.py").read())
    test_carga()
    test_un_dispositivo(doc)

IMPORTANTE: este script usa MiAddinLoader.py (AddReferenceByPath),
NO clr.AddReference("name") que falla con:
    IOError: Could not add reference to assembly MiAddin
"""

import os
import sys

# Cargar el wrapper via loader robusto (AddReferenceByPath con fallbacks)
# Asume que MiAddinLoader.py esta en la misma carpeta que este script.
_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit"
_LOADER = os.path.join(_HERE, "MiAddinLoader.py")
if not os.path.exists(_LOADER):
    # Buscar en ruta fallback comun
    _LOADER = os.path.join(os.environ.get("REVITELECTRICO_ROOT",
                                          r"D:\Work\PROJECTS\RevitElectrico"),
                          "src", "fase-6-revit", "MiAddinLoader.py")
exec(open(_LOADER).read())
# Ahora `Placer` esta disponible en el scope global.


def test_carga():
    """Solo valida que la DLL carga y expone Placer."""
    # `Placer` ya viene del loader (MiAddinLoader.py)
    print "[OK] Placer cargado correctamente"
    print "[OK] Placer.Version():", Placer.Version()
    print "[OK] Metodos disponibles:"
    print "     - PlaceFaceBased(doc, faceRef, uv, param, symbol)"
    print "     - PlaceFaceBasedAtPoint(doc, face, point, param, symbol)"
    print "     - ProjectPointToFace(face, point)"
    print "     - DiagnoseSymbol(symbol)"
    return True


def test_un_dispositivo(doc):
    """
    Coloca UN FamilySymbol face-based en un muro cercano al primer
    dispositivo del plan F01. Sirve para validar el wiring completo.
    """
    import json
    import os
    import math
    from Autodesk.Revit.DB import (
        Transaction, FilteredElementCollector, FamilySymbol,
        Wall, BuiltInCategory, XYZ,
    )

    import clr  # noqa: F401  (ya importado por el loader)
    # Placer ya viene del loader (MiAddinLoader.py)

    root = os.environ.get("REVITELECTRICO_ROOT",
                          r"D:\Work\PROJECTS\RevitElectrico")
    plan_path = os.path.join(root, "data", "plan_F01_v01.json")

    with open(plan_path, "r") as f:
        plan = json.load(f)
    dispositivos = plan.get("dispositivos", plan) if isinstance(plan, dict) else plan
    d = dispositivos[0]
    print "Probando con dispositivo:", d.get("family_name"), d.get("id_bloque")

    p = d["placement_pt"]
    punto = XYZ(p[0], p[1], p[2])

    # Encontrar muro
    muros = FilteredElementCollector(doc).OfClass(Wall)
    muro_cercano = None
    mejor_d = 0.5
    for w in muros:
        try:
            loc = w.Location
            if loc and loc.GetType().Name == "LocationCurve":
                r = loc.Curve.Project(punto)
                if r and r.XYZPoint:
                    pp = r.XYZPoint
                    d_ = math.sqrt((pp.X - punto.X) ** 2 + (pp.Y - punto.Y) ** 2)
                    if d_ < mejor_d:
                        mejor_d = d_
                        muro_cercano = w
        except Exception:
            continue

    if not muro_cercano:
        print "[FAIL] No se encontro muro cercano"
        return False

    print "Muro encontrado. Dist:", mejor_d, "m"

    # Face mas cercana
    from Autodesk.Revit.DB import Options
    opt = Options()
    geom = muro_cercano.get_Geometry(opt)
    face = None
    for obj in geom:
        if obj.GetType().Name == "Solid":
            for f in obj.Faces:
                try:
                    n = f.Normal
                    if abs(n.Z) < 0.9:  # vertical
                        r = f.Project(punto)
                        if r and r.XYZPoint:
                            if face is None:
                                face = f
                                break
                except Exception:
                    continue

    if not face:
        print "[FAIL] No se encontro face vertical en el muro"
        return False

    # FamilySymbol
    sym = None
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_ElectricalFixtures))
    for s in col:
        if s.Family.Name == d["family_name"]:
            sym = s
            break

    if not sym:
        print "[FAIL] FamilySymbol no encontrado:", d["family_name"]
        return False

    if not sym.IsActive:
        sym.Activate()

    # Diagnostico
    print Placer.DiagnoseSymbol(sym)

    # Transaccion
    t = Transaction(doc, "Test MiAddin wrapper")
    t.Start()
    try:
        inst = Placer.PlaceFaceBasedAtPoint(doc, face, punto, 0.0, sym)
        t.Commit()
        if inst is None:
            print "[FAIL] PlaceFaceBasedAtPoint devolvio None"
            return False
        print "[OK] FamilyInstance creada. Id:", inst.Id.IntegerValue
        return True
    except Exception as ex:
        t.RollBack()
        print "[FAIL] Excepcion:", str(ex)
        return False


if __name__ == "__main__":
    test_carga()
    try:
        doc  # noqa: F821
        test_un_dispositivo(doc)
    except NameError:
        from pyrevit import revit
        doc = revit.doc
        test_un_dispositivo(doc)
