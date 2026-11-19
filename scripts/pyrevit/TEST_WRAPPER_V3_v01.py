# -*- coding: utf-8 -*-
# TEST_WRAPPER_V3_v01.py - Probar PlaceFaceBasedByReference (v3)
# Ejecutar en pyRevit (después de MiAddinLoader.py)

exec(open(r"D:\Work\PROJECTS\RevitElectrico\bin\MiAddinLoader.py").read())

import clr, math
from Autodesk.Revit.DB import (XYZ, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, FamilySymbol, HostObjectUtils, ShellLayerType, Transaction)
from System import Int64

doc = __revit__.ActiveUIDocument.Document

# 1. Buscar símbolo M_Toma doble Normal
s = None
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol) and "M_Toma doble" in elem.FamilyName:
            p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p and p.AsString() == "Normal":
                s = elem
                break
    except: pass

if not s:
    print("Símbolo no encontrado")
else:
    # 2. Muro 5349586 - obtener Reference interior (GetSideFaces)
    wall = doc.GetElement(ElementId(Int64(5349586)))
    if not wall:
        print("Muro no encontrado")
    else:
        int_refs = HostObjectUtils.GetSideFaces(wall, ShellLayerType.Interior)
        face_ref = None
        for ref in int_refs:
            f = wall.GetGeometryObjectFromReference(ref)
            if f and abs(f.FaceNormal.Z) < 0.1:
                face_ref = ref
                print("Reference OK, Normal=({:.1f},{:.1f},{:.1f})".format(
                    f.FaceNormal.X, f.FaceNormal.Y, f.FaceNormal.Z))
                break
        
        if not face_ref:
            print("Reference interior no encontrado")
        else:
            # 3. Punto de prueba
            pt = XYZ(45.4, 18.0, 43.37 + 0.30 * 3.28084)
            
            # 4. USAR PlaceFaceBasedByReference (v3) - Reference + point + param + symbol
            t = Transaction(doc, "Test Wrapper v3"); t.Start()
            try:
                if not s.IsActive: s.Activate()
                # PlaceFaceBasedByReference(doc, faceRef, point, param, symbol)
                inst = Placer.PlaceFaceBasedByReference(doc, face_ref, pt, 0.0, s)
                print("SUCCESS! Inst Id: {}".format(int(inst.Id.Value)))
            except Exception as e:
                print("Error: {}".format(e))
            t.Commit()