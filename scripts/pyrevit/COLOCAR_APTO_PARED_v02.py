# -*- coding: utf-8 -*-
"""
COLOCAR_APTO_PARED_v02.py - IronPython 2.7 para pyRevit
Usa ElementTransformUtils.RotateElement para rotar level-based
"""

import clr, json, math, datetime, sys
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (XYZ, UV, Line, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, Ceiling, FamilySymbol, FamilyInstance,
    Transaction, Level, Options, Solid, Face, Reference, PlanarFace,
    ElementTransformUtils)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"
FPM = 3.280839895
def m_a_ft(m): return m * FPM

def clean(s): return s.replace('\ufeff','').replace('\u200b','').strip() if s else s

doc = __revit__.ActiveUIDocument.Document

# 1. RECOLECTAR MUROS PISO 5
nivel5_id = 192512
muros = []
for w in FilteredElementCollector(doc).OfClass(Wall).WhereElementIsNotElementType().ToElements():
    bp = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    bp_id = int(bp.AsElementId().Value) if bp and bp.HasValue else 0
    lvl_id = int(w.LevelId.Value)
    if (bp_id == nivel5_id or lvl_id == nivel5_id) and w.Location:
        muros.append(w)
print("Muros Piso 5: {}".format(len(muros)))

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

# 2. CARGAR JSON F01
with open(JSON_PATH, 'r') as f:
    data = json.load(f)
apto = data['apartamentos']['F01']
devices = apto['devices']
print("F01: {} dispositivos".format(len(devices)))

# 3. SÍMBOLOS
S = {}
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol):
            fam = clean(elem.FamilyName)
            p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            typ = clean(p.AsString()) if p and p.HasValue else "SinNombre"
            S[(fam, typ)] = elem
    except: pass

def find_sym(fam, typ):
    fam = clean(fam); typ = clean(typ)
    if (fam, typ) in S: return S[(fam, typ)]
    for (f, t), s in S.items():
        if f == fam and (t == typ or typ in t or t in typ): return s
    for (f, t), s in S.items():
        if f == fam: return s
    return None

# 4. NIVEL
nivel5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level).ToElements():
    if int(lvl.Id.Value) == nivel5_id: nivel5 = lvl; break

# 5. COLOCAR + ROTAR CON ElementTransformUtils
t = Transaction(doc, "Colocar F01 Orientado a Pared v2"); t.Start()
ok = 0
for i, dev in enumerate(devices, 1):
    fam = dev['familia_revit']; typ = dev['tipo_revit']
    s = find_sym(fam, typ)
    if not s: continue
    
    x, y = dev['x'], dev['y']
    
    # Rotación objetivo
    if fam in ["M_Toma doble", "M_Comunicaciones"]:
        rot = get_wall_rotation_at(XYZ(x, y, 0))
        if rot is None: rot = 0
    elif fam in ["M_Interruptores", "M_Pulsador - Interruptor", "M_Timbre", "EA"]:
        rot = math.radians(dev.get('rotation', 0))
    else:
        continue  # FB-TECHO saltar
    
    # Z
    if fam in ["M_Toma doble", "M_Comunicaciones"]:
        z = 43.37 + m_a_ft(0.30)
    elif fam in ["M_Interruptores", "M_Pulsador - Interruptor", "M_Timbre"]:
        z = 43.37 + m_a_ft(1.10)
    elif fam == "EA":
        z = 43.37 + m_a_ft(1.90)
    else:
        z = 43.37 + m_a_ft(0.30)
    
    pt_final = XYZ(x, y, z)
    if not s.IsActive: s.Activate()
    inst = doc.Create.NewFamilyInstance(pt_final, s, StructuralType.NonStructural)
    
    # ROTAR CON ElementTransformUtils (funciona en level-based)
    if rot and rot != 0:
        try:
            axis = Line.CreateBound(pt_final, XYZ(x, y, z + 1))
            ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot)
        except Exception as e:
            print("  [ROT ERR] {} Id={}: {}".format(fam, inst.Id, e))
    
    ok += 1

t.Commit()
print("F01 level-based colocados y rotados: {}".format(ok))