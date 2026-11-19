# -*- coding: utf-8 -*-
# Colocar F01 completo con regla original: JSON rot + 90° para tomas/comms
# Ejecutar en pyRevit

import clr, json, math
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (XYZ, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, FamilySymbol, FamilyInstance,
    Transaction, Level, ElementTransformUtils, Line)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"
FPM = 3.280839895
def m_a_ft(m): return m * FPM
def clean(s): return s.replace('\ufeff','').replace('\u200b','').strip() if s else s

doc = __revit__.ActiveUIDocument.Document

with open(JSON_PATH, 'r') as f:
    data = json.load(f)
devices = data['apartamentos']['F01']['devices']

# Símbolos
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

t = Transaction(doc, "Colocar F01 Regla Original"); t.Start()
ok = 0
for dev in devices:
    fam = dev['familia_revit']; typ = dev['tipo_revit']
    s = find_sym(fam, typ)
    if not s: continue
    
    x, y = dev['x'], dev['y']
    rot_dxf = math.radians(dev.get('rotation', 0))
    
    # Regla: tomas/comms = rot_dxf + 90°; resto = rot_dxf
    if fam in ["M_Toma doble", "M_Comunicaciones"]:
        rot = rot_dxf + math.radians(90)
    else:
        rot = rot_dxf
    
    # Z
    if fam in ["M_Toma doble", "M_Comunicaciones"]:
        z = 43.37 + m_a_ft(0.30)
    elif fam in ["M_Interruptores", "M_Pulsador - Interruptor", "M_Timbre"]:
        z = 43.37 + m_a_ft(1.10)
    elif fam == "EA":
        z = 43.37 + m_a_ft(1.90)
    elif fam in ["M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"]:
        continue  # FB-TECHO aparte
    else:
        z = 43.37 + m_a_ft(0.30)
    
    pt = XYZ(x, y, z)
    if not s.IsActive: s.Activate()
    inst = doc.Create.NewFamilyInstance(pt, s, StructuralType.NonStructural)
    
    if rot != 0:
        try:
            axis = Line.CreateBound(pt, XYZ(x, y, z + 1))
            ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot)
        except: pass
    ok += 1

t.Commit()
print("Colocados: {}".format(ok))