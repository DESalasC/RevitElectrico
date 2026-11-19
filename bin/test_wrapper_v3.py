# -*- coding: utf-8 -*-
"""
test_wrapper_v3.py
==================
Test minimo y SELF-CONTAINED para validar MiAddin.dll v3 (con reflexion).

Este script:
  1. Carga MiAddin.dll via clr.AddReferenceByPath (NO clr.AddReference).
  2. Lista las sobrecargas de NewFamilyInstance en tu Revit real.
  3. Prueba PlaceFaceBasedByReference con 1 dispositivo del plan F01.

Reemplaza a cualquier script anterior que use clr.AddReference("MiAddin").

Uso en pyRevit Python Shell (Revit 2026):
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\test_wrapper_v3.py").read())

NO necesitas pasar argumentos: usa 'doc' del scope global si esta,
sino obtiene via pyrevit.revit.doc.
"""

import os
import sys
import clr


# ============================================================================
# 1. CONFIGURAR RUTA A MiAddin.dll
# ============================================================================
# Ajusta esta ruta si tu DLL esta en otro sitio.
DLL_PATH = os.environ.get(
    "MIADDIN_DLL",
    r"D:\Work\PROJECTS\RevitElectrico\bin\MiAddin.dll"
)
if not os.path.exists(DLL_PATH):
    # Buscar en el repo del proyecto (donde descargaste el paquete)
    root = os.environ.get("REVITELECTRICO_ROOT", r"D:\Work\PROJECTS\RevitElectrico")
    candidates = [
        os.path.join(root, "bin", "MiAddin.dll"),
        os.path.join(root, "MiAddin", "build", "MiAddin.dll"),
        os.path.join(root, "MiAddin", "MiAddin.dll"),
    ]
    for c in candidates:
        if os.path.exists(c):
            DLL_PATH = c
            break

print "[test_wrapper_v3] DLL_PATH:", DLL_PATH
if not os.path.exists(DLL_PATH):
    print "FAIL: DLL no encontrada. Setea MIADDIN_DLL=ruta\\a\\MiAddin.dll"
    sys.exit(1)


# ============================================================================
# 2. CARGAR LA DLL - usando AddReferenceByPath (NO AddReference)
# ============================================================================
# clr.AddReference("name") NO funciona: busca en GAC/PrivateBinPath.
# clr.AddReferenceByPath(ruta_absoluta) SI carga desde filesystem.
try:
    clr.AddReferenceByPath(DLL_PATH)
    print "[OK] clr.AddReferenceByPath exitoso"
except Exception as ex:
    print "FAIL AddReferenceByPath:", str(ex)
    print "Probando fallbacks..."
    # Fallback 1: AddReferenceToFileAndPath
    try:
        folder = os.path.dirname(DLL_PATH)
        if folder not in sys.path:
            sys.path.append(folder)
        clr.AddReferenceToFileAndPath(DLL_PATH)
        print "[OK] Fallback AddReferenceToFileAndPath exitoso"
    except Exception as ex2:
        # Fallback 2: System.Reflection.Assembly.LoadFrom
        try:
            import System
            asm = System.Reflection.Assembly.LoadFrom(DLL_PATH)
            clr.AddReference(asm)
            print "[OK] Fallback Assembly.LoadFrom exitoso"
        except Exception as ex3:
            print "TODOS LOS METODOS FALLARON:"
            print "  1.", str(ex)
            print "  2.", str(ex2)
            print "  3.", str(ex3)
            sys.exit(1)

from MiAddin import Placer
print "[OK] Placer.Version():", Placer.Version()


# ============================================================================
# 3. LISTAR LAS SOBRECARGAS DISPONIBLES EN TU REVIT
# ============================================================================
# Esto lista las ~10 sobrecargas de NewFamilyInstance que Revit 2026 expone.
# Sirve para confirmar que la reflexion del wrapper encuentra la correcta.
print ""
print "=" * 70
print "SOBRECARGAS DE NewFamilyInstance EN TU REVIT:"
print "=" * 70
try:
    doc  # noqa: F821 - viene del scope global de pyRevit
except NameError:
    try:
        from pyrevit import revit
        doc = revit.doc
    except Exception:
        print "(no se pudo obtener 'doc' - ignora este paso)"
        doc = None

if doc is not None:
    print Placer.ListNewFamilyInstanceOverloads(doc)


