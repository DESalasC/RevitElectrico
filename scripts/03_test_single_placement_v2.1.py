# -*- coding: utf-8 -*-
# ============================================================================
# SCRIPT: 03_test_single_placement_v2.1.py
# VERSIÓN: 2.1
# FECHA: 2026-11-13 14:30
# PROPÓSITO: Prueba de colocación de UN elemento
# ============================================================================

import sys
import os
import json
import io
import datetime

print("=" * 80)
print("SCRIPT v2.1 - " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 80)

# Obtener documento
try:
    if '__revit__' in globals():
        doc = __revit__.ActiveUIDocument.Document
    else:
        import clr
        clr.AddReference('RevitServices')
        from RevitServices.Persistence import DocumentManager
        doc = DocumentManager.Instance.CurrentDBDocument
except:
    print("ERROR: No hay documento Revit activo")
    sys.exit(1)

print("Documento: " + doc.Title)

# Imports
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')
from Autodesk.Revit.DB import *
from RevitServices.Transactions import TransactionManager

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
json_path = r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E06_v01.json"

# PUNTO BASE: Coordenadas del TB-Parcial en el DXF general
# AJUSTA ESTOS VALORES con las coordenadas reales del TB-Parcial
TB_PARCIAL_DXF_X = 6.516  # AJUSTAR: X del TB-Parcial en DXF (metros)
TB_PARCIAL_DXF_Y = 10.804  # AJUSTAR: Y del TB-Parcial en DXF (metros)

M_TO_FT = 3.28084

# ============================================================================
# CARGAR JSON
# ============================================================================
with io.open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

dispositivos = data['dispositivos']
print("\nTotal dispositivos: " + str(len(dispositivos)))

# ============================================================================
# BUSCAR PANEL EN REVIT
# ============================================================================
print("\n" + "=" * 80)
print("BUSCANDO PANEL TB-Panel")
print("=" * 80)

panels = FilteredElementCollector(doc)\
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment)\
    .WhereElementIsNotElementType()\
    .ToElements()

panel_instance = None
for panel in panels:
    symbol = panel.Symbol
    if 'TB-Panel' in symbol.Name or 'EPB25-304C' in symbol.Name:
        panel_instance = panel
        loc = panel.Location
        if isinstance(loc, LocationPoint):
            pt = loc.Point
            print("✓ Panel encontrado")
            print("  Id: " + str(panel.Id.IntegerValue))
            print("  Posición (pies): X={:.3f}, Y={:.3f}, Z={:.3f}".format(pt.X, pt.Y, pt.Z))
            print("  Posición (metros): X={:.3f}, Y={:.3f}, Z={:.3f}".format(
                pt.X / M_TO_FT, pt.Y / M_TO_FT, pt.Z / M_TO_FT))
        break

if not panel_instance:
    print("⚠️  Panel no encontrado")
    print("Paneles disponibles:")
    for p in panels:
        print("  - " + p.Symbol.Family.Name + " / " + p.Symbol.Name)
    sys.exit(1)

# ============================================================================
# CALCULAR OFFSET
# ============================================================================
panel_point = panel_instance.Location.Point
offset_x = panel_point.X - (TB_PARCIAL_DXF_X * M_TO_FT)
offset_y = panel_point.Y - (TB_PARCIAL_DXF_Y * M_TO_FT)
offset_z = panel_point.Z

print("\nOffset calculado (pies):")
print("  X: {:.3f}".format(offset_x))
print("  Y: {:.3f}".format(offset_y))
print("  Z: {:.3f}".format(offset_z))

# ============================================================================
# SELECCIONAR ELEMENTO DE PRUEBA
# ============================================================================
print("\n" + "=" * 80)
print("ELEMENTO DE PRUEBA")
print("=" * 80)

test_device = None
for disp in dispositivos:
    if 'ELEC-I-S' in disp['nombre']:
        test_device = disp
        break

if not test_device:
    test_device = dispositivos[0]

print("Nombre: " + test_device['nombre'])
print("Posición DXF (m): x={:.3f}, y={:.3f}".format(test_device['x'], test_device['y']))
print("Altura (m): " + str(test_device['altura_nominal_m']))
print("Rotación: " + str(test_device['rotacion_grados']))

# Convertir coordenadas
x_abs_ft = (test_device['x'] * M_TO_FT) + offset_x
y_abs_ft = (test_device['y'] * M_TO_FT) + offset_y
z_abs_ft = offset_z + (test_device['altura_nominal_m'] * M_TO_FT)

print("\nPosición absoluta Revit (pies):")
print("  X: {:.3f}".format(x_abs_ft))
print("  Y: {:.3f}".format(y_abs_ft))
print("  Z: {:.3f}".format(z_abs_ft))

# ============================================================================
# BUSCAR FAMILIA
# ============================================================================
print("\n" + "=" * 80)
print("BUSCANDO FAMILIA")
print("=" * 80)

