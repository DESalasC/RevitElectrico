# -*- coding: utf-8 -*-
# =====================================================================
# RE6_ORACULO_ORIENTACION_E06_v01.py  |  SCRIPT_ID = ORC-ORI  |  VERSION 1.0.0
# Mide la orientacion real (bounding box) de cada familia|tipo en el
# apartamento E06 (modelado a mano en CENTRAL-V01) para establecer
# firmas de referencia y corregir los volteados detectados.
# =====================================================================
# EJECUCION: Copiar/pegar en pyRevit Python Shell con CENTRAL-V01 abierto.
# SALIDA: JSON en data/oraculo_orientacion_E06_v01.json
# =====================================================================

import sys
import json
import math
import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import UIApplication

# ---------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------
OUT_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\oraculo_orientacion_E06_v01.json"
FT2M = 0.3048

# Area aproximada de E06 (basada en inventario E06: x ~ -2 a 4, y ~ -0.2 a 8)
E06_BBOX_MIN = XYZ(-2.5 / FT2M, -0.5 / FT2M, 12.0 / FT2M)
E06_BBOX_MAX = XYZ(4.5 / FT2M, 8.5 / FT2M, 17.0 / FT2M)

# Familias objetivo (del mapeo del proyecto)
TARGET_FAMILIAS = [
    "M_Toma doble",
    "M_Comunicaciones",
    "M_Interruptores",
    "M_Climatizacion",
    "M_ClimatizacionV",
    "M_Pulsador - Interruptor",
    "M_Zumbador",
    "M_Timbre",
    "M_Toma - 220V",
    "M_Toma resistente a la intemperie",
    "M_Caja de conexiones hexagonal",
    "M_Cajas de conexiones - Sin carga",
    "M_Iluminacion",
    "Consolidation_Point",
    "E_Panel Distribucion",
    "EA",
    "M_Toma de telefono - Datos",
]

# Mapeo de nombre DXF a familia/tipo (para comparar con rotacion DXF)
DXF_TO_FAMILIA = {
    "ELEC-T-D-t-15A": ("M_Toma doble", "Normal"),
    "ELEC-T-GFCI-t-15A": ("M_Toma doble", "GFCI"),
    "ELEC-TEL": ("M_Comunicaciones", "Datos"),
    "ELEC-I-S-C1-5A": ("M_Interruptores", "Simple conmutable"),
    "ELEC-I-S-1-5A": ("M_Interruptores", "Simple"),
    "S3": ("M_Interruptores", "Triple"),
    "ELEC-F-CONTROL": ("M_Climatizacion", "Interruptor Ventilador"),
    "ELEC-F-VENT": ("M_ClimatizacionV", "Ventilador"),
    "ELEC-TIMBRE": ("M_Pulsador - Interruptor", "Timbre"),
    "ELEC-CAMPANA": ("M_Zumbador", "Campana timbre"),
    "ELEC-NET-PAU": ("Consolidation_Point", "CPB6L"),
    "Bala Stil Led 10W": ("M_Iluminacion", "SONO FLEX 10 trim"),
    "Bala Stil Led 13W": ("M_Iluminacion", "SONO FLEX 13 trim"),
    "Bala Stil Led 22W": ("M_Iluminacion", "SONO FLEX 22 trim"),
    "ELEC-EXT": ("EA", "M_Extractor"),
}

# Inventario E06 (para obtener rotacion DXF esperada por handle)
INV_E06_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\inventario_dispositivos_E06_v03.json"

# ---------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------
def eid(e):
    try:
        return int(e.Value)
    except Exception:
        try:
            return int(e.IntegerValue)
        except Exception:
            return -1

def num(x, n=4):
    try:
        return round(float(x), n)
    except Exception:
        return None

def v3(pt):
    return {"x_ft": num(pt.X), "y_ft": num(pt.Y), "z_ft": num(pt.Z),
            "x_m": num(pt.X * FT2M), "y_m": num(pt.Y * FT2M), "z_m": num(pt.Z * FT2M)}

def angle_deg(v1, v2):
    """Angulo entre dos vectores XYZ en grados [0, 360)"""
    try:
        a = v1.AngleTo(v2) * 180.0 / math.pi
        return num(a)
    except Exception:
        return None

