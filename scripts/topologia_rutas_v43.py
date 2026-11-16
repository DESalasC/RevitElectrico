# -*- coding: utf-8 -*-
# topologia_rutas_v43.py | v43.0 | 2026-11-14
# Construye cadenas de ruteo a partir del mapeo dispositivo-conduit
import io, json, math, datetime

VER = "43.0"
print("=" * 78)
print("TOPOLOGIA DE RUTAS v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 78)

try:
    _ = doc.Title
except:
    doc = __revit__.ActiveUIDocument.Document
print("Documento: " + doc.Title)

# ============================================================================
# 1. CARGAR DATOS
# ============================================================================
MAPEO_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\mapeo_rutas_F01_F02.json"
ANALISIS_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\analisis_ruteo_F01_F02.json"

print("\nCargando datos...")
with io.open(MAPEO_PATH, 'r', encoding='utf-8') as f:
    mapeo_data = json.load(f)

with io.open(ANALISIS_PATH, 'r', encoding='utf-8') as f:
    analisis_data = json.load(f)

conduits = {c["id"]: c for c in analisis_data.get("conduits", [])}
fittings = {f["id"]: f for f in analisis_data.get("accesorios", [])}
mapeo = mapeo_data.get("mapeo", [])

print("Conduits cargados: %d" % len(conduits))
print("Accesorios cargados: %d" % len(fittings))
print("Conexiones dispositivo-conduit: %d" % len(mapeo))

# ============================================================================
# 2. CONSTRUIR GRAFO DE CONEXIONES
# ============================================================================
print("\n" + "=" * 78)
print("CONSTRUYENDO GRAFO DE CONEXIONES")
print("=" * 78)

# El grafo será: {id_elemento: [lista de ids conectados]}
grafo = {}

# Agregar conexiones de conduits
for c_id, c_data in conduits.items():
    grafo[c_id] = c_data.get("conectores", [])

# Agregar conexiones de accesorios
for f_id, f_data in fittings.items():
    grafo[f_id] = f_data.get("conectores", [])

# Agregar dispositivos al grafo (como nodos finales)
for m in mapeo:
    dev_id = m["dispositivo_id"]
    cond_id = m["conduit_id"]
    if dev_id not in grafo:
        grafo[dev_id] = []
    grafo[dev_id].append(cond_id)
    if cond_id not in grafo:
        grafo[cond_id] = []
    grafo[cond_id].append(dev_id)

print("Nodos totales en el grafo: %d" % len(grafo))

# ============================================================================
# 3. IDENTIFICAR RUTAS (Caminos desde dispositivos hacia atrás)
# ============================================================================
print("\n" + "=" * 78)
print("IDENTIFICANDO RUTAS")
print("=" * 78)

rutas = []
visitados_global = set()

for m in mapeo:
    dev_id = m["dispositivo_id"]
    if dev_id in visitados_global:
        continue  # Ya procesado en otra ruta
    
    # Iniciar recorrido desde el dispositivo
    ruta_actual = {
        "dispositivo_id": dev_id,
        "dispositivo_mark": m["dispositivo_mark"],
        "categoria": m["categoria"],
        "cadena_elementos": [],
        "longitud_total_m": 0.0,
        "diametros_involucrados": set()
    }
    
    # Recorrido en profundidad (DFS) simple hacia atrás
    pila = [dev_id]
    visitados_ruta = {dev_id}
    
    while pila:
        nodo_actual = pila.pop()
        
        # Si es un conduit, sumar su longitud y diámetro
        if nodo_actual in conduits:
            c_data = conduits[nodo_actual]
            ruta_actual["cadena_elementos"].append({
                "tipo": "conduit",
                "id": nodo_actual,
                "nombre_tipo": c_data.get("tipo", "Desconocido"),
                "diametro_pulg": c_data.get("diametro_pulg"),
                "longitud_m": c_data.get("longitud_m", 0.0),
                "orientacion": c_data.get("orientacion")
            })
            ruta_actual["longitud_total_m"] += c_data.get("longitud_m", 0.0)
            if c_data.get("diametro_pulg"):
                ruta_actual["diametros_involucrados"].add(c_data["diametro_pulg"])
        
        # Si es un accesorio, registrarlo
        elif nodo_actual in fittings:
            f_data = fittings[nodo_actual]
            ruta_actual["cadena_elementos"].append({
                "tipo": "accesorio",
                "id": nodo_actual,
                "nombre_tipo": f_data.get("tipo", "Desconocido")
            })
        
        # Explorar vecinos no visitados
        for vecino in grafo.get(nodo_actual, []):
            if vecino not in visitados_ruta:
                # Detener el recorrido si llegamos a un "origen" conocido (ej. tablero o CP)
                # Por ahora, limitamos la profundidad para no recorrer todo el edificio
                if len(ruta_actual["cadena_elementos"]) < 15:  # Límite de seguridad
                    visitados_ruta.add(vecino)
                    visitados_global.add(vecino)
                    pila.append(vecino)
    
    # Convertir set a lista para serialización JSON
    ruta_actual["diametros_involucrados"] = list(ruta_actual["diametros_involucrados"])
    rutas.append(ruta_actual)

print("Rutas únicas identificadas: %d" % len(rutas))

# ============================================================================
# 4. ANÁLISIS DE PATRONES DE RUTA
# ============================================================================
print("\n" + "=" * 78)
print("ANÁLISIS DE PATRONES DE RUTA")
print("=" * 78)

# Estadísticas por categoría de dispositivo
por_categoria = {}
for r in rutas:
    cat = r["categoria"]
    por_categoria[cat] = por_categoria.get(cat, 0) + 1

print("\nRutas por categoría de dispositivo:")
for cat, count in sorted(por_categoria.items()):
    print("  %-25s: %d rutas" % (cat, count))

# Estadísticas de diámetros por categoría
print("\nDiámetros típicos por categoría:")
for cat in por_categoria.keys():
    rutas_cat = [r for r in rutas if r["categoria"] == cat]
    diametros_cat = set()
    for r in rutas_cat:
        diametros_cat.update(r["diametros_involucrados"])
    print("  %-25s: %s" % (cat, ", ".join(sorted([str(d) + '"' for d in diametros_cat]))))

# Longitud promedio de ruta
longitudes = [r["longitud_total_m"] for r in rutas if r["longitud_total_m"] > 0]
if longitudes:
    print("\nLongitud promedio de ruta: %.2f m (Min: %.2f m, Max: %.2f m)" % (
        sum(longitudes)/len(longitudes), min(longitudes), max(longitudes)))

# ============================================================================
# 5. GUARDAR RESULTADOS
# ============================================================================
output_path = r"D:\Work\PROJECTS\RevitElectrico\data\topologia_rutas_F01_F02.json"
with io.open(output_path, 'w', encoding='utf-8') as f:
    json.dump({
        "version": VER,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rutas": len(rutas),
        "rutas": rutas,
        "estadisticas": {
            "por_categoria": por_categoria,
            "longitud_promedio_m": sum(longitudes)/len(longitudes) if longitudes else 0
        }
    }, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 78)
print("RESULTADO GUARDADO")
print("=" * 78)
print("Archivo: %s" % output_path)
print("Total rutas analizadas: %d" % len(rutas))
print("=" * 78)