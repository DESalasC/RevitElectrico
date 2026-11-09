"""
================================================================================
RE5_ATRIBUTOS_ANEXOS_v01.py — Atributos anexos (texto -> bloque) del DXF eléctrico
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 Standalone (NO Revit, NO Grasshopper)
================================================================================

OBJETIVO:
  Leer entidades TEXT y MTEXT del DXF fuente, asociar cada texto al bloque INSERT
  más cercano dentro de un umbral configurable, y enriquecer el JSON de salida de
  RE1_NORMALIZA_DXF_v01.py con un campo `atributos_anexos` por bloque. Los textos
  que no quedan cerca de ningún bloque se reportan por separado.

  Los textos anexos suelen llevar información eléctrica (CIRCUITO, ALTURA, PANEL,
  TUBO, CABLE, etc.) que no está dentro del bloque, por lo que hay que asociar
  bloque + texto cercano para convertir esa información en datos de la familia
  de Revit.

ENTRADAS (CLI):
  --json-in   : ruta al JSON de salida de RE1_NORMALIZA_DXF_v01.py (contiene bloques)
  --dxf       : ruta al archivo DXF fuente (para leer TEXT y MTEXT)
  --json-out  : ruta del JSON de salida enriquecido (default:
               data/<chip>_atributos_anexos.json)
  --umbral    : distancia máxima 2D (en metros) para asociar texto -> bloque
               (default: 2.0)
  --chip      : identificador del predio/lote (default: SANTAMARTA_T5)

SALIDA:
  JSON con:
    - metadatos (chip, origen, umbral, version)
    - resumen (conteos de textos, asociaciones, textos no asociados)
    - bloques: lista de bloques de RE1 enriquecida con atributos_anexos:
        [{nombre_bloque, capa, punto_insert, atributos_anexos: [
            {texto, distancia_m, tipo_atributo}, ...]}, ...]
    - textos_no_asociados: lista de textos sin bloque cercano
    - mapeo_revit: copia del mapeo de RE1

NORMATIVA:
  - Modelo 3D solo para validación de interferencias y coordinación interna.
  - No es documento constructivo certificado.

HISTORIAL:
  v01.0 (2026-10-23) — versión inicial. Atributos anexos texto -> bloque.
================================================================================

"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import ezdxf
except ImportError as exc:  # pragma: no cover - depende del entorno
    raise SystemExit(
        "ezdxf no está instalado. Instálelo con: pip install ezdxf"
    ) from exc

DEFAULT_CHIP = "SANTAMARTA_T5"
DEFAULT_UMBRAL_M = 2.0
DEFAULT_VERSION = "v01.0"

# Palabras clave para clasificar el tipo de atributo eléctrico de un texto.
# Cada tupla: (tipo_atributo, (palabras_clave...))
CLAVES_TIPO_ATRIBUTO: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("circuito", ("CIRCUITO", "CIRC", "CKT")),
    ("altura", ("ALTURA", "ALTO", "MTS", "M.", "M", "ELEV")),
    ("panel", ("PANEL", "TABLERO", "TABL")),
    ("tubo", ("TUBO", "CONDUIT", "CONDUCTOR")),
    ("cable", ("CABLE", "CABLEADO")),
    ("fase", ("FASE", "L1", "L2", "L3", "N", "T")),
    ("amperaje", ("A", "AMP", "AMPS")),
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _distancia_2d(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
    """Distancia euclidiana 2D entre dos puntos (ignora Z)."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _palabras_texto(texto: str) -> List[str]:
    """Devuelve las palabras alfanumericas de un texto en mayusculas."""
    return re.findall(r"[A-Za-z0-9]+", (texto or "").upper())


def _es_texto_electrico(texto: str, capa: str) -> bool:
    """Devuelve True si el texto parece ser un atributo eléctrico."""
    t = (texto or "").strip()
    c = (capa or "").strip().upper()
    if not t:
        return False
    # Por capa eléctrica
    if any(c.startswith(pref.upper()) for pref in ("ELEC-", "E-", "TDT", "APARTAMENTO", "PANEL")):
        return True
    # Por palabras clave en el contenido (matching de palabra completa)
    palabras = set(_palabras_texto(t))
    for _, palabras_clave in CLAVES_TIPO_ATRIBUTO:
        if any(palabra in palabras for palabra in palabras_clave):
            return True
    return False


