"""
================================================================================
test_RE1_NORMALIZA_DXF_v01.py — Tests para RE1_NORMALIZA_DXF_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 + pytest
================================================================================

OBJETIVO:
  Verificar que RE1_NORMALIZA_DXF_v01.py:
  1. Reubica coordenadas al origen (0,0) corrigiendo el offset masivo.
  2. Filtra bloques con nombres basura.
  3. Mapea bloques eléctricos a familias de Revit.
  4. Genera JSON de salida con la estructura esperada.

FIXTURE:
  tests/fase-1-contexto/fixture_RE1_normalizado.json

USO:
  pytest tests/fase-1-contexto/test_RE1_NORMALIZA_DXF_v01.py -v
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import ezdxf
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "src" / "fase-1-contexto" / "RE1_NORMALIZA_DXF_v01.py"

spec = importlib.util.spec_from_file_location("RE1_NORMALIZA_DXF_v01", SCRIPT_PATH)
_re1_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_re1_mod)
normalizar_dxf = _re1_mod.normalizar_dxf

FIXTURE_PATH = Path(__file__).parent / "fixture_RE1_normalizado.json"


def _crear_dxf_prueba(tmp_path: Path) -> Path:
    """Genera un DXF de prueba con un bloque eléctrico, uno basura y una polilínea."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Bloque eléctrico "Paneles" en punto (100, 200, 0)
    msp.add_blockref("Paneles", insert=(100.0, 200.0, 0.0))

    # Bloque basura (debe filtrarse)
    msp.add_blockref("sadfasdggfjhkkl", insert=(50.0, 50.0, 0.0))

    # Polilínea eléctrica en capa ELEC-LIGHT-PIPE
    polilinea = msp.add_lwpolyline(
        [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0)],
    )
    polilinea.dxf.layer = "ELEC-LIGHT-PIPE"

    dxf_path = tmp_path / "prueba.dxf"
    doc.saveas(str(dxf_path))
    return dxf_path


def _cargar_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_normalizacion_reubica_coordenadas(tmp_path: Path) -> None:
    """El offset masivo se corrige y los puntos se reubican al origen."""
    dxf_path = _crear_dxf_prueba(tmp_path)
    salida_path = tmp_path / "salida.json"

    resultado = normalizar_dxf(dxf_path, salida_path, chip="SANTAMARTA_T5")

    bloque = resultado["bloques"][0]
    assert bloque["nombre_bloque"] == "Paneles"
    assert bloque["punto_insert"] == [1091.903, 1914.822, 0.0]
    assert bloque["familia_revit_sugerida"] == "Tablero eléctrico"


def test_filtra_bloques_basura(tmp_path: Path) -> None:
    """Los bloques con nombres basura se filtran y no aparecen en la salida."""
    dxf_path = _crear_dxf_prueba(tmp_path)
    salida_path = tmp_path / "salida.json"

    resultado = normalizar_dxf(dxf_path, salida_path, chip="SANTAMARTA_T5")

    nombres = [b["nombre_bloque"] for b in resultado["bloques"]]
    assert "sadfasdggfjhkkl" not in nombres
    assert resultado["resumen"]["bloques_basura_filtrados"] >= 1


def test_estructura_json_salida(tmp_path: Path) -> None:
    """El JSON de salida contiene metadatos, resumen, bloques, polilineas y mapeo_revit."""
    dxf_path = _crear_dxf_prueba(tmp_path)
    salida_path = tmp_path / "salida.json"

    resultado = normalizar_dxf(dxf_path, salida_path, chip="SANTAMARTA_T5")

    assert "metadatos" in resultado
    assert "resumen" in resultado
    assert "bloques" in resultado
    assert "polilineas" in resultado
    assert "lineas" in resultado
    assert "arcos" in resultado
    assert "circulos" in resultado
    assert "mapeo_revit" in resultado
    assert resultado["metadatos"]["chip"] == "SANTAMARTA_T5"
    assert resultado["metadatos"]["offset_aplicado_x"] == -991.903
    assert resultado["metadatos"]["offset_aplicado_y"] == -1714.822


def test_polilineas_electricas_se_identifican(tmp_path: Path) -> None:
    """Las polilíneas en capas eléctricas se marcan como es_electrica=True."""
    dxf_path = _crear_dxf_prueba(tmp_path)
    salida_path = tmp_path / "salida.json"

    resultado = normalizar_dxf(dxf_path, salida_path, chip="SANTAMARTA_T5")

    poli = resultado["polilineas"][0]
    assert poli["es_electrica"] is True
    assert resultado["resumen"]["polilineas_electricas"] == 1


def test_guardar_json_en_disco(tmp_path: Path) -> None:
    """El archivo JSON de salida se escribe en disco y es legible."""
    dxf_path = _crear_dxf_prueba(tmp_path)
    salida_path = tmp_path / "salida.json"

    normalizar_dxf(dxf_path, salida_path, chip="SANTAMARTA_T5")

    assert salida_path.exists()
    with open(salida_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["metadatos"]["chip"] == "SANTAMARTA_T5"
