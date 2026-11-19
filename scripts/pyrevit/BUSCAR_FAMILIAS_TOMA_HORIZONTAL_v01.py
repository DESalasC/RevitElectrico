# -*- coding: utf-8 -*-
# BUSCAR_FAMILIAS_TOMA_HORIZONTAL_v01.py - Buscar familias de toma modeladas en horizontal
# Ejecutar en pyRevit

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (FilteredElementCollector, FamilySymbol, BuiltInCategory,
    BuiltInParameter, Options, Solid, PlanarFace, XYZ)

doc = __revit__.ActiveUIDocument.Document

print("=== FAMILIAS ELÉCTRICAS Y SU ORIENTACIÓN ===\n")

for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol):
            cat = elem.Category
            if cat and cat.Id.IntegerValue == int(BuiltInCategory.OST_ElectricalFixtures):
                fam_name = elem.FamilyName
                sym_name = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
                
                # Ver geometría del símbolo (origin y caras)
                opt = Options()
                opt.ComputeReferences = False
                opt.DetailLevel = 0  # Coarse
                
                geom = elem.get_Geometry(opt)
                if geom:
                    for obj in geom:
                        if isinstance(obj, Solid):
                            # Ver caras principales
                            for face in obj.Faces:
                                if isinstance(face, PlanarFace):
                                    normal = face.FaceNormal
                                    area = face.Area
                                    if area > 0.01:  # caras significativas
                                        print("{} | {} | Face Normal=({:.2f},{:.2f},{:.2f}) Area={:.2f}".format(
                                            fam_name, sym_name, normal.X, normal.Y, normal.Z, area))
                print("---")
    except: pass