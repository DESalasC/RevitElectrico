# -*- coding: utf-8 -*-
"""
RE7_ANALIZAR_COBERTURA_v01.py
Analizador de cobertura por servicio para el ruteo F7.

Compara conduits creados en Revit contra los 147 tramos de referencia de V02-f,
desglosando cobertura por servicio, diametro y estado de verificacion.

Lee:
  - data/f7_conduits_creados_v01.json          (salida de RE7_CREAR_CONDUITS_v01.py)
  - data/f7_conduits_ref_v02f_v01.json         (salida de RE7_CREAR_CONDUITS_REFERENCIA_V02F_v01.py)
  - data/f7_conduits_desde_revit_v01.json      (salida de RE7_EXPORTAR_CONDUITS_REVIT_v01.py)
  - datos de referencia V02-f: .claude/worktrees/conduit-parser/data/v02f/conduits_v01.json

Escribe:
  - data/f7_cobertura_por_servicio_v01.json

Uso (Python 3.12 externo, no Revit):
    python RE7_ANALIZAR_COBERTURA_v01.py
"""
import datetime
import json
import math
import os
import sys

try:
    from pathlib import Path
except Exception:
    pass

FT_A_MM = 304.8


def raiz_proyecto():
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz and os.path.exists(raiz):
        return raiz
    return r"D:\Work\PROJECTS\RevitElectrico"


