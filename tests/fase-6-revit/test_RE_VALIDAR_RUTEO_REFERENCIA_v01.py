# -*- coding: utf-8 -*-
"""Tests de la validacion del ruteo de referencia (V02-f)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ / "src" / "fase-6-revit" / "RE_VALIDAR_RUTEO_REFERENCIA_v01.py"


def cargar_modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("re_validar_ruteo", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("No se pudo cargar {r}".format(r=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = cargar_modulo()

CONDUITS = [
    {"id": 1, "servicio": "TOMAS", "diam_mm": 21.0, "long_mm": 1000.0,
     "a": [0, 0, 14200], "b": [1000, 0, 14200]},
    {"id": 2, "servicio": "", "diam_mm": 27.0, "long_mm": 500.0,
     "a": [1000, 0, 14200], "b": [1500, 0, 14200]},
    {"id": 3, "servicio": "", "diam_mm": 27.0, "long_mm": 700.0,
     "a": [0, 0, 288220], "b": [700, 0, 288220]},
]
DISPOSITIVOS = [
    {"id": 10, "x": 0, "y": 0, "z": 14200},
    {"id": 11, "x": 1500, "y": 0, "z": 14200},
    {"id": 12, "x": 9000, "y": 9000, "z": 14200},
    {"id": 13, "x": 0, "y": 0, "z": 28924},
]


def test_detecta_tramos_fuera_de_rango():
    informe = MOD.validar(DISPOSITIVOS, CONDUITS)
    assert informe["tramos_total"] == 3
    assert informe["tramos_validos"] == 2
    assert informe["tramos_fuera_de_rango"] == [3]
    assert informe["longitud_valida_m"] == 1.5
    assert informe["longitud_total_m"] == 2.2


def test_resume_servicio_y_diametro():
    informe = MOD.validar(DISPOSITIVOS, CONDUITS)
    assert informe["por_servicio"] == {"(vacio)": 1, "TOMAS": 1}
    assert informe["por_diametro_mm"] == {21: 1, 27: 1}
    assert informe["tramos_sin_servicio"] == [2]


def test_conexion_de_aparatos():
    informe = MOD.validar(DISPOSITIVOS, CONDUITS)
    # 10 y 11 tocan extremos; 12 esta lejos y 13 esta fuera de rango.
    assert informe["dispositivos_con_conexion"] == 2
    assert informe["dispositivos_sin_conexion"] == [12]


def test_esta_fuera_de_rango():
    assert MOD.esta_fuera_de_rango([0, 0, 288220])
    assert not MOD.esta_fuera_de_rango([14000, 10000, 14200])
    assert MOD.esta_fuera_de_rango([218384, 251269, 14200])
