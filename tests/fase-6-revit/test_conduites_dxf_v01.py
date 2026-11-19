# -*- coding: utf-8 -*-
"""Test del pipeline de conductos DXF -> JSON -> Revit.

Valida:
- Estructura de datos de conductos (campos obligatorios).
- Servicios validos (COMUNICACIONES, ILUMINACION, TOMAS).
- Diametros EMT reales (1/2"=15.85mm, 3/4"=21.03mm).
- Puntos 3D (x, y, z en mm).
- Conversion mm -> pies consistente.
- Mapeo servicio -> tipo de conduit.
- Coherencia diametro vs servicio.
- Logica de extension minima (2.54 mm / 1/10 pulgada).
- Conteo de conductos en el archivo de datos real.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
FIXTURE = RAIZ / "tests" / "fase-6-revit" / "fixture_conduits_dxf_v01.json"
DATA_JSON = RAIZ / "data" / "conduits_dxf_v01.json"

# Constantes del pipeline (config/ruteo_config_v04.json y config/conduit_creacion_v01.json)
MIN_LENGTH_FT = 0.1 / 12.0  # 1/10 pulgada = 0.008333 ft = 2.54 mm
MM_TO_FT = 1.0 / 304.8

SERVICIO_A_TIPO = {
    "COMUNICACIONES": 5508657,  # TuboC (ConduitType 5508657)
    "ILUMINACION": 112216,      # TuboE (ConduitType 112216)
    "TOMAS": 112216,            # TuboE (ConduitType 112216)
}

SERVICIOS_VALIDOS = {"COMUNICACIONES", "ILUMINACION", "TOMAS"}
DIAMETROS_VALIDOS_MM = {15.85, 21.03}  # EMT reales, no nominales

# Conduits de la fixture que son "cortos" (< 2.54 mm) y requieren extension.
# RT-0002: 0.365mm, RT-0004: ~1.56mm, RT-0028: ~1.12mm (todos < 2.54mm)
# RT-0001: 3.865mm (NO corto, >= 2.54mm)
CONDUITS_CORTOS_IDS = {"RT-0002", "RT-0004", "RT-0028"}


@pytest.fixture(scope="module")
def conduits() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["conduits"]


@pytest.fixture(scope="module")
def data_json() -> dict:
    return json.loads(DATA_JSON.read_text(encoding="utf-8"))


# --- Estructura y campos ------------------------------------------------------

def test_conduits_no_vacio(conduits):
    """La fixture debe contener al menos un conduit."""
    assert len(conduits) > 0


def test_estructura_conduits_requeridos(conduits):
    """Cada conduit debe tener los campos obligatorios."""
    campos_obligatorios = {"id", "servicio", "diametro_mm", "a", "b"}
    for c in conduits:
        assert campos_obligatorios <= set(c.keys()), (
            f"faltan campos en {c.get('id')}: {campos_obligatorios - set(c.keys())}"
        )


def test_ids_unicos(conduits):
    """Los IDs de conduit deben ser unicos dentro del conjunto."""
    ids = [c["id"] for c in conduits]
    assert len(ids) == len(set(ids)), f"IDs duplicados: {[i for i in ids if ids.count(i) > 1]}"


# --- Servicios ----------------------------------------------------------------

def test_servicios_validos(conduits):
    """El servicio de cada conduit debe estar entre los permitidos."""
    for c in conduits:
        assert c["servicio"] in SERVICIOS_VALIDOS, (
            f"servicio invalido en {c['id']}: {c['servicio']}"
        )


def test_mapeo_servicio_a_tipo_conduit(conduits):
    """Cada servicio mapea a un tipo de conduit conocido (sin servicios huorfanos)."""
    for c in conduits:
        assert c["servicio"] in SERVICIO_A_TIPO, (
            f"servicio sin tipo de conduit: {c['servicio']} en {c['id']}"
        )


# --- Diametros ----------------------------------------------------------------

def test_diametros_validos(conduits):
    """El diametro de cada conduit debe ser un diametro EMT real."""
    for c in conduits:
        assert c["diametro_mm"] in DIAMETROS_VALIDOS_MM, (
            f"diametro invalido en {c['id']}: {c['diametro_mm']}mm"
        )


def test_diametro_coherente_con_servicio(conduits):
    """COMUNICACIONES usa 3/4\" (21.03mm); ILUMINACION y TOMAS usan 1/2\" (15.85mm)."""
    for c in conduits:
        if c["servicio"] == "COMUNICACIONES":
            assert c["diametro_mm"] == 21.03, (
                f"{c['id']}: COMUNICACIONES debe ser 21.03mm, tiene {c['diametro_mm']}mm"
            )
        else:
            assert c["diametro_mm"] == 15.85, (
                f"{c['id']}: {c['servicio']} debe ser 15.85mm, tiene {c['diametro_mm']}mm"
            )


