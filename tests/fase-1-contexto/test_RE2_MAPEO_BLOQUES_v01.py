"""
================================================================================
test_RE2_MAPEO_BLOQUES_v01.py — Tests para RE2_MAPEO_BLOQUES_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 + pytest
================================================================================

OBJETIVO:
  Verificar que RE2_MAPEO_BLOQUES_v01.py:
  1. Mapea bloques eléctricos a familias de Revit con categoría y altura.
  2. Identifica marcadores de conductores (no se modelan).
  3. Clasifica bloques basura y bloques a descartar.
  4. Genera JSON de salida con resumen y detalle.

FIXTURE:
  tests/fase-1-contexto/fixture_RE2_mapeo_entrada.json

USO:
  pytest tests/fase-1-contexto/test_RE2_MAPEO_BLOQUES_v01.py -v
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "src" / "fase-1-contexto" / "RE2_MAPEO_BLOQUES_v01.py"

spec = importlib.util.spec_from_file_location("RE2_MAPEO_BLOQUES_v01", SCRIPT_PATH)
_re2_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_re2_mod)
mapear_bloques = _re2_mod.mapear_bloques

FIXTURE_PATH = Path(__file__).parent / "fixture_RE2_mapeo_entrada.json"


def _cargar_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_mapea_bloques_a_familias_revit(tmp_path: Path) -> None:
    """Los bloques eléctricos conocidos se mapean a su familia de Revit."""
    datos = _cargar_fixture()
    json_in = tmp_path / "entrada.json"
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    json_out = tmp_path / "salida.json"

    resultado = mapear_bloques(json_in, json_out, chip="SANTAMARTA_T5")

    por_nombre = {m["nombre_bloque"]: m for m in resultado["mapeo"]}

    assert por_nombre["Paneles"]["familia_revit"] == "M_Tablero eléctrico.rfa"
    assert por_nombre["Paneles"]["categoria"] == "Tableros eléctricos"
    assert por_nombre["Paneles"]["modelar"] is True
    assert por_nombre["Paneles"]["altura_default_m"] == 1.4

    assert por_nombre["Bala Stil Led 12W"]["familia_revit"] == "M_Foco empotrado - Redondo - LED.rfa"
    assert por_nombre["Bala Stil Led 12W"]["categoria"] == "Luminarias"
    assert por_nombre["Bala Stil Led 12W"]["modelar"] is True


def test_marcador_conductores_no_se_modela(tmp_path: Path) -> None:
    """Los marcadores de conductores (1FTNR) no se modelan como dispositivo."""
    datos = _cargar_fixture()
    json_in = tmp_path / "entrada.json"
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    json_out = tmp_path / "salida.json"

    resultado = mapear_bloques(json_in, json_out, chip="SANTAMARTA_T5")

    por_nombre = {m["nombre_bloque"]: m for m in resultado["mapeo"]}

    assert por_nombre["1FTNR"]["es_codigo_conductores"] is True
    assert por_nombre["1FTNR"]["modelar"] is False
    assert por_nombre["1FTNR"]["familia_revit"] is None


def test_bloque_basura_se_clasifica(tmp_path: Path) -> None:
    """Los bloques con nombres basura se clasifican como Basura y no se modelan."""
    datos = _cargar_fixture()
    json_in = tmp_path / "entrada.json"
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    json_out = tmp_path / "salida.json"

    resultado = mapear_bloques(json_in, json_out, chip="SANTAMARTA_T5")

    por_nombre = {m["nombre_bloque"]: m for m in resultado["mapeo"]}

    assert por_nombre["sadfasdggfjhkkl"]["categoria"] == "Basura"
    assert por_nombre["sadfasdggfjhkkl"]["modelar"] is False
    assert por_nombre["sadfasdggfjhkkl"]["familia_revit"] is None
    assert resultado["resumen"]["instancias_basura"] >= 1


def test_bloque_no_mapeado_se_marca_por_defecto(tmp_path: Path) -> None:
    """Un bloque no mapeado explícitamente se marca como 'Por definir'."""
    datos = _cargar_fixture()
    json_in = tmp_path / "entrada.json"
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    json_out = tmp_path / "salida.json"

    resultado = mapear_bloques(json_in, json_out, chip="SANTAMARTA_T5")

    por_nombre = {m["nombre_bloque"]: m for m in resultado["mapeo"]}

    assert "Apartamento Tipo F 01" in por_nombre
    assert por_nombre["Apartamento Tipo F 01"]["categoria"] == "Marcador de unidad"
    assert por_nombre["Apartamento Tipo F 01"]["modelar"] is False


def test_tdt_dispositivo_datos_no_modelar_por_defecto(tmp_path: Path) -> None:
    """Los dispositivos TDT están en categoría Dispositivos de datos y no se modelan por defecto."""
    datos = _cargar_fixture()
    json_in = tmp_path / "entrada.json"
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    json_out = tmp_path / "salida.json"

    resultado = mapear_bloques(json_in, json_out, chip="SANTAMARTA_T5")

    por_nombre = {m["nombre_bloque"]: m for m in resultado["mapeo"]}

    assert por_nombre["TDT E-07"]["categoria"] == "Dispositivos de datos"
    assert por_nombre["TDT E-07"]["familia_revit"] == "M_Toma-Comunicaciones.rfa"
    assert por_nombre["TDT E-07"]["modelar"] is False


def test_estructura_json_salida(tmp_path: Path) -> None:
    """El JSON de salida contiene metadatos, resumen, mapeo y bloques_detalle."""
    datos = _cargar_fixture()
    json_in = tmp_path / "entrada.json"
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    json_out = tmp_path / "salida.json"

    resultado = mapear_bloques(json_in, json_out, chip="SANTAMARTA_T5")

    assert "metadatos" in resultado
    assert "resumen" in resultado
    assert "mapeo" in resultado
    assert "bloques_detalle" in resultado
    assert resultado["metadatos"]["chip"] == "SANTAMARTA_T5"
    assert resultado["resumen"]["bloques_distintos"] >= 1
    assert len(resultado["bloques_detalle"]) == len(datos["bloques"])


def test_guardar_json_en_disco(tmp_path: Path) -> None:
    """El archivo JSON de salida se escribe en disco y es legible."""
    datos = _cargar_fixture()
    json_in = tmp_path / "entrada.json"
    with open(json_in, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    json_out = tmp_path / "salida.json"

    mapear_bloques(json_in, json_out, chip="SANTAMARTA_T5")

    assert json_out.exists()
    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["metadatos"]["chip"] == "SANTAMARTA_T5"
