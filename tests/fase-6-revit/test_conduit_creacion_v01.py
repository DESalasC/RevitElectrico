# -*- coding: utf-8 -*-
"""Contrato de creacion de conduit (config/conduit_creacion_v01.json).

Comprueba que la tabla de diametros es coherente con la API medida y que los
servicios son los mismos del ruteo: una sola fuente, sin duplicar reglas.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CONDUIT = RAIZ / "config" / "conduit_creacion_v01.json"
RUTEO = RAIZ / "config" / "ruteo_config_v04.json"


@pytest.fixture(scope="module")
def conduit() -> dict:
    return json.loads(CONDUIT.read_text(encoding="utf-8"))


def test_tabla_de_diametros_es_coherente(conduit):
    tabla = conduit["diametros_emt"]["tabla"]
    assert len(tabla) == 10
    pies = [fila["pies"] for fila in tabla]
    assert pies == sorted(pies), "los diametros deben venir en orden creciente"
    for fila in tabla:
        assert fila["mm"] == pytest.approx(fila["pies"] * 304.8, abs=0.1)


def test_diametros_de_la_equivalencia_existen(conduit):
    """Todo diametro que use la tabla de cables tiene que existir en el modelo."""
    equivalencias = json.loads(
        (RAIZ / "config" / "equivalencias_conduit_v01.json").read_text(encoding="utf-8"))
    usados = {
        fila["diametro_conduit_pulgadas"]
        for material in equivalencias["materiales"].values()
        for fila in material["equivalencias_12AWG"]
    }
    disponibles = {fila["pulgadas"] for fila in conduit["diametros_emt"]["tabla"]}
    assert usados <= disponibles, "faltan diametros en el modelo: " + repr(usados - disponibles)


def test_servicios_coinciden_con_el_ruteo(conduit):
    ruteo = json.loads(RUTEO.read_text(encoding="utf-8"))
    assert set(conduit["servicios"]) == set(ruteo["servicios_permitidos"])


def test_tipos_tienen_id_unico_y_nombre_duplicado_declarado(conduit):
    tipos = conduit["tipos_existentes"]
    ids = [t["id"] for t in tipos]
    assert len(ids) == len(set(ids))
    nombres = [t["nombre"] for t in tipos]
    assert len(nombres) != len(set(nombres)), (
        "el config debe seguir declarando el nombre duplicado mientras no se renombre"
    )
    assert all(t["norma"] == "EMT" for t in tipos)
