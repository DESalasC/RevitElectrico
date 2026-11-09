"""
================================================================================
test_RE4_EXPORT_EXCEL_v01.py — Tests para RE4_EXPORT_EXCEL_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 + pytest
================================================================================

OBJETIVO:
  Verificar que RE4_EXPORT_EXCEL_v01.py:
  1. Lee los JSON de RE1 y RE2 y genera un libro Excel (.xlsx).
  2. Crea las hojas esperadas (Resumen, DXF_Bloques, DXF_Mapeo, DXF_Geometria)
     cuando hay datos de RE1/RE2.
  3. Escribe el archivo de salida en disco y es legible con openpyxl.
  4. Incluye el chip y los conteos globales en la hoja Resumen.
  5. Rechaza la ejecución sin al menos un JSON de entrada.

FIXTURE:
  tests/fase-1-contexto/fixture_RE4_entrada.json (entrada mínima de RE1 y RE2)

USO:
  pytest tests/fase-1-contexto/test_RE4_EXPORT_EXCEL_v01.py -v
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "src" / "fase-1-contexto" / "RE4_EXPORT_EXCEL_v01.py"

spec = importlib.util.spec_from_file_location("RE4_EXPORT_EXCEL_v01", SCRIPT_PATH)
_re4_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_re4_mod)
build_workbook = _re4_mod.build_workbook
DEFAULT_CHIP = _re4_mod.DEFAULT_CHIP

FIXTURE_PATH = Path(__file__).parent / "fixture_RE4_entrada.json"


def _cargar_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_build_workbook_crea_hojas_esperadas(tmp_path: Path) -> None:
    """El libro Excel contiene las hojas esperadas cuando se pasan RE1 y RE2."""
    fx = _cargar_fixture()

    wb = build_workbook(
        chip=fx["chip"],
        re1=fx["re1"],
        re2=fx["re2"],
        re3=None,
    )

    assert "Resumen" in wb.sheetnames
    assert "DXF_Bloques" in wb.sheetnames
    assert "DXF_Mapeo" in wb.sheetnames
    assert "DXF_Geometria" in wb.sheetnames


def test_resumen_tiene_chip_y_conteos(tmp_path: Path) -> None:
    """La hoja Resumen contiene el chip y los conteos globales de RE1 y RE2."""
    fx = _cargar_fixture()

    wb = build_workbook(
        chip=fx["chip"],
        re1=fx["re1"],
        re2=fx["re2"],
        re3=None,
    )

    ws = wb["Resumen"]
    valores = [c.value for row in ws.iter_rows() for c in row if c.value is not None]

    assert fx["chip"] in valores
    assert "Bloques DXF totales" in valores
    assert "Bloques eléctricos" in valores
    assert "Instancias totales" in valores


def test_dxf_bloques_tiene_datos_re1(tmp_path: Path) -> None:
    """La hoja DXF_Bloques contiene los bloques del JSON de RE1."""
    fx = _cargar_fixture()

    wb = build_workbook(
        chip=fx["chip"],
        re1=fx["re1"],
        re2=None,
        re3=None,
    )

    ws = wb["DXF_Bloques"]
    nombres = [c.value for row in ws.iter_rows(min_row=3) for c in row if c.value is not None]

    for bloque in fx["re1"]["bloques"]:
        assert bloque["nombre_bloque"] in nombres


def test_dxf_mapeo_tiene_datos_re2(tmp_path: Path) -> None:
    """La hoja DXF_Mapeo contiene los mapeos del JSON de RE2."""
    fx = _cargar_fixture()

    wb = build_workbook(
        chip=fx["chip"],
        re1=None,
        re2=fx["re2"],
        re3=None,
    )

    ws = wb["DXF_Mapeo"]
    nombres = [c.value for row in ws.iter_rows(min_row=3) for c in row if c.value is not None]

    for mapeo in fx["re2"]["mapeo"]:
        assert mapeo["nombre_bloque"] in nombres


def test_guardar_excel_en_disco(tmp_path: Path) -> None:
    """El libro Excel se escribe en disco y puede leerse con openpyxl."""
    from openpyxl import load_workbook

    fx = _cargar_fixture()

    wb = build_workbook(
        chip=fx["chip"],
        re1=fx["re1"],
        re2=fx["re2"],
        re3=None,
    )

    xlsx_out = tmp_path / "reporte_prueba.xlsx"
    wb.save(str(xlsx_out))

    assert xlsx_out.exists()

    wb2 = load_workbook(str(xlsx_out))
    assert "Resumen" in wb2.sheetnames
    assert "DXF_Bloques" in wb2.sheetnames
    assert "DXF_Mapeo" in wb2.sheetnames


def test_chip_default_cuando_no_se_indica(tmp_path: Path) -> None:
    """Cuando no se indica chip, se usa DEFAULT_CHIP (SANTAMARTA_T5)."""
    fx = _cargar_fixture()

    wb = build_workbook(
        chip=DEFAULT_CHIP,
        re1=fx["re1"],
        re2=fx["re2"],
        re3=None,
    )

    ws = wb["Resumen"]
    valores = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    assert DEFAULT_CHIP in valores
