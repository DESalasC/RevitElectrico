# -*- coding: utf-8 -*-
# ruteo_ortogonal_v50_actualizado.py | v50.1 | 2026-11-14
# Ruteo automático ortogonal para conduits eléctricos - ACTUALIZADO
import io, json, math, datetime

VER = "50.1"
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
except:
    import clr
    clr.AddReference('RevitAPI')
    from Autodesk.Revit.DB import *
    from Autodesk.Revit.DB.Electrical import *

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
# 1. CONFIGURACIÓN ACTUALIZADA
# ============================================================================
APTO_NAME = "F 01"
PANEL_ID = 5501141  # TF 01 - CORREGIDO
CEILING_HEIGHT_M = 14.30

# Diámetros según categoría (en pies para Revit)
DIAMETROS = {
    "Lighting Fixtures": 0.63 / 12.0,      # 1/2" en pies
    "Electrical Fixtures": 0.63 / 12.0,    # 1/2" en pies
    "Communication Devices": 0.83 / 12.0,  # 3/4" en pies
    "Data Devices": 1.06 / 12.0,           # 1" en pies
}

print("\nConfiguración:")
print("  Apartamento: %s" % APTO_NAME)
print("  Panel ID: %d (TF 01)" % PANEL_ID)
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
print("Panel encontrado: Id=%d (TF 01) | Pos=(%.2f, %.2f, %.2f) m" % (
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

# Mostrar tipos disponibles
print("\nTipos de conduit disponibles:")
for i, (key, fs) in enumerate(list(conduit_types.items())[:10]):
    try:
        p_diam = fs.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
        diam = p_diam.AsDouble() * 12.0 if p_diam else 0
        print("  [%d] %s | Diámetro: %.2f\"" % (i+1, key, diam))
    except:
        print("  [%d] %s | Diámetro: ?" % (i+1, key))

# ============================================================================
# 4. GENERAR RUTEO ORTOGONAL (PRUEBA CON 5 DISPOSITIVOS)
# ============================================================================
print("\n" + "=" * 78)
print("GENERANDO RUTEO ORTOGONAL (PRUEBA CON 5 DISPOSITIVOS)")
print("=" * 78)

t = Transaction(doc, "Ruteo automático ortogonal - Prueba")
t.Start()

conduits_creados = 0

# Tomar solo los primeros 5 dispositivos para prueba
dispositivos_prueba = dispositivos[:5]

troncal_start = XYZ(panel_pt.X, panel_pt.Y, CEILING_HEIGHT_M * M2FT)

for idx, dev in enumerate(dispositivos_prueba):
    print("\n[%d/%d] Dispositivo Id=%d (%s)" % (idx + 1, len(dispositivos_prueba), dev["id"], dev["categoria"]))
    
    dev_pt = XYZ(dev["x_m"] * M2FT, dev["y_m"] * M2FT, dev["z_m"] * M2FT)
    ceiling_pt = XYZ(dev_pt.X, dev_pt.Y, CEILING_HEIGHT_M * M2FT)
    
    diam_ft = DIAMETROS.get(dev["categoria"], 0.63 / 12.0)
    
    # Buscar tipo de conduit con ese diámetro
    conduit_type = None
    for key, fs in conduit_types.items():
        try:
            p_diam = fs.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
            if p_diam and abs(p_diam.AsDouble() - diam_ft) < 0.01:
                conduit_type = fs
                print("  Tipo seleccionado: %s (%.2f\")" % (key, diam_ft * 12.0))
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
        # 1. Crear bajante vertical
        line_vertical = Line.CreateBound(dev_pt, ceiling_pt)
        conduit_vertical = doc.Create.NewConduit(conduit_type, line_vertical)
        conduits_creados += 1
        print("  ✓ Bajante vertical creada (Id=%d)" % iid(conduit_vertical.Id))
        
        # 2. Crear tramo horizontal
        intermediate_pt = XYZ(ceiling_pt.X, troncal_start.Y, ceiling_pt.Z)
        
        if abs(ceiling_pt.X - troncal_start.X) > 0.01:
            line_x = Line.CreateBound(ceiling_pt, intermediate_pt)
            conduit_x = doc.Create.NewConduit(conduit_type, line_x)
            conduits_creados += 1
            print("  ✓ Tramo horizontal X creado (Id=%d)" % iid(conduit_x.Id))
        
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
print("\n⚠️  IMPORTANTE: Revisa visualmente el resultado en Revit")
print("   Si los conduits se ven correctos, podemos proceder con todos los dispositivos")
print("=" * 78)