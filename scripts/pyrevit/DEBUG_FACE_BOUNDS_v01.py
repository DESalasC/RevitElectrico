# -*- coding: utf-8 -*-
# Debug: ver qué caras encuentra cerca de (45.4, 18)

import clr, math
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
    if d > 5.0: continue
    
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
                    normal = face.FaceNormal
                    origin = face.Origin
                    wall_dir = XYZ(-normal.Y, normal.X, 0)
                    
                    # Proyectar punto al plano
                    offset = (pt_test.X - origin.X) * normal.X + (pt_test.Y - origin.Y) * normal.Y
                    pt_on = XYZ(pt_test.X - offset * normal.X, pt_test.Y - offset * normal.Y, origin.Z)
                    
                    u = (pt_on.X - origin.X) * wall_dir.X + (pt_on.Y - origin.Y) * wall_dir.Y
                    v = pt_on.Z - origin.Z
                    
                    print("Wall {} Normal=({:.1f},{:.1f}) d={:.2f} BB U=[{:.1f},{:.1f}] V=[{:.1f},{:.1f}] u={:.1f} v={:.1f}".format(
                        int(w.Id.Value), normal.X, normal.Y, d,
                        bb.Min.U, bb.Max.U, bb.Min.V, bb.Max.V, u, v))
    except: pass