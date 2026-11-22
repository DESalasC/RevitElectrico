"""
TEST_INTERRUPTORES_v01.py - Diagnostico de sobrecargas para M_Interruptores
Fecha: 2026-11-22

CONTEXTO: ni el overload 4-arg con nivel (v03) ni el 3-arg sin host (v05)
colocan M_Interruptores en el punto dado: ambas mandan la instancia a
(0,0,1100). Este test prueba 6 variantes en UN dispositivo, imprime la
posicion REAL (Location.Point) despues de CADA PASO (colocar / set-level /
rotar) para identificar exactamente cual paso la mueve, y borra cada
instancia de prueba. No modifica nada permanente.

Ejecutar en pyRevit Python Shell:
  exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\TEST_INTERRUPTORES_v01.py").read())
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
z_off = ALT_MM * MM_TO_FT

# Nivel Piso 5
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - 13219.0) < 10:
        level_piso5 = lvl
        break
if not level_piso5:
    raise Exception("No se encontro nivel Piso 5")
lev_ft = level_piso5.Elevation
z_abs = lev_ft + z_off

print("OBJETIVO: X={:.1f}mm Y={:.1f}mm Z_abs={:.1f}mm Z_off={:.1f}mm".format(
    X_MM, Y_MM, z_abs * MM, z_off * MM))

# Simbolo Simple
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
    raise Exception("No se encontro simbolo Simple de M_Interruptores")


def loc_str(inst):
    try:
        lp = inst.Location
        if isinstance(lp, LocationPoint):
            p = lp.Point
            return "({:.1f}, {:.1f}, {:.1f})mm".format(p.X * MM, p.Y * MM, p.Z * MM)
        return "no-LocationPoint"
    except Exception as ex:
        return "ERR " + str(ex)[:40]


def level_str(inst):
    try:
        lv = doc.GetElement(inst.LevelId)
        return lv.Name if lv else "(sin nivel)"
    except:
        return "?"


def probar(nombre, colocar, hacer_set_level=True):
    print("")
    print("=" * 52)
    print("METODO " + nombre)
    t = Transaction(doc, "TEST " + nombre[:6])
    t.Start()
    try:
        if not sym.IsActive:
            sym.Activate()
            doc.Regenerate()
    except:
        pass
    inst = None
    try:
        inst = colocar()
        print("  tras COLOCAR:    " + loc_str(inst) + " | nivel=" + level_str(inst))
    except Exception as ex:
        print("  COLOCAR FALLO:   " + str(ex)[:130])
    if inst:
        if hacer_set_level:
            try:
                for bp in (BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
                           BuiltInParameter.LEVEL_PARAM,
                           BuiltInParameter.FAMILY_LEVEL_PARAM):
                    p = inst.get_Parameter(bp)
                    if p and not p.IsReadOnly:
                        p.Set(level_piso5.Id)
                        break
                print("  tras SET-LEVEL:  " + loc_str(inst) + " | nivel=" + level_str(inst))
            except Exception as ex:
                print("  SET-LEVEL ERR:   " + str(ex)[:80])
        try:
            pt_axis = XYZ(x, y, z_abs)
            ax = Line.CreateBound(pt_axis, XYZ(pt_axis.X, pt_axis.Y, pt_axis.Z + 1))
            inst.Location.Rotate(ax, math.radians(180.0))
            print("  tras ROTAR 180:  " + loc_str(inst))
        except Exception as ex:
            print("  ROTAR ERR:       " + str(ex)[:80])
        try:
            doc.Delete(inst.Id)
            print("  (instancia de prueba eliminada)")
        except:
            pass
    t.Commit()


# M1: 3-arg, Z absoluto (replica v05, instrumentada)
probar("M1: 3-arg z_abs (v05)",
       lambda: doc.Create.NewFamilyInstance(XYZ(x, y, z_abs), sym, Structure.StructuralType.NonStructural))

# M2: 3-arg, Z como offset
probar("M2: 3-arg z_offset",
       lambda: doc.Create.NewFamilyInstance(XYZ(x, y, z_off), sym, Structure.StructuralType.NonStructural))

# M3: 4-arg LEVEL, Z como offset
probar("M3: 4-arg level z_offset",
       lambda: doc.Create.NewFamilyInstance(XYZ(x, y, z_off), sym, level_piso5, Structure.StructuralType.NonStructural))

# M4: 4-arg LEVEL, Z absoluto (replica v03, instrumentada)
probar("M4: 4-arg level z_abs (v03)",
       lambda: doc.Create.NewFamilyInstance(XYZ(x, y, z_abs), sym, level_piso5, Structure.StructuralType.NonStructural))

# M5: 4-arg WALL como host
best_w, best_d = None, 1e9
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
            best_d, best_w = d, w
    except:
        continue
print("")
print("Muro mas cercano al objetivo: dist={:.1f}mm".format(best_d * MM))
if best_w and best_d < 1.0:
    probar("M5: 4-arg WALL-host z_abs",
           lambda: doc.Create.NewFamilyInstance(XYZ(x, y, z_abs), sym, best_w, Structure.StructuralType.NonStructural))
else:
    print("M5 omitido (sin muro a <304mm del punto)")

# M6: 2-arg LEVEL
probar("M6: 2-arg level z_abs",
       lambda: doc.Create.NewFamilyInstance(XYZ(x, y, z_abs), sym, level_piso5))

print("")
print("=" * 52)
print("TEST COMPLETO - no queda ninguna instancia de prueba en el modelo")