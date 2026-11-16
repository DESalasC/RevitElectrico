# -*- coding: utf-8 -*-
# ruteo_ortogonal_v54.py | v54.0 | 2026-11-14
# Ruteo automático ortogonal robusto + asignación de parámetros personalizados
import io, json, math, datetime

VER = "54.0"
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
except:
    import clr
    clr.AddReference('RevitAPI')
    from Autodesk.Revit.DB import *

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

# ============================================================================
# 1. CONFIGURACIÓN
# ============================================================================
# Usamos el documento E06 con el panel TF 01 para prueba de comparación
APTO_NAME = "F 01 (prueba en doc E06)"
PANEL_ID = 5501141  # TF 01 en el documento E06
CEILING_HEIGHT_M = 14.30

print("\nConfiguracion:")
print("  Apartamento: %s" % APTO_NAME)
print("  Panel ID: %d" % PANEL_ID)
print("  Altura cielorraso: %.2f m" % CEILING_HEIGHT_M)

# ============================================================================
# 2. OBTENER PANEL Y TIPOS DE CONDUIT
# ============================================================================
panel = by_id(doc, PANEL_ID)
if not panel:
    print("ERROR: Panel Id=%d no encontrado" % PANEL_ID)
    exit(1)

panel_pt = panel.Location.Point
print("Panel encontrado: Id=%d | Pos=(%.2f, %.2f, %.2f) m" % (
    PANEL_ID, panel_pt.X * FT, panel_pt.Y * FT, panel_pt.Z * FT))

# Obtener todos los tipos de conduit disponibles
conduit_types = []
for fs in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsElementType().ToElements():
    conduit_types.append(fs)

if not conduit_types:
    print("ERROR: No se encontraron tipos de conduit en el documento.")
    exit(1)

# Usar el primer tipo disponible como fallback (ya sabemos que es "Tubo", TypeId 112216)
default_conduit_type = conduit_types[0]
print("Tipo de conduit por defecto seleccionado: %s (TypeId=%d)" % (default_conduit_type.Name, iid(default_conduit_type.Id)))

# ============================================================================
# 3. OBTENER DISPOSITIVOS
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
            # Filtrar solo dispositivos cerca del panel TF 01 para la prueba (X~11.6, Y~7.5)
            # Esto evita que el script intente rutear dispositivos de otros apartamentos en el mismo archivo
            if 10.0 < (pt.X * FT) < 13.0 and 6.0 < (pt.Y * FT) < 9.0:
                dispositivos.append({
                    "id": iid(e.Id),
                    "categoria": e.Category.Name,
                    "x_m": pt.X * FT,
                    "y_m": pt.Y * FT,
                    "z_m": pt.Z * FT
                })

print("Dispositivos encontrados en la zona de prueba: %d" % len(dispositivos))

# ============================================================================
# 4. GENERAR RUTEO ORTOGONAL
# ============================================================================
print("\n" + "=" * 78)
print("GENERANDO RUTEO ORTOGONAL")
print("=" * 78)

t = Transaction(doc, "Ruteo automatico ortogonal v54")
t.Start()

conduits_creados = 0

# Punto de inicio del troncal en el cielorraso sobre el panel
troncal_start = XYZ(panel_pt.X, panel_pt.Y, CEILING_HEIGHT_M * M2FT)

for idx, dev in enumerate(dispositivos):
    print("\n[%d/%d] Dispositivo Id=%d (%s)" % (idx + 1, len(dispositivos), dev["id"], dev["categoria"]))
    
    dev_pt = XYZ(dev["x_m"] * M2FT, dev["y_m"] * M2FT, dev["z_m"] * M2FT)
    ceiling_pt = XYZ(dev_pt.X, dev_pt.Y, CEILING_HEIGHT_M * M2FT)
    
    try:
        # 1. Crear bajante vertical
        line_vertical = Line.CreateBound(dev_pt, ceiling_pt)
        conduit_vertical = doc.Create.NewConduit(default_conduit_type, line_vertical)
        conduits_creados += 1
        print("  OK - Bajante vertical creada (Id=%d)" % iid(conduit_vertical.Id))
        
        # 2. Crear tramo horizontal ortogonal (primero en X, luego en Y)
        intermediate_pt = XYZ(ceiling_pt.X, troncal_start.Y, ceiling_pt.Z)
        
        if abs(ceiling_pt.X - troncal_start.X) > 0.01:
            line_x = Line.CreateBound(ceiling_pt, intermediate_pt)
            conduit_x = doc.Create.NewConduit(default_conduit_type, line_x)
            conduits_creados += 1
            print("  OK - Tramo horizontal X creado (Id=%d)" % iid