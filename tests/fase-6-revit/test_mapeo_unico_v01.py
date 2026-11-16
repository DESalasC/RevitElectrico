# -*- coding: utf-8 -*-
"""Guarda contra la deriva de mapeos y contra el export silenciosamente vacio.

Dos fallos reales que estos tests impiden repetir:

1. El comparador tenia su propia copia del mapeo DXF->Revit, desincronizada en cuatro
   entradas y con cinco familias ausentes. Ahora lo extrae del colocador.
2. El exportador usaba ``fi.Level``, que en IronPython lanza AttributeError; como el
   bucle descarta el elemento ante cualquier excepcion, el export salia con 0 instancias
   sin avisar.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
COMPARADOR = RAIZ / "src" / "fase-6-revit" / "RE_COMPARAR_INVENTARIO_v01.py"
EXPORTADOR = RAIZ / "src" / "fase-6-revit" / "RE_AUDITAR_DISPOSITIVOS_v01.py"


def cargar_comparador():
    spec = importlib.util.spec_from_file_location("re_comparar", COMPARADOR)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("No se pudo cargar {r}".format(r=COMPARADOR))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def comparador():
    return cargar_comparador()


def test_mapeo_unico_con_las_entradas_corregidas(comparador) -> None:
    mapeo = comparador.MAPA_DXF_REVIT_DEFECTO
    assert len(mapeo) == 16
    assert mapeo["ELEC-CAMPANA"] == ("M_Timbre", "Campana")
    assert mapeo["ELEC-NET-PAU"] == ("Consolidation_Point", "CPB6BL")
    assert mapeo["ELEC-TEL"] == ("M_Comunicaciones", "Datos")
    assert mapeo["ELEC-EXT"] == ("EA", "EA 1010")
    assert mapeo["ELEC-I-S-C1-5A"] == ("M_Interruptores", "Simple conmutable")


def test_canonico_usa_altura_local_y_no_la_nominal(comparador) -> None:
    inventario = {
        "dispositivos": [
            {
                "handle": "BA",
                "nombre": "ELEC-T-D-t-15A",
                "x": 0.0,
                "y": 0.0,
                "altura_nominal_m": 1.10,
                "altura_local_m": 0.70,
            }
        ]
    }

    canonicos = comparador.construir_canonico(inventario, 0.0, 0.0, 13.22)

    assert len(canonicos) == 1
    assert canonicos[0]["altura_local_m"] == 0.70
    assert canonicos[0]["z_esperado_abs_m"] == pytest.approx(13.92, abs=1e-6)


def test_canonico_cae_a_altura_nominal_si_falta_la_local(comparador) -> None:
    inventario = {
        "dispositivos": [
            {"handle": "X", "nombre": "ELEC-T-D-t-15A", "x": 0.0, "y": 0.0, "altura_nominal_m": 0.30}
        ]
    }

    canonicos = comparador.construir_canonico(inventario, 0.0, 0.0, 13.22)

    assert canonicos[0]["z_esperado_abs_m"] == pytest.approx(13.52, abs=1e-6)


def test_exportador_no_usa_fi_level() -> None:
    fuente = EXPORTADOR.read_text(encoding="utf-8")
    assert "fi.Level.Name" not in fuente
    assert "nivel_de(fi, doc)" in fuente


def test_exportador_tiene_helper_de_nivel() -> None:
    fuente = EXPORTADOR.read_text(encoding="utf-8")
    assert "def nivel_de(elemento, doc)" in fuente
    assert "def orientacion_segura(elemento)" in fuente


def test_exportador_filtra_categorias_electricas() -> None:
    """Sin filtro, el export arrastra miles de instancias de arquitectura al diff."""
    fuente = EXPORTADOR.read_text(encoding="utf-8")
    assert "CATEGORIAS_ELECTRICAS_DEFECTO" in fuente
    assert "categorias and cat_name not in categorias" in fuente
    assert "Mechanical Equipment" in fuente, "EA vive en categoria mecanica"
