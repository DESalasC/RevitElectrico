# -*- coding: utf-8 -*-
"""Contrato de nomenclatura: el mapeo de colocacion debe existir en CENTRAL-V01.

Decision del operador (2026-11-15): las familias y tipos validos son los de
`STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt`, la ultima version disponible.

Este test extrae `MAPEO_DEFAULT` del script de colocacion (sin ejecutarlo, que
importaria clr) y comprueba cada entrada contra el catalogo levantado por MCP.
Si una entrada usa una familia o un tipo inexistente, falla aqui y no en Revit a
mitad de una colocacion.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "src" / "fase-6-revit" / "RE_COLOCAR_DISPOSITIVOS_generico.py"
CATALOGO = RAIZ / "config" / "catalogo_familias_CENTRAL_V01_v01.json"

# Entradas conocidas como no resolubles. Vacio: ELEC-EXT se resolvio el 2026-11-15
# como EA | EA 1010 por decision del operador. El mecanismo se conserva para futuros
# desajustes: una entrada aqui debe acompanarse de su motivo y de la decision pendiente.
PENDIENTES_CONOCIDOS: dict[str, str] = {}


def cargar_mapeo() -> dict:
    """Lee MAPEO_DEFAULT del fuente sin importar el modulo."""
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if not isinstance(nodo, ast.Assign):
            continue
        for objetivo in nodo.targets:
            if isinstance(objetivo, ast.Name) and objetivo.id == "MAPEO_DEFAULT":
                return ast.literal_eval(nodo.value)
    raise AssertionError("No se encontro MAPEO_DEFAULT en {ruta}".format(ruta=SCRIPT))


@pytest.fixture(scope="module")
def catalogo() -> dict:
    with CATALOGO.open(encoding="utf-8") as fh:
        datos = json.load(fh)
    return {
        "familias": {f["familia"] for f in datos["familias"]},
        "tipos": {(f["familia"], f["tipo"]) for f in datos["familias"]},
        "detalle": datos["familias"],
    }


@pytest.fixture(scope="module")
def mapeo() -> dict:
    return cargar_mapeo()


CODIGOS = sorted(cargar_mapeo())


def test_catalogo_sin_duplicados(catalogo: dict) -> None:
    assert len(catalogo["tipos"]) == len(catalogo["detalle"])


def test_catalogo_declara_sus_familias(catalogo: dict) -> None:
    assert "EA" in catalogo["familias"]
    assert "M_Iluminacion" in catalogo["familias"]
    assert "M_Toma doble" in catalogo["familias"]


@pytest.mark.parametrize("codigo", CODIGOS)
def test_mapeo_resuelve_en_catalogo(codigo: str, mapeo: dict, catalogo: dict, request: pytest.FixtureRequest) -> None:
    entrada = mapeo[codigo]
    familia, tipo = entrada if isinstance(entrada, tuple) else (entrada, None)

    if codigo in PENDIENTES_CONOCIDOS:
        request.node.add_marker(
            pytest.mark.xfail(strict=True, reason=PENDIENTES_CONOCIDOS[codigo])
        )

    assert familia in catalogo["familias"], (
        "{c}: la familia '{f}' no existe en CENTRAL-V01".format(c=codigo, f=familia)
    )
    if tipo is not None:
        assert (familia, tipo) in catalogo["tipos"], (
            "{c}: el tipo '{t}' no existe en la familia '{f}' de CENTRAL-V01".format(
                c=codigo, t=tipo, f=familia
            )
        )


def cargar_delta_rotacion() -> dict:
    """Lee DELTA_ROT_POR_FAMILIA del fuente sin importar el modulo."""
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if not isinstance(nodo, ast.Assign):
            continue
        for objetivo in nodo.targets:
            if isinstance(objetivo, ast.Name) and objetivo.id == "DELTA_ROT_POR_FAMILIA":
                return ast.literal_eval(nodo.value)
    raise AssertionError("No se encontro DELTA_ROT_POR_FAMILIA")


def test_delta_de_rotacion_para_tomas_horizontal(catalogo: dict) -> None:
    """En Colombia las tomas van con la placa horizontal; la familia esta vertical."""
    deltas = cargar_delta_rotacion()

    assert deltas.get("M_Toma doble") == 90.0
    for familia in deltas:
        assert familia in catalogo["familias"], (
            "delta definido para una familia inexistente: {f}".format(f=familia)
        )


def test_delta_solo_afecta_a_las_familias_declaradas(catalogo: dict) -> None:
    deltas = cargar_delta_rotacion()
    assert set(deltas) == {"M_Toma doble"}


def test_todos_los_codigos_tienen_entrada(mapeo: dict) -> None:
    assert len(mapeo) == 16
    for codigo, entrada in mapeo.items():
        assert isinstance(entrada, tuple) and len(entrada) == 2, (
            "{c} deberia ser (familia, tipo)".format(c=codigo)
        )
