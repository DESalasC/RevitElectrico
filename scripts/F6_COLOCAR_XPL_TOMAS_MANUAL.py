"""
F6_COLOCAR_XPL_TOMAS_MANUAL.py - v02
Version: 02
Date: 2026-11-20
Fix: Rotate with ElementTransformUtils.RotateElement (Location.Rotation is read-only)
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import traceback

APTO_OBJETIVO = 'TF 01a'  # ← cambiar aquí
JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_electricos_xpl_absolutos.json"

NIVEL_PISO5_ELEV_MM = 13219.0
ALTURAS_MM = {
    'M_Toma doble': 1000,
    'M_Comunicaciones': 1000,
}

FAMILIAS_ROTAR_90 = {'M_Toma doble', 'M_Comunicaciones'}

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("="*60)
print("F6_COLOCAR_XPL_TOMAS_MANUAL v02")
print("APTO:", APTO_OBJETIVO)
print("MODO: Level-based + Pick Host manual")
print("="*60)

with open(JSON_PATH, 'r') as f:
    data = json.load(f)

tomas = [d for d in data['dispositivos'] 
         if d['apto_asignado'] == APTO_OBJETIVO and d['familia_revit'] in ('M_Toma doble', 'M_Comunicaciones')]
print("Tomas en {}: {}".format(APTO_OBJETIVO, len(tomas)))

# Level Piso 5
level_piso5 = None
for lvl in FilteredElementCollector(doc).OfClass(Level):
    if lvl.Name == "Piso 5" or abs(lvl.Elevation * 304.8 - NIVEL_PISO5_ELEV_MM) < 10:
        level_piso5 = lvl
        break
level_piso5_id = level_piso5.Id
level_piso5_elev_ft = level_piso5.Elevation

# Symbols
symbols = {}
for fam_name in ('M_Toma doble', 'M_Comunicaciones'):
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.Family.Name == fam_name:
            symbols[fam_name] = s
            if not s.IsActive: s.Activate()
            break

# Transaction
t = Transaction(doc, "Place Tomas {} - Level-based".format(APTO_OBJETIVO))
t.Start()

MM_TO_FT = 0.003280839895
placed = 0

for d in tomas:
    x = d['x_mm'] * MM_TO_FT
    y = d['y_mm'] * MM_TO_FT
    fam = d['familia_revit']
    z_mm = ALTURAS_MM.get(fam, NIVEL_PISO5_ELEV_MM)
    z_ft = z_mm * MM_TO_FT
    
    symbol = symbols.get(fam)
    if not symbol: continue
    
    rot = math.radians(d['rotacion_grados'])
    if fam in FAMILIAS_ROTAR_90:
        rot += math.pi / 2  # +90° para placa horizontal
    
    # Z ABSOLUTO = elevación nivel + altura dispositivo
    target_z = level_piso5_elev_ft + z_ft
    pt = XYZ(x, y, target_z)
    
    # Level-based placement
    inst = doc.Create.NewFamilyInstance(pt, symbol, level_piso5, Structure.StructuralType.NonStructural)
    
    # FORCE Level parameter
    p_level = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
    if p_level: p_level.Set(level_piso5_id)
    
    # Rotation: use ElementTransformUtils.RotateElement (Location.Rotation is read-only)
    if abs(rot) > 1e-6:
        axis = Line.CreateBound(pt, pt + XYZ(0, 0, 10.0))
        ElementTransformUtils.RotateElement(doc, inst.Id, axis, rot)
    
    # Unique Mark
    mark = "{}_{}_{}_{}".format(
        fam.replace('M_','').replace(' ','')[:8],
        d['tipo_revit'].replace(' ','')[:6],
        int(round(d['x_mm'])), int(round(d['y_mm']))
    )
    p_mark = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    if p_mark: p_mark.Set(mark)
    
    placed += 1
    print("  OK: {} @ ({:.2f},{:.2f},{:.2f}) rot={:.0f}deg mark={}".format(
        d['nombre_dxf'], x, y, target_z, math.degrees(rot), mark))

t.Commit()
print("\nDone. Placed: {} on Piso 5 at correct height.".format(placed))
print(">>> Ahora: Seleccionar todas -> Modify -> Pick Host -> Click en cara de muro")