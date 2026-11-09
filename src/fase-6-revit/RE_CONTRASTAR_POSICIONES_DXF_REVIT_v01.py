# -*- coding: utf-8 -*-
# RE_CONTRASTAR_POSICIONES_DXF_REVIT_v01.py
# Compara posiciones de FamilyInstances/Conduits exportadas de Revit contra el DXF,
# agrupados por tablero (Panel Name en Revit / TABLERO en DXF), y calcula
# desplazamientos (ΔX, ΔY, ΔZ) por homologo.
#
# Integra MAPA_BLOQUES_REVIT_v3.json para traducir código DXF -> familia/símbolo Revit
# antes de buscar en el índice de Revit.
#
# Ejecutar fuera de Revit (Python 3 estándar).
#
# Uso:
#   python RE_CONTRASTAR_POSICIONES_DXF_REVIT_v01.py \
#       --revit data/posiciones_revit_export.json \
#       --dxf 3.-Proceso\_prueba_modelado\modelo_apt_F02_piso5.json \
#       --mapa 3.-Proceso\_prueba_modelado\MAPA_BLOQUES_REVIT_v3.json \
#       --salida data/contraste_posiciones_dxf_revit.json

import json
import math
import os
import argparse
from collections import defaultdict

# ---------------------------------------------------------------------------
# Carga y guardado de JSON
# ---------------------------------------------------------------------------
def cargar_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_json(path, datos):
    directorio = os.path.dirname(path)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=True, indent=2)

# ---------------------------------------------------------------------------
# Normalizar nombre para emparejamiento (case-insensitive, sin espacios extra)
# ---------------------------------------------------------------------------
def normalizar_nombre(nombre):
    if not nombre:
        return ""
    return str(nombre).strip().lower()

