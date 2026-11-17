# -*- coding: utf-8 -*-
"""Tests de F0: congelado del corpus de ruteo (V02-f)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ / "src" / "fase-6-revit" / "RE_F0_CONGELAR_CORPUS_v01.py"


def cargar_modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("re_f0_corpus", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("No se pudo cargar {r}".format(r=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = cargar_modulo()

CONDUITS = [
    {"id": 1, "servicio": "TOMAS", "diam_mm": 21.0, "long_mm": 1000.0,
     "a": [11600, 7500, 14200], "b": [11700, 7500, 14200]},
    {"id": 2, "servicio": "", "diam_mm": 27.0, "long_mm": 500.0,
     "a": [11700, 7500, 14200], "b": [11800, 7500, 14200]},
    {"id": 3, "servicio": "ILUMINACION", "diam_mm": 21.0, "long_mm": 700.0,
     "a": [0, 0, 288220], "b": [700, 0, 288220]},
    {"id": 4, "servicio": "TOMAS", "diam_mm": 21.0, "long_mm": 200.0,
     "a": [218384, 251269, 14200], "b": [218384, 251969, 14200]},
]
DISPOSITIVOS = [
    {"id": 10, "fam": "M_Toma doble", "tipo": "Normal", "x": 11600, "y": 7500, "z": 14200},
    {"id": 11, "fam": "M_Caja de conexiones hexagonal", "tipo": "120V",
     "x": 11700, "y": 7500, "z": 14200},
    {"id": 12, "fam": "M_Toma doble", "tipo": "Normal", "x": 0, "y": 0, "z": 28924},
    {"id": 13, "fam": "M_Toma doble", "tipo": "Normal", "x": 40000, "y": 7500, "z": 14200},
]


def test_excluye_tramos_fuera_de_rango_y_sin_servicio():
    corpus = MOD.congelar(DISPOSITIVOS, CONDUITS)
    ids = [c["id"] for c in corpus["conduits"]]
    assert ids == [1]
    motivos = {d["id"]: d["motivo"] for d in corpus["metricas"]["descartes_conduits"]}
    assert motivos == {2: "sin_servicio", 3: "fuera_de_rango", 4: "fuera_de_rango"}


def test_excluye_dispositivos_fuera_de_rango_o_de_unidad():
    corpus = MOD.congelar(DISPOSITIVOS, CONDUITS)
    ids = [d["id"] for d in corpus["dispositivos"]]
    assert ids == [10, 11]
    motivos = {d["id"]: d["motivo"] for d in corpus["metricas"]["descartes_dispositivos"]}
    assert motivos[12] == "fuera_de_rango"
    assert motivos[13] == "fuera_de_unidad"


def test_metricas_basicas():
    corpus = MOD.congelar(DISPOSITIVOS, CONDUITS)
    m = corpus["metricas"]
    assert m["tramos"] == 1
    assert m["longitud_m"] == 1.0
    assert m["dispositivos"] == 2
    assert m["aparatos"] == 1
    assert m["cajas"] == 1
    assert m["m_por_aparato"] == 1.0
    assert m["por_servicio"] == {"TOMAS": 1}
    assert m["por_unidad"] == {"F 01": 2}


def test_hash_estable(tmp_path):
    corpus = MOD.congelar(DISPOSITIVOS, CONDUITS)
    h1 = MOD.escribir_corpus(corpus, tmp_path / "a")
    h2 = MOD.escribir_corpus(corpus, tmp_path / "b")
    assert h1 == h2
    assert set(h1) == {"dispositivos.json", "conduits.json", "metricas.json"}
