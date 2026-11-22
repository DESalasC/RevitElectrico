# -*- coding: utf-8 -*-
"""
F7_RUTEO_PYREVIT_v02.py - Ruteo de conduits reales en Revit 2026 (pyRevit IronPython 2.7)

Correcciones sobre v01:
  1. CRITICO: Toda la creacion va envuelta en una Transaction (sin ella,
     Conduit.Create lanza InvalidOperationException).
  2. CRITICO: os.makedirs(..., exist_ok=True) para no fallar si el dir existe.
     En IronPython 2.7 se emula con try/except OSError.
  3. sys.exit() reemplazado por 'raise SystemExit(1)' (mas limpio en pyRevit).
  4. RBS_CONDUIT_DIAMETER_PARAM en Revit 2024+ es parametro de TIPO, no de
     instancia. Se intenta asignar al tipo dentro de la misma transaccion;
     si el tipo es read-only, se reporta como warning y se continúa.
  5. Validacion p1 != p2 (distancia >= 1 mm) para evitar ArgumentException.
  6. Reporte incluye ElementId del conduit creado.
  7. Se quito clr.AddReference("RevitAPIUI") innecesario.

Uso (dentro de pyRevit Python Shell o como script pyRevit en Revit 2026):
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\F7_RUTEO_PYREVIT_v02.py").read())
"""

import json
import clr
import datetime
import sys
import os

clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    XYZ, ElementId, BuiltInParameter, FilteredElementCollector,
    Transaction, Level,
)
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
from System import Int64

VERSION = "v02"

# TypeIds de conduits existentes en CENTRAL-V01 (conduit_creacion_v01.json).
# Si en el documento actual los IDs difieren, ajustar aqui o cargar desde JSON.
CONDUIT_TYPE_IDS = {
    "COMUNICACIONES": 5508657,  # Tubo Comunicaciones
    "TOMAS": 112216,            # Tubo (with Fittings) - recomendado
    "ILUMINACION": 112216,      # Tubo (with Fittings)
    "FUERZA": 112216,           # Tubo (with Fittings)
}

# Distancia minima entre p1 y p2 (en pies) para evitar ArgumentException.
# 1 mm ~ 0.00328 ft; usamos un margen conservador.
MIN_LEN_FT = 0.01


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def m_a_ft(m):
    return m * 3.280839895


def mm_a_ft(mm):
    return mm / 304.8


def log(msg):
    print(msg)


def eid(val):
    """Construye ElementId usando Int64 para evitar ambiguedad en IronPython."""
    return ElementId(Int64(val))


def load_json(p):
    with open(p, "r") as f:
        return json.load(f)


def save_json(p, d):
    directorio = os.path.dirname(p)
    if directorio and not os.path.exists(directorio):
        try:
            os.makedirs(directorio)
        except OSError:
            # Ya existe (puede ocurrir en condiciones de carrera).
            pass
    with open(p, "w") as f:
        json.dump(d, f, ensure_ascii=True, indent=2)


def obtener_doc():
    """Devuelve el documento activo. Intenta __revit__ primero, luego pyrevit."""
    # 1) pyRevit clásico expone __revit__ como el host (C# UIPopupScriptExecutor)
    try:
        return __revit__.ActiveUIDocument.Document
    except Exception:
        pass
    # 2) pyRevit moderno expone 'revit' module
    try:
        from pyrevit import revit
        return revit.doc
    except Exception:
        pass
    # 3) Ultimo intento: API C# directa via COM/Activate
    try:
        import clr as _clr
        _clr.AddReference("RevitServices")
        from RevitServices.Persistence import DocumentManager
        return DocumentManager.Instance.CurrentDBDocument
    except Exception:
        return None


def buscar_nivel_piso5(doc, elevacion_objetivo=43.37, tolerancia=0.5):
    """Busca un nivel cuyo elevation coincide con el objetivo; fallback al primer nivel."""
    niveles = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    if not niveles:
        return None
    for lvl in niveles:
        if abs(lvl.Elevation - elevacion_objetivo) < tolerancia:
            return lvl
    # Fallback: primer nivel de la lista
    return niveles[0]


def buscar_tipo_conduit_por_diametro(doc, servicio, diametro_pies, type_id_por_defecto):
    """
    Intenta encontrar un ConduitType cuyo parametro RBS_CONDUIT_DIAMETER_PARAM
    coincida (dentro de tolerancia) con el diametro deseado. Si no encuentra,
    devuelve el type_id_por_defecto (sera ajustado dentro de la transaccion).
    """
    try:
        tipos = FilteredElementCollector(doc).OfClass(ConduitType).ToElements()
    except Exception:
        tipos = []

    for t in tipos:
        p = t.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
        if not p:
            continue
        try:
            diam_actual = p.AsDouble()
        except Exception:
            continue
        if diam_actual is None:
            continue
        if abs(diam_actual - diametro_pies) < 0.005:  # ~1.5 mm de tolerancia
            # Verificar nombre/servicio si es posible
            nombre = (t.Name or "").upper()
            if servicio.upper() in nombre or nombre == "":
                return t.Id
    return eid(type_id_por_defecto)