# ---------------------------------------------------------------------------
# Cargar MAPA v3 y construir diccionario codigo_dxf -> {familia, simbolo}
# ---------------------------------------------------------------------------
def cargar_mapa(mapa_path):
    """Retorna diccionario: codigo_dxf_normalizado -> {familia, simbolo, mapear, altura_m}

Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""
    mapa_data = cargar_json(mapa_path)
    mapeo = mapa_data.get("mapeo", {})
    diccionario = {}
    for codigo_dxf, entrada in mapeo.items():
        clave = normalizar_nombre(codigo_dxf)
        diccionario[clave] = {
            "familia": entrada.get("familia", ""),
            "simbolo": entrada.get("simbolo", ""),
            "mapear": entrada.get("mapear", False),
            "altura_m": entrada.get("altura_m", 0.0),
            "anfitrion": entrada.get("anfitrion", ""),
            "capa": entrada.get("capa", ""),
        }
    return diccionario

# ---------------------------------------------------------------------------
# Obtener familia y símbolo Revit para un código DXF (usando MAPA)
# ---------------------------------------------------------------------------
def obtener_familia_simbolo_revit(codigo_dxf, mapa_diccionario):
    clave = normalizar_nombre(codigo_dxf)
    entrada = mapa_diccionario.get(clave)
    if entrada:
        return entrada["familia"], entrada["simbolo"], entrada["mapear"]
    # Fallback: usar el código DXF directamente como familia
    return codigo_dxf, "", False

# ---------------------------------------------------------------------------
# Emparejar elementos de Revit con elementos del DXF por (familia, símbolo, panel/tablero)
# ---------------------------------------------------------------------------
def contrastar_posiciones(revit_data, dxf_data, mapa_diccionario=None):
    revit_instances = revit_data.get("family_instances", [])
    revit_conduits = revit_data.get("conduits", [])
    dxf_elementos = dxf_data.get("elementos", [])

    # Índice de FamilyInstances de Revit por (familia, símbolo, panel_name)
    indice_revit = {}
    for inst in revit_instances:
        clave = (normalizar_nombre(inst["familia"]), normalizar_nombre(inst["simbolo"]),
                 normalizar_nombre(inst["panel_name"]))
        indice_revit.setdefault(clave, []).append(inst)

    # Índice de Conduits de Revit por (sistema, panel_name)
    indice_revit_conduit = {}
    for cond in revit_conduits:
        clave = (normalizar_nombre(cond["sistema"]), normalizar_nombre(cond["panel_name"]))
        indice_revit_conduit.setdefault(clave, []).append(cond)

    # Índice de tableros de Revit (familia E_Distribution Panel)
    tableros_revit = []
    for inst in revit_instances:
        if inst.get("es_tablero"):
            tableros_revit.append(inst)

    resultados = []
    estadisticas = {
        "total_dxf_dispositivos": 0,
        "total_dxf_marcadores": 0,
        "total_dxf_tubos": 0,
        "total_tableros_revit": len(tableros_revit),
        "emparejados": 0,
        "sin_emparejar_revit": 0,
        "sin_emparejar_dxf": 0,
        "desplazamientos_calculados": 0,
    }

    # Procesar elementos del DXF
    for elem in dxf_elementos:
        tipo = elem.get("tipo", "")
        nombre = elem.get("nombre", "")
        tablero = elem.get("tablero", elem.get("panel_name", ""))
        es_marcador = elem.get("es_marcador", False)

        if tipo == "dispositivo":
            estadisticas["total_dxf_dispositivos"] += 1
            if es_marcador or nombre in ("1FTN", "1TNR", "1FTNR", "2FT2N", "1FTR", "1FTN2R", "1TN2R"):
                estadisticas["total_dxf_marcadores"] += 1
                resultados.append({
                    "nombre": nombre,
                    "tipo": "marcador_conductor",
                    "tablero": tablero,
                    "estado": "saltado",
                    "motivo": "Marcador de conductor, no dispositivo físico"
                })
                continue

            # Usar MAPA para obtener familia/símbolo Revit
            if mapa_diccionario:
                familia_revit, simbolo_revit, debe_mapear = obtener_familia_simbolo_revit(nombre, mapa_diccionario)
                if not debe_mapear:
                    estadisticas["sin_emparejar_revit"] += 1
                    resultados.append({
                        "nombre": nombre,
                        "tipo": "dispositivo",
                        "tablero": tablero,
                        "estado": "sin_mapeo",
                        "motivo": "mapear=false en MAPA v3"
                    })
                    continue
            else:
                familia_revit = nombre
                simbolo_revit = ""

            # Buscar homologo en Revit por (familia, símbolo, tablero)
            clave_revit = (normalizar_nombre(familia_revit), normalizar_nombre(simbolo_revit),
                           normalizar_nombre(tablero))
            candidatas = indice_revit.get(clave_revit, [])

            if not candidatas:
                # Fallback: buscar solo por familia y tablero (sin símbolo)
                clave_fallback = (normalizar_nombre(familia_revit), "", normalizar_nombre(tablero))
                candidatas = indice_revit.get(clave_fallback, [])

            if not candidatas:
                estadisticas["sin_emparejar_revit"] += 1
                resultados.append({
                    "nombre": nombre,
                    "tipo": "dispositivo",
                    "tablero": tablero,
                    "familia_buscar": familia_revit,
                    "simbolo_buscar": simbolo_revit,
                    "estado": "sin_instancia_revit",
                    "motivo": "No hay FamilyInstance en Revit con este nombre/tablero"
                })
                continue

            revit_inst = candidatas[0]
            x_dxf = elem.get("x", 0.0)
            y_dxf = elem.get("y", 0.0)
            z_dxf = elem.get("z", 0.0)

            dx = revit_inst["x"] - x_dxf if revit_inst["x"] is not None and x_dxf is not None else None
            dy = revit_inst["y"] - y_dxf if revit_inst["y"] is not None and y_dxf is not None else None
            dz = revit_inst["z"] - z_dxf if revit_inst["z"] is not None and z_dxf is not None else None

            estadisticas["emparejados"] += 1
            if dx is not None and dy is not None:
                estadisticas["desplazamientos_calculados"] += 1

            resultados.append({
                "nombre": nombre,
                "tipo": "dispositivo",
                "tablero": tablero,
                "familia_revit": revit_inst["familia"],
                "simbolo_revit": revit_inst["simbolo"],
                "instance_id": revit_inst["id"],
                "x_dxf": x_dxf,
                "y_dxf": y_dxf,
                "z_dxf": z_dxf,
                "x_revit": revit_inst["x"],
                "y_revit": revit_inst["y"],
                "z_revit": revit_inst["z"],
                "desplazamiento": {"dx": dx, "dy": dy, "dz": dz},
                "estado": "emparejado",
            })

        elif tipo == "tubo_horizontal":
            estadisticas["total_dxf_tubos"] += 1
            sistema = elem.get("sistema", "ILUMINACIÓN")
            clave_conduit = (normalizar_nombre(sistema), normalizar_nombre(tablero))
            candidatas = indice_revit_conduit.get(clave_conduit, [])

            if not candidatas:
                estadisticas["sin_emparejar_revit"] += 1
                resultados.append({
                    "nombre": nombre,
                    "tipo": "tubo_horizontal",
                    "sistema": sistema,
                    "tablero": tablero,
                    "estado": "sin_conduit_revit",
                    "motivo": "No hay Conduit en Revit con este sistema/tablero"
                })
                continue

            cond = candidatas[0]
            x_dxf = elem.get("x", 0.0)
            y_dxf = elem.get("y", 0.0)
            z_dxf = elem.get("z", 0.0)

            dx = cond["x"] - x_dxf if cond["x"] is not None and x_dxf is not None else None
            dy = cond["y"] - y_dxf if cond["y"] is not None and y_dxf is not None else None
            dz = cond["z"] - z_dxf if cond["z"] is not None and z_dxf is not None else None

            estadisticas["emparejados"] += 1
            if dx is not None and dy is not None:
                estadisticas["desplazamientos_calculados"] += 1

            resultados.append({
                "nombre": nombre,
                "tipo": "tubo_horizontal",
                "sistema": sistema,
                "tablero": tablero,
                "conduit_id": cond["id"],
                "x_dxf": x_dxf,
                "y_dxf": y_dxf,
                "z_dxf": z_dxf,
                "x_revit": cond["x"],
                "y_revit": cond["y"],
                "z_revit": cond["z"],
                "desplazamiento": {"dx": dx, "dy": dy, "dz": dz},
                "estado": "emparejado",
            })

    # Agrupar desplazamientos por tablero (clave: cada "Apartamento Tipo nn")
    desplazamientos_por_tablero = defaultdict(list)
    for r in resultados:
        if r["estado"] == "emparejado" and r.get("desplazamiento", {}).get("dx") is not None:
            desplazamientos_por_tablero[r["tablero"]].append({
                "nombre": r["nombre"],
                "tipo": r["tipo"],
                "dx": r["desplazamiento"]["dx"],
                "dy": r["desplazamiento"]["dy"],
                "dz": r["desplazamiento"]["dz"],
            })

    # Calcular promedio y rango por tablero
    resumen_por_tablero = {}
    for tablero, lista in desplazamientos_por_tablero.items():
        if not lista:
            continue
        dxs = [d["dx"] for d in lista if d["dx"] is not None]
        dys = [d["dy"] for d in lista if d["dy"] is not None]
        dzs = [d["dz"] for d in lista if d["dz"] is not None]
        resumen_por_tablero[tablero] = {
            "n_elementos": len(lista),
            "dx_promedio": sum(dxs) / len(dxs) if dxs else None,
            "dy_promedio": sum(dys) / len(dys) if dys else None,
            "dz_promedio": sum(dzs) / len(dzs) if dzs else None,
            "dx_min": min(dxs) if dxs else None,
            "dx_max": max(dxs) if dxs else None,
            "dy_min": min(dys) if dys else None,
            "dy_max": max(dys) if dys else None,
            "desplazamientos_detalle": lista,
        }

    salida = {
        "documento_revit": revit_data.get("documento", ""),
        "ruta_documento_revit": revit_data.get("ruta_documento", ""),
        "documento_dxf": dxf_data if isinstance(dxf_data, str) else "",
        "fecha_contraste": "2026-10-28",
        "mapa_utilizado": mapa_diccionario is not None,
        "estadisticas": estadisticas,
        "resumen_por_tablero": resumen_por_tablero,
        "detalle": resultados,
    }

    return salida


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Contrastar posiciones DXF vs Revit por tablero")
    parser.add_argument("--revit", required=True, help="Ruta a posiciones_revit_export.json")
    parser.add_argument("--dxf", required=True, help="Ruta a modelo_apt_F02_piso5.json (DXF)")
    parser.add_argument("--mapa", required=False, default=None, help="Ruta a MAPA_BLOQUES_REVIT_v3.json (opcional)")
    parser.add_argument("--salida", required=True, help="Ruta de salida para contraste_posiciones_dxf_revit.json")
    args = parser.parse_args()

    print("=== RE_CONTRASTAR_POSICIONES_DXF_REVIT_v01 ===")

    try:
        revit_data = cargar_json(args.revit)
        print("JSON de Revit cargado: {} FamilyInstances, {} Conduits".format(
            len(revit_data.get("family_instances", [])),
            len(revit_data.get("conduits", []))))
    except Exception as exc:
        print("ERROR cargando JSON de Revit: {}".format(exc))
        return

    try:
        dxf_data = cargar_json(args.dxf)
        print("JSON de DXF cargado: {} elementos".format(len(dxf_data.get("elementos", []))))
    except Exception as exc:
        print("ERROR cargando JSON de DXF: {}".format(exc))
        return

    mapa_diccionario = None
    if args.mapa:
        try:
            mapa_diccionario = cargar_mapa(args.mapa)
            print("MAPA v3 cargado: {} entradas".format(len(mapa_diccionario)))
        except Exception as exc:
            print("ADVERTENCIA: no se pudo cargar MAPA: {}".format(exc))
            mapa_diccionario = None

    resultado = contrastar_posiciones(revit_data, dxf_data, mapa_diccionario)

    try:
        guardar_json(args.salida, resultado)
        print("\nContraste guardado en: {}".format(args.salida))
    except Exception as exc:
        print("ERROR guardando contraste: {}".format(exc))

    print("\n=== ESTADÍSTICAS ===")
    for k, v in resultado["estadisticas"].items():
        print("  {}: {}".format(k, v))

    print("\n=== RESUMEN POR TABLERO ===")
    for tablero, res in resultado["resumen_por_tablero"].items():
        print("  Tablero '{}': {} elementos, ΔX={}, ΔY={}, ΔZ={}".format(
            tablero, res["n_elementos"],
            round(res["dx_promedio"], 3) if res["dx_promedio"] is not None else "N/A",
            round(res["dy_promedio"], 3) if res["dy_promedio"] is not None else "N/A",
            round(res["dz_promedio"], 3) if res["dz_promedio"] is not None else "N/A"))

    return resultado


if __name__ == "__main__":
    main()
