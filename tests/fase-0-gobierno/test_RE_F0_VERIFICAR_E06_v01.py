# -*- coding: utf-8 -*-
"""Test estatico de F0 - scripts IronPython de verificacion (Revit).

No pueden ejecutarse contra la API de Revit desde CPython, asi que se validan por
analisis estatico del codigo fuente. No demuestra que funcionen en Revit, pero
impide las regresiones que ya han costado sesiones:

1. sintaxis invalida,
2. f-strings (no existen en IronPython 2.7),
3. anotaciones de tipo,
4. apertura de transacciones (deben ser de solo lectura),
5. rutas absolutas de usuario.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2] / "src" / "fase-6-revit"

SCRIPTS = {
    "censo_benchmark": RAIZ / "RE_F0_CENSO_BENCHMARK_v01.py",
    "verificador_guid": RAIZ / "RE_F0_VERIFICAR_E06_v01.py",
    "verificador_uniqueid": RAIZ / "RE_F0_VERIFICAR_E06_v02.py",
}


@pytest.fixture(scope="module", params=sorted(SCRIPTS), ids=sorted(SCRIPTS))
def script(request: pytest.FixtureRequest) -> tuple[str, str, ast.Module]:
    nombre = request.param
    fuente = SCRIPTS[nombre].read_text(encoding="utf-8")
    return nombre, fuente, ast.parse(fuente)


def test_script_existe(script: tuple[str, str, ast.Module]) -> None:
    assert SCRIPTS[script[0]].is_file()


def test_sintaxis_valida(script: tuple[str, str, ast.Module]) -> None:
    _, _, arbol = script
    assert isinstance(arbol, ast.Module)
    assert len(arbol.body) > 0


def test_sin_fstrings(script: tuple[str, str, ast.Module]) -> None:
    _, _, arbol = script
    assert [n for n in ast.walk(arbol) if isinstance(n, ast.JoinedStr)] == []


def test_sin_anotaciones_de_tipo(script: tuple[str, str, ast.Module]) -> None:
    _, _, arbol = script
    con_anotacion = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef):
            if nodo.returns is not None:
                con_anotacion.append(nodo.name)
            for arg in list(nodo.args.args) + list(nodo.args.kwonlyargs):
                if arg.annotation is not None:
                    con_anotacion.append(nodo.name)
    assert con_anotacion == [], "IronPython 2.7 no soporta anotaciones: {0}".format(con_anotacion)


def test_solo_lectura_sin_transacciones(script: tuple[str, str, ast.Module]) -> None:
    _, fuente, _ = script
    assert "Transaction(doc" not in fuente


def test_sin_rutas_absolutas_de_usuario(script: tuple[str, str, ast.Module]) -> None:
    _, fuente, _ = script
    assert "C:\\Users" not in fuente
    assert "D:\\Users" not in fuente


def test_usa_variable_de_entorno(script: tuple[str, str, ast.Module]) -> None:
    _, fuente, _ = script
    assert "REVITELECTRICO_ROOT" in fuente


def test_verificador_guid_declara_funcion_y_lote() -> None:
    fuente = SCRIPTS["verificador_guid"].read_text(encoding="utf-8")
    assert "def verificar_e06(" in fuente
    assert "46c3f138-025d-47d4-b24a-41cd21181a58" in fuente


def test_verificador_guid_veredictos_acotados() -> None:
    fuente = SCRIPTS["verificador_guid"].read_text(encoding="utf-8")
    for veredicto in ("conservar", "descartar", "revisar", "no_encontrado"):
        assert veredicto in fuente


def test_verificador_uniqueid_usa_uid_y_veredictos() -> None:
    fuente = SCRIPTS["verificador_uniqueid"].read_text(encoding="utf-8")
    assert "def verificar_e06_por_uniqueid(" in fuente
    assert "unique_id" in fuente
    for veredicto in ("no_persistido", "persistido", "parcial", "sin_datos"):
        assert veredicto in fuente


def test_censo_declara_bloques_y_veredictos() -> None:
    fuente = SCRIPTS["censo_benchmark"].read_text(encoding="utf-8")
    assert "def censo_benchmark(" in fuente
    assert "OST_Conduit" in fuente
    assert "IsModified" in fuente
    for veredicto in ("con_ruteo", "sin_ruteo", "sin_electricas", "vacio"):
        assert veredicto in fuente