# ============================================================================
# 4. PROBAR PlaceFaceBasedByReference CON 1 DISPOSITIVO
# ============================================================================
def probar_un_dispositivo(doc):
    """Prueba el wrapper con un dispositivo real del plan F01."""
    import json
    import math
    from Autodesk.Revit.DB import (
        Transaction, FilteredElementCollector, Wall, FamilySymbol,
        XYZ, BuiltInCategory, HostObjectUtils, ShellLayerType,
    )

    # Plan F01
    root = os.environ.get("REVITELECTRICO_ROOT", r"D:\Work\PROJECTS\RevitElectrico")
    plan_path = os.path.join(root, "data", "plan_F01_v01.json")
    if not os.path.exists(plan_path):
        print "Plan no encontrado:", plan_path
        return False

    with open(plan_path, "r") as f:
        plan = json.load(f)
    dispositivos = plan.get("dispositivos", plan) if isinstance(plan, dict) else plan
    d = dispositivos[0]
    print ""
    print "Probando con dispositivo:", d.get("family_name"), d.get("id_bloque")

    p = d["placement_pt"]
    punto = XYZ(p[0], p[1], p[2])

    # Encontrar muro cercano
    muro_cercano = None
    mejor_d = 0.5
    for w in FilteredElementCollector(doc).OfClass(Wall):
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
        print "FAIL: no se encontro muro cercano al punto", punto
        return False
    print "Muro encontrado. Dist:", mejor_d, "m"

    # OBTENER REFERENCES DE LAS CARAS DEL MURO via HostObjectUtils
    # ESTO es lo que SIEMPRE devuelve References validas.
    refs_interior = HostObjectUtils.GetSideFaces(muro_cercano, ShellLayerType.Interior)
    refs_exterior = HostObjectUtils.GetSideFaces(muro_cercano, ShellLayerType.Exterior)
    print "References interior:", len(refs_interior)
    print "References exterior:", len(refs_exterior)

    # Elegir la Reference cuya Face proyecta el punto mas cercano
    mejor_ref = None
    mejor_dist = 1e9
    for ref in list(refs_interior) + list(refs_exterior):
        try:
            uv = Placer.ProjectPointByReference(doc, ref, punto)
            if uv is None:
                continue
            # Calcular dist via la Face
            face = Placer.GetFaceFromReference(doc, ref)
            if face is None:
                continue
            r = face.Project(punto)
            if r and r.XYZPoint:
                pp = r.XYZPoint
                d_ = math.sqrt((pp.X - punto.X) ** 2 +
                               (pp.Y - punto.Y) ** 2 +
                               (pp.Z - punto.Z) ** 2)
                if d_ < mejor_dist:
                    mejor_dist = d_
                    mejor_ref = ref
        except Exception as ex:
            print "  (ref omitida:", str(ex)[:80], ")"
            continue

    if mejor_ref is None:
        print "FAIL: ninguna Reference proyecta el punto"
        return False
    print "Mejor Reference encontrada. Dist proyeccion:", mejor_dist, "m"

    # Buscar FamilySymbol
    sym = None
    for s in (FilteredElementCollector(doc)
              .OfClass(FamilySymbol)
              .OfCategory(BuiltInCategory.OST_ElectricalFixtures)):
        if s.Family.Name == d["family_name"]:
            sym = s
            break
    if sym is None:
        print "FAIL: FamilySymbol no encontrado:", d["family_name"]
        return False
    if not sym.IsActive:
        sym.Activate()
    print "FamilySymbol:", Placer.DiagnoseSymbol(sym)

    # Transaccion + llamada al wrapper
    t = Transaction(doc, "Test MiAddin v3 reflexion")
    t.Start()
    try:
        # ESTA es la llamada clave. Una sola linea. Sin manejar UV ni IntersectionResult.
        inst = Placer.PlaceFaceBasedByReference(doc, mejor_ref, punto, 0.0, sym)
        t.Commit()
        if inst is None:
            print "FAIL: PlaceFaceBasedByReference devolvio None"
            return False
        print "[OK] FamilyInstance creada. Id:", inst.Id.IntegerValue
        return True
    except Exception as ex:
        t.RollBack()
        print "FAIL Excepcion:", str(ex)
        return False


if __name__ == "__main__":
    if doc is not None:
        probar_un_dispositivo(doc)
    else:
        print "(no se probo con dispositivo: 'doc' no disponible)"
