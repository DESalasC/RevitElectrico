# -*- coding: utf-8 -*-
# DIAG_CREAR_UNO_wrapper.py
# Intenta crear UNA FamilyInstance real con familia M_Iluminacion para capturar el error exacto.
# Ejecutar: pyrevit agent run <este_archivo> --mode=modify --revit=5500 --timeout=120

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import traceback

doc = __revit__.ActiveUIDocument.Document
nivel = None
for lv in FilteredElementCollector(doc).OfClass(Level):
    if lv.Name == "Piso 5":
        nivel = lv
        break

print("Nivel Piso 5: id={}".format(nivel.Id if nivel else "NO ENCONTRADO"))

# Buscar familia M_Iluminacion
simbolo = None
fam_encontrada = None
for fam in FilteredElementCollector(doc).OfClass(Family):
    if fam.Name == "M_Iluminacion":
        fam_encontrada = fam
        ids = fam.GetFamilySymbolIds()
        if ids:
            simbolo = doc.GetElement(ids[0])
        break

print("Familia M_Iluminacion: {} | simbolo: {}".format(
    fam_encontrada.Id if fam_encontrada else None,
    simbolo.Id if simbolo else None))

if simbolo:
    print("Simbolo activo?: {}".format(simbolo.IsActive))
    if not simbolo.IsActive:
        try:
            simbolo.Activate()
            print("Simbolo activado.")
        except Exception as ex:
            print("Error activando simbolo: {}".format(ex))

# Buscar un muro de Piso 5 para host
muro = None
for w in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls):
    try:
        if w.LevelId.IntegerValue == nivel.Id.IntegerValue:
            muro = w
            break
    except Exception:
        continue
print("Muro Piso 5: {}".format(muro.Id if muro else None))

# Intentar crear una instancia en (0,0,0) relativo al muro (en pies del modelo)
try:
    t = Transaction(doc, "Test crear uno")
    t.Start()
    punto = XYZ(10, 10, 10)  # pies
    dir_vec = XYZ(1, 0, 0)
    if muro:
        ref = muro.FindNearestReference(punto)
        inst = doc.Create.NewFamilyInstance(ref, punto, dir_vec, simbolo)
    else:
        inst = doc.Create.NewFamilyInstance(punto, simbolo, nivel, StructuralType.NonStructural)
    t.Commit()
    print("EXITO: instancia creada id={}".format(inst.Id))
except Exception as ex:
    try:
        t.RollBack()
    except Exception:
        pass
    print("ERROR creando instancia:")
    traceback.print_exc()
