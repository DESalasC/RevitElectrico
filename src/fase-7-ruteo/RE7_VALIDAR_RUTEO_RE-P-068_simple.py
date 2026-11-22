# -*- coding: utf-8 -*-
"""
RE7_VALIDAR_RUTEO_RE-P-068_simple.py
Validacion directa RE-P-068: compara conduits creados (desde Revit) contra V02-f.
"""
import json
import math
import os
import datetime

raiz = r"D:\Work\PROJECTS\RevitElectrico"
ref_path = os.path.join(raiz, ".claude", "worktrees", "conduit-parser", "data", "v02f", "conduits_v01.json")
creado_path = os.path.join(raiz, "data", "f7_conduits_desde_revit_v01.json")
out_path = os.path.join(raiz, "data", "f7_validacion_re-p-068_v01.json")

print("=" * 60)
print("RE7_VALIDAR_RUTEO_RE-P-068_simple - Validacion contra V02-f")
print("ejecutado_utc={}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
print("=" * 60)

# Cargar referencia V02-f
with open(ref_path, "r") as f:
    datos_ref = json.load(f)
tramos_ref = datos_ref if isinstance(datos_ref, list) else datos_ref.get("tramos", [])
print("Tramos de referencia V02-f: {}".format(len(tramos_ref)))

# Normalizar referencia
def punto_a_mm(p):
    return [float(p[0]), float(p[1]), float(p[2])]

def distancia_puntos(p, q):
    return math.sqrt((p[0]-q[0])**2 + (p[1]-q[1])**2 + (p[2]-q[2])**2)

def normalizar_tramo(a_mm, b_mm):
    return tuple(sorted([tuple(a_mm), tuple(b_mm)]))

ref_list = []
for t in tramos_ref:
    a = punto_a_mm(t["a"])
    b = punto_a_mm(t["b"])
    ref_list.append({
        "id": t.get("id"),
        "tipo": t.get("tipo", ""),
        "servicio": t.get("servicio", ""),
        "diam_mm": float(t.get("diam_mm", 0)),
        "longitud_mm": distancia_puntos(a, b),
        "clave": normalizar_tramo(a, b),
        "a": a,
        "b": b,
    })

ref_por_clave = {r["clave"]: r for r in ref_list}
ref_por_id = {r["id"]: r for r in ref_list}

# Cargar conduits creados
with open(creado_path, "r") as f:
    datos_creados = json.load(f)
conduits_creados = datos_creados.get("conduits", [])
print("Conduits creados cargados: {}".format(len(conduits_creados)))

# Validar
resultados = []
coincididas_ids = set()
coincidencias_exactas = 0
coincidencias_proximas = 0
sin_coincidencia = 0
TOLERANCIA = 200.0

for c in conduits_creados:
    creado_id = c.get("conduit_id")
    a_real = c.get("a_mm")
    b_real = c.get("b_mm")
    if a_real is not None:
        a_real = [float(v) for v in a_real]
    if b_real is not None:
        b_real = [float(v) for v in b_real]

    ref = None
    dist_endpoints = None

    # Buscar por coordenadas (clave normalizada)
    if a_real is not None and b_real is not None:
        clave_creado = normalizar_tramo(a_real, b_real)
        if clave_creado in ref_por_clave:
            ref = ref_por_clave[clave_creado]
            coincididas_ids.add(ref["id"])
            d1 = distancia_puntos(a_real, ref["a"]) + distancia_puntos(b_real, ref["b"])
            d2 = distancia_puntos(a_real, ref["b"]) + distancia_puntos(b_real, ref["a"])
            dist_endpoints = min(d1, d2)

    if ref is not None:
        es_exacto = (dist_endpoints == 0.0) if dist_endpoints is not None else False
        if es_exacto:
            coincidencias_exactas += 1
        elif dist_endpoints is not None and dist_endpoints <= TOLERANCIA:
            coincidencias_proximas += 1
        else:
            sin_coincidencia += 1
    else:
        sin_coincidencia += 1

    resultados.append({
        "conduit_id_creado": creado_id,
        "ref_id": ref["id"] if ref else None,
        "ref_servicio": ref["servicio"] if ref else None,
        "ref_diam_mm": ref["diam_mm"] if ref else None,
        "dist_endpoints_mm": round(dist_endpoints, 2) if dist_endpoints is not None else None,
        "clave_match_exacto": ref is not None and dist_endpoints == 0.0,
    })

# Resumen
total_creados = len(conduits_creados)
total_ref = len(ref_list)
total_coincididas = len(coincididas_ids)
no_coincidadas_ref = [r for r in ref_list if r["id"] not in coincididas_ids]

reporte = {
    "version": "v01",
    "script": "RE7_VALIDAR_RUTEO_RE-P-068_simple",
    "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    "parametros": {"tolerancia_coincidencia_mm": TOLERANCIA},
    "fuentes": {"conduits_creados": creado_path, "referencia_v02f": ref_path},
    "resumen": {
        "conduits_creados_total": total_creados,
        "tramos_referencia_total": total_ref,
        "coincidencias_exactas": coincidencias_exactas,
        "coincidencias_proximas": coincidencias_proximas,
        "sin_coincidencia_creados": sin_coincidencia,
        "tramos_ref_coincididos_total": total_coincididas,
        "tramos_ref_sin_coincidir": len(no_coincidadas_ref),
        "cobertura_ref_porcentaje": round(100.0 * total_coincididas / total_ref, 2) if total_ref else 0.0,
    },
    "resultados": resultados,
    "tramos_ref_sin_coincidir": [
        {"id": r["id"], "tipo": r["tipo"], "servicio": r["servicio"],
         "diam_mm": r["diam_mm"], "longitud_mm": r["longitud_mm"],
         "a_mm": r["a"], "b_mm": r["b"]}
        for r in no_coincidadas_ref
    ],
}

with open(out_path, "w") as f:
    json.dump(reporte, f, ensure_ascii=True, indent=2)

print("Reporte guardado en: {}".format(out_path))
print("")
print("RESUMEN:")
print("  Conduits creados: {}".format(total_creados))
print("  Tramos referencia V02-f: {}".format(total_ref))
print("  Coincidencias exactas: {}".format(coincidencias_exactas))
print("  Coincidencias cercanas (<{}mm): {}".format(TOLERANCIA, coincidencias_proximas))
print("  Creados sin coincidencia: {}".format(sin_coincidencia))
print("  Tramos ref no coincididos: {}".format(len(no_coincidadas_ref)))
print("  Cobertura referencia: {}%".format(reporte["resumen"]["cobertura_ref_porcentaje"]))
print("=" * 60)
