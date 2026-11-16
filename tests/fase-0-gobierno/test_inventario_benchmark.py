# -*- coding: utf-8 -*-
"""Validacion del inventario electrico del benchmark.

El inventario se levanto por MCP y por el censo IronPython, y se corrigio a mano donde
las fuentes discrepaban. Estas pruebas fijan los hechos que importan para F1:

* el total cuadra con el censo (175 electricas + 3 extractores),
* ninguna familia sin muestra suficiente queda marcada como minable,
* `M_Interruptores` esta cargada pero sin instancias (no se puede minar),
* `EA` vive en categoria mecanica, no electrica (el censo por nombre la perdia).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RUTA = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "referencia"
    / "inventario_electrico_benchmark_v01.json"
)

MINIMO_MUESTRAS = 3


@pytest.fixture(scope="module")
def datos() -> dict:
    with RUTA.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def familias(datos: dict) -> dict:
    return {f["familia"]: f for f in datos["familias"]}


def test_archivo_utf8_y_sin_filas_de_control() -> None:
    texto = RUTA.read_bytes().decode("utf-8")
    assert "ver M_Interruptores de iluminacion" not in texto


def test_total_de_instancias_cuadra(datos: dict, familias: dict) -> None:
    suma = sum(f["instancias"] for f in familias.values())
    assert suma == datos["totales"]["electricas_mas_extractores"] == 178


def test_conteo_por_tipo_cuadra_con_instancias(familias: dict) -> None:
    for nombre, familia in familias.items():
        suma_tipos = sum(familia["tipos_con_instancias"].values())
        assert suma_tipos == familia["instancias"], (
            "{n}: tipos suman {s} pero instancias dice {i}".format(
                n=nombre, s=suma_tipos, i=familia["instancias"]
            )
        )


def test_minable_exige_muestra_suficiente(familias: dict) -> None:
    for nombre, familia in familias.items():
        if familia["minable_F1"]:
            assert familia["instancias"] >= MINIMO_MUESTRAS, (
                "{n} marcada minable con {i} muestras".format(n=nombre, i=familia["instancias"])
            )


def test_interruptores_cargados_sin_instancias(familias: dict) -> None:
    interruptores = familias["M_Interruptores"]
    assert interruptores["instancias"] == 0
    assert len(interruptores["tipos_cargados"]) == 7
    assert interruptores["minable_F1"] is False


def test_ea_es_categoria_mecanica(familias: dict) -> None:
    ea = familias["EA"]
    assert ea["categoria"] == "Mechanical Equipment"
    assert ea["instancias"] == 3
    assert ea["minable_F1"] is True


def test_iluminacion_con_tres_tipos_distintos(familias: dict) -> None:
    iluminacion = familias["M_Iluminacion"]
    assert iluminacion["instancias"] == 18
    assert set(iluminacion["tipos_con_instancias"]) == {
        "SONO FLEX 10 trim",
        "SONO FLEX 13 trim",
        "SONO FLEX 22 trim",
    }


def test_conduits_suman_el_total(datos: dict) -> None:
    assert sum(c["n"] for c in datos["conduits_por_tipo"]) == datos["totales"]["conduits"] == 147
