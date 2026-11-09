"""
================================================================================
test_RE_EXTRACT_BLOQUES_ANIDADOS_v01.py — Tests para RE_EXTRACT_BLOQUES_ANIDADOS_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 + pytest
================================================================================

OBJETIVO:
  Verificar que RE_EXTRACT_BLOQUES_ANIDADOS_v01.py:
  1. Extrae definiciones de bloque con sus entidades internas (tipo, capa, punto, rotacion).
  2. Extrae INSERTs del espacio de modelo con su punto de insercion y rotacion.
  3. Asocia cada INSERT con los componentes internos de su definicion de bloque.
  4. Sugiere familias de Revit para bloques electricos conocidos.
  5. Genera JSON de salida con la estructura esperada.

FIXTURE:
  tests/fase-1-contexto/fixture_RE_EXTRACT_BLOQUES_ANIDADOS_v01.json

USO:
  pytest tests/fase-1-contexto/test_RE_EXTRACT_BLOQUES_ANIDADOS_v01.py -v
================================================================================

"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import ezdxf
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "src" / "fase-1-contexto" / "RE_EXTRACT_BLOQUES_ANIDADOS_v01.py"

spec = importlib.util.spec_from_file_location("RE_EXTRACT_BLOQUES_ANIDADOS_v01", SCRIPT_PATH)
_extract_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_extract_mod)
extraer_bloques_anidados = _extract_mod.extraer_bloques_anidados

FIXTURE_PATH = Path(__file__).parent / "fixture_RE_EXTRACT_BLOQUES_ANIDADOS_v01.json"


def _crear_dxf_prueba(tmp_path: Path) -> Path:
    """Genera un DXF de prueba con definiciones de bloque y INSERTs en el modelo."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Definicion de bloque "ELEC-T-D-t-15A" con 3 entidades internas
    bdef_toma = doc.blocks.new(name="ELEC-T-D-t-15A")
    bdef_toma.add_circle(center=(0.0, 0.052, 0.0), radius=0.051)
    bdef_toma.add_lwpolyline([(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.1, 0.1, 0.0)], close=True)
    bdef_toma.add_lwpolyline([(0.0, 0.0, 0.0), (0.05, 0.0, 0.0)], close=False)

    # Definicion de bloque "ELEC-I-S-1-5A" con 2 entidades internas
    bdef_inter = doc.blocks.new(name="ELEC-I-S-1-5A")
    bdef_inter.add_circle(center=(0.0, 0.0, 0.0), radius=0.03)
    bdef_inter.add_lwpolyline([(-0.05, -0.05, 0.0), (0.05, -0.05, 0.0), (0.05, 0.05, 0.0), (-0.05, 0.05, 0.0)], close=True)

    # INSERTs en el espacio de modelo (marcadores de dispositivo)
    br_toma = msp.add_blockref("ELEC-T-D-t-15A", insert=(2.8, 8.57, 0.0))
    br_toma.dxf.rotation = 180.0
    br_toma.dxf.layer = "ELEC-APPL-TOMAS"
    br_inter = msp.add_blockref("ELEC-I-S-1-5A", insert=(5.107, 2.294, 0.0))
    br_inter.dxf.rotation = 0.0
    br_inter.dxf.layer = "ELEC-APPL-ILUM"

    dxf_path = tmp_path / "prueba_anidados.dxf"
    doc.saveas(str(dxf_path))
    return dxf_path


def _cargar_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_extrae_bloques_apartamento_y_componentes_internos(tmp_path: Path) -> None:
    """Se extraen los bloques INSERT del modelo con sus componentes internos."""
    dxf_path = _crear_dxf_prueba(tmp_path)

    resultado = extraer_bloques_anidados(dxf_path, chip="SANTAMARTA_T5")

    # 2 bloques INSERT en el modelo
    assert resultado["resumen"]["bloques_apartamento_en_modelo"] == 2
    # 2 definiciones de bloque distintas
    assert resultado["resumen"]["definiciones_bloque_distintas"] == 2
    # Total componentes internos: 3 + 2 = 5
    assert resultado["resumen"]["total_componentes_internos"] == 5

    nombres = [b["nombre_bloque"] for b in resultado["bloques_apartamento"]]
    assert "ELEC-T-D-t-15A" in nombres
    assert "ELEC-I-S-1-5A" in nombres


