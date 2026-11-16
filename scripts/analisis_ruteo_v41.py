# -*- coding: utf-8 -*-
# analisis_ruteo_v41.py | v41.0 | 2026-11-14
# CORREGIDO: obtener tipo de conduit correctamente
import io, json, math, datetime

VER = "41.0"
print("=" * 78)
print("ANALISIS DE RUTEO v%s | %s" % (VER, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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

def clean(s):
    if not s: return s
    return s.replace("\ufeff", "").replace("\u200b", "").strip()

def get_type_name(elem):
    """Obtener nombre del tipo de un elemento"""
    try:
        type_id = elem.GetTypeId()
        if type_id and iid(type_id) > 0:
            tipo = doc.GetElement(type_id)
            if tipo:
                # Intentar varios métodos
                try:
                    return clean(tipo.Name)
                except:
                    pass
                try:
                    p = tipo.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                    if p and p.HasValue:
                        return clean(p.AsString())
                except:
                    pass
    except:
        pass
    return "desconocido"

# ============================================================================
# 1. EXTRAER TODOS LOS CONDUITS
# ============================================================================
print("\n" + "=" * 78)
print("EXTRAYENDO CONDUITS")
print("=" * 78)

conduits = []
conduit_elements = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Conduit).WhereElementIsNotElementType().ToElements()
print("Total elementos conduit encontrados: %d" % len(conduit_elements))

for c in conduit_elements:
    try:
        # Información básica - CORREGIDO
        info = {
            "id": iid(c.Id),
            "tipo": get_type_name(c),
        }
        
        # Geometría
        loc = c.Location
        if isinstance(loc, LocationCurve):
            curve = loc.Curve
            pt_start = curve.GetEndPoint(0)
            pt_end = curve.GetEndPoint(1)
            
            info["x_start_m"] = round(pt_start.X * FT, 4)
            info["y_start_m"] = round(pt_start.Y * FT, 4)
            info["z_start_m"] = round(pt_start.Z * FT, 4)
            info["x_end_m"] = round(pt_end.X * FT, 4)
            info["y_end_m"] = round(pt_end.Y * FT, 4)
            info["z_end_m"] = round(pt_end.Z * FT, 4)
            
            # Longitud
            info["longitud_m"] = round(curve.Length * FT, 4)
            
            # Determinar orientación
            dz = abs(pt_end.Z - pt_start.Z) * FT
            if dz < 0.01:
                info["orientacion"] = "horizontal"
            elif abs(pt_end.X - pt_start.X) * FT < 0.01 and abs(pt_end.Y - pt_start.Y) * FT < 0.01:
                info["orientacion"] = "vertical"
            else:
                info["orientacion"] = "inclinada"
            
            # Altura promedio
            info["altura_promedio_m"] = round((pt_start.Z + pt_end.Z) / 2 * FT, 4)
        
        # Conectores (qué otros conduits se conectan)
        conectores = []
        try:
            for conn in c.MEPModel.ConnectorManager.Connectors:
                for ref in conn.AllRefs:
                    if ref.Owner.Id != c.Id:
                        conectores.append(iid(ref.Owner.Id))
        except:
            pass
        info["conectores"] = list(set(conectores))
        
        # Nivel
        try:
            p_lv = c.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
            if p_lv and p_lv.AsElementId() and iid(p_lv.AsElementId()) > 0:
                lvl_elem = doc.GetElement(p_lv.AsElementId())
                info["nivel"] = clean(lvl_elem.Name) if lvl_elem else ""
            else:
                info["nivel"] = ""
        except:
            info["nivel"] = ""
        
        # Diámetro (si está disponible)
        try:
            p_diam = c.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
            if p_diam and p_diam.HasValue:
                info["diametro_pulg"] = round(p_diam.AsDouble() * FT * 39.3701, 2)
            else:
                info["diametro_pulg"] = None
        except:
            info["diametro_pulg"] = None
        
        conduits.append(info)
    except Exception as e:
        print("  ERROR en conduit Id=%d: %s" % (iid(c.Id), str(e)))

print("Total conduits procesados: %d" % len(conduits))

# ============================================================================
# 2. EXTRAER ACCESORIOS (codos, tes, uniones)
# ============================================================================
print("\n" + "=" * 78)
print("EXTRAYENDO ACCESORIOS")
print("=" * 78)

fittings = []
fitting_elements = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ConduitFitting).WhereElementIsNotElementType().ToElements()
print("Total elementos accesorio encontrados: %d" % len(fitting_elements))

