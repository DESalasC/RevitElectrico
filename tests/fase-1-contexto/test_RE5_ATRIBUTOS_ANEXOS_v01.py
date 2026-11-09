"""
================================================================================
test_RE5_ATRIBUTOS_ANEXOS_v01.py — Tests para RE5_ATRIBUTOS_ANEXOS_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 + pytest (CPython, se hace mock de ezdxf)
================================================================================

OBJETIVO:
  Verificar que RE5_ATRIBUTOS_ANEXOS_v01.py:
  1. Lee TEXT y MTEXT del DXF (mockeado) y los asocia al bloque INSERT mas
     cercano dentro del umbral.
  2. Enriquece cada bloque de RE1 con el campo atributos_anexos.
  3. Clasifica el tipo de atributo (circuito, altura, panel, otro).
  4. Reporta textos no asociados cuando superan el umbral o no son electricos.
  5. Guarda el JSON enriquecido en disco.

FIXTURE:
  tests/fase-1-contexto/fixture_RE5_atributos_anexos.json

USO:
  pytest tests/fase-1-contexto/test_RE5_ATRIBUTOS_ANEXOS_v01.py -v

NOTA:
  Como este script lee un DXF real mediante ezdxf, los tests mockean
  ezdxf.readfile para no depender de un archivo DXF fisico.
================================================================================

"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "fase-1-contexto"
    / "RE5_ATRIBUTOS_ANEXOS_v01.py"
)

FIXTURE_PATH = Path(__file__).parent / "fixture_RE5_atributos_anexos.json"


def _cargar_modulo():
    """Carga RE5_ATRIBUTOS_ANEXOS_v01.py como modulo independiente."""
    spec = importlib.util.spec_from_file_location(
        "RE5_ATRIBUTOS_ANEXOS_v01", SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _hacer_entidad_texto(texto, capa, punto, height=2.5, dxftype="TEXT"):
    """Crea una entidad falsa que simula TEXT o MTEXT de ezdxf."""
    ent = MagicMock()
    ent.dxftype.return_value = dxftype
    ent.dxf.layer = capa
    ent.dxf.insert = MagicMock()
    ent.dxf.insert.x = punto[0]
    ent.dxf.insert.y = punto[1]
    ent.dxf.insert.z = punto[2]
    if dxftype == "MTEXT":
        ent.text = texto
        ent.dxf.char_height = height
    else:
        ent.dxf.text = texto
        ent.dxf.height = height
    return ent


def _hacer_doc_con_textos(textos):
    """Crea un doc falso cuyo modelspace retorna las entidades texto."""
    msp = MagicMock()
    msp.__iter__ = lambda self: iter(textos)
    doc = MagicMock()
    doc.modelspace.return_value = msp
    return doc


_mod = _cargar_modulo()
procesar_atributos_anexos = _mod.procesar_atributos_anexos


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_asociacion_texto_bloque_dentro_umbral(tmp_path):
    """Un texto cercano a un bloque (dentro del umbral) se asocia correctamente."""
    fixture = _cargar_fixture()
    bloques = fixture["bloques_entrada"]
    textos_dxf = fixture["textos_dxf"]

    # CIRCUITO-01 en (5.3, 3.1) esta cerca de ELEC-T-D-t-15A en (5.0, 3.0)
    entidades = [
        _hacer_entidad_texto(t["texto"], t["capa"], t["punto"])
        for t in textos_dxf
    ]
    doc = _hacer_doc_con_textos(entidades)

    json_in = tmp_path / "re1.json"
    json_in.write_text(
        json.dumps({"bloques": bloques, "mapeo_revit": fixture["mapeo_revit"]}),
        encoding="utf-8",
    )
    json_out = tmp_path / "re5.json"

    with patch.object(_mod.ezdxf, "readfile", return_value=doc):
        resultado = procesar_atributos_anexos(
            json_in, Path("dummy.dxf"), json_out,
            chip=fixture["chip"], umbral_m=fixture["umbral_m"],
        )

    bloque_toma = next(
        b for b in resultado["bloques"] if b["nombre_bloque"] == "ELEC-T-D-t-15A"
    )
    atributos = bloque_toma["atributos_anexos"]
    assert len(atributos) >= 1
    circuito = next(
        (a for a in atributos if a["texto"] == "CIRCUITO-01"), None
    )
    assert circuito is not None
    assert circuito["tipo"] == "circuito"
    assert circuito["distancia_m"] <= fixture["umbral_m"]


def test_texto_lejos_de_todos_los_bloques_es_no_asociado(tmp_path):
    """Un texto lejos de todos los bloques (supera el umbral) va a no_asociados."""
    fixture = _cargar_fixture()
    bloques = fixture["bloques_entrada"]
    textos_dxf = fixture["textos_dxf"]

    entidades = [
        _hacer_entidad_texto(t["texto"], t["capa"], t["punto"])
        for t in textos_dxf
    ]
    doc = _hacer_doc_con_textos(entidades)

    json_in = tmp_path / "re1.json"
    json_in.write_text(
        json.dumps({"bloques": bloques, "mapeo_revit": fixture["mapeo_revit"]}),
        encoding="utf-8",
    )
    json_out = tmp_path / "re5.json"

    with patch.object(_mod.ezdxf, "readfile", return_value=doc):
        resultado = procesar_atributos_anexos(
            json_in, Path("dummy.dxf"), json_out,
            chip=fixture["chip"], umbral_m=fixture["umbral_m"],
        )

    no_asociados = [
        t for t in resultado["textos_no_asociados"]
        if t["texto"] == "PANEL PRINCIPAL"
    ]
    assert len(no_asociados) == 1
    assert no_asociados[0]["tipo"] == "panel"


def test_texto_no_electrico_no_se_asocia(tmp_path):
    """Un texto que no es electrico no genera asociacion ni aparece como no asociado."""
    fixture = _cargar_fixture()
    bloques = fixture["bloques_entrada"]
    textos_dxf = fixture["textos_dxf"]

    entidades = [
        _hacer_entidad_texto(t["texto"], t["capa"], t["punto"])
        for t in textos_dxf
    ]
    doc = _hacer_doc_con_textos(entidades)

    json_in = tmp_path / "re1.json"
    json_in.write_text(
        json.dumps({"bloques": bloques, "mapeo_revit": fixture["mapeo_revit"]}),
        encoding="utf-8",
    )
    json_out = tmp_path / "re5.json"

    with patch.object(_mod.ezdxf, "readfile", return_value=doc):
        resultado = procesar_atributos_anexos(
            json_in, Path("dummy.dxf"), json_out,
            chip=fixture["chip"], umbral_m=fixture["umbral_m"],
        )

    # "NOTA NO ELECTRICA" no debe aparecer en textos_no_asociados (no es electrico)
    textos_no_assoc = [t["texto"] for t in resultado["textos_no_asociados"]]
    assert "NOTA NO ELECTRICA" not in textos_no_assoc
    # Tampoco debe crear atributos en los bloques cercanos
    for b in resultado["bloques"]:
        textos_bloque = [a["texto"] for a in b["atributos_anexos"]]
        assert "NOTA NO ELECTRICA" not in textos_bloque


def test_clasificacion_tipo_altura(tmp_path):
    """Un texto con ALTURA se clasifica como tipo 'altura'."""
    fixture = _cargar_fixture()
    bloques = fixture["bloques_entrada"]
    # ALTURA 2.60 en (10.5, 8.2) cerca de ELEC-I-S-1-5A en (10.0, 8.0)
    texto_altura = {
        "texto": "ALTURA 2.60", "capa": "ELEC-APPL-SW", "punto": [10.5, 8.2, 0.0]
    }
    entidades = [_hacer_entidad_texto(**texto_altura)]
    doc = _hacer_doc_con_textos(entidades)

    json_in = tmp_path / "re1.json"
    json_in.write_text(
        json.dumps({"bloques": bloques, "mapeo_revit": fixture["mapeo_revit"]}),
        encoding="utf-8",
    )
    json_out = tmp_path / "re5.json"

    with patch.object(_mod.ezdxf, "readfile", return_value=doc):
        resultado = procesar_atributos_anexos(
            json_in, Path("dummy.dxf"), json_out,
            chip=fixture["chip"], umbral_m=fixture["umbral_m"],
        )

    bloque_sw = next(
        b for b in resultado["bloques"] if b["nombre_bloque"] == "ELEC-I-S-1-5A"
    )
    atributos = bloque_sw["atributos_anexos"]
    altura = next((a for a in atributos if a["texto"] == "ALTURA 2.60"), None)
    assert altura is not None
    assert altura["tipo"] == "altura"


def test_guardar_json_en_disco(tmp_path):
    """El resultado se serializa a JSON y se guarda en disco."""
    fixture = _cargar_fixture()
    bloques = fixture["bloques_entrada"]
    textos_dxf = fixture["textos_dxf"]
    entidades = [
        _hacer_entidad_texto(t["texto"], t["capa"], t["punto"])
        for t in textos_dxf
    ]
    doc = _hacer_doc_con_textos(entidades)

    json_in = tmp_path / "re1.json"
    json_in.write_text(
        json.dumps({"bloques": bloques, "mapeo_revit": fixture["mapeo_revit"]}),
        encoding="utf-8",
    )
    json_out = tmp_path / "re5.json"

    with patch.object(_mod.ezdxf, "readfile", return_value=doc):
        resultado = procesar_atributos_anexos(
            json_in, Path("dummy.dxf"), json_out,
            chip=fixture["chip"], umbral_m=fixture["umbral_m"],
        )

    assert json_out.exists()
    with open(json_out, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "metadatos" in data
    assert "resumen" in data
    assert "bloques" in data
    assert "textos_no_asociados" in data
    assert data["metadatos"]["chip"] == fixture["chip"]
    assert data["metadatos"]["umbral_m"] == fixture["umbral_m"]


def test_umbral_personalizado_excluye_asociaciones_lejanas(tmp_path):
    """Con un umbral muy pequeño, textos que antes se asociaban ya no lo hacen."""
    fixture = _cargar_fixture()
    bloques = fixture["bloques_entrada"]
    textos_dxf = fixture["textos_dxf"]
    entidades = [
        _hacer_entidad_texto(t["texto"], t["capa"], t["punto"])
        for t in textos_dxf
    ]
    doc = _hacer_doc_con_textos(entidades)

    json_in = tmp_path / "re1.json"
    json_in.write_text(
        json.dumps({"bloques": bloques, "mapeo_revit": fixture["mapeo_revit"]}),
        encoding="utf-8",
    )
    json_out = tmp_path / "re5.json"

    # Umbral de 0.1 m: CIRCUITO-01 (dist ~0.31) y ALTURA (dist ~0.54) ya no se asocian
    with patch.object(_mod.ezdxf, "readfile", return_value=doc):
        resultado = procesar_atributos_anexos(
            json_in, Path("dummy.dxf"), json_out,
            chip=fixture["chip"], umbral_m=0.1,
        )

    total_atributos = sum(
        len(b.get("atributos_anexos", [])) for b in resultado["bloques"]
    )
    assert total_atributos == 0
    # Los textos electricos ahora están en no asociados
    no_assoc_textos = {t["texto"] for t in resultado["textos_no_asociados"]}
    assert "CIRCUITO-01" in no_assoc_textos
    assert "ALTURA 2.60" in no_assoc_textos
