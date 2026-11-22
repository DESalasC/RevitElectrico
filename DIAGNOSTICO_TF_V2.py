# DIAGNOSTICO TF - versión robusta sin problemas de formato
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
import clr
clr.AddReference('RevitAPI')

doc = __revit__.ActiveUIDocument.Document

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
    x_mm = round(float(pt.X) * 304.8, 1)
    y_mm = round(float(pt.Y) * 304.8, 1)
    z_mm = round(float(pt.Z) * 304.8, 1)
    
    level_elem = doc.GetElement(e.LevelId)
    level_name = level_elem.Name if level_elem else "SIN_NIVEL"
    
    tipo_param = e.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    tipo_val = tipo_param.AsString() if tipo_param else "SIN_TIPO"
    
    item = {
        'fam': fam_name, 'tipo': tipo_val, 'mark': mark,
        'x_mm': x_mm, 'y_mm': y_mm, 'z_mm': z_mm,
        'level': level_name, 'id': int(str(e.Id))
    }
    
    if ('TF' in mark) or ('TF' in fam_name):
        found_tf.append(item)
    else:
        found_otros.append(item)

print("=" * 60)
print("INTERRUPTORES TF EN MODELO: {}".format(len(found_tf)))
print("=" * 60)
for f in sorted(found_tf, key=lambda x: (x['mark'], x['x_mm'])):
    print("  Fam={} Tipo={} Mark={} X={} Y={} Z={}mm Nivel={} Id={}".format(
        str(f['fam']), str(f['tipo']), str(f['mark']),
        str(f['x_mm']), str(f['y_mm']), str(f['z_mm']),
        str(f['level']), str(f['id'])))

print("\nOTROS INTERRUPTORES (muestra): {}".format(len(found_otros)))
for f in sorted(found_otros, key=lambda x: (x['mark'], x['x_mm']))[:10]:
    print("  Fam={} Tipo={} Mark={} X={} Y={} Z={}mm Nivel={}".format(
        str(f['fam']), str(f['tipo']), str(f['mark']),
        str(f['x_mm']), str(f['y_mm']), str(f['z_mm']),
        str(f['level'])))

# View Range
view = doc.ActiveView
if hasattr(view, 'GetViewRange'):
    vr = view.GetViewRange()
    print("\nVIEW RANGE:")
    print("  Top:     {}mm".format(round(float(vr.GetOffset(PlanViewPlane.Top)) * 304.8)))
    print("  Cut:     {}mm".format(round(float(vr.GetOffset(PlanViewPlane.CutPlane)) * 304.8)))
    print("  Bottom:  {}mm".format(round(float(vr.GetOffset(PlanViewPlane.Bottom)) * 304.8)))
    print("  Depth:   {}mm".format(round(float(vr.GetOffset(PlanViewPlane.ViewDepth)) * 304.8)))
    cut_plane = float(vr.GetOffset(PlanViewPlane.CutPlane)) * 304.8
    print("  >>> Cut Plane: {}mm (interruptores a ~14319mm)".format(round(cut_plane)))
    if cut_plane < 13000:
        print("  >>> PROBLEMA: Cut Plane DEBAJO de interruptores!")

# Crop
crop_mgr = view.GetCropRegionShapeManager()
if crop_mgr.GetCropRegion():
    curves = crop_mgr.GetCropRegion()[0]
    bbox = curves.GetBoundingBox()
    print("\nCROP ACTIVO:")
    print("  Min: X={} Y={}".format(round(float(bbox.Min.X)*304.8), round(float(bbox.Min.Y)*304.8)))
    print("  Max: X={} Y={}".format(round(float(bbox.Max.X)*304.8), round(float(bbox.Max.Y)*304.8)))
    if found_tf:
        tf_x_min = min(f['x_mm'] for f in found_tf)
        tf_x_max = max(f['x_mm'] for f in found_tf)
        tf_y_min = min(f['y_mm'] for f in found_tf)
        tf_y_max = max(f['y_mm'] for f in found_tf)
        print("TF bbox: X=[{}, {}] Y=[{}, {}]".format(tf_x_min, tf_x_max, tf_y_min, tf_y_max))
        crop_x_min = bbox.Min.X * 304.8
        crop_x_max = bbox.Max.X * 304.8
        crop_y_min = bbox.Min.Y * 304.8
        crop_y_max = bbox.Max.Y * 304.8
        if tf_x_min < crop_x_min or tf_x_max > crop_x_max or tf_y_min < crop_y_min or tf_y_max > crop_y_max:
            print("  >>> TF FUERA DEL CROP!")
        else:
            print("  >>> TF DENTRO DEL CROP")
else:
    print("\nSIN CROP")