family_name = test_device['nombre']
print("Buscando: " + family_name)

target_cats = [
    BuiltInCategory.OST_LightingDevices,
    BuiltInCategory.OST_ElectricalEquipment,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_SpecialityEquipment,
    BuiltInCategory.OST_MechanicalEquipment
]

family_symbol = None
for cat in target_cats:
    collector = FilteredElementCollector(doc).OfCategory(cat).WhereElementIsElementType()
    for fs in collector:
        if fs.Family.Name == family_name or fs.Name == family_name:
            family_symbol = fs
            print("✓ Familia encontrada")
            print("  Categoría: " + cat.ToString())
            print("  Family: " + fs.Family.Name)
            print("  Type: " + fs.Name)
            break
    if family_symbol:
        break

if not family_symbol:
    print("⚠️  Familia no encontrada: " + family_name)
    sys.exit(1)

# ============================================================================
# DETERMINAR HOST TYPE
# ============================================================================
ceiling_keywords = ['M_Iluminacion', 'M_ClimatizacionV', 'Bala']
is_ceiling = any(k in family_symbol.Family.Name for k in ceiling_keywords)
host_type = "CEILING" if is_ceiling else "WALL"

print("\nTipo de host: " + host_type)

# ============================================================================
# BUSCAR HOST
# ============================================================================
print("\n" + "=" * 80)
print("BUSCANDO HOST")
print("=" * 80)

placement_point = XYZ(x_abs_ft, y_abs_ft, z_abs_ft)
host_element = None
host_face_ref = None
min_distance = float('inf')

if host_type == "WALL":
    walls = FilteredElementCollector(doc)\
        .OfCategory(BuiltInCategory.OST_Walls)\
        .WhereElementIsNotElementType()\
        .ToElements()
    
    for wall in walls:
        try:
            geo_options = Options()
            geo_options.ComputeReferences = True
            geo_element = wall.get_Geometry(geo_options)
            
            if geo_element:
                for geo_obj in geo_element:
                    if isinstance(geo_obj, Solid):
                        for face in geo_obj.Faces:
                            if isinstance(face, PlanarFace):
                                distance = face.Origin.DistanceTo(placement_point)
                                if distance < min_distance and distance < 5.0:
                                    min_distance = distance
                                    host_element = wall
                                    host_face_ref = face.Reference
        except:
            pass
    
    if host_element:
        print("✓ Muro host: Id=" + str(host_element.Id.IntegerValue))
        print("  Distancia: {:.3f} pies ({:.3f} m)".format(min_distance, min_distance / M_TO_FT))
    else:
        print("⚠️  No se encontró muro cercano")

else:  # CEILING
    ceilings = FilteredElementCollector(doc)\
        .OfCategory(BuiltInCategory.OST_Ceilings)\
        .WhereElementIsNotElementType()\
        .ToElements()
    
    for ceiling in ceilings:
        try:
            geo_options = Options()
            geo_options.ComputeReferences = True
            geo_element = ceiling.get_Geometry(geo_options)
            
            if geo_element:
                for geo_obj in geo_element:
                    if isinstance(geo_obj, Solid):
                        for face in geo_obj.Faces:
                            if isinstance(face, PlanarFace):
                                distance = face.Origin.DistanceTo(placement_point)
                                if distance < min_distance and distance < 10.0:
                                    min_distance = distance
                                    host_element = ceiling
                                    host_face_ref = face.Reference
        except:
            pass
    
    if host_element:
        print("✓ Techo host: Id=" + str(host_element.Id.IntegerValue))
        print("  Distancia: {:.3f} pies ({:.3f} m)".format(min_distance, min_distance / M_TO_FT))
    else:
        print("⚠️  No se encontró techo cercano")

# ============================================================================
# RESULTADO
# ============================================================================
print("\n" + "=" * 80)
print("RESULTADO")
print("=" * 80)

if host_element and host_face_ref:
    print("✓ LISTO PARA COLOCAR")
    print("\nDescomenta el código abajo para colocar realmente")
    
    # DESCOMENTAR PARA COLOCAR:
    # TransactionManager.Instance.EnsureInTransaction(doc)
    # try:
    #     if host_type == "WALL":
    #         new_inst = doc.Create.NewFamilyInstance(
    #             host_face_ref, placement_point, XYZ.BasisX, family_symbol)
    #     else:
    #         new_inst = doc.Create.NewFamilyInstance(
    #             host_face_ref, placement_point, family_symbol)
    #     print("✓ Colocado: Id=" + str(new_inst.Id.IntegerValue))
    #     TransactionManager.Instance.TransactionTaskDone()
    # except Exception as e:
    #     print("ERROR: " + str(e))
    #     TransactionManager.Instance.ForceCloseTransaction()
else:
    print("⚠️  NO SE PUEDE COLOCAR - Host no encontrado")

print("\n" + "=" * 80)