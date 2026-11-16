# -*- coding: utf-8 -*-
"""Tests de F0 - sonda del canal de ejecucion (Track T).

La funcion ``listar_pipes`` acepta una raiz parametrizable, de modo que la prueba no
depende de que Windows exponga ``\\\\.\\pipe\\`` ni de que Revit este abierto.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

RAIZ_TEST = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ_TEST / "src" / "fase-0-gobierno" / "RE_F0_SONDA_CANAL_v01.py"
RUTA_FIXTURE = Path(__file__).parent / "fixture_RE_F0_SONDA_CANAL_v01.json"


def cargar_modulo() -> ModuleType:
    """Importa el script de sonda por ruta de archivo."""
    spec = importlib.util.spec_from_file_location("re_f0_sonda_canal", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover - proteccion
        raise ImportError("No se pudo cargar {ruta}".format(ruta=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def sonda() -> ModuleType:
    return cargar_modulo()


@pytest.fixture(scope="module")
def datos_fixture() -> dict:
    with RUTA_FIXTURE.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_listar_pipes_filtra_por_nombre(sonda: ModuleType, tmp_path: Path, datos_fixture: dict) -> None:
    for nombre in datos_fixture["pipes"]["muestra"]:
        (tmp_path / nombre).write_text("", encoding="utf-8")

    encontrados = sonda.listar_pipes(filtro=datos_fixture["pipes"]["filtro"], raiz=str(tmp_path))

    assert encontrados == datos_fixture["pipes"]["esperados"]


def test_listar_pipes_raiz_inexistente_devuelve_vacio(sonda: ModuleType, tmp_path: Path) -> None:
    assert sonda.listar_pipes(raiz=str(tmp_path / "no-existe")) == []


def test_probar_tcp_puerto_cerrado(sonda: ModuleType, datos_fixture: dict) -> None:
    resultado = sonda.probar_tcp(
        host=datos_fixture["tcp"]["host"],
        puerto=datos_fixture["tcp"]["puerto_cerrado"],
        timeout=datos_fixture["tcp"]["timeout_s"],
    )

    assert resultado["responde"] is False
    assert resultado["error"] is not None
    assert resultado["latencia_ms"] is not None


def test_evaluar_sin_canal(sonda: ModuleType, datos_fixture: dict) -> None:
    evaluacion = sonda.evaluar([], {"responde": False})

    assert evaluacion["disponible"] is datos_fixture["esperado"]["disponible_sin_canal"]
    assert evaluacion["modo"] == datos_fixture["esperado"]["modo_sin_canal"]
    assert "runbook" in evaluacion["recomendacion"].lower()


def test_evaluar_solo_pipe(sonda: ModuleType, datos_fixture: dict) -> None:
    evaluacion = sonda.evaluar(datos_fixture["pipes"]["esperados"], {"responde": False})

    assert evaluacion["disponible"] is True
    assert evaluacion["modo"] == datos_fixture["esperado"]["modo_solo_pipe"]


def test_construir_sonda_incluye_no_bloqueante(sonda: ModuleType, datos_fixture: dict) -> None:
    pipes = datos_fixture["pipes"]["esperados"]
    tcp = {"host": "127.0.0.1", "puerto": 19682, "responde": False, "error": "x", "latencia_ms": 1.0}
    datos = sonda.construir_sonda(pipes, tcp, sonda.evaluar(pipes, tcp))

    assert datos["proyecto"] == "RE"
    assert datos["pipes"]["total"] == len(pipes)
    assert "no condiciona" in datos["nota"] or "no bloquea" in datos["nota"]


def test_main_escribe_json_y_no_falla(sonda: ModuleType, tmp_path: Path) -> None:
    salida = tmp_path / "sonda.json"

    codigo = sonda.main(["--salida", str(salida), "--timeout", "0.5"])

    assert codigo == 0
    assert salida.is_file()
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert "evaluacion" in datos
    assert isinstance(datos["evaluacion"]["disponible"], bool)
