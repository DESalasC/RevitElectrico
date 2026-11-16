# -*- coding: utf-8 -*-
"""El mapeo DXF -> familia|tipo del colocador debe existir en el catalogo de CENTRAL-V01.

Motivo: `MAPEO_DEFAULT` tenia dos entradas de una version anterior del modelo
(`ELEC-TEL -> Telefono` y `ELEC-I-S-C1-5A -> Conmutable`) mientras CENTRAL-V01 usa `Datos` y
`Simple conmutable`. Colocar con el mapeo viejo habria creado tipos distintos a los de E 06.

El mapeo se extrae por AST del propio script: una sola fuente de verdad.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUTA_COLOCADOR = RAIZ / "src" / "fase-6-revit" / "RE_COLOCAR_DISPOSITIVOS_generico.py"
RUTA_CATALOGO = RAIZ / "config" / "catalogo_familias_CENTRAL_V01_v01.json"


def mapeo_por_ast() -> dict:
    arbol = ast.parse(RUTA_COLOCADOR.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign):
            for destino in nodo.targets:
                if getattr(destino, "id", None) == "MAPEO_DEFAULT":
                    return ast.literal_eval(nodo.value)
    raise AssertionError("MAPEO_DEFAULT no encontrado en el colocador")


@pytest.fixture(scope="module")
def mapeo() -> dict:
    return mapeo_por_ast()


@pytest.fixture(scope="module")
def catalogo() -> set:
    datos = json.loads(RUTA_CATALOGO.read_text(encoding="utf-8"))
    return {(f["familia"], f["tipo"]) for f in datos["familias"]}


def test_el_mapeo_se_puede_leer(mapeo: dict) -> None:
    assert len(mapeo) >= 14
    for codigo, par in mapeo.items():
        assert isinstance(par, tuple) and len(par) == 2, codigo


def test_todo_el_mapeo_existe_en_el_catalogo(mapeo: dict, catalogo: set) -> None:
    """Si un par no esta en CENTRAL-V01, la colocacion crearia un tipo inexistente."""
    faltantes = sorted(k for k, v in mapeo.items() if v not in catalogo)
    assert not faltantes, "pares fuera del catalogo: {f}".format(f=faltantes)


def test_las_dos_correcciones_del_operador(mapeo: dict) -> None:
    assert mapeo["ELEC-TEL"] == ("M_Comunicaciones", "Datos")
    assert mapeo["ELEC-I-S-C1-5A"] == ("M_Interruptores", "Simple conmutable")


def test_las_tomas_y_luminarias_no_cambian(mapeo: dict) -> None:
    assert mapeo["ELEC-T-D-t-15A"] == ("M_Toma doble", "Normal")
    assert mapeo["ELEC-T-GFCI-t-15A"] == ("M_Toma doble", "GFCI")
    assert mapeo["Bala Stil Led 13W"] == ("M_Iluminacion", "SONO FLEX 13 trim")
    assert mapeo["ELEC-CAMPANA"] == ("M_Timbre", "Campana")
    assert mapeo["ELEC-F-VENT"] == ("M_ClimatizacionV", "Ventilador")
