# -*- coding: utf-8 -*-
# ruteo_ortogonal_v50.py | v50.0 | 2026-11-14
# Ruteo automático ortogonal para conduits eléctricos
import io, json, math, datetime

VER = "50.0"
print("=" * 78)
print("RUTEO ORTOGONAL v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 78)

try:
    _ = doc.Title
except:
    doc = __revit__.ActiveUIDocument.Document
print("Documento: " + doc.Title)

try:
    from Autodesk.Revit.DB import *
    from Autodesk.Revit.DB.Electrical import *
    from Autodesk.Revit.DB.Mechanical import *
except:
    import clr
    clr.AddReference('RevitAPI')
    from Autodesk.Revit.DB import *
    from Autodesk.Revit.DB.Electrical import *
    from Autodesk.Revit.DB.Mechanical import *

FT = 0.3048
M2FT = 3.28084

def iid(e):
    if e is None: return -1
    try: return int(e.Value)
    except:
        try: return int(e.IntegerValue)
        except: return -1

def by_id(d, n):
    for e in FilteredElementCollector(d).WhereElementIsNotElementType().ToElements():
        if iid(e.Id) == n: return e
    return None

def clean(s):
    if not s: return s
    return s.replace("\ufeff", "").replace("\u200b", "").strip()

# ============================================================================
# 1. CONFIGURACIÓN
# ============================================================================
# Apartamento objetivo (ajustar según el documento)
APTO_NAME = "F 01"  # Cambiar a "E 06" cuando se pruebe en el documento principal
PANEL_ID = 5481263  # TF 01 en F01/F02, o 5501145 (TD 06) en E06
CEILING_HEIGHT_M = 14.30  # Altura del cielorraso (ajustar según el apartamento)

# Diámetros según categoría (en pulgadas, convertir a pies para Revit)
DIAMETROS = {
    "Lighting Fixtures": 0.63 / 12.0,      # 1/2" en pies
    "Electrical Fixtures": 0.63 / 12.0,    # 1/2" en pies
    "Communication Devices": 0.83 / 12.0,  # 3/4" en pies
    "Data Devices": 1.06 / 12.0,           # 1" en pies
}

# Familias de conduit (ajustar según las familias disponibles en el proyecto)
CONDUIT_FAMILY_NAME = "Tubo"  # Nombre de la familia de conduit
CONDUIT_FITTING_FAMILY_NAME = "Conduit Elbow 90°"  # Nombre de la familia de codos

print("\nConfiguración:")
print("  Apartamento: %s" % APTO_NAME)
print("  Panel ID: %d" % PANEL_ID)
print("  Altura cielorraso: %.2f m" % CEILING_HEIGHT_M)

# ============================================================================
# 2. OBTENER DISPOSITIVOS Y PANEL
# ============================================================================
print("\nObteniendo dispositivos...")
dispositivos = []
cats = [BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_ElectricalFixtures,
        BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_DataDevices]

for cat in cats:
    for e in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
        loc = e.Location
        if isinstance(loc, LocationPoint):
            pt = loc.Point
            dispositivos.append({
                "id": iid(e.Id),
                "categoria": e.Category.Name,
                "x_m": pt.X * FT,
                "y_m": pt.Y * FT,
                "z_m": pt.Z * FT
            })

print("Dispositivos encontrados: %d" % len(dispositivos))

panel = by_id(doc, PANEL_ID)
if not panel:
    print("ERROR: Panel Id=%d no encontrado" % PANEL_ID)
    exit(1)

panel_pt = panel.Location.Point
print("Panel encontrado: Id=%d | Pos=(%.2f, %.2f, %.2f) m" % (
    panel_pt.X * FT, panel_pt.Y * FT, panel_pt.Z * FT))

# ============================================================================
# 3. BUSCAR FAMILIAS DE CONDUIT
# ============================================================================
print("\nBuscando familias de conduit...")
conduit_types = {}
for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsElementType().ToElements():
    try:
        fam_name = clean(fs.Family.Name)
        type_name = clean(fs.Name)
        key = "%s|%s" % (fam_name, type_name)
        conduit_types[key] = fs
    except:
        pass

print("Tipos de conduit encontrados: %d" % len(conduit_types))

# Buscar codos
fitting_types = {}
for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ConduitFitting).WhereElementIsElementType().ToElements():
    try:
        fam_name = clean(fs.Family.Name)
        type_name = clean(fs.Name)
        key = "%s|%s" % (fam_name, type_name)
        fitting_types[key] = fs
    except:
        pass

