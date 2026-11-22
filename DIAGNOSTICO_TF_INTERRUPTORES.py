# DIAGNÓSTICO REAL - Verificar qué hay REALMENTE en el modelo para TF
# Ejecutar en pyRevit Python Shell

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import clr
clr.AddReference('RevitAPI')

doc = __revit__.ActiveUIDocument.Document

# Buscar TODOS los M_Interruptores y M_Pulsador del modelo
collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
found_tf = []
found_otros = []

for e in collector:
    fam_name = e.Symbol.Family.Name
    if fam_name not in ('M_Interruptores', 'M_Pulsador - Interruptor'):
        continue
    
    mark_param = e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    mark_val = mark_param.AsString() if mark_param else None
    mark = mark_val if mark_val else "SIN_MARK"
    
    loc = e.Location
    if not isinstance(loc, LocationPoint):
        continue
    
    pt = loc.Point
    x_mm = round(pt.X * 304.8, 1)
    y_mm = round(pt.Y * 304.8, 1)
    z_mm = round(pt.Z * 304.8, 1)
    
    level_elem = doc.GetElement(e.LevelId)
    level_name = level_elem.Name if level_elem else "SIN_NIVEL"
    
    item = {
        'fam': fam_name,
        'tipo': e.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() if e.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM) else "SIN_TIPO",
        'mark': mark,
        'x_mm': x_mm,
        'y_mm': y_mm,
        'z_mm': z_mm,
        'level': level_name,
        'id': int(str(e.Id))
    }
    
    if ('TF' in mark) or ('TF' in fam_name):
        found_tf.append(item)
    else:
        found_otros.append(item)

print("=" * 60)
print("INTERRUPTORES TF EN MODELO: {}".format(len(found_tf)))
print("=" * 60)
for f in sorted(found_tf, key=lambda x: (x['mark'], x['x_mm'])):
    print("  [{}] {} | {} | Mark={} | X={:.1f} Y={:.1f} Z={:.1f}mm | Nivel={} | Id={}".format(
        f['fam'], f['tipo'], f['mark'], f['x_mm'], f['y_mm'], f['z_mm'], f['level'], f['id']))

print("\n" + "=" * 60)
print("OTROS INTERRUPTORES (muestra): {}".format(len(found_otros)))
print("=" * 60)
for f in sorted(found_otros, key=lambda x: (x['mark'], x['x_mm']))[:20]:
    print("  [{}] {} | {} | Mark={} | X={:.1f} Y={:.1f} Z={:.1f}mm | Nivel={}".format(
        f['fam'], f['tipo'], f['mark'], f['x_mm'], f['y_mm'], f['z_mm'], f['level']))

# Verificar view range
view = doc.ActiveView
if hasattr(view, 'GetViewRange'):
    vr = view.GetViewRange()
    print("\nVIEW RANGE VISTA ACTIVA:")
    print("  Top Offset:      {:.0f}mm".format(vr.GetOffset(PlanViewPlane.Top) * 304.8))
    print("  Cut Plane:       {:.0f}mm".format(vr.GetOffset(PlanViewPlane.CutPlane) * 304.8))
    print("  Bottom Offset:   {:.0f}mm".format(vr.GetOffset(PlanViewPlane.Bottom) * 304.8))
    print("  View Depth:      {:.0f}mm".format(vr.GetOffset(PlanViewPlane.ViewDepth) * 304.8))
    
    print("\nZ interruptores esperados: ~14319mm (Piso 5 + 1100mm)")
    cut_plane_mm = vr.GetOffset(PlanViewPlane.CutPlane) * 304.8
    print("Cut Plane actual: {:.0f}mm".format(cut_plane_mm))
    if cut_plane_mm < 13000:
        print("  >>> PROBLEMA: Cut Plane DEBAJO de interruptores!")

# Verificar crop
crop_mgr = view.GetCropRegionShapeManager()
if crop_mgr.GetCropRegion():
    curves = crop_mgr.GetCropRegion()[0]
    bbox = curves.GetBoundingBox()
    print("\nCROP ACTIVO:")
    print("  Min: X={:.0f} Y={:.0f} mm".format(bbox.Min.X*304.8, bbox.Min.Y*304.8))
    print("  Max: X={:.0f} Y={:.0f} mm".format(bbox.Max.X*304.8, bbox.Max.Y*304.8))
    
    tf_x_min = min(f['x_mm'] for f in found_tf) if found_tf else 0
    tf_x_max = max(f['x_mm'] for f in found_tf) if found_tf else 0
    tf_y_min = min(f['y_mm'] for f in found_tf) if found_tf else 0
    tf_y_max = max(f['y_mm'] for f in found_tf) if found_tf else 0
    print("\nBounding box TF en modelo:")
    print("  X: [{:.0f}, {:.0f}] mm".format(tf_x_min, tf_x_max))
    print("  Y: [{:.0f}, {:.0f}] mm".format(tf_y_min, tf_y_max))
    
    crop_x_min = bbox.Min.X * 304.8
    crop_x_max = bbox.Max.X * 304.8
    crop_y_min = bbox.Min.Y * 304.8
    crop_y_max = bbox.Max.Y * 304.8
    
    if tf_x_min < crop_x_min or tf_x_max > crop_x_max or tf_y_min < crop_y_min or tf_y_max > crop_y_max:
        print("  >>> PROBLEMA: TF FUERA DEL CROP!")
    else:
        print("  >>> TF DENTRO DEL CROP")
else:
    print("\nSIN CROP en vista activa")