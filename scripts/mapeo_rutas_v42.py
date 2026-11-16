# -*- coding: utf-8 -*-
# mapeo_rutas_v42.py | v42.0 | 2026-11-14
# Mapea conduits a dispositivos por proximidad geométrica
import io, json, math, datetime

VER = "42.0"
print("=" * 78)
print("MAPEO DE RUTAS v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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

# ============================================================================
# 1. CARGAR DATOS DEL ANÁLISIS ANTERIOR
# ============================================================================
JSON_RUTEO = r"D:\Work\PROJECTS\RevitElectrico\data\analisis_ruteo_F01_F02.json"
print("\nCargando análisis de ruteo...")
with io.open(JSON_RUTEO, 'r', encoding='utf-8') as f:
    data_ruteo = json.load(f)

conduits_raw = data_ruteo.get("conduits", [])
fittings = data_ruteo.get("accesorios", [])

# FILTRO CRÍTICO: Solo elementos en el rango de altura del Piso 5 (13.0m a 16.5m)
Z_MIN = 13.0
Z_MAX = 16.5

conduits = []
for c in conduits_raw:
    z_prom = c.get("altura_promedio_m", 0)
    if Z_MIN <= z_prom <= Z_MAX:
        conduits.append(c)

print("Conduits totales: %d | Filtrados en Piso 5 (Z=%.1f-%.1f): %d" % (len(conduits_raw), Z_MIN, Z_MAX, len(conduits)))

# ============================================================================
# 2. OBTENER DISPOSITIVOS ELÉCTRICOS EN EL MODELO
# ============================================================================
print("\nObteniendo dispositivos eléctricos...")
dispositivos = []
cats = [BuiltInCategory.OST_LightingFixtures, BuiltInCategory.OST_ElectricalFixtures, 
        BuiltInCategory.OST_CommunicationDevices, BuiltInCategory.OST_DataDevices]

for cat in cats:
    for e in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
        loc = e.Location
        if isinstance(loc, LocationPoint):
            pt = loc.Point
            z_m = pt.Z * FT
            if Z_MIN <= z_m <= Z_MAX:  # Solo del piso actual
                # Intentar obtener el Mark o Handle
                mark = ""
                try:
                    p_mk = e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
                    if p_mk and p_mk.HasValue:
                        mark = p_mk.AsString()
                except:
                    pass
                
                dispositivos.append({
                    "id": iid(e.Id),
                    "mark": mark,
                    "x_m": pt.X * FT,
                    "y_m": pt.Y * FT,
                    "z_m": z_m,
                    "categoria": e.Category.Name
                })

print("Dispositivos encontrados en el rango de altura: %d" % len(dispositivos))

# ============================================================================
# 3. MAPEO POR PROXIMIDAD
# ============================================================================
print("\n" + "=" * 78)
print("MAPEANDO CONEXIONES (Tolerancia: 0.30 m)")
print("=" * 78)

TOL_PROXIMIDAD = 0.30  # metros
mapeo = []

for dev in dispositivos:
    mejor_conduit = None
    dist_min = float('inf')
    punto_conexion = None
    
    for c in conduits:
        # Revisar extremo inicial
        d_start = math.sqrt((dev["x_m"] - c["x_start_m"])**2 + (dev["y_m"] - c["y_start_m"])**2 + (dev["z_m"] - c["z_start_m"])**2)
        if d_start < dist_min:
            dist_min = d_start
            mejor_conduit = c
            punto_conexion = "inicio"
            
        # Revisar extremo final
        d_end = math.sqrt((dev["x_m"] - c["x_end_m"])**2 + (dev["y_m"] - c["y_end_m"])**2 + (dev["z_m"] - c["z_end_m"])**2)
        if d_end < dist_min:
            dist_min = d_end
            mejor_conduit = c
            punto_conexion = "fin"
    
    if mejor_conduit and dist_min <= TOL_PROXIMIDAD:
        mapeo.append({
            "dispositivo_id": dev["id"],
            "dispositivo_mark": dev["mark"],
            "categoria": dev["categoria"],
            "conduit_id": mejor_conduit["id"],
            "conduit_tipo": mejor_conduit["tipo"],
            "diametro_pulg": mejor_conduit.get("diametro_pulg"),
            "punto_conexion": punto_conexion,
            "distancia_m": round(dist_min, 3),
            "coord_dev": [dev["x_m"], dev["y_m"], dev["z_m"]],
            "coord_conduit": [mejor_conduit["x_start_m"], mejor_conduit["y_start_m"], mejor_conduit["z_start_m"]] if punto_conexion == "inicio" else [mejor_conduit["x_end_m"], mejor_conduit["y_end_m"], mejor_conduit["z_end_m"]]
        })
        print("  [OK] %-20s (Id:%-6s) -> Conduit Id:%-6s (%s, %.2f\") | Dist: %.2f m" % (
            dev["categoria"][:20], str(dev["id"]), str(mejor_conduit["id"]), mejor_conduit["tipo"], 
            mejor_conduit.get("diametro_pulg", "?"), dist_min))
    else:
        print("  [!] %-20s (Id:%-6s) -> SIN CONDUIT CERCANO" % (dev["categoria"][:20], str(dev["id"])))

# ============================================================================
# 4. GUARDAR RESULTADOS
# ============================================================================
output_path = r"D:\Work\PROJECTS\RevitElectrico\data\mapeo_rutas_F01_F02.json"
with io.open(output_path, 'w', encoding='utf-8') as f:
    json.dump({
        "version": VER,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_conduits_filtrados": len(conduits),
        "total_dispositivos": len(dispositivos),
        "conexiones_exitosas": len(mapeo),
        "mapeo": mapeo
    }, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 78)
print("RESULTADO GUARDADO")
print("=" * 78)
print("Archivo: %s" % output_path)
print("Conexiones mapeadas: %d de %d dispositivos" % (len(mapeo), len(dispositivos)))
print("=" * 78)