def angle_signed(v1, v2, normal):
    """Angulo con signo (normal define sentido positivo)"""
    try:
        a = v1.AngleTo(v2) * 180.0 / math.pi
        cross = v1.CrossProduct(v2)
        if cross.Dot(normal) < 0:
            a = 360.0 - a
        return num(a)
    except Exception:
        return None

def long_axis_from_bbox(bbox):
    """Eje largo del bounding box (vector unitario en XY)"""
    if bbox is None or bbox.Min.IsAlmostEqualTo(bbox.Max):
        return None
    dx = bbox.Max.X - bbox.Min.X
    dy = bbox.Max.Y - bbox.Min.Y
    dz = bbox.Max.Z - bbox.Min.Z
    # Proyectar a XY para orientacion en planta
    if abs(dx) > abs(dy):
        return XYZ(1 if dx > 0 else -1, 0, 0)
    elif abs(dy) > abs(dx):
        return XYZ(0, 1 if dy > 0 else -1, 0)
    else:
        return XYZ(1 if dx > 0 else -1, 0, 0)

def bbox_extents(bbox):
    """Extensiones del bbox en mm"""
    if bbox is None:
        return {"x_mm": 0, "y_mm": 0, "z_mm": 0}
    dx = (bbox.Max.X - bbox.Min.X) * FT2M * 1000
    dy = (bbox.Max.Y - bbox.Min.Y) * FT2M * 1000
    dz = (bbox.Max.Z - bbox.Min.Z) * FT2M * 1000
    return {"x_mm": num(dx), "y_mm": num(dy), "z_mm": num(dz)}

