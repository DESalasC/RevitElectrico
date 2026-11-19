# -*- coding: utf-8 -*-
# Fix rotación específicos - usa ElementTransformUtils.RotateElement
# Ejecutar en pyRevit Python Shell

ids_tomas = [5555219,5555220,5555221,5555222,5555223,5555232,5555234,5555235,5555236]
ids_manuales = [5556292,5556661,5556741,5556779]  # puestas manualmente, verificar

import clr, math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (ElementId, Line, XYZ, BuiltInCategory, BuiltInParameter,
                                FilteredElementCollector, Wall, Options, Solid, PlanarFace,
                                ElementTransformUtils)
from System import Int64

doc = __revit__.ActiveUIDocument.Document

# Recolectar muros Piso 5
nivel5_id = 192512
muros = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id = int(bp.AsElementId().Value) if bp and bp.HasValue else 0
    lvl_id = int(w.LevelId.Value)
    if (bp_id == nivel5_id or lvl_id == nivel5_id) and w.Location:
        muros.append(w)

def get_wall_rotation_at(pt, max_dist=5.0):
    best_face = None
    best_dist = float('inf')
    for w in muros:
        try:
            opt = Options(); opt.ComputeReferences = True
            geom = w.get_Geometry(opt)
            if not geom: continue
            for obj in geom:
                if not isinstance(obj, Solid): continue
                for face in obj.Faces:
                    if not isinstance(face, PlanarFace): continue
                    if abs(face.FaceNormal.Z) > 0.1: continue
                    proj = face.Project(pt)
                    if proj:
                        uv = proj.UVPoint
                        bb = face.GetBoundingBox()
                        if bb.Min.U <= uv.U <= bb.Max.U and bb.Min.V <= uv.V <= bb.Max.V:
                            pt_on_face = face.Evaluate(uv)
                            d = pt.DistanceTo(pt_on_face)
                            if d < best_dist and d < max_dist:
                                best_dist = d
                                best_face = face
        except: continue
    if best_face:
        n = best_face.FaceNormal
        wall_dir = XYZ(-n.Y, n.X, 0)
        angle = math.atan2(wall_dir.Y, wall_dir.X)
        return angle + math.radians(90)
    return None

t = Transaction(doc, "Fix Tomas Especificas"); t.Start()
fixed = 0
for eid in ids_tomas:
    el = doc.GetElement(ElementId(Int64(eid)))
    if not el or not el.Location: continue
    pt = el.Location.Point if hasattr(el.Location, 'Point') else el.Location.Curve.Evaluate(0.5, True)
    rot = get_wall_rotation_at(pt)
    if rot:
        try:
            axis = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1))
            ElementTransformUtils.RotateElement(doc, el.Id, axis, rot)
            fixed += 1
            print("Fixed Id={} rot={:.1f}°".format(eid, math.degrees(rot)))
        except Exception as e:
            print("Err Id={}: {}".format(eid, e))
    else:
        print("No wall for Id={}".format(eid))

# Verificar los manuales
print("\n--- Manuales ---")
for eid in ids_manuales:
    el = doc.GetElement(ElementId(Int64(eid)))
    if el and el.Location:
        pt = el.Location.Point if hasattr(el.Location, 'Point') else el.Location.Curve.Evaluate(0.5, True)
        fam = el.Symbol.FamilyName
        print("Id={} Fam={} Pt=({:.2f},{:.2f})".format(eid, fam, pt.X, pt.Y))

t.Commit()
print("\nCorregidas: {}".format(fixed))