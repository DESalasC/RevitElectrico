# Orientar tomas a pared mas cercana - IronPython 2.7 para pyRevit
# Ejecutar en pyRevit Python Shell

ids = [5553975,5553976,5553977,5553978,5553979,5553992,5554010,5554011,5554012,5554021,5554022,5554023,5554024,5554025,5554038,5554056,5554057,5554058,5554128,5554130,5554132,5554134,5554136,5554138,5554140,5554142,5554144,5554146,5554148,5554150,5554152,5554154,5554156,5554158,5554160,5554162,5554164,5554166,5554168,5554170,5554172,5554174,5554176,5554178,5554180,5554182,5554184,5554186,5554188,5554190,5554192,5554194,5554196,5554198,5554200,5554202,5554204,5554206,5554208,5554210,5554212,5554214,5554216,5554218,5554220,5554222,5554224,5554226,5554228,5554230,5554232,5554234,5554236,5554238,5554240,5554242,5554244,5554246,5554248,5554250,5554252,3633823,5553973,5553974,5553980,5554013,5554014,5554015,5554016,5554017,5554018,5554019,5554020,5554026,5554059,5554060,5554061,5554062,5554063,5554064]

import clr, math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (ElementId, Line, XYZ, BuiltInCategory, BuiltInParameter,
                                FilteredElementCollector, Wall, Options, Solid, PlanarFace, Transaction)
from System import Int64

doc = __revit__.ActiveUIDocument.Document

# 1. Recolectar muros Piso 5
nivel5_id = 192512
muros = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id = int(bp.AsElementId().Value) if bp and bp.HasValue else 0
    lvl_id = int(w.LevelId.Value)
    if (bp_id == nivel5_id or lvl_id == nivel5_id) and w.Location:
        muros.append(w)

print("Muros Piso 5: {}".format(len(muros)))

# 2. Para cada toma: buscar muro mas cercano y alinear
t = Transaction(doc, "Orientar Tomas a Pared"); t.Start()
fixed = 0
for eid in ids:
    el = doc.GetElement(ElementId(Int64(eid)))
    if not el or not el.Location: continue
    loc = el.Location
    if not hasattr(loc, 'Point'):
        # LocationCurve - usar punto medio
        try:
            pt = loc.Curve.Evaluate(0.5, True)
        except:
            continue
    else:
        pt = loc.Point
    
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
                            if d < best_dist and d < 5.0:
                                best_dist = d
                                best_face = face
        except: continue
    
    if best_face:
        n = best_face.FaceNormal
        wall_dir = XYZ(-n.Y, n.X, 0)
        target_angle = math.atan2(wall_dir.Y, wall_dir.X)
        final_rot = target_angle + math.radians(90)
        
        if hasattr(loc, 'Rotation'):
            current_rot = loc.Rotation
        else:
            current_rot = 0
        axis = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1))
        loc.Rotate(axis, final_rot - current_rot)
        fixed += 1
    else:
        print("  Sin muro cercano para Id={}".format(eid))

t.Commit()
print("Tomas orientadas a pared: {}".format(fixed))