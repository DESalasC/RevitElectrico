# -*- coding: utf-8 -*-
"""
RE_APLICAR_MAPA_V3_v01.py — Aplica MAPA_BLOQUES_REVIT_v3.json a los dispositivos
y genera FamilyInstance en Revit 2026.
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 Standalone (NO Revit) — genera JSON de reporte con la lista de
acciones a ejecutar en Revit (pyRevit / Dynamo).

OBJETIVO:
  Leer MAPA_BLOQUES_REVIT_v3.json (mapeo bloque DXF -> familia/simbolo/anfitrion)
  y apartamento_F_02_dispositivos.json (59 dispositivos con x_revit/y_revit),
  y producir un JSON de reporte con:
    - dispositivos a modelar (mapear: true) con familia, simbolo, anfitrion,
      altura, punto XY en Revit, rotacion y escala.
    - marcadores de conductores (mapear: false) a saltar (sin FamilyInstance,
      sin tubo vertical).
    - dispositivos sin mapeo (sin entrada en el mapa).
  El reporte puede consumirse por un script de Revit (pyRevit/IronPython)
  que cree las FamilyInstance reales usando NewFamilyInstance(face, …) para
  anfitrion == ceiling y NewFamilyInstance(level, …) para anfitrion == muro.

NOTAS DE IMPLEMENTACION EN REVIT (para quien ejecute dentro de Revit):
  - anfitrion == "ceiling":  NewFamilyInstance(face_cieloraso, XYZ, symbol)
                             (cara inferior del cieloraso, Z ≈ 15.72–15.82 m)
  - anfitrion == "muro":     NewFamilyInstance(level, XYZ, symbol, estructural=false)
  - Rotacion: aplicar rot en grados sobre el eje Z del symbol.
  - Escala: aplicar xscale/yscale al symbol si la familia lo permite.


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

DEFAULT_CHIP = "SANTAMARTA_T5"
DEFAULT_NIVEL = "Piso 5"
DEFAULT_ALTEZA_CIELORASO_M = 15.82  # cara inferior del cieloraso (m)


def _cargar_json(ruta: Path) -> Dict[str, Any]:
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def _buscar_entrada_mapa(
    mapa: Dict[str, Any], nombre_bloque: str
) -> Tuple[Dict[str, Any] | None, bool]:
    """
    Busca la entrada de mapeo para un nombre de bloque.
    Devuelve (entrada, encontrado). La entrada puede ser None si el bloque
    no esta en el mapa.
    """
    mapeo = mapa.get("mapeo", {})
    if nombre_bloque in mapeo:
        return mapeo[nombre_bloque], True
    return None, False


def aplicar_mapa(
    mapa_path: Path,
    dispositivos_path: Path,
    chip: str = DEFAULT_CHIP,
    nivel: str = DEFAULT_NIVEL,
    altura_cieloraso_m: float = DEFAULT_ALTEZA_CIELORASO_M,
) -> Dict[str, Any]:
    """
    Aplica el mapa de bloques a los dispositivos y genera el reporte de
    acciones a ejecutar en Revit.
    """
    mapa = _cargar_json(mapa_path)
    dispositivos = _cargar_json(dispositivos_path)

    mapeo = mapa.get("mapeo", {})
    dispositivos_internos: List[Dict[str, Any]] = dispositivos.get(
        "dispositivos_internos", []
    )

    acciones_modelar: List[Dict[str, Any]] = []
    acciones_saltar: List[Dict[str, Any]] = []
    acciones_sin_mapeo: List[Dict[str, Any]] = []

    cont_modelar = 0
    cont_saltar = 0
    cont_sin_mapeo = 0
    cont_techo = 0
    cont_muro = 0
    cont_otro_anfitrion = 0

    for disp in dispositivos_internos:
        nombre = disp.get("nombre_bloque_hijo", "")
        capa = disp.get("capa", "")
        x_revit = disp.get("x_revit")
        y_revit = disp.get("y_revit")
        rotacion = disp.get("rotacion", 0)
        xscale = disp.get("xscale", 1)
        yscale = disp.get("yscale", 1)
        orden = disp.get("orden")

        entrada, encontrado = _buscar_entrada_mapa(mapa, nombre)

        if not encontrado:
            # No hay entrada en el mapa: dispositivo sin mapear
            acciones_sin_mapeo.append(
                {
                    "orden": orden,
                    "nombre_bloque": nombre,
                    "capa": capa,
                    "x_revit": x_revit,
                    "y_revit": y_revit,
                    "rotacion": rotacion,
                    "xscale": xscale,
                    "yscale": yscale,
                    "motivo": "No hay entrada en MAPA_BLOQUES_REVIT_v3.json",
                }
            )
            cont_sin_mapeo += 1
            continue

        mapear = entrada.get("mapear", False)

        if not mapear:
            # Marcador de conductor u otro elemento no físico: saltar
            acciones_saltar.append(
                {
                    "orden": orden,
                    "nombre_bloque": nombre,
                    "capa": capa,
                    "x_revit": x_revit,
                    "y_revit": y_revit,
                    "rotacion": rotacion,
                    "xscale": xscale,
                    "yscale": yscale,
                    "familia": entrada.get("familia"),
                    "simbolo": entrada.get("simbolo"),
                    "motivo": entrada.get(
                        "nota", "Marcador no dispositivo; no crear FamilyInstance"
                    ),
                }
            )
            cont_saltar += 1
            continue

        # Dispositivo físico a modelar
        familia = entrada.get("familia")
        simbolo = entrada.get("simbolo")
        anfitrion = entrada.get("anfitrion")
        altura_m = entrada.get("altura_m")

        accion = {
            "orden": orden,
            "nombre_bloque": nombre,
            "capa": capa,
            "x_revit": x_revit,
            "y_revit": y_revit,
            "z_revit": altura_m,
            "rotacion": rotacion,
            "xscale": xscale,
            "yscale": yscale,
            "familia": familia,
            "simbolo": simbolo,
            "anfitrion": anfitrion,
            "nivel": nivel,
            "altura_cieloraso_m": (
                altura_cieloraso_m if anfitrion == "ceiling" else None
            ),
            "nivel_revit": nivel if anfitrion == "muro" else None,
            "metodo_instancia": (
                "NewFamilyInstance(face, ...)" if anfitrion == "ceiling" else "NewFamilyInstance(level, ...)"
            ),
        }
        acciones_modelar.append(accion)
        cont_modelar += 1

        if anfitrion == "ceiling":
            cont_techo += 1
        elif anfitrion == "muro":
            cont_muro += 1
        else:
            cont_otro_anfitrion += 1

    reporte = {
        "version": "v3",
        "proyecto": mapa.get("proyecto", "RevitElectrico - T5-SantaMarta"),
        "bloque_padre": mapa.get("bloque_padre", ""),
        "nivel": nivel,
        "chip": chip,
        "mapa_origen": str(mapa_path),
        "dispositivos_origen": str(dispositivos_path),
        "altura_cieloraso_m": altura_cieloraso_m,
        "estadisticas": {
            "dispositivos_total": len(dispositivos_internos),
            "a_modelar": cont_modelar,
            "a_saltar_marcador": cont_saltar,
            "sin_mapeo": cont_sin_mapeo,
            "anfitrion_techo": cont_techo,
            "anfitrion_muro": cont_muro,
            "anfitrion_otro": cont_otro_anfitrion,
        },
        "acciones_modelar": acciones_modelar,
        "acciones_saltar": acciones_saltar,
        "acciones_sin_mapeo": acciones_sin_mapeo,
    }

    return reporte


def guardar_reporte(reporte: Dict[str, Any], json_out: Path) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aplica MAPA_BLOQUES_REVIT_v3.json a los dispositivos y "
        "genera el reporte de acciones para Revit 2026."
    )
    parser.add_argument(
        "--mapa",
        type=str,
        required=True,
        help="Ruta a MAPA_BLOQUES_REVIT_v3.json",
    )
    parser.add_argument(
        "--dispositivos",
        type=str,
        required=True,
        help="Ruta a apartamento_F_02_dispositivos.json",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de reporte de salida "
        "(default: data/<chip>_aplicar_mapa_v3.json)",
    )
    parser.add_argument(
        "--chip",
        type=str,
        default=DEFAULT_CHIP,
        help="Identificador del predio/lote (default: SANTAMARTA_T5)",
    )
    parser.add_argument(
        "--nivel",
        type=str,
        default=DEFAULT_NIVEL,
        help="Nivel de Revit para dispositivos de tipo muro (default: Piso 5)",
    )
    parser.add_argument(
        "--altura-cieloraso",
        type=float,
        default=DEFAULT_ALTEZA_CIELORASO_M,
        help="Altura de la cara inferior del cieloraso en metros "
        "(default: 15.82)",
    )

    args = parser.parse_args()

    mapa_path = Path(args.mapa)
    if not mapa_path.exists():
        raise SystemExit("El archivo del mapa no existe: {}".format(mapa_path))

    dispositivos_path = Path(args.dispositivos)
    if not dispositivos_path.exists():
        raise SystemExit(
            "El archivo de dispositivos no existe: {}".format(dispositivos_path)
        )

    chip = args.chip or DEFAULT_CHIP
    if args.json_out:
        json_out = Path(args.json_out)
    else:
        root = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
        json_out = root / "data" / "{}_aplicar_mapa_v3.json".format(chip)

    reporte = aplicar_mapa(
        mapa_path,
        dispositivos_path,
        chip=chip,
        nivel=args.nivel,
        altura_cieloraso_m=args.altura_cieloraso,
    )

    guardar_reporte(reporte, json_out)

    print("=" * 60)
    print("RE_APLICAR_MAPA_V3_v01 — Reporte generado")
    print("=" * 60)
    print("Mapa: {}".format(mapa_path))
    print("Dispositivos: {}".format(dispositivos_path))
    print("Chip: {}".format(chip))
    print("Nivel: {}".format(args.nivel))
    print("Altura cieloraso: {} m".format(args.altura_cieloraso))
    print()
    print("Dispositivos totales: {}".format(reporte["estadisticas"]["dispositivos_total"]))
    print("  A modelar: {}".format(reporte["estadisticas"]["a_modelar"]))
    print("  A saltar (marcador): {}".format(reporte["estadisticas"]["a_saltar_marcador"]))
    print("  Sin mapeo: {}".format(reporte["estadisticas"]["sin_mapeo"]))
    print("  Anfitrion techo: {}".format(reporte["estadisticas"]["anfitrion_techo"]))
    print("  Anfitrion muro: {}".format(reporte["estadisticas"]["anfitrion_muro"]))
    print("  Anfitrion otro: {}".format(reporte["estadisticas"]["anfitrion_otro"]))
    print()
    print("JSON guardado en: {}".format(json_out))


if __name__ == "__main__":
    main()