for f in fitting_elements:
    try:
        info = {
            "id": iid(f.Id),
            "tipo": get_type_name(f),
        }
        
        # Posición
        loc = f.Location
        if isinstance(loc, LocationPoint):
            pt = loc.Point
            info["x_m"] = round(pt.X * FT, 4)
            info["y_m"] = round(pt.Y * FT, 4)
            info["z_m"] = round(pt.Z * FT, 4)
        
        # Conectores
        conectores = []
        try:
            for conn in f.MEPModel.ConnectorManager.Connectors:
                for ref in conn.AllRefs:
                    if ref.Owner.Id != f.Id:
                        conectores.append(iid(ref.Owner.Id))
        except:
            pass
        info["conectores"] = list(set(conectores))
        
        fittings.append(info)
    except Exception as e:
        print("  ERROR en accesorio Id=%d: %s" % (iid(f.Id), str(e)))

print("Total accesorios procesados: %d" % len(fittings))

# ============================================================================
# 3. ANÁLISIS DE PATRONES
# ============================================================================
print("\n" + "=" * 78)
print("ANALISIS DE PATRONES")
print("=" * 78)

# Estadísticas por tipo de conduit
por_tipo = {}
for c in conduits:
    tipo = c.get("tipo", "desconocido")
    por_tipo[tipo] = por_tipo.get(tipo, 0) + 1

print("\nConduits por tipo:")
for tipo, count in sorted(por_tipo.items()):
    print("  %-30s: %d" % (tipo, count))

# Estadísticas por orientación
por_orient = {}
for c in conduits:
    orient = c.get("orientacion", "desconocida")
    por_orient[orient] = por_orient.get(orient, 0) + 1

print("\nConduits por orientación:")
for orient, count in sorted(por_orient.items()):
    print("  %-15s: %d" % (orient, count))

# Alturas promedio por orientación
alturas_por_orient = {}
for c in conduits:
    orient = c.get("orientacion")
    alt = c.get("altura_promedio_m")
    if orient and alt:
        if orient not in alturas_por_orient:
            alturas_por_orient[orient] = []
        alturas_por_orient[orient].append(alt)

print("\nAltura promedio por orientación:")
for orient, alturas in sorted(alturas_por_orient.items()):
    prom = sum(alturas) / len(alturas)
    print("  %-15s: %.2f m (min=%.2f, max=%.2f)" % (orient, prom, min(alturas), max(alturas)))

# Diámetros
diametros = {}
for c in conduits:
    d = c.get("diametro_pulg")
    if d:
        diametros[d] = diametros.get(d, 0) + 1

print("\nDiámetros encontrados:")
for d, count in sorted(diametros.items()):
    print("  %.2f pulg: %d conduits" % (d, count))

# Estadísticas de accesorios
por_tipo_acc = {}
for f in fittings:
    tipo = f.get("tipo", "desconocido")
    por_tipo_acc[tipo] = por_tipo_acc.get(tipo, 0) + 1

print("\nAccesorios por tipo:")
for tipo, count in sorted(por_tipo_acc.items()):
    print("  %-30s: %d" % (tipo, count))

# ============================================================================
# 4. GUARDAR RESULTADOS
# ============================================================================
output_path = r"D:\Work\PROJECTS\RevitElectrico\data\analisis_ruteo_F01_F02.json"
with io.open(output_path, 'w', encoding='utf-8') as f:
    json.dump({
        "version": VER,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "total_conduits": len(conduits),
        "total_accesorios": len(fittings),
        "conduits": conduits,
        "accesorios": fittings,
        "estadisticas": {
            "por_tipo": por_tipo,
            "por_orientacion": por_orient,
            "alturas_por_orientacion": {k: {"promedio": sum(v)/len(v), "min": min(v), "max": max(v)} 
                                       for k, v in alturas_por_orient.items()},
            "diametros": diametros,
            "accesorios_por_tipo": por_tipo_acc
        }
    }, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 78)
print("RESULTADO GUARDADO")
print("=" * 78)
print("Archivo: %s" % output_path)
print("Total conduits: %d" % len(conduits))
print("Total accesorios: %d" % len(fittings))
print("=" * 78)