def load_inventario_e06():
    try:
        with open(INV_E06_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print("[WARN] No se pudo cargar inventario E06: {}".format(e))
        return {"dispositivos": []}

def get_dxf_rotation_by_handle(handle, inv):
    for d in inv.get("dispositivos", []):
        if d.get("handle") == handle:
            return d.get("rotacion_grados")
    return None

# ---------------------------------------------------------------------
# RESOLUCION DEL DOCUMENTO
# ---------------------------------------------------------------------
def resolve_doc():
    G = globals()
    a = G.get("__revit__", None)
    if isinstance(a, UIApplication):
        return a.ActiveUIDocument.Document
    try:
        import __builtin__ as B
    except Exception:
        try:
            import builtins as B
        except Exception:
            B = None
    if B is not None:
        a = getattr(B, "__revit__", None)
        if isinstance(a, UIApplication):
            return a.ActiveUIDocument.Document
    try:
        from pyrevit import HOST_APP
        if HOST_APP.uiapp is not None:
            return HOST_APP.uiapp.ActiveUIDocument.Document
    except Exception:
        pass
    try:
        from RevitServices.Persistence import DocumentManager
        d = DocumentManager.Instance.CurrentDBDocument
        if d is not None:
            return d
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------
# PRINCIPAL
# ---------------------------------------------------------------------
def main():
    doc = resolve_doc()
    if doc is None:
        print("[ERROR] No se pudo resolver el documento Revit.")
        return

    print("=" * 78)
    print("ORACULO ORIENTACION E06  v1.0.0")
    print("Documento: {}".format(doc.Title))
    print("=" * 78)

    inv_e06 = load_inventario_e06()
    inv_by_handle = {}
    for d in inv_e06.get("dispositivos", []):
        inv_by_handle[d.get("handle")] = d

    # Collect all FamilyInstances in E06 area
    collector = FilteredElementCollector(doc).OfClass(FamilyInstance).WhereElementIsNotElementType()
    # Filtrar por bounding box aproximado de E06 (rapido)
    # Nota: filtro espacial preciso requiere BoundingBoxIntersectsFilter
    # Para simplicidad, filtramos despues de collect

    print("\nRecolectando instancias en area E06...")
    instances = []
    for fi in collector:
        try:
            fam_name = fi.Symbol.Family.Name
            if fam_name not in TARGET_FAMILIAS:
                continue
            loc = fi.Location
            if loc is None or loc.Point is None:
                continue
            pt = loc.Point
            if (pt.X < E06_BBOX_MIN.X or pt.X > E06_BBOX_MAX.X or
                pt.Y < E06_BBOX_MIN.Y or pt.Y > E06_BBOX_MAX.Y or
                pt.Z < E06_BBOX_MIN.Z or pt.Z > E06_BBOX_MAX.Z):
                continue
            instances.append(fi)
        except Exception:
            pass

    print("Instancias en area E06: {}".format(len(instances)))

    # Agrupar por familia|tipo
    groups = {}
    for fi in instances:
        try:
            fam_name = fi.Symbol.Family.Name
            type_name = fi.Symbol.Name
            key = "{} | {}".format(fam_name, type_name)
            if key not in groups:
                groups[key] = []
            groups[key].append(fi)
        except Exception:
            pass

    print("\nGrupos familia|tipo encontrados: {}".format(len(groups)))
    for k, v in sorted(groups.items()):
        print("  {} : {} instancias".format(k, len(v)))

    # Analizar cada grupo
    resultados = {
        "script": "ORC-ORI",
        "version": "1.0.0",
        "documento": doc.Title,
        "fecha": __import__("datetime").datetime.now().isoformat(),
        "area_bbox_m": {
            "min": {"x": -2.5, "y": -0.5, "z": 12.0},
            "max": {"x": 4.5, "y": 8.5, "z": 17.0}
        },
        "firmas_por_familia_tipo": {},
        "resumen_volteados": {}
    }

    for key, fis in sorted(groups.items()):
        fam_name, type_name = key.split(" | ", 1)
        print("\n--- Analizando: {} ---".format(key))

        firmas = []
        for fi in fis:
            try:
                eid_val = eid(fi.Id)
                loc = fi.Location
                pt = loc.Point if loc else None
                rot = loc.Rotation if loc and hasattr(loc, 'Rotation') else 0.0

                # Bounding box
                bb = fi.get_BoundingBox(None)
                ext = bbox_extents(bb)
                long_axis = long_axis_from_bbox(bb)

                # Host wall normal (si es face-based)
                host_normal = None
                host_id = None
                try:
                    host = fi.Host
                    if host is not None:
                        host_id = eid(host.Id)
                        # Obtener cara del host mas cercana
                        # Para muros, la normal apunta al exterior del muro
                        # Intentar obtener geometria del host
                        opts = Options()
                        opts.ComputeReferences = True
                        geom = host.get_Geometry(opts)
                        # Simplificado: usar Location.Curve del muro para normal
                        if hasattr(host, 'Location') and host.Location is not None:
                            wc = host.Location.Curve
                            if wc is not None:
                                dir_vec = wc.GetEndPoint(1).Subtract(wc.GetEndPoint(0)).Normalize()
                                # Normal perpendicular en XY (giro -90°)
                                host_normal = XYZ(-dir_vec.Y, dir_vec.X, 0)
                except Exception:
                    pass

                # Angulo relativo al host
                angulo_rel_host = None
                if long_axis is not None and host_normal is not None:
                    angulo_rel_host = angle_deg(long_axis, host_normal)

                # Buscar handle DXF correspondiente por proximidad
                handle_dxf = None
                rot_dxf = None
                min_dist = 1e9
                for d in inv_e06.get("dispositivos", []):
                    dpt = XYZ(d["x"] / FT2M, d["y"] / FT2M, d["z_absoluta_m"] / FT2M)
                    if pt is not None:
                        dist = pt.DistanceTo(dpt)
                        if dist < min_dist and dist < 0.5 / FT2M:  # < 0.5m
                            min_dist = dist
                            handle_dxf = d["handle"]
                            rot_dxf = d.get("rotacion_grados")

                firma = {
                    "element_id": eid_val,
                    "handle_dxf": handle_dxf,
                    "posicion_m": v3(pt) if pt else None,
                    "rotacion_location_deg": num(rot * 180.0 / math.pi) if rot else None,
                    "bbox_extents_mm": ext,
                    "long_axis_xy": {"x": num(long_axis.X), "y": num(long_axis.Y)} if long_axis else None,
                    "host_id": host_id,
                    "host_normal_xy": {"x": num(host_normal.X), "y": num(host_normal.Y)} if host_normal else None,
                    "angulo_relativo_host_deg": angulo_rel_host,
                    "rotacion_dxf_grados": rot_dxf,
                    "delta_dxf_vs_real": None
                }

                if rot_dxf is not None and firma["rotacion_location_deg"] is not None:
                    # La rotacion en Revit (location.Rotation) es el angulo del eje local de la familia
                    # Para face-based, hereda del host. El delta es lo que hay que corregir.
                    delta = firma["rotacion_location_deg"] - rot_dxf
                    # Normalizar a [-180, 180]
                    while delta > 180:
                        delta -= 360
                    while delta < -180:
                        delta += 360
                    firma["delta_dxf_vs_real"] = num(delta)

                firmas.append(firma)

            except Exception as e:
                print("  [ERROR] Instancia {}: {}".format(eid(fi.Id), e))

        # Estadisticas del grupo
        deltas = [f["delta_dxf_vs_real"] for f in firmas if f["delta_dxf_vs_real"] is not None]
        if deltas:
            delta_avg = sum(deltas) / len(deltas)
            delta_mode = max(set([round(d) for d in deltas]), key=[round(d) for d in deltas].count)
        else:
            delta_avg = None
            delta_mode = None

        resultados["firmas_por_familia_tipo"][key] = {
            "familia": fam_name,
            "tipo": type_name,
            "n_instancias": len(firmas),
            "instancias": firmas,
            "delta_promedio_grados": num(delta_avg) if delta_avg is not None else None,
            "delta_moda_grados": delta_mode,
            "bbox_tipico_mm": None  # se calcula abajo
        }

        # BBox tipico (mediana de extensiones)
        if firmas:
            xs = [f["bbox_extents_mm"]["x_mm"] for f in firmas if f["bbox_extents_mm"]]
            ys = [f["bbox_extents_mm"]["y_mm"] for f in firmas if f["bbox_extents_mm"]]
            zs = [f["bbox_extents_mm"]["z_mm"] for f in firmas if f["bbox_extents_mm"]]
            def median(lst):
                if not lst: return 0
                s = sorted(lst)
                n = len(s)
                return s[n//2] if n % 2 else (s[n//2-1] + s[n//2]) / 2.0
            resultados["firmas_por_familia_tipo"][key]["bbox_tipico_mm"] = {
                "x_mm": num(median(xs)),
                "y_mm": num(median(ys)),
                "z_mm": num(median(zs))
            }

        print("  Instancias: {}, Delta modo: {}, Delta prom: {}".format(
            len(firmas), delta_mode, num(delta_avg) if delta_avg else "N/A"))

    # Resumen de volteados (familias donde delta != 0 y != 90 para tomas)
    for key, data in resultados["firmas_por_familia_tipo"].items():
        delta = data.get("delta_moda_grados")
        if delta is not None and abs(delta) > 5:
            fam = data["familia"]
            resultados["resumen_volteados"][key] = {
                "familia": fam,
                "tipo": data["tipo"],
                "delta_moda_grados": delta,
                "delta_promedio_grados": data["delta_promedio_grados"],
                "interpretacion": "VOLTEADA" if abs(delta - 180) < 30 else ("DESFASADA_90" if abs(abs(delta) - 90) < 30 else "OTRA")
            }

    # Guardar JSON
    with open(OUT_PATH, 'w') as f:
        json.dump(resultados, f, indent=2)

    print("\n" + "=" * 78)
    print("RESULTADO GUARDADO EN: {}".format(OUT_PATH))
    print("=" * 78)

    # Imprimir resumen final
    print("\n>>> RESUMEN FIRMAS DE ORIENTACION <<<")
    for key, data in sorted(resultados["firmas_por_familia_tipo"].items()):
        print("  {:<40}  n={:>2}  delta_moda={:>6}  delta_prom={:>6}  bbox={}".format(
            key,
            data["n_instancias"],
            data["delta_moda_grados"] if data["delta_moda_grados"] is not None else "N/A",
            num(data["delta_promedio_grados"]) if data["delta_promedio_grados"] is not None else "N/A",
            data["bbox_tipico_mm"]
        ))

    print("\n>>> VOLTEADOS DETECTADOS <<<")
    for key, v in resultados["resumen_volteados"].items():
        print("  {} : delta_moda={} -> {}".format(key, v["delta_moda_grados"], v["interpretacion"]))

    return resultados

if __name__ == "__main__":
    main()