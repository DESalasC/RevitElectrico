# -*- coding: utf-8 -*-
"""
================================================================================
test_RE_COMPARAR_INVENTARIO_v01.py — Tests para RE_COMPARAR_INVENTARIO_v01
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6 (F2: auditoría + diff)
Python 3.12 + pytest (CPython, sin Revit).
================================================================================

OBJETIVO:
  Verificar que RE_COMPARAR_INVENTARIO_v01.py:
  1. Convierte pies de Revit a metros y aplica el offset DXF->Revit.
  2. Empareja canon DXF vs export Revit por tipo y proximidad (greedy).
  3. Clasifica: OK, DESPLAZADO, DESPLAZADO_CRITICO, FALTANTE, DUPLICADO,
     TIPO_NO_MAPEADO.
  4. Evalúa criterios de aceptación A1-A8 del plan de corrección.
  5. Emite JSON de diff + informe HTML.

FIXTURE:
  tests/fase-6-revit/fixture_RE_COMPARAR_INVENTARIO_v01.json

USO:
  pytest tests/fase-6-revit/test_RE_COMPARAR_INVENTARIO_v01.py -v
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
    / "RE_COMPARAR_INVENTARIO_v01.py"
)
FIXTURE_PATH = Path(__file__).parent / "fixture_RE_COMPARAR_INVENTARIO_v01.json"


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location(
        "RE_COMPARAR_INVENTARIO_v01", SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _ejecutar_script(mod, tmp_path, inventario, revit, salida, reporte):
    """Ejecuta main() directamente (CPython 3.12, solo stdlib)."""
    inv_path = tmp_path / "inventario.json"
    revit_path = tmp_path / "revit.json"
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(inventario, f, ensure_ascii=False)
    with open(revit_path, "w", encoding="utf-8") as f:
        json.dump(revit, f, ensure_ascii=False)

    argv = [
        "--inventario", str(inv_path),
        "--revit", str(revit_path),
        "--offset-x", "2.3682",
        "--offset-y", "9.6937",
        "--nivel-elevacion-m", "13.22",
        "--tol-nominal", "0.02",
        "--tol-final", "0.10",
        "--tol-z", "0.02",
        "--tol-rot", "2.0",
        "--tol-match", "0.25",
        "--apartamento", "E06",
        "--salida", str(salida),
        "--reporte", str(reporte),
    ]
    return mod.main(argv), salida, reporte


def _dispositivos_por_handle(informe):
    return {d["handle"]: d for d in informe["dispositivos"] if d.get("handle")}


def _sobrantes_por_id(informe):
    return {d["id_revit"]: d for d in informe["dispositivos"] if d.get("handle") is None}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mod():
    return _cargar_modulo()


def test_ejecucion_retorna_cero_y_genera_archivos(mod, tmp_path):
    """main() retorna 0 y escribe JSON de diff + informe HTML."""
    fx = _cargar_fixture()
    salida = tmp_path / "diff.json"
    reporte = tmp_path / "diff.html"
    codigo, _, _ = _ejecutar_script(
        mod, tmp_path, fx["inventario_canonico"], fx["export_revit"], salida, reporte)

    assert codigo == 0
    assert salida.exists()
    assert reporte.exists()

    with open(salida, "r", encoding="utf-8") as f:
        informe = json.load(f)
    assert informe["apartamento"] == "E06"
    assert "resumen" in informe and "criterios" in informe
    assert "dispositivos" in informe and isinstance(informe["dispositivos"], list)

    with open(reporte, "r", encoding="utf-8") as f:
        html_contenido = f.read()
    assert "E06" in html_contenido
    assert "OK" in html_contenido and "FALTANTE" in html_contenido


def test_resumen_conteos_correctos(mod, tmp_path):
    """Conteos del resumen coinciden con el escenario del fixture."""
    fx = _cargar_fixture()
    salida = tmp_path / "diff.json"
    reporte = tmp_path / "diff.html"
    codigo, _, _ = _ejecutar_script(
        mod, tmp_path, fx["inventario_canonico"], fx["export_revit"], salida, reporte)
    assert codigo == 0

    with open(salida, "r", encoding="utf-8") as f:
        informe = json.load(f)

    esp = fx["esperado"]
    res = informe["resumen"]
    assert res["total_dispositivos_dxf"] == esp["total_dispositivos_dxf"]  # 4
    assert res["total_instancias_revit"] == esp["total_instancias_revit"]  # 5
    assert res["emparejados"] == esp["emparejados"]  # 3
    assert res["ok"] == esp["ok"]  # 2
    assert res["desplazado"] == esp["desplazado"]  # 1
    assert res["desplazado_critico"] == esp["desplazado_critico"]  # 0
    assert res["faltantes"] == esp["faltantes"]  # 1
    assert res["duplicados"] == esp["duplicados"]  # 1
    assert res["tipo_no_mapeado"] == esp["tipo_no_mapeado"]  # 1
    assert res["cobertura_pct"] == esp["cobertura_pct"]  # 75.0


def test_clasificacion_por_dispositivo(mod, tmp_path):
    """Cada dispositivo canonico recibe la clasificacion esperada."""
    fx = _cargar_fixture()
    salida = tmp_path / "diff.json"
    reporte = tmp_path / "diff.html"
    _ejecutar_script(
        mod, tmp_path, fx["inventario_canonico"], fx["export_revit"], salida, reporte)

    with open(salida, "r", encoding="utf-8") as f:
        informe = json.load(f)

    por_handle = _dispositivos_por_handle(informe)
    for handle, clase_esperada in fx["esperado"]["clasificaciones"].items():
        assert handle in por_handle, "Falta dispositivo {}".format(handle)
        assert por_handle[handle]["clasificacion"] == clase_esperada


def test_distancias_y_conversion_pies_metros(mod, tmp_path):
    """Las distancias XY respetan la conversion pies->metros y el offset."""
    fx = _cargar_fixture()
    salida = tmp_path / "diff.json"
    reporte = tmp_path / "diff.html"
    _ejecutar_script(
        mod, tmp_path, fx["inventario_canonico"], fx["export_revit"], salida, reporte)

    with open(salida, "r", encoding="utf-8") as f:
        informe = json.load(f)

    por_handle = _dispositivos_por_handle(informe)
    for handle, dist_esperada in fx["esperado"]["distancias_m"].items():
        d = por_handle[handle]["dist_m"]
        assert d is not None
        assert abs(d - dist_esperada) < 0.001, "{} dist {} != {}".format(handle, d, dist_esperada)


def test_faltante_sin_instancia_revit(mod, tmp_path):
    """El dispositivo sin instancia en Revit queda como FALTANTE con id None."""
    fx = _cargar_fixture()
    salida = tmp_path / "diff.json"
    reporte = tmp_path / "diff.html"
    _ejecutar_script(
        mod, tmp_path, fx["inventario_canonico"], fx["export_revit"], salida, reporte)

    with open(salida, "r", encoding="utf-8") as f:
        informe = json.load(f)

    por_handle = _dispositivos_por_handle(informe)
    h103 = por_handle["H103"]
    assert h103["clasificacion"] == "FALTANTE"
    assert h103["id_revit"] is None
    assert h103["x_revit_m"] is None and h103["y_revit_m"] is None


def test_sobrantes_duplicado_y_no_mapeado(mod, tmp_path):
    """Las instancias Revit sobrantes se clasifican DUPLICADO o TIPO_NO_MAPEADO."""
    fx = _cargar_fixture()
    salida = tmp_path / "diff.json"
    reporte = tmp_path / "diff.html"
    _ejecutar_script(
        mod, tmp_path, fx["inventario_canonico"], fx["export_revit"], salida, reporte)

    with open(salida, "r", encoding="utf-8") as f:
        informe = json.load(f)

    sobrantes = _sobrantes_por_id(informe)
    esp_ids = fx["esperado"]["sobrantes_ids"]
    esp_clase = fx["esperado"]["sobrantes_clase"]
    for rid in esp_ids:
        assert rid in sobrantes, "Falta sobrante id {}".format(rid)
        assert sobrantes[rid]["clasificacion"] == esp_clase[str(rid)]


def test_criterios_aceptacion(mod, tmp_path):
    """Criterios A1-A8: cobertura 75% -> A1 y A2 no cumplen; A4 (sin crítico) cumple."""
    fx = _cargar_fixture()
    salida = tmp_path / "diff.json"
    reporte = tmp_path / "diff.html"
    _ejecutar_script(
        mod, tmp_path, fx["inventario_canonico"], fx["export_revit"], salida, reporte)

    with open(salida, "r", encoding="utf-8") as f:
        informe = json.load(f)

    crit = informe["criterios"]
    assert crit["A1_cobertura_100_pct"] is False
    assert crit["A2_sobrantes_cero"] is False
    assert crit["A4_xy_final_0.10_m"] is True
    assert isinstance(crit["A8_avisos_host_cero"], bool)


def test_export_revit_inexistente_retorna_codigo_2(mod, tmp_path):
    """Sin archivo de export de Revit, main() retorna 2 y avisa por salida estándar."""
    fx = _cargar_fixture()
    inv_path = tmp_path / "inventario.json"
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(fx["inventario_canonico"], f, ensure_ascii=False)

    argv = [
        "--inventario", str(inv_path),
        "--revit", str(tmp_path / "no_existe.json"),
        "--salida", str(tmp_path / "out.json"),
        "--reporte", str(tmp_path / "out.html"),
    ]
    codigo = mod.main(argv)
    assert codigo == 2