def test_bloque_tiene_punto_rotacion_y_capa(tmp_path: Path) -> None:
    """Cada bloque apartamento registra punto de insercion, rotacion y capa."""
    dxf_path = _crear_dxf_prueba(tmp_path)

    resultado = extraer_bloques_anidados(dxf_path, chip="SANTAMARTA_T5")

    toma = [b for b in resultado["bloques_apartamento"] if b["nombre_bloque"] == "ELEC-T-D-t-15A"][0]
    assert toma["punto_insert"] == [2.8, 8.57, 0.0]
    assert toma["rotacion"] == 180.0
    assert toma["capa"] == "ELEC-APPL-TOMAS"
    assert toma["es_electrica"] is True


def test_componentes_internos_tienen_tipo_y_capa(tmp_path: Path) -> None:
    """Cada componente interno tiene tipo y capa registrados."""
    dxf_path = _crear_dxf_prueba(tmp_path)

    resultado = extraer_bloques_anidados(dxf_path, chip="SANTAMARTA_T5")

    toma = [b for b in resultado["bloques_apartamento"] if b["nombre_bloque"] == "ELEC-T-D-t-15A"][0]
    componentes = toma["componentes_internos"]
    assert len(componentes) == 3

    tipos = [c["tipo"] for c in componentes]
    assert "CIRCLE" in tipos
    assert "LWPOLYLINE" in tipos

    for c in componentes:
        assert "capa" in c
        assert "es_electrica" in c


def test_definiciones_bloque_se_detallan(tmp_path: Path) -> None:
    """Cada definicion de bloque aparece en 'definiciones_bloque' con sus entidades."""
    dxf_path = _crear_dxf_prueba(tmp_path)

    resultado = extraer_bloques_anidados(dxf_path, chip="SANTAMARTA_T5")

    definiciones = {d["nombre_bloque"]: d for d in resultado["definiciones_bloque"]}
    assert "ELEC-T-D-t-15A" in definiciones
    assert "ELEC-I-S-1-5A" in definiciones
    assert definiciones["ELEC-T-D-t-15A"]["total_entidades"] == 3
    assert definiciones["ELEC-I-S-1-5A"]["total_entidades"] == 2


def test_familia_revit_sugerida_para_bloques_conocidos(tmp_path: Path) -> None:
    """Se sugiere la familia de Revit para bloques electricos conocidos."""
    dxf_path = _crear_dxf_prueba(tmp_path)

    resultado = extraer_bloques_anidados(dxf_path, chip="SANTAMARTA_T5")

    toma = [b for b in resultado["bloques_apartamento"] if b["nombre_bloque"] == "ELEC-T-D-t-15A"][0]
    assert toma["familia_revit_sugerida"] == "Toma doble 15A"

    inter = [b for b in resultado["bloques_apartamento"] if b["nombre_bloque"] == "ELEC-I-S-1-5A"][0]
    assert inter["familia_revit_sugerida"] == "Interruptor simple 1x 5A"


def test_estructura_json_salida(tmp_path: Path) -> None:
    """El JSON de salida contiene metadatos, resumen, bloques_apartamento, definiciones_bloque y mapeo_sugerido_revit."""
    dxf_path = _crear_dxf_prueba(tmp_path)

    resultado = extraer_bloques_anidados(dxf_path, chip="SANTAMARTA_T5")

    assert "metadatos" in resultado
    assert "resumen" in resultado
    assert "bloques_apartamento" in resultado
    assert "definiciones_bloque" in resultado
    assert "mapeo_sugerido_revit" in resultado
    assert resultado["metadatos"]["chip"] == "SANTAMARTA_T5"


def test_guardar_json_en_disco(tmp_path: Path) -> None:
    """El archivo JSON de salida se escribe en disco y es legible."""
    dxf_path = _crear_dxf_prueba(tmp_path)
    salida_path = tmp_path / "salida.json"

    resultado = extraer_bloques_anidados(dxf_path, chip="SANTAMARTA_T5")

    salida_path.parent.mkdir(parents=True, exist_ok=True)
    with open(salida_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)

    assert salida_path.exists()
    with open(salida_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["metadatos"]["chip"] == "SANTAMARTA_T5"
    assert data["resumen"]["bloques_apartamento_en_modelo"] == 2
