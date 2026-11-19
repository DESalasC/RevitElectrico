# -*- coding: utf-8 -*-
"""
CONDUITES_DESDE_DXF_v01.py

Extrae conductos del DXF de bloques electricos (STM-T5-P5_bloques_electricos.dxf)
para apartamentos especificados. Encuentra inserts de bloques de apartamento en
modelspace, lee dispositivos y polilineas de conducto dentro de cada bloque
(coordenadas relativas, base=(0,0)), las transforma a coordenadas globales y
genera JSON listo para crear conductos en Revit via Conduit.Create.

Unidades: coordenadas en mm, diametros en mm, longitudes en mm, alturas en m.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from collections import Counter
from typing import Any

import ezdxf

# Ruta al directorio ruteo para reutilizar modulos existentes
_RUTEO_DIR = os.path.dirname(os.path.abspath(__file__))
if _RUTEO_DIR not in sys.path:
    sys.path.insert(0, _RUTEO_DIR)

from config import cargar_config, PULGADAS_A_MM  # noqa: E402
from dxf_lector import cables_desde_nombre  # noqa: E402


# --- mapeo capa de tuberia -> servicio (duplicado de config para trazabilidad) ---
CAPA_A_SERVICIO: dict[str, str] = {
    "ELEC-LIGHT-PIPE": "ILUMINACION",
    "ELEC-POWER- PIPE": "TOMAS",
    "ELEC-Powr-service": "FUERZA",
    "ELEC-Data-Service": "COMUNICACIONES",
}

# Cota de banda por servicio (m, relativa al nivel). Duplicado de config.
COTA_BANDA: dict[str, float] = {
    "ILUMINACION": 2.65,
    "TOMAS": 2.68,
    "COMUNICACIONES": 2.71,
    "FUERZA": 2.74,
}

# Diametro fijo por servicio (pulgadas, mm). COMUNICACIONES va fijo a 3/4".
DIAMETRO_FIJO: dict[str, tuple[str, float]] = {
    "COMUNICACIONES": ("3/4\"", 19.05),
}

# Tolerancias (m)
TOL_EXTREMO_DISPOSITIVO = 0.50      # m: distancia maxima para asociar extremo a dispositivo
TOL_MARCADOR_POLILINEA = 0.30       # m: distancia maxima para asociar marcador a polilinea
LARGO_MINIMO_TRAMO = 0.0001         # m: 0.1 mm; descarta solo polilineas degeneradas (el DXF dibuja tramos cortos dentro del bloque)

# Diametro por defecto (pulgadas, mm) cuando no hay marcador ni regla fija
DIAMETRO_DEFAULT = ("1/2\"", 12.70)
CABLES_DEFAULT = 3

# Revit EMT conduit diametros REALES (de conduit_creacion_v01.json, verificado contra API Revit).
# El diametro que se fija en RBS_CONDUIT_DIAMETER_PARAM debe coincidir con esta tabla;
# los valores nominales (12.70, 19.05) NO son validos para la API de Revit.
EMT_DIAMETROS_MM: dict[str, float] = {
    '1/2"': 15.85,
    '3/4"': 21.03,
    '1"': 27.13,
    '1-1/4"': 35.05,
    '1-1/2"': 41.15,
    '2"': 53.04,
    '2-1/2"': 63.09,
    '3"': 78.03,
    '3-1/2"': 91.14,
    '4"': 103.02,
}


def _cargar_mapeo_handle_apartamento(
    raiz_proyecto: str,
) -> dict[str, list[str]]:
    """Carga mapeo handle_dxf -> lista de apartamentos desde inventarios.

    Lee todos los archivos data/inventarios/inventario_dispositivos_F*.json
    y construye un índice: handle_dxf -> [apartamento_tipo, ...].
    Un handle puede aparecer en varios apartamentos (muros compartidos);
    se devuelven todos para resolver por proximidad en el caller.
    """
    mapeo: dict[str, list[str]] = {}
    patron = os.path.join(raiz_proyecto, "data", "inventarios", "inventario_dispositivos_F*.json")
    for ruta in sorted(glob.glob(patron)):
        try:
            with open(ruta, encoding="utf-8") as f:
                inv = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        meta = inv.get("metadatos", {})
        apto = meta.get("apartamento_tipo")
        if not apto:
            continue
        for disp in inv.get("dispositivos", []):
            h = disp.get("handle")
            if h:
                mapeo.setdefault(h, []).append(apto)
    return mapeo


def dist2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _punto_mas_cercano(
    p: tuple[float, float],
    puntos: list[tuple[float, float]],
) -> tuple[tuple[float, float] | None, float]:
    """Devuelve (punto mas cercano, distancia)."""
    mejor: tuple[float, float] | None = None
    mejor_d = float("inf")
    for q in puntos:
        d = dist2(p, q)
        if d < mejor_d:
            mejor_d = d
            mejor = q
    return mejor, mejor_d


def _dist_punto_polilinea(
    p: tuple[float, float],
    vertices: list[tuple[float, float]],
) -> float:
    """Distancia minima de p a cualquier segmento de la polilinea."""
    mejor = float("inf")
    for i in range(len(vertices) - 1):
        a = vertices[i]
        b = vertices[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        if l2 == 0.0:
            d = dist2(p, a)
        else:
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
            px = a[0] + t * dx
            py = a[1] + t * dy
            d = dist2(p, (px, py))
        if d < mejor:
            mejor = d
    return mejor


def _diametro_para_cables(
    cables: int,
    servicio: str,
    cfg: Any | None,
) -> tuple[str, float, str]:
    """Devuelve (pulgadas, mm, origen) del diametro para la cantidad de cables.

    Prioridad:
      1. Diametro fijo por servicio (COMUNICACIONES = 3/4").
      2. Tabla de capacidad del config (PVC/12AWG para apartamentos).
      3. Default 1/2".
    """
    if servicio in DIAMETRO_FIJO:
        pulgadas, mm = DIAMETRO_FIJO[servicio]
        return pulgadas, mm, "fijo_servicio"

    if cfg is not None:
        try:
            pulgadas, mm, _cap = cfg.diametro_para(cables)
            return pulgadas, mm, "cables"
        except Exception:
            pass

    pulgadas, mm = DIAMETRO_DEFAULT
    return pulgadas, mm, "default"


def _extraer_contenido_bloque(
    bt: Any,
    x_off: float,
    y_off: float,
) -> dict[str, list[dict[str, Any]]]:
    """Extrae dispositivos, marcadores y polilineas de un bloque (coordenadas globales)."""
    dispositivos: list[dict[str, Any]] = []
    marcadores: list[dict[str, Any]] = []
    polilineas: list[dict[str, Any]] = []

    for e in bt:
        tipo = e.dxftype()
        capa = e.dxf.layer

        if tipo == "INSERT":
            nombre = e.dxf.name or ""
            ins = e.dxf.insert
            x = float(ins.x) + x_off
            y = float(ins.y) + y_off

            cables = cables_desde_nombre(nombre)
            if cables is not None:
                marcadores.append({
                    "handle": e.dxf.handle,
                    "nombre": nombre,
                    "capa": capa,
                    "x": x,
                    "y": y,
                    "cables": cables,
                })
            elif capa.startswith(("ELEC-", "Elec-", "E-")) or capa in ("0",):
                dispositivos.append({
                    "handle": e.dxf.handle,
                    "nombre": nombre,
                    "capa": capa,
                    "x": x,
                    "y": y,
                })

        elif tipo == "LWPOLYLINE":
            if capa not in CAPA_A_SERVICIO:
                continue
            pts = [(float(p[0]) + x_off, float(p[1]) + y_off) for p in e.get_points()]
            if len(pts) < 2:
                continue
            polilineas.append({
                "handle": e.dxf.handle,
                "capa": capa,
                "puntos": pts,
            })

    return {
        "dispositivos": dispositivos,
        "marcadores": marcadores,
        "polilineas": polilineas,
    }


def _construir_conduits(
    contenido: dict[str, list[dict[str, Any]]],
    apartamento_por_defecto: str,
    x_off: float,
    y_off: float,
    elevacion_nivel_m: float,
    cfg: Any | None,
    tramo_counter: list[int],
    mapeo_handle_apto: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Convierte polilineas y dispositivos de un apartamento en entradas de conduit.

    El campo "apartamento" se resuelve por panel/tablero-anclaje:
    se miran los handles de los dispositivos en los extremos de cada polilinea
    y se busca en el mapeo handle -> apartamento. Si hay coincidencia univoca,
    se usa ese apartamento; si hay conflicto o no hay mapeo, se usa
    apartamento_por_defecto (el bloque del DXF) como fallback.
    """
    conduits: list[dict[str, Any]] = []
    dispositivos = contenido["dispositivos"]
    marcadores = contenido["marcadores"]
    polilineas = contenido["polilineas"]

    # Ordenar polilineas por capa y luego por largo (mas largas primero, como el ruteador)
    def largo_pl(pl: dict[str, Any]) -> float:
        total = 0.0
        for i in range(len(pl["puntos"]) - 1):
            total += dist2(pl["puntos"][i], pl["puntos"][i + 1])
        return total

    ordenadas = sorted(polilineas, key=lambda pl: (pl["capa"], -largo_pl(pl)))

    for pl in ordenadas:
        servicio = CAPA_A_SERVICIO[pl["capa"]]
        puntos = pl["puntos"]

        # Largo total en mm
        largo_mm = largo_pl(pl)
        if largo_mm / 1000.0 < LARGO_MINIMO_TRAMO:
            continue

        # Extremos: asociar a dispositivos mas cercanos
        extremos: list[dict[str, Any]] = []
        for extremo_pt in (puntos[0], puntos[-1]):
            mejor_disp = None
            mejor_d = float("inf")
            for disp in dispositivos:
                d = dist2(extremo_pt, (disp["x"], disp["y"]))
                if d < mejor_d:
                    mejor_d = d
                    mejor_disp = disp
            if mejor_disp is not None and mejor_d <= TOL_EXTREMO_DISPOSITIVO * 1000.0:
                extremos.append({
                    "tipo": "dispositivo",
                    "x": round(extremo_pt[0], 3),
                    "y": round(extremo_pt[1], 3),
                    "distancia_m": round(mejor_d / 1000.0, 3),
                    "handle": mejor_disp["handle"],
                    "nombre": mejor_disp["nombre"],
                    "capa": mejor_disp["capa"],
                    "servicio": CAPA_A_SERVICIO.get(mejor_disp["capa"]),
                })
            else:
                extremos.append({
                    "tipo": "libre",
                    "x": round(extremo_pt[0], 3),
                    "y": round(extremo_pt[1], 3),
                    "distancia_m": round(mejor_d / 1000.0, 3) if mejor_disp else None,
                    "nombre": (mejor_disp["nombre"] if mejor_disp else ""),
                })

        # Cables: buscar marcador mas cercano a la polilinea
        cables = CABLES_DEFAULT
        cables_origen = "default"
        mejor_marc = None
        mejor_d_marc = float("inf")
        for marc in marcadores:
            d = _dist_punto_polilinea((marc["x"], marc["y"]), puntos)
            if d < mejor_d_marc:
                mejor_d_marc = d
                mejor_marc = marc
        if mejor_marc is not None and mejor_d_marc <= TOL_MARCADOR_POLILINEA * 1000.0:
            cables = mejor_marc["cables"]
            cables_origen = "marcador"

        # Diametro: pulgadas desde el marcador/config, mm desde la tabla EMT de Revit
        pulgadas, _diam_nominal, diametro_origen = _diametro_para_cables(cables, servicio, cfg)
        diam_mm = EMT_DIAMETROS_MM.get(pulgadas, EMT_DIAMETROS_MM['1/2"'])

        # Cota y Z absoluta
        cota_m = COTA_BANDA.get(servicio, 2.65)
        z_abs_m = round(elevacion_nivel_m + cota_m, 4)
        z_mm = round(z_abs_m * 1000.0)

        tramo_counter[0] += 1
        tramo_id = "RT-%04d" % tramo_counter[0]

        # Determinar apartamento por panel/tablero-anclaje (dispositivos en extremos)
        apartamento_asignado = apartamento_por_defecto
        if mapeo_handle_apto:
            apartamentos_extremos: list[str] = []
            for extremo in extremos:
                h = extremo.get("handle")
                if h and h in mapeo_handle_apto:
                    apartamentos_extremos.extend(mapeo_handle_apto[h])
            if apartamentos_extremos:
                apto_contador = Counter(apartamentos_extremos)
                apartamento_asignado = apto_contador.most_common(1)[0][0]

        conduits.append({
            "id": tramo_id,
            "handle_dxf": pl["handle"],
            "apartamento": apartamento_asignado,
            "capa": pl["capa"],
            "servicio": servicio,
            "cables": cables,
            "cables_origen": cables_origen,
            "material": "PVC",
            "calibre": "12 AWG",
            "diametro_pulgadas": pulgadas,
            "diametro_mm": round(diam_mm, 2),
            "diametro_origen": diametro_origen,
            "largo_mm": round(largo_mm, 3),
            "cota_m": round(cota_m, 3),
            "z_absoluta_m": z_abs_m,
            "a": [round(puntos[0][0], 3), round(puntos[0][1], 3), z_mm],
            "b": [round(puntos[-1][0], 3), round(puntos[-1][1], 3), z_mm],
            "puntos_2d": [[round(x, 3), round(y, 3)] for x, y in puntos],
            "extremos": extremos,
            "avisos": [],
        })

    return conduits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extrae conductos desde DXF de bloques electricos (apartamentos F01/F02)"
    )
    parser.add_argument("--dxf", required=True, help="DXF de entrada (bloques electricos)")
    parser.add_argument(
        "--apartamentos",
        required=True,
        help="Nombres de bloques de apartamento separados por coma "
        "(ej: 'Apartamento Tipo F 01,Apartamento Tipo F 02')",
    )
    parser.add_argument("--config", default=None, help="JSON de configuracion de ruteo")
    parser.add_argument("--out", required=True, help="JSON de salida con conductos")
    parser.add_argument("--nivel", default="Piso 5", help="Nombre del nivel en Revit")
    parser.add_argument(
        "--elevacion-nivel",
        type=float,
        default=13.22,
        help="Elevacion del nivel en metros (Piso 5 = 13.22 m)",
    )
    args = parser.parse_args(argv)

    # Resolver rutas relativas contra la raiz del proyecto
    raiz_proyecto = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))

    dxf = args.dxf if os.path.isabs(args.dxf) else os.path.join(raiz_proyecto, args.dxf)
    if not os.path.exists(dxf):
        print("ERROR: no existe el DXF: %s" % dxf, file=sys.stderr)
        return 2

    cfg = None
    if args.config:
        ruta_cfg = args.config if os.path.isabs(args.config) else os.path.join(raiz_proyecto, args.config)
        cfg = cargar_config(ruta_cfg, raiz_proyecto)

    out = args.out if os.path.isabs(args.out) else os.path.join(raiz_proyecto, args.out)

    apartamentos = [a.strip() for a in args.apartamentos.split(",") if a.strip()]

    # Leer DXF
    doc = ezdxf.readfile(dxf)
    msp = doc.modelspace()

    # Encontrar inserts de bloques de apartamento en modelspace -> offsets globales
    bloque_inserts: dict[str, tuple[float, float]] = {}
    for e in msp:
        if e.dxftype() == "INSERT" and e.dxf.name in apartamentos:
            ins = e.dxf.insert
            bloque_inserts[e.dxf.name] = (float(ins.x), float(ins.y))

    faltantes = [a for a in apartamentos if a not in bloque_inserts]
    if faltantes:
        print("ERROR: no se encontraron inserts en modelspace para: %s" % ", ".join(faltantes),
              file=sys.stderr)
        print("   Inserts disponibles con 'Apartamento':")
        for e in msp:
            if e.dxftype() == "INSERT" and "Apartamento" in (e.dxf.name or ""):
                ins = e.dxf.insert
                print("     %s en (%.2f, %.2f)" % (e.dxf.name, ins.x, ins.y))
        return 2

    # Procesar cada apartamento
    todos_conduits: list[dict[str, Any]] = []
    resumen_por_apto: dict[str, dict[str, Any]] = {}
    tramo_counter = [0]

    # Cargar mapeo handle_dxf -> apartamento (por panel/tablero-anclaje)
    mapeo_handle_apto = _cargar_mapeo_handle_apartamento(raiz_proyecto)
    if mapeo_handle_apto:
        print("Mapeo handle->apartamento cargado: %d handles" % len(mapeo_handle_apto))

    for apto in apartamentos:
        x_off, y_off = bloque_inserts[apto]
        bt = doc.blocks[apto]
        contenido = _extraer_contenido_bloque(bt, x_off, y_off)

        conduits = _construir_conduits(
            contenido, apto, x_off, y_off,
            args.elevacion_nivel, cfg, tramo_counter,
            mapeo_handle_apto=mapeo_handle_apto,
        )
        todos_conduits.extend(conduits)

        resumen_por_apto[apto] = {
            "insert_x": round(x_off, 3),
            "insert_y": round(y_off, 3),
            "dispositivos": len(contenido["dispositivos"]),
            "marcadores": len(contenido["marcadores"]),
            "polilineas": len(contenido["polilineas"]),
            "conduits": len(conduits),
        }

    # Estadisticas por servicio
    por_servicio: dict[str, int] = {}
    largo_por_servicio: dict[str, float] = {}
    por_diametro: dict[str, int] = {}
    for c in todos_conduits:
        por_servicio[c["servicio"]] = por_servicio.get(c["servicio"], 0) + 1
        largo_por_servicio[c["servicio"]] = largo_por_servicio.get(c["servicio"], 0.0) + c["largo_mm"]
        por_diametro[c["diametro_pulgadas"]] = por_diametro.get(c["diametro_pulgadas"], 0) + 1

    salida = {
        "version": "v01",
        "dxf": os.path.basename(dxf),
        "nivel": args.nivel,
        "elevacion_nivel_m": args.elevacion_nivel,
        "apartamentos": resumen_por_apto,
        "resumen": {
            "total_conduits": len(todos_conduits),
            "por_servicio": por_servicio,
            "largo_por_servicio_mm": {k: round(v, 2) for k, v in largo_por_servicio.items()},
            "por_diametro": por_diametro,
            "longitud_total_mm": round(sum(c["largo_mm"] for c in todos_conduits), 2),
        },
        "conduits": todos_conduits,
    }

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=1, ensure_ascii=False)

    print("Conduits extraidos: %d" % len(todos_conduits))
    print("  Por servicio: %s" % por_servicio)
    print("  Por diametro: %s" % por_diametro)
    print("  Longitud total: %.2f mm" % salida["resumen"]["longitud_total_mm"])
    print("JSON -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