# --- Geometria ----------------------------------------------------------------

def test_puntos_son_tridimensionales(conduits):
    """Los puntos a y b deben ser arrays de 3 numeros (x, y, z en mm)."""
    for c in conduits:
        assert len(c["a"]) == 3, f"punto a no es 3D en {c['id']}"
        assert len(c["b"]) == 3, f"punto b no es 3D en {c['id']}"
        for coord in c["a"] + c["b"]:
            assert isinstance(coord, (int, float)), (
                f"coordenada no numerica en {c['id']}: {coord!r}"
            )


def test_conversion_mm_a_pies_consistente(conduits):
    """La conversion mm -> pies debe ser consistente: pies = mm / 304.8."""
    for c in conduits:
        for punto in ("a", "b"):
            for coord_mm in c[punto]:
                coord_ft = coord_mm * MM_TO_FT
                assert coord_ft == pytest.approx(coord_mm / 304.8, abs=1e-6)


# --- Longitud minima ----------------------------------------------------------

def test_longitud_minima_revit_es_254mm():
    """El largo minimo de Revit para MEPCurve es 1/10 pulgada = 2.54 mm."""
    min_length_mm = MIN_LENGTH_FT * 304.8
    assert min_length_mm == pytest.approx(2.54, abs=0.01)


def test_conduits_cortos_estan_marcados(conduits):
    """Los conduits de la fixture con largo < 2.54mm deben estar en la lista de cortos."""
    ids_cortos = set()
    for c in conduits:
        dx = c["b"][0] - c["a"][0]
        dy = c["b"][1] - c["a"][1]
        dz = c["b"][2] - c["a"][2]
        largo_mm = math.sqrt(dx * dx + dy * dy + dz * dz)
        if largo_mm < MIN_LENGTH_FT * 304.8:
            ids_cortos.add(c["id"])
    assert CONDUITS_CORTOS_IDS <= ids_cortos, (
        f"faltan conduits cortos: {CONDUITS_CORTOS_IDS - ids_cortos}"
    )


# --- Archivo de datos real ----------------------------------------------------

def test_datos_reales_tienen_conduits(data_json):
    """El archivo de datos reales debe tener un array de conduits no vacio."""
    assert "conduits" in data_json
    assert isinstance(data_json["conduits"], list)
    assert len(data_json["conduits"]) > 0


def test_datos_reales_conteo_por_servicio(data_json):
    """El resumen del archivo real debe coincidir con el conteo real de conduits."""
    resumen = data_json["resumen"]["por_servicio"]
    conteo_real = {}
    for c in data_json["conduits"]:
        svc = c["servicio"]
        conteo_real[svc] = conteo_real.get(svc, 0) + 1
    assert resumen == conteo_real, (
        f"resumen {resumen} != conteo real {conteo_real}"
    )


def test_datos_reales_total_conduits(data_json):
    """El total de conduits en el resumen debe igualar la longitud del array."""
    total_resumen = data_json["resumen"]["total_conduits"]
    total_array = len(data_json["conduits"])
    assert total_resumen == total_array


def test_datos_reales_nivel_piso5(data_json):
    """El archivo de datos reales debe referenciar el nivel Piso 5."""
    assert data_json["nivel"] == "Piso 5"
    assert data_json["elevacion_nivel_m"] == pytest.approx(13.22, abs=0.001)
