# -*- coding: utf-8 -*-
# asignar_circuitos_v25.py | v25.0 | 2026-11-14
# Extrae circuitos del DXF y asigna Panel + Circuit Number + Mark
import io, json, math, datetime, re

VER = "25.0"
print("=" * 78)
print("ASIGNAR CIRCUITOS v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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

try:
    import ezdxf
except ImportError:
    print("ERROR: ezdxf no está instalado")
    exit(1)

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
DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo E 06.dxf"
REPORT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\reporte_colocacion_E06_v24.json"
PANEL_NAME = "TD 06"

# ============================================================================
# 2. CARGAR REPORTE DE COLOCACIÓN
# ============================================================================
print("\nCargando reporte de colocación...")
with io.open(REPORT_PATH, "r", encoding="utf-8") as f:
    reporte = json.load(f)

print("Elementos en reporte: %d" % len(reporte))

# ============================================================================
# 3. LEER DXF Y EXTRAER TEXTOS
# ============================================================================
print("\nLeyendo DXF: " + DXF_PATH)
dxf_doc = ezdxf.readfile(DXF_PATH)
msp = dxf_doc.modelspace()

# Extraer INSERTs y TEXTs
inserts = {}
texts = []

for entity in msp:
    if entity.dxftype() == 'INSERT':
        handle = entity.dxf.handle
        x = entity.dxf.insert[0]
        y = entity.dxf.insert[1]
        inserts[handle] = {"x": x, "y": y}
    elif entity.dxftype() in ['TEXT', 'MTEXT']:
        x = entity.dxf.insert[0] if hasattr(entity.dxf, 'insert') else 0
        y = entity.dxf.insert[1] if hasattr(entity.dxf, 'insert') else 0
        text = entity.dxf.text if hasattr(entity.dxf, 'text') else ""
        if entity.dxftype() == 'MTEXT':
            text = entity.text
        texts.append({"x": x, "y": y, "text": text})

print("INSERTs encontrados: %d" % len(inserts))
print("TEXTs encontrados: %d" % len(texts))

# ============================================================================
# 4. ASOCIAR TEXTOS CERCANOS A CADA INSERT
# ============================================================================
print("\nAsociando textos a bloques...")
RADIO_BUSQUEDA = 0.5  # metros

circuito_por_handle = {}

for handle, ins in inserts.items():
    x_ins = ins["x"]
    y_ins = ins["y"]
    
    textos_cercanos = []
    for txt in texts:
        dx = txt["x"] - x_ins
        dy = txt["y"] - y_ins
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < RADIO_BUSQUEDA:
            textos_cercanos.append(txt["text"])
    
    # Buscar circuito (patrón: letras-números, ej: TE-03, IL-01, AL-02)
    circuito = None
    for txt in textos_cercanos:
        # Patrones comunes de circuitos eléctricos
        match = re.search(r'\b([A-Z]{2,3}-\d{2,3})\b', txt)
        if match:
            circuito = match.group(1)
            break
    
    if circuito:
        circuito_por_handle[handle] = circuito

print("Circuitos encontrados: %d" % len(circuito_por_handle))
print("\nCircuitos extraídos:")
for handle, circ in sorted(circuito_por_handle.items()):
    print("  Handle %s: %s" % (handle, circ))

# ============================================================================
# 5. ACTUALIZAR ELEMENTOS REVIT
# ============================================================================
print("\n" + "=" * 78)
print("ACTUALIZANDO ELEMENTOS REVIT")
print("=" * 78)

t = Transaction(doc, "Asignar circuitos y panel")
t.Start()

success_count = 0
error_count = 0

for item in reporte:
    if item["status"] != "OK":
        continue
    
    handle = item["handle"]
    revit_id = item["revit_id"]
    nombre = item["nombre"]
    
    elem = by_id(doc, revit_id)
    if not elem:
        print("\n[%s] ERROR: Elemento %d no encontrado" % (handle, revit_id))
        error_count += 1
        continue
    
    print("\n[%s] %s (Id=%d)" % (handle, nombre, revit_id))
    
    # Obtener circuito
    circuito = circuito_por_handle.get(handle, "SIN CIRCUITO")
    
    # 1. Asignar Panel
    try:
        p_panel = elem.get_Parameter(BuiltInParameter.RBS_ELEC_PANEL_NAME)
        if p_panel and not p_panel.IsReadOnly:
            p_panel.Set(PANEL_NAME)
            print("  Panel: %s" % PANEL_NAME)
    except Exception as e:
        print("  ERROR Panel: %s" % str(e))
    
    # 2. Asignar Circuit Number
    try:
        p_circuit = elem.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_NUMBER)
        if p_circuit and not p_circuit.IsReadOnly:
            p_circuit.Set(circuito)
            print("  Circuit Number: %s" % circuito)
    except Exception as e:
        print("  ERROR Circuit: %s" % str(e))
    
    # 3. Actualizar Mark
    try:
        p_mk = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if p_mk and not p_mk.IsReadOnly:
            mark_val = "E06|%s|%s" % (handle, circuito)
            p_mk.Set(mark_val)
            print("  Mark: %s" % mark_val)
    except Exception as e:
        print("  ERROR Mark: %s" % str(e))
    
    success_count += 1

t.Commit()

# ============================================================================
# 6. REPORTE FINAL
# ============================================================================
print("\n" + "=" * 78)
print("REPORTE FINAL")
print("=" * 78)
print("Elementos actualizados: %d" % success_count)
print("Errores: %d" % error_count)

# Resumen de circuitos
print("\nResumen de circuitos asignados:")
circuitos_asignados = {}
for item in reporte:
    if item["status"] == "OK":
        handle = item["handle"]
        circuito = circuito_por_handle.get(handle, "SIN CIRCUITO")
        circuitos_asignados[circuito] = circuitos_asignados.get(circuito, 0) + 1

for circ, count in sorted(circuitos_asignados.items()):
    print("  %-15s: %d dispositivos" % (circ, count))

print("\n" + "=" * 78)
print("FIN - %s" % datetime.datetime.now().strftime("%H:%M:%S"))
print("=" * 78)