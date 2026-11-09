"""
================================================================================
RE2_MAPEO_BLOQUES_v01.py — Mapeo de bloques DXF a familias de Revit 2026
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 Standalone (NO Revit, NO Grasshopper)
================================================================================

OBJETIVO:
  Leer el JSON normalizado de RE1 (bloques INSERT con nombre, capa, punto
  insert reubicado) y mapear cada bloque a una familia de Revit 2026, con
  categoría, altura de instalación default, indicador de si se modela o no,
  y si es código de conductores (marcador, no dispositivo).

  También clasifica bloques basura (nombres aleatorios) y bloques a descartar
  (anotaciones, otros sistemas, símbolos de apartamento, marcadores no
  dispositivos).

ENTRADAS (CLI):
  --json-in   : ruta al JSON de salida de RE1_NORMALIZA_DXF_v01.py
  --json-out  : ruta del JSON de salida (default: data/<chip>_mapeo_bloques.json)
  --chip      : identificador del predio/lote (default: SANTAMARTA_T5)

SALIDA:
  JSON con:
    - metadatos (chip, origen, total de bloques leídos)
    - resumen (conteos por categoría: modelar, descartar, basura, conductores)
    - mapeo: lista de {nombre_bloque, categoria, familia_revit, altura_default_m,
                    modelar, es_codigo_conductores, capas, instancias}
    - bloques_detalle: cada bloque INSERT individual con su mapeo aplicado

HISTORIAL:
  v01.0 (2026-10-21) — versión inicial. Mapeo bloque → familia Revit.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CHIP = "SANTAMARTA_T5"

# ---------------------------------------------------------------------------
# Tabla conductores -> diametro de Conduit (según norma eléctrica)
# Rangos: (min_conductores, max_conductores, diametro_pulgadas, diametro_mm)
# ---------------------------------------------------------------------------

DIAMETRO_CONDUIT_POR_CONDUCTORES = (
    (1, 2, "3/4\"", 20),
    (3, 4, "1\"", 25),
    (5, 6, "1-1/4\"", 32),
    (7, 8, "1-1/2\"", 40),
    (9, 12, "2\"", 50),
)


def _diametro_conduit_por_conductores(n_conductores: int) -> Dict[str, Any]:
    """
    Devuelve el diametro de Conduit recomendado para una cantidad de conductores.
    Retorna dict con claves: conductores, diametro_pulgadas, diametro_mm.
    Si n_conductores esta fuera de los rangos definidos, retorna el mayor disponible.
    """
    n = int(n_conductores)
    for min_c, max_c, pulgadas, mm in DIAMETRO_CONDUIT_POR_CONDUCTORES:
        if min_c <= n <= max_c:
            return {
                "conductores": n,
                "diametro_pulgadas": pulgadas,
                "diametro_mm": mm,
            }
    # Fuera de rango: usar el mayor diametro disponible
    ultimo = DIAMETRO_CONDUIT_POR_CONDUCTORES[-1]
    return {
        "conductores": n,
        "diametro_pulgadas": ultimo[2],
        "diametro_mm": ultimo[3],
    }


# ---------------------------------------------------------------------------
# Mapeo maestro: nombre de bloque DXF -> entrada de familia Revit 2026
# Basado en el diagnóstico DXF final (bloques eléctricos identificados) y
# en STM-T4-P4_mapeo_bloques_revit.json (3.-Proceso).
# ---------------------------------------------------------------------------

MAPEO_BLOQUES_REVIT: Dict[str, Dict[str, Any]] = {
    # --- Luminarias (modelar) ---
    "Bala Stil Led 12W": {
        "categoria": "Luminarias",
        "familia_revit": "M_Foco empotrado - Redondo - LED.rfa",
        "altura_default_m": 2.65,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Luminaria tipo bala LED de techo",
    },
    "Bala Stil Led 16W": {
        "categoria": "Luminarias",
        "familia_revit": "M_Foco empotrado - Redondo - LED.rfa",
        "altura_default_m": 2.65,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Luminaria tipo bala LED 16W de techo",
    },
    "HERMETICA 40W": {
        "categoria": "Luminarias",
        "familia_revit": "M_Luz de techo - Redondo plano.rfa",
        "altura_default_m": 2.65,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Luminaria hermética 40W de techo",
    },
    "ELEC-LAF EMERG BAT LED": {
        "categoria": "Luminarias",
        "familia_revit": "M_Aplique de emergencia.rfa",
        "altura_default_m": 2.65,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Luminaria de emergencia con batería LED",
    },
    "1FTN": {
        "categoria": "Marcador de conductores",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": True,
        "nota": "Define cantidad de conductores del tubo; NO se modela como dispositivo.",
        "conductores": 3,
    },
    "1FTNR": {
        "categoria": "Marcador de conductores",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": True,
        "nota": "Define cantidad de conductores del tubo; NO se modela como dispositivo.",
        "conductores": 4,
    },
    # --- Dispositivos eléctricos (modelar) ---
    "Paneles": {
        "categoria": "Tableros eléctricos",
        "familia_revit": "M_Tablero eléctrico.rfa",
        "altura_default_m": 1.4,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Tablero eléctrico",
    },
    "tablero": {
        "categoria": "Tableros eléctricos",
        "familia_revit": "M_Tablero eléctrico.rfa",
        "altura_default_m": 1.4,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Tablero eléctrico",
    },
    "Paneles Solares 550W": {
        "categoria": "Energía solar",
        "familia_revit": "M_Panel solar 550W.rfa",
        "altura_default_m": 2.65,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Panel solar 550W",
    },
    "ELEC-I-S-1-5A": {
        "categoria": "Dispositivos eléctricos",
        "familia_revit": "M_Interruptor-Simple.rfa",
        "altura_default_m": 1.1,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Interruptor simple 1x 5A",
    },
    "ELEC-T-D-t-15A": {
        "categoria": "Dispositivos eléctricos",
        "familia_revit": "M_Toma-Doble.rfa",
        "altura_default_m": 0.3,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Toma doble 15A",
    },
    "SS-Sensor Proximidad": {
        "categoria": "Dispositivos eléctricos",
        "familia_revit": "M_Sensor de ocupación de techo - Voltaje normal.rfa",
        "altura_default_m": 2.65,
        "modelar": True,
        "es_codigo_conductores": False,
        "nota": "Sensor de proximidad/ocupación",
    },
    # --- Marcadores de conductores (NO modelar, son códigos) ---
    "1FTR": {
        "categoria": "Marcador de conductores",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": True,
        "nota": "Define cantidad de conductores del tubo; NO se modela como dispositivo.",
        "conductores": 3,
    },
    "1TNR": {
        "categoria": "Marcador de conductores",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": True,
        "nota": "Define cantidad de conductores del tubo; NO se modela como dispositivo.",
        "conductores": 3,
    },
    "2FT2N": {
        "categoria": "Marcador de conductores",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": True,
        "nota": "Define cantidad de conductores del tubo; NO se modela como dispositivo.",
        "conductores": 5,
    },
    "2F2N1T1R": {
        "categoria": "Marcador de conductores",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": True,
        "nota": "Define cantidad de conductores del tubo; NO se modela como dispositivo.",
        "conductores": 6,
    },
    # --- Dispositivos de datos (modelar solo si se requiere coordinación) ---
    "TDT B-16": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT C-11": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT D-12": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-05": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-06": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-07": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-08": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-09": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-10": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-19": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-20": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT E-21": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT F-01": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT F-02": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT F-03": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT F-04": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT F-13": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT F-17": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT-B15": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT-F14": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    "TDT-F18": {
        "categoria": "Dispositivos de datos",
        "familia_revit": "M_Toma-Comunicaciones.rfa",
        "altura_default_m": 0.3,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Caja TDT de apartamento. Fuera del alcance eléctrico.",
    },
    # --- Marcadores de unidad / sistema (NO modelar) ---
    "Apartamento Tipo F 17 y 03": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamentos Tipo F 18 y 04": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo B 15": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo B 16": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo C 11": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo D 12": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo E 06": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo E 07": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo E 08": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo E 20": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo E2 19": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo E2 21": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo F 01": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamento Tipo F 13": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamentos Tipo E 09": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apartamentos Tipo F 14": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apatamento Tipo E 05": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apatamento Tipo F 02": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    "Apatamentos Tipo E 10": {
        "categoria": "Marcador de unidad",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Símbolo de apartamento. No modelar.",
    },
    # --- Marcadores no dispositivos ---
    "ELEC-SUBEELEC": {
        "categoria": "Marcador",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Marcador de subida eléctrica (riser). No es dispositivo.",
    },
    "Acometidas Electricas Piso 2": {
        "categoria": "Marcador",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Marcador de acometida. No es dispositivo.",
    },
    "Acometidas Aire Piso 2-5": {
        "categoria": "Marcador",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Marcador de acometida de aire. No es dispositivo.",
    },
}


def _entrada_por_defecto(nombre_bloque: str) -> Dict[str, Any]:
    """Devuelve la entrada default para un bloque no mapeado explicitamente."""
    return {
        "categoria": "Por definir",
        "familia_revit": None,
        "altura_default_m": None,
        "modelar": False,
        "es_codigo_conductores": False,
        "nota": "Bloque no mapeado; revisar manualmente.",
    }


def mapear_bloques(
    json_in: Path,
    json_out: Path,
    chip: str = DEFAULT_CHIP,
) -> Dict[str, Any]:
    """
    Lee el JSON normalizado de RE1, mapea cada bloque INSERT a una familia
    de Revit y escribe el JSON de mapeo en disco. Devuelve el diccionario
    de salida (también escrito en disco).
    """
    with open(json_in, "r", encoding="utf-8") as f:
        datos_entrada = json.load(f)

    bloques_entrada: List[Dict[str, Any]] = datos_entrada.get("bloques", [])

    mapeo: List[Dict[str, Any]] = []
    bloques_detalle: List[Dict[str, Any]] = []

    cont_modelar = 0
    cont_descartar = 0
    cont_basura = 0
    cont_conductores = 0
    cont_sin_mapear = 0

    # Contador de instancias por nombre de bloque
    instancias_por_bloque: Dict[str, int] = {}
    capas_por_bloque: Dict[str, set] = {}

    for bloque in bloques_entrada:
        nombre = bloque.get("nombre_bloque", "")
        capa = bloque.get("capa", "")
        punto_insert = bloque.get("punto_insert", [])

        # Contar instancias y capas por nombre
        instancias_por_bloque[nombre] = instancias_por_bloque.get(nombre, 0) + 1
        if nombre not in capas_por_bloque:
            capas_por_bloque[nombre] = set()
        capas_por_bloque[nombre].add(capa)

        # Determinar si el nombre es basura (misma heurística que RE1)
        es_basura = _es_nombre_basura(nombre)

        if es_basura:
            entrada = {
                "categoria": "Basura",
                "familia_revit": None,
                "altura_default_m": None,
                "modelar": False,
                "es_codigo_conductores": False,
                "nota": "Nombre de bloque basura; filtrar.",
            }
            cont_basura += 1
        else:
            entrada = MAPEO_BLOQUES_REVIT.get(
                nombre, _entrada_por_defecto(nombre)
            )
            if entrada["familia_revit"] is None and not entrada["modelar"]:
                # No es basura pero tampoco se mapeó a algo modelable
                cont_sin_mapear += 1

        if entrada["es_codigo_conductores"]:
            cont_conductores += 1
        elif entrada["modelar"]:
            cont_modelar += 1
        else:
            cont_descartar += 1

        # Entrada consolidada de mapeo (por nombre de bloque, única)
        entrada_mapeo = {
            "nombre_bloque": nombre,
            "categoria": entrada["categoria"],
            "familia_revit": entrada["familia_revit"],
            "altura_default_m": entrada["altura_default_m"],
            "modelar": entrada["modelar"],
            "es_codigo_conductores": entrada["es_codigo_conductores"],
            "instancias": instancias_por_bloque[nombre],
            "capas": sorted(capas_por_bloque[nombre]),
            "nota": entrada.get("nota", ""),
        }
        if "conductores" in entrada:
            entrada_mapeo["conductores"] = entrada["conductores"]
            diametro = _diametro_conduit_por_conductores(entrada["conductores"])
            entrada_mapeo["diametro_conduit_pulgadas"] = diametro["diametro_pulgadas"]
            entrada_mapeo["diametro_conduit_mm"] = diametro["diametro_mm"]

        # Evitar duplicados en la lista de mapeo (uno por nombre de bloque)
        if not any(m["nombre_bloque"] == nombre for m in mapeo):
            mapeo.append(entrada_mapeo)

        # Detalle de cada bloque INSERT individual
        bloque_detalle = {
            "nombre_bloque": nombre,
            "capa": capa,
            "punto_insert": punto_insert,
            "categoria": entrada["categoria"],
            "familia_revit": entrada["familia_revit"],
            "altura_default_m": entrada["altura_default_m"],
            "modelar": entrada["modelar"],
            "es_codigo_conductores": entrada["es_codigo_conductores"],
            "es_basura": es_basura,
            "nota": entrada.get("nota", ""),
        }
        bloques_detalle.append(bloque_detalle)

    salida = {
        "metadatos": {
            "chip": chip,
            "origen_json_in": str(json_in),
            "total_bloques_leidos": len(bloques_entrada),
            "version": "v01.0",
        },
        "resumen": {
            "bloques_distintos": len(mapeo),
            "instancias_total": len(bloques_detalle),
            "instancias_a_modelar": cont_modelar,
            "instancias_descartar": cont_descartar,
            "instancias_basura": cont_basura,
            "instancias_codigo_conductores": cont_conductores,
            "bloques_sin_mapear": cont_sin_mapear,
        },
        "mapeo": mapeo,
        "bloques_detalle": bloques_detalle,
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    return salida


def _es_nombre_basura(nombre: str) -> bool:
    """Devuelve True si el nombre del bloque es basura (debe filtrarse)."""
    n = (nombre or "").strip()
    if not n:
        return True
    # Nombres basura conocidos del diagnóstico
    nombres_basura = (
        "sadfasdggfjhkkl",
        "ghghgh",
        "sdgsdsg",
        "sdfsdgjgfd",
        "dsfgsh",
        "sifon",
        "FRE",
        "A$C74C362D2",
        "A$C0F1C539B",
        "*U776",
        "ASDFASGGDSF",
        "adsfasdggfdjh",
        "asdfah",
        "asdfashj",
        "dsfgfhfj",
        "fdfgfghgjfhkj",
        "sadfadsgfsdhj",
        "sadfasdfghfj",
        "sdfsdsfhd",
        "SADFASG",
        "SETI",
        "COTAS T4",
        "Comunicaciones ZC Pisos 2-5",
        "Deteccion de Incendio Piso 4",
    )
    if n in nombres_basura:
        return True
    import re

    # Nombres alfanuméricos aleatorios (basura típica de CAD)
    if re.fullmatch(r"[A-Za-z0-9$]{6,}", n) and not n.isalnum():
        return True
    if len(n) >= 10 and re.fullmatch(r"[a-z]{6,}", n):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mapea bloques DXF a familias de Revit 2026 (RevitElectrico)."
    )
    parser.add_argument(
        "--json-in", type=str, required=True, help="Ruta al JSON de RE1 (entrada)"
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de salida (default: data/<chip>_mapeo_bloques.json)",
    )
    parser.add_argument(
        "--chip",
        type=str,
        default=DEFAULT_CHIP,
        help="Identificador del predio/lote (default: SANTAMARTA_T5)",
    )

    args = parser.parse_args()

    json_in = Path(args.json_in)
    if not json_in.exists():
        raise SystemExit(f"El archivo JSON de entrada no existe: {json_in}")

    chip = args.chip or DEFAULT_CHIP
    if args.json_out:
        json_out = Path(args.json_out)
    else:
        root = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
        json_out = root / "data" / f"{chip}_mapeo_bloques.json"

    resultado = mapear_bloques(json_in, json_out, chip)

    print("=== Mapeo de bloques a Revit completado ===")
    print(f"Origen: {resultado['metadatos']['origen_json_in']}")
    print(f"Chip: {resultado['metadatos']['chip']}")
    print(f"Bloques leídos: {resultado['metadatos']['total_bloques_leidos']}")
    print(f"Bloques distintos mapeados: {resultado['resumen']['bloques_distintos']}")
    print(f"Instancias totales: {resultado['resumen']['instancias_total']}")
    print(f"  A modelar: {resultado['resumen']['instancias_a_modelar']}")
    print(f"  A descartar: {resultado['resumen']['instancias_descartar']}")
    print(f"  Basura: {resultado['resumen']['instancias_basura']}")
    print(f"  Código conductores: {resultado['resumen']['instancias_codigo_conductores']}")
    print(f"JSON guardado en: {json_out}")


def generar_tramos_conduit(
    resultado_mapeo: Dict[str, Any],
    json_out: Path,
    chip: str = DEFAULT_CHIP,
) -> Dict[str, Any]:
    """
    A partir del resultado de mapear_bloques, genera una lista de tramos de
    Conduit para los bloques marcadores de conductores (es_codigo_conductores).
    Cada tramo incluye: nombre_bloque, punto (del primer detalle), conductores,
    diametro_pulgadas, diametro_mm, tramo_id.
    """
    mapeo = resultado_mapeo.get("mapeo", [])
    bloques_detalle = resultado_mapeo.get("bloques_detalle", [])

    # Indexar el primer punto de detalle por nombre de bloque
    punto_por_bloque: Dict[str, List[float]] = {}
    for detalle in bloques_detalle:
        nombre = detalle.get("nombre_bloque", "")
        if nombre not in punto_por_bloque and detalle.get("punto_insert"):
            punto_por_bloque[nombre] = detalle["punto_insert"]

    tramos: List[Dict[str, Any]] = []
    for entrada in mapeo:
        if not entrada.get("es_codigo_conductores"):
            continue
        nombre = entrada["nombre_bloque"]
        conductores = entrada.get("conductores")
        if conductores is None:
            continue
        diametro = _diametro_conduit_por_conductores(conductores)
        tramo = {
            "tramo_id": f"CONDUIT-{nombre}",
            "nombre_bloque": nombre,
            "punto": punto_por_bloque.get(nombre, [0.0, 0.0, 0.0]),
            "conductores": conductores,
            "diametro_pulgadas": diametro["diametro_pulgadas"],
            "diametro_mm": diametro["diametro_mm"],
        }
        tramos.append(tramo)

    salida = {
        "chip": chip,
        "origen": "RE2_MAPEO_BLOQUES_v01.generar_tramos_conduit",
        "resumen": {
            "tramos_total": len(tramos),
        },
        "tramos": tramos,
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    return salida


if __name__ == "__main__":
    main()

