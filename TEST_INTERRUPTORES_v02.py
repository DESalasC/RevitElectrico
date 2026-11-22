"""
TEST_INTERRUPTORES_v02.py - M_Interruptores OneLevelBasedHosted: receta de colocacion
Fecha: 2026-11-22

CONTEXTO: M_Interruptores es OneLevelBasedHosted (wall-hosted). El overload
wall-host coloca la instancia pero Location.Point reporta (0,0,1100.1).
En el test v01, una rotacion forzo la resolucion del hosting y la instancia
aterrizo en la pared. Este test instrumenta con BoundingBox (coordenadas
mundo, no miente) tras cada paso, probando 3 recetas:
  V1: colocar(wall-host) -> MOVE(bbox-delta a pared) -> ROTAR 90
  V2: colocar(wall-host) -> micro-ROTAR 0.5 (forzar hosting) -> MOVE -> ROTAR 90
  V3: colocar(wall-host) con punto YA PROYECTADO en la curva del muro -> ROTAR 90
Cada instancia de prueba se elimina. No queda nada permanente.

Ejecutar en pyRevit Python Shell:
  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\TEST_INTERRUPTORES_v02.py").read())
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import math

doc = __revit__.ActiveUIDocument.Document
MM = 304.8
MM_TO_FT = 0.003280839895

# Objetivo: TF 01a ELEC-I-S-1-5A (-13086, 7965) mm
X_MM, Y_MM = -13086.0, 7965.0
ALT_MM = 1100.0
x = X_MM * MM_TO_FT
y = Y_MM * MM_TO_FT

level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - 13219.0) < 10:
        level_piso5 = lvl
        break
if not level_piso5:
    raise Exception("No se encontro nivel Piso 5")
z_abs = level_piso5.Elevation + ALT_MM * MM_TO_FT
target_json = XYZ(x, y, z_abs)

sym = None
for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
    try:
        if s.Family.Name == "M_Interruptores":
            np_ = s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if np_ and np_.AsString() == "Simple":
                sym = s
                break
    except:
        pass
if not sym:
    raise Exception("No se encontro simbolo Simple")

# --- Muro mas cercano al punto JSON ---
best_w, best_d, best_t = None, 1e9, 0.0
for w in FilteredElementCollector(doc).OfClass(Wall):
    loc = w.Location
    if not isinstance(loc, LocationCurve):
        continue
    c = loc.Curve
    if not c:
        continue
    try:
        p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
        dx, dy = p1.X - p0.X, p1.Y - p0.Y
        L2 = dx * dx + dy * dy
        if L2 > 1e-12:
            tt = max(0.0, min(1.0, ((x - p0.X) * dx + (y - p0.Y) * dy) / L2))
        else:
            tt = 0.0
        d = math.hypot(x - (p0.X + tt * dx), y - (p0.Y + tt * dy))
        if d < best_d:
            best_d, best_w, best_t = d, w, tt
    except:
        continue

if not best_w:
    raise Exception("Sin muro cercano")
c = best_w.Location.Curve
wp0, wp1 = c.GetEndPoint(0), c.GetEndPoint(1)
wdx, wdy = wp1.X - wp0.X, wp1.Y - wp0.Y
target_pared = XYZ(wp0.X + best_t * wdx, wp0.Y + best_t * wdy, z_abs)

print("OBJETIVO JSON:   ({:.1f}, {:.1f})mm".format(X_MM, Y_MM))
print("Muro: dist={:.1f}mm curva=({:.1f},{:.1f})->({:.1f},{:.1f})".format(
    best_d * MM, wp0.X * MM, wp0.Y * MM, wp1.X * MM, wp1.Y * MM))
print("OBJETIVO PARED:  ({:.1f}, {:.1f})mm Z={:.1f}mm".format(
    target_pared.X * MM, target_pared.Y * MM, z_abs * MM))
print("Muro Id={}".format(int(str(best_w.Id))))


def report(inst, paso):
    lps = "noLP"
    try:
        lp = inst.Location
        if isinstance(lp, LocationPoint):
            p = lp.Point
            lps = "({:.1f}, {:.1f}, {:.1f})".format(p.X * MM, p.Y * MM, p.Z * MM)
    except:
        pass
    bbs = "sin-bbox"
    try:
        bb = inst.get_BoundingBox(None)
        if bb:
            cx = (bb.Min.X + bb.Max.X) / 2 * MM
            cy = (bb.Min.Y + bb.Max.Y) / 2 * MM
            cz = (bb.Min.Z + bb.Max.Z) / 2 * MM
            bbs = "centro=({:.1f}, {:.1f}, {:.1f})".format(cx, cy, cz)
    except:
        pass
    hs = "NINGUNO"
    try:
        h = inst.Host
        if h:
            hs = str(int(str(h.Id)))
    except:
        pass
    print("  {}: Location={} | bbox {} | Host={}".format(paso, lps, bbs, hs))


def mover_a_pared(inst):
    bb = inst.get_BoundingBox(None)
    if not bb:
        print("  MOVE omitido (sin bbox)")
        return
    cc = XYZ((bb.Min.X + bb.Max.X) / 2, (bb.Min.Y + bb.Max.Y) / 2, (bb.Min.Z + bb.Max.Z) / 2)
    delta = target_pared - cc
    ElementTransformUtils.MoveElement(doc, inst.Id, delta)
    report(inst, "tras MOVE-a-pared")


def rotar(inst, ang_deg, base_pt, etiqueta):
    ax = Line.CreateBound(base_pt, XYZ(base_pt.X, base_pt.Y, base_pt.Z + 1))
    ElementTransformUtils.RotateElement(doc, inst.Id, ax, math.radians(ang_deg))
    report(inst, etiqueta)


def v1(inst):
    mover_a_pared(inst)
    rotar(inst, 90.0, target_pared, "tras ROTAR 90")


def v2(inst):
    rotar(inst, 0.5, target_pared, "tras micro-ROT 0.5")
    mover_a_pared(inst)
    rotar(inst, 90.0, target_pared, "tras ROTAR 90")


def v3(inst):
    rotar(inst, 90.0, target_pared, "tras ROTAR 90")


def prueba(nombre, punto, pasos):
    print("")
    print("=" * 56)
    print("VARIANTE " + nombre)
    t = Transaction(doc, "TEST2 " + nombre[:2])
    t.Start()
    try:
        if not sym.IsActive:
            sym.Activate()
            doc.Regenerate()
    except:
        pass
    inst = None
    try:
        inst = doc.Create.NewFamilyInstance(punto, sym, best_w, Structure.StructuralType.NonStructural)
        report(inst, "tras COLOCAR   ")
    except Exception as ex:
        print("  COLOCAR FALLO: " + str(ex)[:120])
    if inst:
        try:
            pasos(inst)
        except Exception as ex:
            print("  PASOS ERR: " + str(ex)[:100])
        try:
            doc.Delete(inst.Id)
            print("  (instancia de prueba eliminada)")
        except:
            pass
    t.Commit()


prueba("V1: colocar(json) -> MOVE -> ROTAR", target_json, v1)
prueba("V2: colocar(json) -> microROT -> MOVE -> ROTAR", target_json, v2)
prueba("V3: colocar(punto-en-pared) -> ROTAR", target_pared, v3)

print("")
print("=" * 56)
print("TEST v02 COMPLETO - sin instancias residuales")