print("Tipos de accesorios encontrados: %d" % len(fitting_types))

# ============================================================================
# 4. GENERAR RUTEO ORTOGONAL
# ============================================================================
print("\n" + "=" * 78)
print("GENERANDO RUTEO ORTOGONAL")
print("=" * 78)

t = Transaction(doc, "Ruteo automático ortogonal")
t.Start()

conduits_creados = 0
fittings_creados = 0

# Punto de inicio del troncal (desde el panel)
troncal_start = XYZ(panel_pt.X, panel_pt.Y, CEILING_HEIGHT_M * M2FT)

for idx, dev in enumerate(dispositivos):
    print("\n[%d/%d] Dispositivo Id=%d (%s)" % (idx + 1, len(dispositivos), dev["id"], dev["categoria"]))
    
    # Punto del dispositivo
    dev_pt = XYZ(dev["x_m"] * M2FT, dev["y_m"] * M2FT, dev["z_m"] * M2FT)
    
    # Punto en el cielorraso (bajante)
    ceiling_pt = XYZ(dev_pt.X, dev_pt.Y, CEILING_HEIGHT_M * M2FT)
    
    # Obtener diámetro según categoría
    diam_ft = DIAMETROS.get(dev["categoria"], 0.63 / 12.0)
    
    # Buscar tipo de conduit con ese diámetro
    conduit_type = None
    for key, fs in conduit_types.items():
        try:
            p_diam = fs.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
            if p_diam and abs(p_diam.AsDouble() - diam_ft) < 0.01:
                conduit_type = fs
                break
        except:
            pass
    
    if not conduit_type:
        print("  WARNING: No se encontró conduit de %.2f\", usando el primero disponible" % (diam_ft * 12.0))
        conduit_type = list(conduit_types.values())[0] if conduit_types else None
    
    if not conduit_type:
        print("  ERROR: No hay tipos de conduit disponibles")
        continue
    
    try:
        # 1. Crear bajante vertical (desde dispositivo hasta cielorraso)
        line_vertical = Line.CreateBound(dev_pt, ceiling_pt)
        conduit_vertical = doc.Create.NewConduit(conduit_type, line_vertical)
        conduits_creados += 1
        print("  ✓ Bajante vertical creada (Id=%d)" % iid(conduit_vertical.Id))
        
        # 2. Crear codo en el cielorraso
        # (Nota: Revit puede crear codos automáticamente al conectar conduits)
        
        # 3. Crear tramo horizontal desde el cielorraso hasta el troncal
        # Estrategia simple: ir en X primero, luego en Y
        intermediate_pt = XYZ(ceiling_pt.X, troncal_start.Y, ceiling_pt.Z)
        
        # Tramo en X
        if abs(ceiling_pt.X - troncal_start.X) > 0.01:
            line_x = Line.CreateBound(ceiling_pt, intermediate_pt)
            conduit_x = doc.Create.NewConduit(conduit_type, line_x)
            conduits_creados += 1
            print("  ✓ Tramo horizontal X creado (Id=%d)" % iid(conduit_x.Id))
        
        # Tramo en Y
        if abs(intermediate_pt.Y - troncal_start.Y) > 0.01:
            line_y = Line.CreateBound(intermediate_pt, troncal_start)
            conduit_y = doc.Create.NewConduit(conduit_type, line_y)
            conduits_creados += 1
            print("  ✓ Tramo horizontal Y creado (Id=%d)" % iid(conduit_y.Id))
        
    except Exception as e:
        print("  ERROR: %s" % str(e))

t.Commit()

# ============================================================================
# 5. REPORTE FINAL
# ============================================================================
print("\n" + "=" * 78)
print("REPORTE FINAL")
print("=" * 78)
print("Conduits creados: %d" % conduits_creados)
print("Accesorios creados: %d" % fittings_creados)
print("=" * 78)