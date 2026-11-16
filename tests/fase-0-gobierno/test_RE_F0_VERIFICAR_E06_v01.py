# -*- coding: utf-8 -*-
"""Test estatico de F0 - verificador de E06 (IronPython 2.7).

No puede ejecutarse contra la API de Revit desde CPython, asi que se valida por
analisis estatico del codigo fuente. Esto no demuestra que funcione en Revit, pero
si impide las cuatro regresiones que han costado sesiones:

1. sintaxis invalida,
2. f-strings (no existen en IronPython 2.7),
3. anotaciones de tipo (no soportadas),
4. apertura de transacciones (el verificador debe ser de solo lectura),
5. rutas absolutas de usuario.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RUTA_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "fase-6-revit"
    / "RE_F0_VERIFICAR_E06_v01.py"
)


@pytest.fixture(scope="module")
def fuente() -> str:
    return RUTA_SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def arbol(fuente: str) -> ast.Module:
    return ast.parse(fuente)


def test_script_existe() -> None:
    assert RUTA_SCRIPT.is_file()


def test_sintaxis_valida(arbol: ast.Module) -> None:
    assert isinstance(arbol, ast.Module)
    assert len(arbol.body) > 0


def test_sin_fstrings(arbol: ast.Module) -> None:
    fstrings = [n for n in ast.walk(arbol) if isinstance(n, ast.JoinedStr)]
    assert fstrings == [], "IronPython 2.7 no soporta f-strings"


def test_sin_anotaciones_de_tipo(arbol: ast.Module) -> None:
    con_anotacion = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef):
            if nodo.returns is not None:
                con_anotacion.append(nodo.name)
            for arg in list(nodo.args.args) + list(nodo.args.kwonlyargs):
                if arg.annotation is not None:
                    con_anotacion.append(nodo.name)
    assert con_anotacion == [], "IronPython 2.7 no soporta anotaciones: {0}".format(con_anotacion)


def test_solo_lectura_sin_transacciones(fuente: str) -> None:
    assert "Transaction(doc" not in fuente
    assert "Transaction( doc" not in fuente


def test_declara_funcion_y_lote(fuente: str) -> None:
    assert "def verificar_e06(" in fuente
    assert "46c3f138-025d-47d4-b24a-41cd21181a58" in fuente


def test_veredictos_acotados(fuente: str) -> None:
    for veredicto in ("conservar", "descartar", "revisar", "no_encontrado"):
        assert veredicto in fuente


def test_sin_rutas_absolutas_de_usuario(fuente: str) -> None:
    assert "C:\\Users" not in fuente
    assert "D:\\Users" not in fuente


def test_usa_variable_de_entorno(fuente: str) -> None:
    assert "REVITELECTRICO_ROOT" in fuente