# ---------------------------------------------------------------------------
# Configuracion de rutas
# ---------------------------------------------------------------------------

JSON_CONDUITS = r"D:\Work\PROJECTS\RevitElectrico\data\conduits_dxf_v01_E06.json"
JSON_SALIDA = r"D:\Work\PROJECTS\RevitElectrico\data\conduits_creados_revit_v01.json"

# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------

doc = obtener_doc()
if not doc:
    log("[ERROR] No hay documento activo. Abre un .rvt en Revit 2026 y reejecuta.")
    raise SystemExit(1)

log("=" * 60)
log("F7_RUTEO_PYREVIT_v02 - Ruteo de conduits reales  [Version " + VERSION + "]")
log("Ejecutado: " + datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") + " UTC")
log("Documento: " + str(doc.Title))
log("=" * 60)

# Validar que el JSON de entrada existe
if not os.path.exists(JSON_CONDUITS):
    log("[ERROR] No se encuentra el JSON de conduits:")
    log("        " + JSON_CONDUITS)
    raise SystemExit(1)

try:
    conduits_data = load_json(JSON_CONDUITS)
    conduits = conduits_data.get("conduits", [])
    log("[JSON] {} conduits cargados desde {}".format(len(conduits), JSON_CONDUITS))
except Exception as e:
    log("[ERROR] No se pudo cargar JSON de conduits: {}".format(e))
    raise SystemExit(1)

if not conduits:
    log("[WARN] El JSON no contiene conduits. Nada que crear.")
    save_json(JSON_SALIDA, {"total": 0, "creados": 0, "errores": 0, "detalle": []})
    raise SystemExit(0)

# Buscar nivel Piso 5 (elevacion ~43.37 ft) o fallback al primer nivel
PISO5_LEVEL = buscar_nivel_piso5(doc, elevacion_objetivo=43.37, tolerancia=0.5)
if not PISO5_LEVEL:
    log("[ERROR] No se encontro ningun Level en el documento.")
    raise SystemExit(1)
log("[LEVEL] {} Id={} Elev={}ft".format(
    PISO5_LEVEL.Name, PISO5_LEVEL.Id, round(PISO5_LEVEL.Elevation, 4)))

# Pre-validar TypeIds: avisar si alguno no es ConduitType valido (sin abortar)
type_ids_usados = set(CONDUIT_TYPE_IDS.values())
type_ids_validos = {}
for tid in type_ids_usados:
    try:
        valido = Conduit.IsValidConduitType(doc, eid(tid))
    except Exception:
        valido = False
    type_ids_validos[tid] = valido
    if not valido:
        log("[WARN] TypeId {} NO es valido como ConduitType en este documento.".format(tid))
        log("       Los conduits que lo usen se reportaran como error.")

# ---------------------------------------------------------------------------
# Creacion dentro de UNA sola Transaction
# ---------------------------------------------------------------------------

creados = 0
errores = 0
warnings = 0
detalle = []

tx = Transaction(doc, "F7 Ruteo de conduits v02")
tx.Start()

try:
    for cond in conduits:
        cid = cond.get("id", "?")
        servicio = cond.get("servicio", "TOMAS")
        diametro_mm = cond.get("diametro_mm", 15.85)
        pt_a = cond.get("a", [0, 0, 0])
        pt_b = cond.get("b", [0, 0, 0])

        type_id_num = CONDUIT_TYPE_IDS.get(servicio, 112216)
        diametro_pies = m_a_ft(diametro_mm / 1000.0)

        p1 = XYZ(mm_a_ft(pt_a[0]), mm_a_ft(pt_a[1]), mm_a_ft(pt_a[2]))
        p2 = XYZ(mm_a_ft(pt_b[0]), mm_a_ft(pt_b[1]), mm_a_ft(pt_b[2]))

        # Validar que los puntos no sean coincidentes
        distancia = p1.DistanceTo(p2)
        if distancia < MIN_LEN_FT:
            errores += 1
            detalle.append({
                "id": cid,
                "servicio": servicio,
                "estado": "error",
                "motivo": "Puntos A y B coincidentes o demasiado cercanos (dist={}ft)".format(round(distancia, 6)),
            })
            log("  [ERR] {} puntos coincidentes (dist={}ft)".format(cid, round(distancia, 6)))
            continue

        # Validar typeId (pre-chequeo rapido)
        try:
            if not Conduit.IsValidConduitType(doc, eid(type_id_num)):
                errores += 1
                detalle.append({
                    "id": cid,
                    "servicio": servicio,
                    "estado": "error",
                    "motivo": "TypeId {} no valido para Conduit.Create".format(type_id_num),
                })
                log("  [ERR] {} TypeId {} no valido".format(cid, type_id_num))
                continue
        except Exception as ex:
            errores += 1
            detalle.append({
                "id": cid,
                "servicio": servicio,
                "estado": "error",
                "motivo": "Validacion TypeId fallo: {}".format(ex),
            })
            log("  [ERR] {} validacion typeId: {}".format(cid, ex))
            continue

        try:
            conduit = Conduit.Create(doc, eid(type_id_num), p1, p2, PISO5_LEVEL.Id)
            conduit_id = int(conduit.Id.IntegerValue) if hasattr(conduit.Id, "IntegerValue") else int(conduit.Id.Value)

            # --- Diametro: en Revit 2024+ es parametro de TIPO, no de instancia ---
            diam_asignado = False
            diam_motivo = ""

            # Intento 1: parametro de instancia (legacy / algunos templates)
            p_diam_inst = conduit.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
            if p_diam_inst and not p_diam_inst.IsReadOnly:
                try:
                    p_diam_inst.Set(diametro_pies)
                    diam_asignado = True
                    diam_motivo = "instancia"
                except Exception as ex:
                    diam_motivo = "instancia_readonly_set_fail: {}".format(ex)

            # Intento 2: parametro de tipo (Revit 2024+)
            if not diam_asignado:
                try:
                    conduit_type_el = doc.GetElement(conduit.GetTypeId())
                    if conduit_type_el is not None:
                        p_diam_type = conduit_type_el.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
                        if p_diam_type and not p_diam_type.IsReadOnly:
                            p_diam_type.Set(diametro_pies)
                            diam_asignado = True
                            diam_motivo = "tipo"
                        elif p_diam_type:
                            diam_motivo = "tipo_readonly (diametro={:.4f}ft)".format(p_diam_type.AsDouble())
                        else:
                            diam_motivo = "tipo_sin_parametro_diametro"
                except Exception as ex:
                    diam_motivo = "tipo_set_fail: {}".format(ex)

            if not diam_asignado:
                warnings += 1
                log("  [WARN] {} diametro NO asignado ({}). El conduit se crea con el diametro default del tipo.".format(cid, diam_motivo))

            # --- Servicio via Comments ---
            serv_asignado = False
            p_serv = conduit.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p_serv and not p_serv.IsReadOnly:
                try:
                    p_serv.Set(servicio)
                    serv_asignado = True
                except Exception as ex:
                    log("  [WARN] {} no se pudo asignar Comments: {}".format(cid, ex))

            creados += 1
            detalle.append({
                "id": cid,
                "servicio": servicio,
                "type_id": type_id_num,
                "conduit_element_id": conduit_id,
                "diametro_pies": round(diametro_pies, 6),
                "diametro_asignado": diam_asignado,
                "diametro_motivo": diam_motivo,
                "servicio_asignado": serv_asignado,
                "a": pt_a,
                "b": pt_b,
                "estado": "creado",
            })
            log("  [OK] {} Id={} serv={} type={} diam={}ft (asignado={} via={})".format(
                cid, conduit_id, servicio, type_id_num,
                round(diametro_pies, 4), diam_asignado, diam_motivo))

        except Exception as e:
            errores += 1
            detalle.append({
                "id": cid,
                "servicio": servicio,
                "estado": "error",
                "motivo": str(e),
            })
            log("  [ERR] {}: {}".format(cid, e))

    # Commit de la transaccion
    tx.Commit()
    log("[TX] Transaccion confirmada (Commit).")

except Exception as e:
    # Si algo se rompe a nivel de Transaction, hacer rollback
    try:
        tx.RollBack()
        log("[TX] Transaccion revertida (RollBack) por error: {}".format(e))
    except Exception:
        pass
    raise

# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

reporte = {
    "version_script": VERSION,
    "documento": str(doc.Title),
    "fecha_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    "total": len(conduits),
    "creados": creados,
    "errores": errores,
    "warnings": warnings,
    "json_entrada": JSON_CONDUITS,
    "nivel_usado": {
        "nombre": PISO5_LEVEL.Name,
        "id": int(PISO5_LEVEL.Id.IntegerValue) if hasattr(PISO5_LEVEL.Id, "IntegerValue") else int(PISO5_LEVEL.Id.Value),
        "elevacion_ft": round(PISO5_LEVEL.Elevation, 6),
    },
    "type_ids_validados": {
        str(tid): {"valido": type_ids_validos[tid]} for tid in type_ids_validos
    },
    "detalle": detalle,
}
save_json(JSON_SALIDA, reporte)

log("")
log("=" * 60)
log("F7 COMPLETADO: {} creados, {} errores, {} warnings".format(creados, errores, warnings))
log("Reporte guardado en: " + JSON_SALIDA)
log("=" * 60)
