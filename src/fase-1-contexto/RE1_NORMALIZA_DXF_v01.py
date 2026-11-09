"""
================================================================================
RE1_NORMALIZA_DXF_v01.py — Normalización de DXF eléctrico para Revit 2026
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 Standalone (NO Revit, NO Grasshopper)
================================================================================

OBJETIVO:
  Leer un DXF eléctrico fuente, reubicar coordenadas al origen (0,0) corrigiendo
  el offset masivo detectado en el diagnóstico, filtrar bloques con nombres basura
  y generar un JSON intermedio con bloques eléctricos identificables listos para
  mapear a familias de Revit.

NORMATIVA:
  - Modelo 3D solo para validación de interferencias y coordinación interna.
  - No es documento constructivo certificado.
  - Cálculos RETIE/NTC 2050 se hacen de forma independiente (planos 2D).

ENTRADAS (CLI):
  --dxf         : ruta al archivo DXF fuente
  --salida      : ruta del JSON de salida (default: data/<chip>_normalizado.json)
  --offset-x    : desplazamiento X a corregir (default: -991.903)
  --offset-y    : desplazamiento Y a corregir (default: -1714.822)
  --chip        : identificador del predio/lote (default: SANTAMARTA_T5)

SALIDA:
  JSON con:
    - metadatos (origen, offset aplicado, chip)
    - resumen (conteos de entidades)
    - bloques: lista de bloques INSERT con nombre, capa, punto insert (reubicado)
    - polilineas: lista de LWPOLYLINE con puntos reubicados
    - mapeo_revit: mapeo provisional nombre_bloque -> familia_revit

HISTORIAL:
  v01.0 (2026-10-21) — versión inicial. Normalización DXF para RevitElectrico.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import ezdxf
except ImportError as exc:  # pragma: no cover - depende del entorno
    raise SystemExit(
        "ezdxf no está instalado. Instálelo con: pip install ezdxf"
    ) from exc

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_OFFSET_X = -991.903
DEFAULT_OFFSET_Y = -1714.822
DEFAULT_CHIP = "SANTAMARTA_T5"

# Prefijos de capas eléctricas identificables (según diagnóstico DXF)
CAPAS_ELECTRICAS = (
    "ELEC-",
    "Elec-",
    "E-Lite-",
    "Elec-Lite-",
    "TDT",
    "Apartamento",
    "Paneles",
    "tablero",
)

# Bloques con nombres basura detectados en el diagnóstico (filtrarlos)
NOMBRES_BASURA = (
    "sadfasdggfjhkkl",
    "ghghgh",
    "sdgsdsg",
    "sdfsdgjgfd",
    "dsfgsh",
    "sifon",
    "FRE",
    "A$C74C362D2",
    "A$C0F1C539B",
)

# Mapeo provisional de bloques eléctricos -> familias de Revit (sin atributos)
MAPEO_BLOQUES_REVIT: Dict[str, str] = {
    "Bala Stil Led 12W": "Luminaria LED 12W",
    "1FTN": "Luminaria tubular 1x",
    "1FTNR": "Luminaria tubular 1x con reflector",
    "ELEC-LAF EMERG BAT LED": "Luminaria emergencia LED batería",
    "SS-Sensor Proximidad": "Sensor de proximidad",
    "ELEC-I-S-1-5A": "Interruptor simple 1x 5A",
    "ELEC-T-D-t-15A": "Toma doble 15A",
    "Bala Stil Led 16W": "Luminaria LED 16W",
    "HERMETICA 40W": "Luminaria hermética 40W",
    "Paneles": "Tablero eléctrico",
    "tablero": "Tablero eléctrico",
    "Paneles Solares 550W": "Panel solar 550W",
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _es_nombre_basura(nombre: str) -> bool:
    """Devuelve True si el nombre del bloque es basura (debe filtrarse)."""
    n = (nombre or "").strip()
    if not n:
        return True
    if n in NOMBRES_BASURA:
        return True
    # Nombres alfanuméricos aleatorios (basura típica de CAD)
    if re.fullmatch(r"[A-Za-z0-9$]{6,}", n) and n.isalnum() is False:
        return True
    if len(n) >= 10 and re.fullmatch(r"[a-z]{6,}", n):
        return True
    return False


def _pertenece_a_capa_electrica(capa: str) -> bool:
    """Devuelve True si la capa es de sistema eléctrico."""
    c = (capa or "").strip()
    return any(c.startswith(pref) for pref in CAPAS_ELECTRICAS)


def _reubicar_punto(
    x: float, y: float, z: float, offset_x: float, offset_y: float
) -> Tuple[float, float, float]:
    """Reubica un punto restando el offset (corrige desplazamiento masivo)."""
    return (round(x - offset_x, 3), round(y - offset_y, 3), round(z, 3))


def _familia_revit(nombre_bloque: str) -> str:
    """Devuelve la familia de Revit sugerida para un bloque eléctrico."""
    return MAPEO_BLOQUES_REVIT.get(nombre_bloque, "Familia por definir")


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def normalizar_dxf(
    dxf_path: Path,
    salida_path: Path,
    offset_x: float = DEFAULT_OFFSET_X,
    offset_y: float = DEFAULT_OFFSET_Y,
    chip: str = DEFAULT_CHIP,
) -> Dict[str, Any]:
    """
    Lee un DXF, reubica coordenadas al origen, filtra bloques basura y genera
    un JSON intermedio con bloques eléctricos identificables.
    """
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    bloques: List[Dict[str, Any]] = []
    polilineas: List[Dict[str, Any]] = []
    lineas: List[Dict[str, Any]] = []
    arcos: List[Dict[str, Any]] = []
    circulos: List[Dict[str, Any]] = []

    bloques_basura_filtrados = 0
    bloques_electricos = 0
    bloques_no_electricos = 0

    for entity in msp:
        capa = entity.dxf.layer
        es_electrica = _pertenece_a_capa_electrica(capa)

        if entity.dxftype() == "INSERT":
            nombre = entity.dxf.name
            if _es_nombre_basura(nombre):
                bloques_basura_filtrados += 1
                continue

            punto_insert = entity.dxf.insert
            x, y, z = _reubicar_punto(
                punto_insert.x, punto_insert.y, punto_insert.z,
                offset_x, offset_y,
            )

            bloque = {
                "nombre_bloque": nombre,
                "capa": capa,
                "es_electrica": es_electrica,
                "punto_insert": [x, y, z],
                "familia_revit_sugerida": _familia_revit(nombre),
            }
            bloques.append(bloque)

            if es_electrica:
                bloques_electricos += 1
            else:
                bloques_no_electricos += 1

        elif entity.dxftype() == "LWPOLYLINE":
            puntos = [
                _reubicar_punto(
                    p[0], p[1], p[2] if len(p) > 2 else 0.0,
                    offset_x, offset_y,
                )
                for p in entity.get_points()
            ]
            if len(puntos) >= 2:
                polilineas.append({
                    "capa": capa,
                    "es_electrica": es_electrica,
                    "puntos": puntos,
                    "cerrada": bool(entity.closed),
                })

        elif entity.dxftype() == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            lineas.append({
                "capa": capa,
                "es_electrica": es_electrica,
                "inicio": _reubicar_punto(start.x, start.y, start.z, offset_x, offset_y),
                "fin": _reubicar_punto(end.x, end.y, end.z, offset_x, offset_y),
            })

        elif entity.dxftype() == "ARC":
            center = entity.dxf.center
            arcos.append({
                "capa": capa,
                "es_electrica": es_electrica,
                "centro": _reubicar_punto(center.x, center.y, center.z, offset_x, offset_y),
                "radio": round(entity.dxf.radius, 3),
                "angulo_inicio": round(math.degrees(entity.dxf.start_angle), 2),
                "angulo_fin": round(math.degrees(entity.dxf.end_angle), 2),
            })

        elif entity.dxftype() == "CIRCLE":
            center = entity.dxf.center
            circulos.append({
                "capa": capa,
                "es_electrica": es_electrica,
                "centro": _reubicar_punto(center.x, center.y, center.z, offset_x, offset_y),
                "radio": round(entity.dxf.radius, 3),
            })

    salida = {
        "metadatos": {
            "origen_dxf": str(dxf_path),
            "chip": chip,
            "offset_aplicado_x": offset_x,
            "offset_aplicado_y": offset_y,
            "version_dxf": doc.dxfversion,
            "unidades": doc.header.get("$INSUNITS", 6),
        },
        "resumen": {
            "bloques_total": len(bloques),
            "bloques_electricos": bloques_electricos,
            "bloques_no_electricos": bloques_no_electricos,
            "bloques_basura_filtrados": bloques_basura_filtrados,
            "polilineas": len(polilineas),
            "polilineas_electricas": sum(1 for p in polilineas if p["es_electrica"]),
            "lineas": len(lineas),
            "lineas_electricas": sum(1 for l in lineas if l["es_electrica"]),
            "arcos": len(arcos),
            "circulos": len(circulos),
        },
        "bloques": bloques,
        "polilineas": polilineas,
        "lineas": lineas,
        "arcos": arcos,
        "circulos": circulos,
        "mapeo_revit": MAPEO_BLOQUES_REVIT,
    }

    salida_path.parent.mkdir(parents=True, exist_ok=True)
    with open(salida_path, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    return salida


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normaliza DXF eléctrico para Revit 2026 (RevitElectrico)."
    )
    parser.add_argument("--dxf", type=str, required=True, help="Ruta al DXF fuente")
    parser.add_argument(
        "--salida", type=str, default="",
        help="Ruta del JSON de salida (default: data/<chip>_normalizado.json)",
    )
    parser.add_argument(
        "--offset-x", type=float, default=DEFAULT_OFFSET_X,
        help="Desplazamiento X a corregir (default: -991.903)",
    )
    parser.add_argument(
        "--offset-y", type=float, default=DEFAULT_OFFSET_Y,
        help="Desplazamiento Y a corregir (default: -1714.822)",
    )
    parser.add_argument(
        "--chip", type=str, default=DEFAULT_CHIP,
        help="Identificador del predio/lote (default: SANTAMARTA_T5)",
    )

    args = parser.parse_args()

    dxf_path = Path(args.dxf)
    if not dxf_path.exists():
        raise SystemExit(f"El archivo DXF no existe: {dxf_path}")

    chip = args.chip or DEFAULT_CHIP
    if args.salida:
        salida_path = Path(args.salida)
    else:
        root = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
        salida_path = root / "data" / f"{chip}_normalizado.json"

    resultado = normalizar_dxf(dxf_path, salida_path, args.offset_x, args.offset_y, chip)

    print("=== Normalización DXF completada ===")
    print(f"Origen: {resultado['metadatos']['origen_dxf']}")
    print(f"Chip: {resultado['metadatos']['chip']}")
    print(f"Offset aplicado: X={resultado['metadatos']['offset_aplicado_x']}, "
          f"Y={resultado['metadatos']['offset_aplicado_y']}")
    print(f"Bloques totales: {resultado['resumen']['bloques_total']}")
    print(f"  Eléctricos: {resultado['resumen']['bloques_electricos']}")
    print(f"  No eléctricos: {resultado['resumen']['bloques_no_electricos']}")
    print(f"  Basura filtrada: {resultado['resumen']['bloques_basura_filtrados']}")
    print(f"Polilíneas: {resultado['resumen']['polilineas']} "
          f"({resultado['resumen']['polilineas_electricas']} eléctricas)")
    print(f"Líneas: {resultado['resumen']['lineas']}")
    print(f"Arcos: {resultado['resumen']['arcos']} | Círculos: {resultado['resumen']['circulos']}")
    print(f"JSON guardado en: {salida_path}")


if __name__ == "__main__":
    main()

