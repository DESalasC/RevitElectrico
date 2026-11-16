# -*- coding: utf-8 -*-
"""Tests de la sonda de tomas en DXF (F1).

Verifican que la sonda encuentra los INSERT de toma, lee la capa, y asocia el texto
mas cercano sin confundirlo con el de un bloque de otro tipo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import ezdxf
import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ / "src" / "fase-1-contexto" / "RE_F1_SONDA_TOMAS_DXF_v01.py"


def cargar_modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("re_f1_sonda_tomas", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("No se pudo cargar {r}".format(r=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def sonda() -> ModuleType:
    return cargar_modulo()


def test_sondear_encuentra_toma_y_su_texto(sonda: ModuleType, tmp_path: Path) -> None:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_blockref("ELEC-T-D-t-15A", (2.0, 3.0), dxfattribs={"layer": "ELEC-APPL-TOMAS"})
    msp.add_text("0.7m", dxfattribs={"insert": (2.2, 3.1, 0.0), "height": 0.2})
    msp.add_text("ESTUFA", dxfattribs={"insert": (2.4, 3.2, 0.0), "height": 0.2})
    plano = tmp_path / "apto.dxf"
    doc.saveas(str(plano))

    datos = sonda.sondear(plano)

    assert datos["resumen"]["tomas"] == 1
    assert datos["resumen"]["capas_de_toma"] == {"ELEC-APPL-TOMAS": 1}
    toma = datos["tomas"][0]
    assert toma["bloque"] == "ELEC-T-D-t-15A"
    assert toma["textos_cercanos"][0]["texto"] == "0.7m"
    assert toma["atributos"] == {}


def test_sondear_ignora_bloques_ajenos(sonda: ModuleType, tmp_path: Path) -> None:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_blockref("PUERTA", (0.0, 0.0), dxfattribs={"layer": "ARQ"})
    plano = tmp_path / "vacio.dxf"
    doc.saveas(str(plano))

    datos = sonda.sondear(plano)

    assert datos["resumen"]["tomas"] == 0


def test_radio_de_texto_configurable(sonda: ModuleType, tmp_path: Path) -> None:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_blockref("ELEC-T-GFCI-t-15A", (0.0, 0.0), dxfattribs={"layer": "ELEC-APPL-TOMAS"})
    msp.add_text("1.05m", dxfattribs={"insert": (1.0, 0.0, 0.0), "height": 0.2})
    plano = tmp_path / "lejos.dxf"
    doc.saveas(str(plano))

    cerca = sonda.sondear(plano, radio=0.5)
    lejos = sonda.sondear(plano, radio=2.0)

    assert cerca["tomas"][0]["textos_cercanos"] == []
    assert lejos["tomas"][0]["textos_cercanos"][0]["texto"] == "1.05m"
