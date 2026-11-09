"""
================================================================================
test_RE_INVENTARIO_APARTAMENTOS_v01.py — Tests para RE_INVENTARIO_APARTAMENTOS_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 + pytest
================================================================================

OBJETIVO:
  Verificar que RE_INVENTARIO_APARTAMENTOS_v01.py:
  1. Genera el inventario maestro de apartamentos con la estructura esperada.
  2. Normaliza nombres de apartamentos ("Apatamento" -> "Apartamento").
  3. Identifica el tablero/panel (capa ELEC-POWER-PANEL o nombre TB-Parcial).
  4. Separa los marcadores de conductor (no se modelan como FamilyInstance).
  5. Asigna identificadores APT-<tipo>-<nro>-P<piso> y TAB-<tipo>-<nro>-P<piso>.
  6. Calcula altura local de montaje (z_revit) y Z absoluta estimada.
  7. Escribe el JSON de salida en disco.

FIXTURE:
  tests/fase-1-contexto/fixture_RE_INVENTARIO_APARTAMENTOS_v01.json

USO:
  pytest tests/fase-1-contexto/test_RE_INVENTARIO_APARTAMENTOS_v01.py -v
================================================================================

"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import ezdxf
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "src" / "fase-1-contexto" / "RE_INVENTARIO_APARTAMENTOS_v01.py"

spec = importlib.util.spec_from_file_location("RE_INVENTARIO_APARTAMENTOS_v01", SCRIPT_PATH)
_inventario_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_inventario_mod)

procesar_apartamento = _inventario_mod.procesar_apartamento
normalizar_nombre_apartamento = _inventario_mod.normalizar_nombre_apartamento
extraer_tipo_nro = _inventario_mod.extraer_tipo_nro
identificador_apartamento = _inventario_mod.identificador_apartamento
identificador_tablero = _inventario_mod.identificador_tablero
_es_tablero = _inventario_mod._es_tablero
_es_marcador_conductor = _inventario_mod._es_marcador_conductor

FIXTURE_PATH = Path(__file__).parent / "fixture_RE_INVENTARIO_APARTAMENTOS_v01.json"


def _cargar_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _crear_dxf_apartamento_f02(tmp_path: Path) -> Path:
    """
    Crea un DXF de prueba que simula el Apartamento Tipo F 02 con:
      - Un bloque padre "Apartamento Tipo F 02" con punto base (0,0,0).
      - INSERTs de dispositivos hijos: toma, interruptor techo, luminaria,
        toma de red (ELEC-TEL), tablero (TB-Parcial) y 2 marcadores de conductor.
    """
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Bloque padre del apartamento
    bdef_ap = doc.blocks.new(name="Apartamento Tipo F 02")
    bdef_ap.add_circle(center=(0.0, 0.0, 0.0), radius=0.01)

    # INSERTs en el espacio de modelo (simulan los bloques hijos del apartamento)
    # Toma a muro (0.3 m)
    br_toma = msp.add_blockref("ELEC-T-GFCI-t-15A", insert=(2.822, 8.7015, 0.0))
    br_toma.dxf.rotation = 0.0
    br_toma.dxf.layer = "ELEC-APPL-TOMAS"

    # Interruptor a techo (2.6 m)
    br_inter = msp.add_blockref("ELEC-I-S-1-5A", insert=(5.1072, 2.2938, 0.0))
    br_inter.dxf.rotation = 90.0
    br_inter.dxf.layer = "ELEC-APPL-ILUM"

    # Luminaria a techo (2.6 m)
    br_luz = msp.add_blockref("Bala Stil Led 10W", insert=(5.0664, 8.2472, 0.0))
    br_luz.dxf.rotation = 0.0
    br_luz.dxf.layer = "ELEC-APPL-ILUM"

    # Toma de red a muro (0.3 m)
    br_tel = msp.add_blockref("ELEC-TEL", insert=(6.1419, 7.2148, 0.0))
    br_tel.dxf.rotation = 90.0
    br_tel.dxf.layer = "ELEC-APPL-NETWORD"

    # Tablero/panel a muro (1.2 m) - capa ELEC-POWER-PANEL
    br_tablero = msp.add_blockref("TB-Parcial", insert=(3.8547, 2.7172, 0.0))
    br_tablero.dxf.rotation = 270.0
    br_tablero.dxf.layer = "ELEC-POWER-PANEL"

    # Marcadores de conductor (no se modelan como FamilyInstance)
    br_marc1 = msp.add_blockref("1FTN", insert=(6.1119, 4.038, 0.0))
    br_marc1.dxf.rotation = 90.0
    br_marc1.dxf.layer = "ELEC-Powr-Pipe-Idem Piso"

    br_marc2 = msp.add_blockref("1TNR", insert=(3.2131, 8.919, 0.0))
    br_marc2.dxf.rotation = 90.0
    br_marc2.dxf.layer = "Elec-Lite-Wire"

    dxf_path = tmp_path / "Apartamento Tipo F 02.dxf"
    doc.saveas(str(dxf_path))
    return dxf_path


# ---------------------------------------------------------------------------
# Tests de utilidades puras
# ---------------------------------------------------------------------------

def test_normalizar_nombre_apartamento_corregir_apatamento():
    """'Apatamento' se normaliza a 'Apartamento'."""
    assert normalizar_nombre_apartamento("Apatamento Tipo E 05") == "Apartamento Tipo E 05"
    assert normalizar_nombre_apartamento("Apartamento Tipo F 02") == "Apartamento Tipo F 02"


def test_normalizar_nombre_apartamento_corregir_apatamentos():
    """'Apatamentos' se normaliza a 'Apartamentos'."""
    assert normalizar_nombre_apartamento("Apatamentos Tipo E 10") == "Apartamentos Tipo E 10"


def test_extraer_tipo_nro():
    """Se extrae tipo y numero de apartamento del nombre normalizado."""
    tipo, nro = extraer_tipo_nro("Apartamento Tipo F 02")
    assert tipo == "F"
    assert nro == "02"

    tipo, nro = extraer_tipo_nro("Apartamento Tipo E2 21")
    assert tipo == "E2"
    assert nro == "21"

    tipo, nro = extraer_tipo_nro("Apartamentos Tipo F 18 y 04")
    assert tipo == "F"
    assert nro == "18 y 04"


def test_identificadores_apartamento_y_tablero():
    """Se construyen los identificadores APT y TAB correctamente."""
    assert identificador_apartamento("F", "02") == "APT-F-02-P5"
    assert identificador_tablero("F", "02") == "TAB-F-02-P5"
    assert identificador_apartamento("E2", "21") == "APT-E2-21-P5"
    assert identificador_tablero("E2", "21") == "TAB-E2-21-P5"


def test_es_tablero_detecta_por_capa():
    """El tablero se detecta por capa ELEC-POWER-PANEL."""
    assert _es_tablero("TB-Parcial", "ELEC-POWER-PANEL") is True
    assert _es_tablero("Panel Principal", "Tablero") is True
    assert _es_tablero("ELEC-T-D-t-15A", "ELEC-APPL-TOMAS") is False


def test_es_tablero_detecta_por_nombre():
    """El tablero se detecta por nombre TB-Parcial u otros nombres conocidos."""
    assert _es_tablero("TB-Parcial", "0") is True
    assert _es_tablero("TF 01", "0") is True
    assert _es_tablero("TF 02", "0") is True


def test_es_marcador_conductor():
    """Los marcadores de conductor se identifican correctamente."""
    assert _es_marcador_conductor("1FTN") is True
    assert _es_marcador_conductor("1TNR") is True
    assert _es_marcador_conductor("1FTNR") is True
    assert _es_marcador_conductor("2FT2N") is True
    assert _es_marcador_conductor("1FTN2R") is True
    assert _es_marcador_conductor("1TN2R") is True
    assert _es_marcador_conductor("1FTR") is True
    assert _es_marcador_conductor("ELEC-T-D-t-15A") is False


# ---------------------------------------------------------------------------
# Tests de procesamiento de apartamento
# ---------------------------------------------------------------------------

def test_procesar_apartamento_estructura(tmp_path: Path):
    """El resultado tiene todos los campos de la estructura de inventario."""
    dxf_path = _crear_dxf_apartamento_f02(tmp_path)
    mapeo_insertos = {
        "Apartamento Tipo F 02": {
            "x_dxf": -0.12, "y_dxf": -8.0233,
            "x_revit": 6.36, "y_revit": 2.2067,
        }
    }

    entrada = procesar_apartamento("Apartamento Tipo F 02.dxf", mapeo_insertos,
                                   ruta_dxf=str(dxf_path))

    assert entrada is not None
    assert entrada["nombre_normalizado"] == "Apartamento Tipo F 02"
    assert entrada["nombre_dxf_original"] == "Apartamento Tipo F 02.dxf"
    assert entrada["tipo"] == "F"
    assert entrada["nro"] == "02"
    assert entrada["piso"] == 5
    assert entrada["nivel_revit"] == "Piso 5"
    assert entrada["elevacion_nivel_m"] == 43.3727
    assert entrada["identificador_apartamento"] == "APT-F-02-P5"
    assert entrada["identificador_tablero"] == "TAB-F-02-P5"
    assert entrada["insert_padre_dxf"] == {"x": -0.12, "y": -8.0233}
    assert entrada["insert_revit"] == {"x": 6.36, "y": 2.2067}
    assert entrada["tiene_tablero"] is True


def test_procesar_apartamento_identifica_tablero(tmp_path: Path):
    """Se identifica el tablero TB-Parcial con sus datos."""
    dxf_path = _crear_dxf_apartamento_f02(tmp_path)
    mapeo_insertos = {
        "Apartamento Tipo F 02": {
            "x_dxf": -0.12, "y_dxf": -8.0233,
            "x_revit": 6.36, "y_revit": 2.2067,
        }
    }

    entrada = procesar_apartamento("Apartamento Tipo F 02.dxf", mapeo_insertos,
                                   ruta_dxf=str(dxf_path))

    tablero = entrada["tablero"]
    assert tablero is not None
    assert tablero["nombre_bloque_hijo"] == "TB-Parcial"
    assert tablero["capa"] == "ELEC-POWER-PANEL"
    assert tablero["x_dxf"] == 3.8547
    assert tablero["y_dxf"] == 2.7172
    assert tablero["z_local_m"] == 1.2
    assert tablero["z_absoluta_m"] == 44.5727
    assert tablero["familia_revit"] == "E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN"
    assert tablero["simbolo"] == "EPB25-304C"
    assert tablero["anfitrion"] == "muro"
    assert tablero["identificador_ancla"] == "TAB-F-02-P5"


def test_procesar_apartamento_dispositivos_hijos(tmp_path: Path):
    """Se extraen los dispositivos hijos como entidades separadas."""
    dxf_path = _crear_dxf_apartamento_f02(tmp_path)
    mapeo_insertos = {
        "Apartamento Tipo F 02": {
            "x_dxf": -0.12, "y_dxf": -8.0233,
            "x_revit": 6.36, "y_revit": 2.2067,
        }
    }

    entrada = procesar_apartamento("Apartamento Tipo F 02.dxf", mapeo_insertos,
                                   ruta_dxf=str(dxf_path))

    dispositivos = entrada["dispositivos_hijos"]
    assert entrada["total_dispositivos_hijos"] == 4
    assert len(dispositivos) == 4

    toma = dispositivos[0]
    assert toma["nombre_bloque_hijo"] == "ELEC-T-GFCI-t-15A"
    assert toma["capa"] == "ELEC-APPL-TOMAS"
    assert toma["x_dxf"] == 2.822
    assert toma["y_dxf"] == 8.7015
    assert toma["z_local_m"] == 0.3
    assert toma["familia_revit"] == "M_Toma doble"
    assert toma["simbolo"] == "GFCI"
    assert toma["anfitrion"] == "muro"

    techo = dispositivos[1]
    assert techo["nombre_bloque_hijo"] == "ELEC-I-S-1-5A"
    assert techo["z_local_m"] == 2.6
    assert techo["anfitrion"] == "ceiling"


def test_procesar_apartamento_separa_marcadores(tmp_path: Path):
    """Los marcadores de conductor se separan y no se mezclan con dispositivos."""
    dxf_path = _crear_dxf_apartamento_f02(tmp_path)
    mapeo_insertos = {
        "Apartamento Tipo F 02": {
            "x_dxf": -0.12, "y_dxf": -8.0233,
            "x_revit": 6.36, "y_revit": 2.2067,
        }
    }

    entrada = procesar_apartamento("Apartamento Tipo F 02.dxf", mapeo_insertos,
                                   ruta_dxf=str(dxf_path))

    marcadores = entrada["marcadores_conductor"]
    assert entrada["total_marcadores"] == 2
    assert len(marcadores) == 2
    nombres_marc = {m["nombre_bloque_hijo"] for m in marcadores}
    assert "1FTN" in nombres_marc
    assert "1TNR" in nombres_marc

    # Ningun marcador debe aparecer en dispositivos_hijos
    nombres_disp = {d["nombre_bloque_hijo"] for d in entrada["dispositivos_hijos"]}
    assert not (nombres_marc & nombres_disp)


def test_procesar_apartamento_offset_pendiente(tmp_path: Path):
    """El offset calculado inicia en None (pendiente de colocacion manual del tablero)."""
    dxf_path = _crear_dxf_apartamento_f02(tmp_path)
    mapeo_insertos = {
        "Apartamento Tipo F 02": {
            "x_dxf": -0.12, "y_dxf": -8.0233,
            "x_revit": 6.36, "y_revit": 2.2067,
        }
    }

    entrada = procesar_apartamento("Apartamento Tipo F 02.dxf", mapeo_insertos,
                                   ruta_dxf=str(dxf_path))

    offset = entrada["offset_calculado"]
    assert offset["offset_x"] is None
    assert offset["offset_y"] is None
    assert "pendiente de colocacion manual" in offset["nota"]


def test_fixture_estructura_salida():
    """El fixture JSON tiene la estructura esperada del inventario."""
    fixture = _cargar_fixture()
    assert fixture["version"] == "v01"
    assert fixture["proyecto"] == "RevitElectrico - T5-SantaMarta"
    assert fixture["nivel_revit"] == "Piso 5"
    assert fixture["elevacion_nivel_m"] == 43.3727
    assert fixture["total_apartamentos"] == 1
    assert fixture["apartamentos_con_tablero"] == 1
    assert "regla_datum" in fixture
    assert "tableros_oficiales" in fixture
    assert fixture["tableros_oficiales"]["F 01"] == "TAB-F-01-P5"
    assert fixture["tableros_oficiales"]["F 02"] == "TAB-F-02-P5"

    ap = fixture["apartamentos"][0]
    assert ap["identificador_apartamento"] == "APT-F-02-P5"
    assert ap["identificador_tablero"] == "TAB-F-02-P5"
    assert ap["tiene_tablero"] is True
    assert ap["tablero"]["identificador_ancla"] == "TAB-F-02-P5"


def test_apartamento_sin_tablero_marcado_como_no_tiene(tmp_path: Path):
    """Un DXF sin bloque de tablero se marca como tiene_tablero=False."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    br = msp.add_blockref("ELEC-T-D-t-15A", insert=(1.0, 2.0, 0.0))
    br.dxf.layer = "ELEC-APPL-TOMAS"

    dxf_path = tmp_path / "Apartamento Sin Tablero.dxf"
    doc.saveas(str(dxf_path))

    mapeo_insertos = {
        "Apartamento Sin Tablero": {
            "x_dxf": 0.0, "y_dxf": 0.0,
            "x_revit": 0.0, "y_revit": 0.0,
        }
    }

    entrada = procesar_apartamento("Apartamento Sin Tablero.dxf", mapeo_insertos,
                                   ruta_dxf=str(dxf_path))

    assert entrada is not None
    assert entrada["tiene_tablero"] is False
    assert entrada["tablero"] is None
    assert entrada["total_dispositivos_hijos"] == 1