def _clasificar_tipo_atributo(texto: str) -> str:
    """Clasifica un texto anexo en un tipo de atributo eléctrico."""
    palabras = set(_palabras_texto(texto))
    for tipo, palabras_clave in CLAVES_TIPO_ATRIBUTO:
        if any(palabra in palabras for palabra in palabras_clave):
            return tipo
    return "otro"


def _leer_textos_anexos(msp) -> List[Dict[str, Any]]:
    """Extrae entidades TEXT y MTEXT del modelspace como lista de dicts."""
    textos: List[Dict[str, Any]] = []
    for entity in msp:
        if entity.dxftype() == "TEXT":
            punto = entity.dxf.insert
            textos.append({
                "texto": entity.dxf.text,
                "capa": entity.dxf.layer,
                "punto_insert": [round(punto.x, 3), round(punto.y, 3), round(punto.z, 3)],
                "altura": round(entity.dxf.height, 3),
            })
        elif entity.dxftype() == "MTEXT":
            punto = entity.dxf.insert
            textos.append({
                "texto": entity.text,
                "capa": entity.dxf.layer,
                "punto_insert": [round(punto.x, 3), round(punto.y, 3), round(punto.z, 3)],
                "altura": round(entity.dxf.char_height, 3),
            })
    return textos


def _asociar_texto_bloque(
    texto_punto: Tuple[float, float, float],
    bloques: List[Dict[str, Any]],
    umbral_m: float,
) -> Optional[Tuple[Dict[str, Any], float]]:
    """
    Busca el bloque INSERT más cercano al punto del texto (distancia 2D).
    Retorna (bloque, distancia) si distancia <= umbral, o None si no hay
    bloque dentro del umbral.
    """
    mejor_bloque: Optional[Dict[str, Any]] = None
    mejor_distancia = float("inf")

    for bloque in bloques:
        punto_bloque = tuple(bloque.get("punto_insert", [0.0, 0.0, 0.0]))
        distancia = _distancia_2d(texto_punto, punto_bloque)
        if distancia < mejor_distancia:
            mejor_distancia = distancia
            mejor_bloque = bloque

    if mejor_bloque is None or mejor_distancia > umbral_m:
        return None
    return mejor_bloque, mejor_distancia


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def procesar_atributos_anexos(
    json_in: Path,
    dxf_path: Path,
    json_out: Path,
    chip: str = DEFAULT_CHIP,
    umbral_m: float = DEFAULT_UMBRAL_M,
) -> Dict[str, Any]:
    """
    Lee el JSON de RE1 (bloques), lee TEXT/MTEXT del DXF fuente, asocia cada
    texto al bloque más cercano dentro del umbral y escribe el JSON enriquecido
    con atributos_anexos por bloque.
    """
    with open(json_in, "r", encoding="utf-8") as f:
        datos_re1 = json.load(f)

    bloques_re1: List[Dict[str, Any]] = datos_re1.get("bloques", [])
    mapeo_revit: Dict[str, Any] = datos_re1.get("mapeo_revit", {})

    # Leer textos anexos del DXF
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    textos_anexos = _leer_textos_anexos(msp)

    # Indexar bloques para enriquecimiento (por posición en lista)
    bloques_enriquecidos: List[Dict[str, Any]] = []
    textos_no_asociados: List[Dict[str, Any]] = []

    asociaciones_exitosas = 0

    for bloque in bloques_re1:
        bloque_copia = dict(bloque)
        bloque_copia["atributos_anexos"] = []

        punto_bloque = tuple(bloque.get("punto_insert", [0.0, 0.0, 0.0]))

        for texto in textos_anexos:
            # Solo considerar textos eléctricos para asociar
            if not _es_texto_electrico(texto["texto"], texto["capa"]):
                continue

            punto_texto = tuple(texto["punto_insert"])
            resultado = _asociar_texto_bloque(punto_texto, [bloque], umbral_m)
            if resultado is not None:
                _, distancia = resultado
                bloque_copia["atributos_anexos"].append({
                    "texto": texto["texto"],
                    "distancia_m": round(distancia, 3),
                    "tipo": _clasificar_tipo_atributo(texto["texto"]),
                })
                asociaciones_exitosas += 1

        bloques_enriquecidos.append(bloque_copia)

    # Textos eléctricos no asociados a ningún bloque (umbral superado o sin bloques)
    todos_los_puntos_bloques = [
        tuple(b.get("punto_insert", [0.0, 0.0, 0.0])) for b in bloques_re1
    ]
    for texto in textos_anexos:
        if not _es_texto_electrico(texto["texto"], texto["capa"]):
            continue
        punto_texto = tuple(texto["punto_insert"])
        # Buscar el bloque global más cercano
        mejor_distancia = float("inf")
        for pb in todos_los_puntos_bloques:
            d = _distancia_2d(punto_texto, pb)
            if d < mejor_distancia:
                mejor_distancia = d
        if mejor_distancia > umbral_m or not todos_los_puntos_bloques:
            textos_no_asociados.append({
                "texto": texto["texto"],
                "capa": texto["capa"],
                "punto_insert": punto_texto,
                "distancia_mas_cercana_m": round(mejor_distancia, 3) if todos_los_puntos_bloques else None,
                "tipo": _clasificar_tipo_atributo(texto["texto"]),
            })

    salida = {
        "metadatos": {
            "chip": chip,
            "origen_json_in": str(json_in),
            "origen_dxf": str(dxf_path),
            "umbral_m": umbral_m,
            "version": DEFAULT_VERSION,
        },
        "resumen": {
            "textos_anexos_total": len(textos_anexos),
            "textos_electricos": sum(1 for t in textos_anexos if _es_texto_electrico(t["texto"], t["capa"])),
            "asociaciones_exitosas": asociaciones_exitosas,
            "textos_no_asociados": len(textos_no_asociados),
            "bloques_con_atributos": sum(1 for b in bloques_enriquecidos if b.get("atributos_anexos")),
            "total_bloques": len(bloques_enriquecidos),
        },
        "bloques": bloques_enriquecidos,
        "textos_no_asociados": textos_no_asociados,
        "mapeo_revit": mapeo_revit,
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    return salida


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Asocia textos anexos (TEXT/MTEXT) del DXF a bloques INSERT "
                    "y enriquece el JSON de RE1 con atributos_anexos (RevitElectrico)."
    )
    parser.add_argument(
        "--json-in", type=str, required=True,
        help="Ruta al JSON de salida de RE1_NORMALIZA_DXF_v01.py (entrada)",
    )
    parser.add_argument(
        "--dxf", type=str, required=True,
        help="Ruta al archivo DXF fuente (para leer TEXT y MTEXT)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de salida enriquecido "
             "(default: data/<chip>_atributos_anexos.json)",
    )
    parser.add_argument(
        "--umbral", type=float, default=DEFAULT_UMBRAL_M,
        help="Distancia máxima 2D (m) para asociar texto -> bloque (default: 2.0)",
    )
    parser.add_argument(
        "--chip", type=str, default=DEFAULT_CHIP,
        help="Identificador del predio/lote (default: SANTAMARTA_T5)",
    )

    args = parser.parse_args()

    json_in = Path(args.json_in)
    if not json_in.exists():
        raise SystemExit(f"El archivo JSON de entrada no existe: {json_in}")

    dxf_path = Path(args.dxf)
    if not dxf_path.exists():
        raise SystemExit(f"El archivo DXF fuente no existe: {dxf_path}")

    chip = args.chip or DEFAULT_CHIP
    if args.json_out:
        json_out = Path(args.json_out)
    else:
        root = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
        json_out = root / "data" / f"{chip}_atributos_anexos.json"

    resultado = procesar_atributos_anexos(
        json_in, dxf_path, json_out, chip=chip, umbral_m=args.umbral
    )

    print("=== Atributos anexos (texto -> bloque) completados ===")
    print(f"Origen JSON: {resultado['metadatos']['origen_json_in']}")
    print(f"Origen DXF: {resultado['metadatos']['origen_dxf']}")
    print(f"Chip: {resultado['metadatos']['chip']}")
    print(f"Umbral: {resultado['metadatos']['umbral_m']} m")
    print(f"Textos anexos totales: {resultado['resumen']['textos_anexos_total']}")
    print(f"  Textos eléctricos: {resultado['resumen']['textos_electricos']}")
    print(f"  Asociaciones exitosas: {resultado['resumen']['asociaciones_exitosas']}")
    print(f"  Textos no asociados: {resultado['resumen']['textos_no_asociados']}")
    print(f"Bloques con atributos: {resultado['resumen']['bloques_con_atributos']} / "
          f"{resultado['resumen']['total_bloques']}")
    print(f"JSON guardado en: {json_out}")


if __name__ == "__main__":
    main()

