# -*- coding: utf-8 -*-
# Debug: encontrar muro cerca de (45.4, 18) en Revit - Fixed IntegerValue

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (XYZ, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Options, Solid, PlanarFace)

doc = __revit__.ActiveUIDocument.Document

nivel5_id = 192512
pt_test = XYZ(45.4, 18.0, 43.37)

for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id = int(bp.AsElementId().Value) if bp and bp.HasValue else 0
    lvl_id = int(w.LevelId.Value)
    if not ((bp_id == nivel5_id or lvl_id == nivel5_id) and w.Location):
        continue
    
    curve = w.Location.Curve
    if not curve: continue
    
    d = curve.Distance(pt_test)
    if d < 2.0:
        print("Wall {} Dist={:.2f} Curve=({:.2f},{:.2f})->({:.2f},{:.2f})".format(
            int(w.Id.Value), d,
            curve.GetEndPoint(0).X, curve.GetEndPoint(0).Y,
            curve.GetEndPoint(1).X, curve.GetEndPoint(1).Y))
        
        try:
            opt = Options(); opt.ComputeReferences = True
            geom = w.get_Geometry(opt)
            if geom:
                for obj in geom:
                    if not isinstance(obj, Solid): continue
                    for face in obj.Faces:
                        if not isinstance(face, PlanarFace): continue
                        if abs(face.FaceNormal.Z) > 0.1: continue
                        bb = face.GetBoundingBox()
                        print("  Face Normal=({:.2f},{:.2f},{:.2f}) BB U=[{:.2f},{:.2f}] V=[{:.2f},{:.2f}]".format(
                            face.FaceNormal.X, face.FaceNormal.Y, face.FaceNormal.Z,
                            bb.Min.U, bb.Max.U, bb.Min.V, bb.Max.V))
        except: pass
        print()