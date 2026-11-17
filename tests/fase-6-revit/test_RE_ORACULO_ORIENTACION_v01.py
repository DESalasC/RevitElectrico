# -*- coding: utf-8 -*-
"""Tests del oraculo de orientacion (RE-P-060).

El fixture son las 36 mediciones reales de E 06 en CENTRAL-V01. La prueba de
fuego es que el oraculo declare sano el apartamento de referencia: si E 06
saliera con volteados, la regla estaria mal derivada.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ / "src" / "fase-6-revit" / "RE_ORACULO_ORIENTACION_v01.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "oraculo_orientacion_E06_v01.json"


def cargar_modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("re_oraculo", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("No se pudo cargar {r}".format(r=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = cargar_modulo()


@pytest.fixture(scope="module")
def registros() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["registros"]


def test_e06_no_tiene_volteados(registros):
    """E 06 es la referencia: el oraculo no puede declararla defectuosa."""
    resumen = MOD.resumir(registros)
    assert resumen["conteo"]["VOLTEADO"] == 0, resumen["volteados"]


def test_interruptores_quedan_aparte(registros):
    """Los 6 interruptores no son face-based: deben salir PARALELO, no OK."""
    resumen = MOD.resumir(registros)
    assert resumen["conteo"]["PARALELO"] == 6
    paralelos = [d for d in resumen["detalle"] if d["estado"] == "PARALELO"]
    assert {d["familia"] for d in paralelos} == {"M_Interruptores"}


def test_face_based_son_los_restantes(registros):
    resumen = MOD.resumir(registros)
    assert resumen["total"] == 36
    assert resumen["conteo"]["OK"] == 30


def test_volteado_sintetico_se_detecta():
    assert MOD.clasificar(0.98) == "VOLTEADO"
    assert MOD.clasificar(-0.98) == "OK"
    assert MOD.clasificar(0.0) == "PARALELO"
    assert MOD.clasificar(0.29) == "PARALELO"
    assert MOD.clasificar(-0.31) == "OK"


def test_resumir_lista_los_volteados():
    resumen = MOD.resumir([
        {"element_id": 1, "familia": "M_Comunicaciones", "tipo": "Datos", "dot": 0.99},
        {"element_id": 2, "familia": "M_Comunicaciones", "tipo": "Datos", "dot": -0.99},
    ])
    assert resumen["conteo"] == {"OK": 1, "VOLTEADO": 1, "PARALELO": 0}
    assert [v["element_id"] for v in resumen["volteados"]] == [1]
