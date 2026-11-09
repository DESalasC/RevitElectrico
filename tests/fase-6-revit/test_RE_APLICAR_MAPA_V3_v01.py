"""
================================================================================
test_RE_APLICAR_MAPA_V3_v01.py — Tests para RE_APLICAR_MAPA_V3_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest
================================================================================

OBJETIVO:
  Verificar que RE_APLICAR_MAPA_V3_v01.py:
  1. Mapea dispositivos físicos (mapear: true) a acciones de modelado con
     familia, simbolo, anfitrion, altura, punto XY y rotacion.
  2. Salta marcadores de conductores (mapear: false) sin crear FamilyInstance.
  3. Marca dispositivos sin entrada en el mapa como "sin mapeo".
  4. Usa NewFamilyInstance(face, ...) para anfitrion == ceiling y
     NewFamilyInstance(level, ...) para anfitrion == muro.
  5. Genera JSON de reporte con estadisticas y lista de acciones.

FIXTURES:
  tests/fase-6-revit/fixture_RE_APLICAR_MAPA_V3_v01.json
  tests/fase-6-revit/fixture_RE_APLICAR_MAPA_V3_v01_dispositivos.json

USO:
  pytest tests/fase-6-revit/test_RE_APLICAR_MAPA_V3_v01.py -v
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "fase-6-revit"
    / "RE_APLICAR_MAPA_V3_v01.py"
)

spec = importlib.util.spec_from_file_location("RE_APLICAR_MAPA_V3_v01", SCRIPT_PATH)
_re_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_re_mod)
aplicar_mapa = _re_mod.aplicar_mapa

MAPA_PATH = Path(__file__).parent / "fixture_RE_APLICAR_MAPA_V3_v01.json"
DISPOSITIVOS_PATH = (
    Path(__file__).parent / "fixture_RE_APLICAR_MAPA_V3_v01_dispositivos.json"
)


def _cargar_json(ruta: Path) -> dict:
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def test_mapea_dispositivo_fisico_a_modelar(tmp_path: Path) -> None:
    """Un dispositivo con mapear: true genera una accion de modelado completa."""
    mapa = _cargar_json(MAPA_PATH)
    dispositivos = _cargar_json(DISPOSITIVOS_PATH)

    reporte = aplicar_mapa(
        MAPA_PATH, DISPOSITIVOS_PATH, chip="SANTAMARTA_T5", nivel="Piso 5"
    )

    acciones = {a["nombre_bloque"]: a for a in reporte["acciones_modelar"]}

    assert "ELEC-T-GFCI-t-15A" in acciones
    accion = acciones["ELEC-T-GFCI-t-15A"]
    assert accion["familia"] == "M_Toma doble"
    assert accion["simbolo"] == "GFCI"
    assert accion["anfitrion"] == "muro"
    assert accion["z_revit"] == 0.30
    assert accion["x_revit"] == 2.822
    assert accion["y_revit"] == 8.7015
    assert accion["rotacion"] == 0
    assert accion["nivel_revit"] == "Piso 5"
    assert accion["metodo_instancia"] == "NewFamilyInstance(level, ...)"


def test_dispositivo_techo_usa_face_based(tmp_path: Path) -> None:
    """Los dispositivos de techo usan NewFamilyInstance(face, ...) y altura del cieloraso."""
    mapa = _cargar_json(MAPA_PATH)
    dispositivos = _cargar_json(DISPOSITIVOS_PATH)

    reporte = aplicar_mapa(
        MAPA_PATH, DISPOSITIVOS_PATH, chip="SANTAMARTA_T5", nivel="Piso 5"
    )

    acciones = {a["nombre_bloque"]: a for a in reporte["acciones_modelar"]}

    assert "ELEC-CAMPANA" in acciones
    accion = acciones["ELEC-CAMPANA"]
    assert accion["anfitrion"] == "ceiling"
    assert accion["metodo_instancia"] == "NewFamilyInstance(face, ...)"
    assert accion["altura_cieloraso_m"] == 15.82
    assert accion["nivel_revit"] is None

    assert "Bala Stil Led 22W" in acciones
    accion_bala = acciones["Bala Stil Led 22W"]
    assert accion_bala["anfitrion"] == "ceiling"
    assert accion_bala["metodo_instancia"] == "NewFamilyInstance(face, ...)"


def test_marcador_conductor_se_salta(tmp_path: Path) -> None:
    """Los marcadores de conductores (mapear: false) se saltan, no generan FamilyInstance."""
    mapa = _cargar_json(MAPA_PATH)
    dispositivos = _cargar_json(DISPOSITIVOS_PATH)

    reporte = aplicar_mapa(
        MAPA_PATH, DISPOSITIVOS_PATH, chip="SANTAMARTA_T5", nivel="Piso 5"
    )

    saltados = {a["nombre_bloque"]: a for a in reporte["acciones_saltar"]}

    assert "1FTN" in saltados
    assert saltados["1FTN"]["familia"] is None
    assert saltados["1FTN"]["motivo"] is not None

    # Ningun marcador debe aparecer en acciones_modelar
    modelar_nombres = {a["nombre_bloque"] for a in reporte["acciones_modelar"]}
    assert "1FTN" not in modelar_nombres
    assert "1FTNR" not in modelar_nombres


def test_dispositivo_sin_mapeo_se_marca(tmp_path: Path) -> None:
    """Un dispositivo sin entrada en el mapa se marca como sin mapeo."""
    mapa = _cargar_json(MAPA_PATH)
    dispositivos = _cargar_json(DISPOSITIVOS_PATH)

    reporte = aplicar_mapa(
        MAPA_PATH, DISPOSITIVOS_PATH, chip="SANTAMARTA_T5", nivel="Piso 5"
    )

    sin_mapeo = reporte["acciones_sin_mapeo"]
    nombres_sin_mapeo = {a["nombre_bloque"] for a in sin_mapeo}

    assert "BLOQUE_NO_EXISTENTE" in nombres_sin_mapeo
    assert reporte["estadisticas"]["sin_mapeo"] >= 1


def test_estadisticas_reporte(tmp_path: Path) -> None:
    """El reporte contiene estadisticas coherentes con los dispositivos de entrada."""
    mapa = _cargar_json(MAPA_PATH)
    dispositivos = _cargar_json(DISPOSITIVOS_PATH)

    reporte = aplicar_mapa(
        MAPA_PATH, DISPOSITIVOS_PATH, chip="SANTAMARTA_T5", nivel="Piso 5"
    )

    stats = reporte["estadisticas"]
    total = len(dispositivos["dispositivos_internos"])

    assert stats["dispositivos_total"] == total
    assert stats["a_modelar"] + stats["a_saltar_marcador"] + stats["sin_mapeo"] == total
    assert stats["anfitrion_techo"] + stats["anfitrion_muro"] + stats["anfitrion_otro"] == stats["a_modelar"]


def test_estructura_json_salida(tmp_path: Path) -> None:
    """El reporte de salida contiene todas las claves esperadas."""
    mapa = _cargar_json(MAPA_PATH)
    dispositivos = _cargar_json(DISPOSITIVOS_PATH)

    reporte = aplicar_mapa(
        MAPA_PATH, DISPOSITIVOS_PATH, chip="SANTAMARTA_T5", nivel="Piso 5"
    )

    assert "version" in reporte
    assert "proyecto" in reporte
    assert "bloque_padre" in reporte
    assert "nivel" in reporte
    assert "chip" in reporte
    assert "mapa_origen" in reporte
    assert "dispositivos_origen" in reporte
    assert "altura_cieloraso_m" in reporte
    assert "estadisticas" in reporte
    assert "acciones_modelar" in reporte
    assert "acciones_saltar" in reporte
    assert "acciones_sin_mapeo" in reporte


def test_guardar_json_en_disco(tmp_path: Path) -> None:
    """El JSON de reporte se escribe en disco y es legible."""
    mapa = _cargar_json(MAPA_PATH)
    dispositivos = _cargar_json(DISPOSITIVOS_PATH)

    reporte = aplicar_mapa(
        MAPA_PATH, DISPOSITIVOS_PATH, chip="SANTAMARTA_T5", nivel="Piso 5"
    )

    json_out = tmp_path / "reporte_aplicar_mapa.json"
    _re_mod.guardar_reporte(reporte, json_out)

    assert json_out.exists()
    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["estadisticas"]["dispositivos_total"] == reporte["estadisticas"]["dispositivos_total"]
    assert data["chip"] == "SANTAMARTA_T5"
