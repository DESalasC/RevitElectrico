# -*- coding: utf-8 -*-
# TEST_HOSTOBJECTUTILS_v01.py - Probar GetSideFaces en un muro

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, HostObjectUtils, ShellLayerType)
from System import Int64

doc = __revit__.ActiveUIDocument.Document

# Buscar muro 5349586 (el de X=45.44)
wall = doc.GetElement(ElementId(Int64(5349586)))
if wall:
    print("Muro encontrado: {}".format(wall.Id))
    
    # Caras interiores
    try:
        int_refs = HostObjectUtils.GetSideFaces(wall, ShellLayerType.Interior)
        print("Referencias interiores: {}".format(len(list(int_refs))))
        for ref in int_refs:
            face = wall.GetGeometryObjectFromReference(ref)
            if face:
                print("  Face Normal=({:.1f},{:.1f},{:.1f})".format(
                    face.FaceNormal.X, face.FaceNormal.Y, face.FaceNormal.Z))
    except Exception as e:
        print("Interior error: {}".format(e))
    
    # Caras exteriores
    try:
        ext_refs = HostObjectUtils.GetSideFaces(wall, ShellLayerType.Exterior)
        print("Referencias exteriores: {}".format(len(list(ext_refs))))
        for ref in ext_refs:
            face = wall.GetGeometryObjectFromReference(ref)
            if face:
                print("  Face Normal=({:.1f},{:.1f},{:.1f})".format(
                    face.FaceNormal.X, face.FaceNormal.Y, face.FaceNormal.Z))
    except Exception as e:
        print("Exterior error: {}".format(e))
else:
    print("Muro no encontrado")