def cargar_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_json(path, datos):
    contenido = json.dumps(datos, ensure_ascii=True, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(contenido)


def distancia_puntos(p, q):
    return math.sqrt((p[0]-q[0])**2 + (p[1]-q[1])**2 + (p[2]-q[2])**2)


def normalizar_tramo(a_mm, b_mm):
    return tuple(sorted([tuple(a_mm), tuple(b_mm)]))


def tramo_longitud(a_mm, b_mm):
    return distancia_puntos(a_mm, b_mm)


def obtener_coords_creado(c):
    a = c.get("a_mm_real") or c.get("a_mm")
    b = c.get("b_mm_real") or c.get("b_mm")
    if a is not None:
        a = [float(v) for v in a]
    if b is not None:
        b = [float(v) for v in b]
    return a, b


def obtener_id_creado(c):
    return c.get("id_ref") or c.get("conduit_id") or c.get("id_script")


def obtener_verificado(c):
    v = c.get("verificado")
    if v is None:
        v = c.get("verificado_creacion")
    return bool(v) if v is not None else True


def obtener_diametro(c):
    d = c.get("diametro_mm")
    if d is None:
        d = c.get("diametro_creado_mm")
    return float(d) if d is not None else 0.0


def obtener_servicio(c):
    s = c.get("servicio")
    if s is None:
        s = c.get("servicio_creado")
    return s or "(vacio)"


def main():
    raiz = raiz_proyecto()
    print("=" * 60)
    print("RE7_ANALIZAR_COBERTURA_v01 - Analisis de cobertura por servicio F7")
    print("ejecutado_utc={}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 60)

    # Cargar referencia V02-f
    ref_path = os.path.join(raiz, ".claude", "worktrees", "conduit-parser", "data", "v02f", "conduits_v01.json")
    datos_ref = cargar_json(ref_path)
    if datos_ref is None:
        print("ERROR: no existe {}".format(ref_path))
        return 1

    tramos_ref = datos_ref if isinstance(datos_ref, list) else datos_ref.get("tramos", [])
    print("Tramos de referencia V02-f: {}".format(len(tramos_ref)))

    # Normalizar referencia para busqueda rapida
    ref_list = []
    for t in tramos_ref:
        a = [float(t["a"][0]), float(t["a"][1]), float(t["a"][2])]
        b = [float(t["b"][0]), float(t["b"][1]), float(t["b"][2])]
        ref_list.append({
            "id": t.get("id"),
            "tipo": t.get("tipo", ""),
            "servicio": t.get("servicio", "") or "(vacio)",
            "diam_mm": float(t.get("diam_mm", 0)),
            "longitud_mm": tramo_longitud(a, b),
            "clave": normalizar_tramo(a, b),
            "a": a,
            "b": b,
        })

    # Intentar cargar conduits creados (de cualquiera de los tres scripts)
    creado_paths = [
        os.path.join(raiz, "data", "f7_conduits_creados_v01.json"),
        os.path.join(raiz, "data", "f7_conduits_ref_v02f_v01.json"),
        os.path.join(raiz, "data", "f7_conduits_desde_revit_v01.json"),
    ]
    conduits_creados = []
    creado_path_usado = None
    for cp in creado_paths:
        datos_creados = cargar_json(cp)
        if datos_creados is not None:
            conduits_creados = datos_creados.get("conduits", [])
            creado_path_usado = cp
            print("Conduits creados cargados desde: {} ({} items)".format(cp, len(conduits_creados)))
            break

    if not conduits_creados:
        print("ERROR: no se encontro reporte de conduits creados.")
        print("     Ejecute primero un script de creacion o exportacion en Revit.")
        return 1

    # Indexar referencia por clave y por id
    ref_por_clave = {r["clave"]: r for r in ref_list}
    ref_por_id = {r["id"]: r for r in ref_list}

    # Analizar cada conduit creado
    resultados = []
    ids_ref_coincidentes = set()
    stats_por_servicio = {}
    stats_por_diametro = {}
    totales_ref = {"conteo": 0, "longitud_mm": 0.0}
    totales_creados = {"conteo": 0, "longitud_mm": 0.0, "verificados_ok": 0}

    for r in ref_list:
        svc = r["servicio"]
        stats_por_servicio.setdefault(svc, {"ref_conteo": 0, "ref_longitud_mm": 0.0, "creado_conteo": 0, "creado_longitud_mm": 0.0, "verificados_ok": 0})
        stats_por_servicio[svc]["ref_conteo"] += 1
        stats_por_servicio[svc]["ref_longitud_mm"] += r["longitud_mm"]
        totales_ref["conteo"] += 1
        totales_ref["longitud_mm"] += r["longitud_mm"]

        diam_key = str(int(r["diam_mm"])) if r["diam_mm"] else "?"
        stats_por_diametro.setdefault(diam_key, {"ref_conteo": 0, "ref_longitud_mm": 0.0, "creado_conteo": 0, "creado_longitud_mm": 0.0, "verificados_ok": 0})
        stats_por_diametro[diam_key]["ref_conteo"] += 1
        stats_por_diametro[diam_key]["ref_longitud_mm"] += r["longitud_mm"]

    for c in conduits_creados:
        creado_id = obtener_id_creado(c)
        a_real, b_real = obtener_coords_creado(c)
        largo_real = c.get("largo_real_mm") or c.get("largo_mm")
        verificado = obtener_verificado(c)
        diametro = obtener_diametro(c)
        diam_key = str(int(diametro)) if diametro else "?"
        servicio = obtener_servicio(c)

        # Buscar coincidencia con referencia
        ref_match = None
        dist_endpoints = None
        id_ref_directo = c.get("id_ref")
        if id_ref_directo is not None and id_ref_directo in ref_por_id:
            ref_match = ref_por_id[id_ref_directo]
            ids_ref_coincidentes.add(id_ref_directo)
        elif a_real is not None and b_real is not None:
            clave_creado = normalizar_tramo(a_real, b_real)
            if clave_creado in ref_por_clave:
                ref_match = ref_por_clave[clave_creado]
                ids_ref_coincidentes.add(ref_match["id"])

        if ref_match is not None and a_real is not None and b_real is not None:
            d1 = distancia_puntos(a_real, ref_match["a"]) + distancia_puntos(b_real, ref_match["b"])
            d2 = distancia_puntos(a_real, ref_match["b"]) + distancia_puntos(b_real, ref_match["a"])
            dist_endpoints = min(d1, d2)

        entrada = {
            "conduit_id_creado": creado_id,
            "id_ref": id_ref_directo,
            "ref_id_match": ref_match["id"] if ref_match else None,
            "ref_servicio": ref_match["servicio"] if ref_match else None,
            "ref_diam_mm": ref_match["diam_mm"] if ref_match else None,
            "ref_longitud_mm": ref_match["longitud_mm"] if ref_match else None,
            "dist_endpoints_mm": round(dist_endpoints, 2) if dist_endpoints is not None else None,
            "verificado_creacion": verificado,
            "largo_creado_mm": largo_real,
            "servicio_creado": servicio,
            "diametro_creado_mm": diametro,
        }
        resultados.append(entrada)

        totales_creados["conteo"] += 1
        totales_creados["longitud_mm"] += largo_real if largo_real else 0
        if verificado:
            totales_creados["verificados_ok"] += 1

        if ref_match is not None:
            svc_match = ref_match["servicio"]
            stats_por_servicio[svc_match]["creado_conteo"] += 1
            stats_por_servicio[svc_match]["creado_longitud_mm"] += largo_real if largo_real else 0
            if verificado:
                stats_por_servicio[svc_match]["verificados_ok"] += 1

            dk = str(int(ref_match["diam_mm"])) if ref_match["diam_mm"] else "?"
            stats_por_diametro[dk]["creado_conteo"] += 1
            stats_por_diametro[dk]["creado_longitud_mm"] += largo_real if largo_real else 0
            if verificado:
                stats_por_diametro[dk]["verificados_ok"] += 1

    # Tramos de referencia sin coincidir
    ref_sin_coincidir = [r for r in ref_list if r["id"] not in ids_ref_coincidentes]

    # Construir reporte
    reporte = {
        "version": "v01",
        "script": "RE7_ANALIZAR_COBERTURA_v01",
        "generado_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "fuentes": {
            "conduits_creados": creado_path_usado,
            "referencia_v02f": ref_path,
        },
        "resumen_global": {
            "tramos_referencia_total": totales_ref["conteo"],
            "tramos_referencia_longitud_mm": round(totales_ref["longitud_mm"], 3),
            "conduits_creados_total": totales_creados["conteo"],
            "conduits_creados_longitud_mm": round(totales_creados["longitud_mm"], 3),
            "conduits_verificados_ok": totales_creados["verificados_ok"],
            "tramos_ref_coincididos": len(ids_ref_coincidentes),
            "tramos_ref_sin_coincidir": len(ref_sin_coincidir),
            "cobertura_conteo_porcentaje": round(100.0 * len(ids_ref_coincidentes) / totales_ref["conteo"], 2) if totales_ref["conteo"] else 0.0,
            "cobertura_longitud_porcentaje": round(100.0 * totales_creados["longitud_mm"] / totales_ref["longitud_mm"], 2) if totales_ref["longitud_mm"] else 0.0,
        },
        "por_servicio": {},
        "por_diametro": {},
        "resultados": resultados,
        "tramos_ref_sin_coincidir": [
            {"id": r["id"], "tipo": r["tipo"], "servicio": r["servicio"],
             "diam_mm": r["diam_mm"], "longitud_mm": r["longitud_mm"],
             "a_mm": r["a"], "b_mm": r["b"]}
            for r in ref_sin_coincidir
        ],
    }

    for svc, st in sorted(stats_por_servicio.items()):
        ref_c = st["ref_conteo"]
        creado_c = st["creado_conteo"]
        ver_ok = st["verificados_ok"]
        reporte["por_servicio"][svc] = {
            "ref_conteo": ref_c,
            "ref_longitud_mm": round(st["ref_longitud_mm"], 3),
            "creado_conteo": creado_c,
            "creado_longitud_mm": round(st["creado_longitud_mm"], 3),
            "verificados_ok": ver_ok,
            "cobertura_conteo_porcentaje": round(100.0 * creado_c / ref_c, 2) if ref_c else 0.0,
            "cobertura_longitud_porcentaje": round(100.0 * st["creado_longitud_mm"] / st["ref_longitud_mm"], 2) if st["ref_longitud_mm"] else 0.0,
            "tasa_verificacion_porcentaje": round(100.0 * ver_ok / creado_c, 2) if creado_c else 0.0,
        }

    for diam, st in sorted(stats_por_diametro.items()):
        ref_c = st["ref_conteo"]
        creado_c = st["creado_conteo"]
        ver_ok = st["verificados_ok"]
        reporte["por_diametro"][diam] = {
            "ref_conteo": ref_c,
            "ref_longitud_mm": round(st["ref_longitud_mm"], 3),
            "creado_conteo": creado_c,
            "creado_longitud_mm": round(st["creado_longitud_mm"], 3),
            "verificados_ok": ver_ok,
            "cobertura_conteo_porcentaje": round(100.0 * creado_c / ref_c, 2) if ref_c else 0.0,
            "cobertura_longitud_porcentaje": round(100.0 * st["creado_longitud_mm"] / st["ref_longitud_mm"], 2) if st["ref_longitud_mm"] else 0.0,
            "tasa_verificacion_porcentaje": round(100.0 * ver_ok / creado_c, 2) if creado_c else 0.0,
        }

    out_path = os.path.join(raiz, "data", "f7_cobertura_por_servicio_v01.json")
    guardar_json(out_path, reporte)
    print("Reporte guardado en: {}".format(out_path))
    print("")
    print("RESUMEN GLOBAL:")
    print("  Tramos referencia V02-f: {}".format(reporte["resumen_global"]["tramos_referencia_total"]))
    print("  Conduits creados: {}".format(reporte["resumen_global"]["conduits_creados_total"]))
    print("  Verificados OK: {}".format(reporte["resumen_global"]["conduits_verificados_ok"]))
    print("  Tramos ref coincididos: {}".format(reporte["resumen_global"]["tramos_ref_coincididos"]))
    print("  Tramos ref sin coincidir: {}".format(reporte["resumen_global"]["tramos_ref_sin_coincidir"]))
    print("  Cobertura conteo: {}%".format(reporte["resumen_global"]["cobertura_conteo_porcentaje"]))
    print("  Cobertura longitud: {}%".format(reporte["resumen_global"]["cobertura_longitud_porcentaje"]))
    print("")
    print("POR SERVICIO:")
    for svc, st in sorted(reporte["por_servicio"].items()):
        print("  {:<18} ref={:>3} creado={:>3} OK={:>3} cobertura={:>6}% long={:>6}%".format(
            svc, st["ref_conteo"], st["creado_conteo"], st["verificados_ok"],
            st["cobertura_conteo_porcentaje"], st["cobertura_longitud_porcentaje"]))
    print("")
    print("POR DIAMETRO (mm):")
    for diam, st in sorted(reporte["por_diametro"].items()):
        print("  {:>4}   ref={:>3} creado={:>3} OK={:>3} cobertura={:>6}%".format(
            diam, st["ref_conteo"], st["creado_conteo"], st["verificados_ok"], st["cobertura_conteo_porcentaje"]))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
