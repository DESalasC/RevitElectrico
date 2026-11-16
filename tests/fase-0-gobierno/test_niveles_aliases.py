# -*- coding: utf-8 -*-
"""Validacion de la tabla de identidad de niveles (config/niveles_aliases_v01.json).

Fija dos cosas que se dieron por supuestas y estaban mal:

1. El edificio tiene **21 pisos**, no 19. Los pisos 1, 2, 4 y 19 existen con nombre
   "CLASIFICACION ACABADOS ..." y son datums de piso, no niveles no habitables.
2. La identidad de un nivel se resuelve por **elevacion sobre una grilla** de 3,25 m
   con base 0,22 m, no por el nombre.

Si estas pruebas fallan, cualquier mapeo de niveles de F1 estara mal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[2] / "config" / "niveles_aliases_v01.json"


@pytest.fixture(scope="module")
def datos() -> dict:
    with RUTA.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_archivo_es_utf8_legible() -> None:
    """Regresion del defecto cp1252: el archivo debe abrirse como UTF-8."""
    texto = RUTA.read_bytes().decode("utf-8")
    assert "CLASIFICACIÓN" in texto


def test_regla_de_grilla(datos: dict) -> None:
    assert datos["base_m"] == 0.22
    assert datos["paso_m"] == 3.25


def test_la_grilla_aplica_desde_piso_1(datos: dict) -> None:
    """El sotano (piso 0) esta fuera de la serie; se valida aparte."""
    base = datos["base_m"]
    paso = datos["paso_m"]
    tol = datos["tolerancia_elevacion_m"]

    for nivel in datos["niveles"]:
        piso = nivel["piso"]
        if piso is None or piso < 1:
            continue
        esperado = base + paso * (piso - 1)
        assert abs(nivel["elevacion_m"] - esperado) <= tol, (
            "Nivel {n} (piso {p}): elevacion {e} != {x}".format(
                n=nivel["nombre_modelo"], p=piso, e=nivel["elevacion_m"], x=round(esperado, 3)
            )
        )


def test_sotano_fuera_de_la_serie(datos: dict) -> None:
    sotano = next(n for n in datos["niveles"] if n["tipo"] == "sotano")
    assert sotano["piso"] == 0
    assert sotano["elevacion_m"] == -1.08


def test_los_21_pisos_existen_una_sola_vez(datos: dict) -> None:
    pisos = [n["piso"] for n in datos["niveles"] if n["piso"] is not None and n["piso"] >= 1]
    assert sorted(pisos) == list(range(1, 22))


def test_niveles_de_acabados_son_pisos_reales(datos: dict) -> None:
    """Correccion del operador: los nombres de acabados son datums de piso."""
    acabados = {n["piso"] for n in datos["niveles"] if n["tipo"] == "acabados"}
    assert acabados == {1, 2, 4, 19}


def test_piso_4_es_el_nivel_de_acabados_4_18(datos: dict) -> None:
    nivel = next(n for n in datos["niveles"] if n["piso"] == 4)
    assert nivel["nombre_modelo"] == "CLASIFICACIÓN ACABADOS MAMPOSTERIA PISO 4-18"
    assert nivel["elevacion_m"] == 9.97


def test_piso_5_mantiene_la_elevacion_del_proyecto(datos: dict) -> None:
    nivel = next(n for n in datos["niveles"] if n["piso"] == 5)
    assert nivel["nombre_modelo"] == "Piso 5"
    assert nivel["elevacion_m"] == 13.22


def test_cubierta_y_sobrecubierta_no_son_pisos(datos: dict) -> None:
    for nombre in ("Cubierta", "SobreCubierta"):
        nivel = next(n for n in datos["niveles"] if n["nombre_modelo"] == nombre)
        assert nivel["piso"] is None
        assert nivel["tipo"] == "cubierta"
