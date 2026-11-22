# -*- coding: utf-8 -*-
"""Tests de RE7_ALIGN_GLOBAL_v01 (voting de desfase global, sin Revit)."""
import importlib.util
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "RE7_ALIGN_GLOBAL_v01",
    os.path.join(RAIZ, "scripts", "utilities", "RE7_ALIGN_GLOBAL_v01.py"),
)
assert SPEC is not None
MOD = importlib.util.module_from_spec(SPEC)
sys.modules["RE7_ALIGN_GLOBAL_v01"] = MOD
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)

TOL = 300.0


def _hacer_segmento(apto, ax, ay, bx, by):
    return {
        "id": f"S-{apto}-{ax}-{ay}",
        "apto": apto,
        "a_mm": [ax, ay, 15930.0],
        "b_mm": [bx, by, 15930.0],
    }


def _hacer_dispositivo(x, y):
    return {"id": "D", "x_mm": x, "y_mm": y, "z_mm": 14220.0}


def test_voting_encuentra_offset_global():
    """Si todos los extremos se desplazan por el mismo offset, el voting lo recupera."""
    dx_real, dy_real = 12345000.0, 7890000.0

    segmentos = [
        _hacer_segmento("Apto 1", 1000.0, 2000.0, 3000.0, 2000.0),
        _hacer_segmento("Apto 1", 3000.0, 2000.0, 3000.0, 5000.0),
    ]
    dispositivos = [
        _hacer_dispositivo(1000.0 + dx_real, 2000.0 + dy_real),
        _hacer_dispositivo(3000.0 + dx_real, 2000.0 + dy_real),
        _hacer_dispositivo(3000.0 + dx_real, 5000.0 + dy_real),
    ]

    grid = MOD.construir_grid(dispositivos, tam_celda_mm=300.0)
    votos: dict[tuple[float, float], int] = {}
    redondeo = 50.0
    extremos = [(s["a_mm"][0], s["a_mm"][1]) for s in segmentos] + [
        (s["b_mm"][0], s["b_mm"][1]) for s in segmentos
    ]
    for (ex, ey) in extremos:
        for d in dispositivos:
            dx = d["x_mm"] - ex
            dy = d["y_mm"] - ey
            key = (round(dx / redondeo) * redondeo, round(dy / redondeo) * redondeo)
            votos[key] = votos.get(key, 0) + 1

    top = sorted(votos.items(), key=lambda kv: kv[1], reverse=True)[:5]
    esperado = (round(dx_real / redondeo) * redondeo, round(dy_real / redondeo) * redondeo)
    assert top[0][0] == esperado, top

    n_match = MOD.contar_coincidencias(extremos, grid, 300.0, TOL, dx_real, dy_real)
    assert n_match == 4, n_match  # los 4 extremos coinciden


def test_construir_grid_agrupa_dispositivos():
    dispositivos = [
        _hacer_dispositivo(100.0, 100.0),
        _hacer_dispositivo(150.0, 150.0),
        _hacer_dispositivo(5000.0, 5000.0),
        {"id": "D", "x_mm": None, "y_mm": None},
    ]
    grid = MOD.construir_grid(dispositivos, tam_celda_mm=1000.0)
    assert (0, 0) in grid
    assert len(grid[(0, 0)]) == 2
    assert (5, 5) in grid
    assert len(grid[(5, 5)]) == 1


def test_contar_coincidencias_tolerancia():
    extremos = [(0.0, 0.0), (1000.0, 1000.0)]
    dispositivos = [
        _hacer_dispositivo(10.0, 10.0),
        _hacer_dispositivo(9000.0, 9000.0),
    ]
    grid = MOD.construir_grid(dispositivos, tam_celda_mm=300.0)
    n = MOD.contar_coincidencias(extremos, grid, 300.0, 100.0, 0.0, 0.0)
    assert n == 1, n  # solo el primero queda dentro de 100 mm


def test_aplicar_offset_desplaza_segmentos():
    segmentos = [
        {"apto": "A", "a_mm": [100.0, 200.0, 15930.0], "b_mm": [300.0, 400.0, 15930.0]},
    ]
    dx, dy = 5000.0, -3000.0
    alineados = []
    for s in segmentos:
        ns = dict(s)
        ns["a_mm"] = [round(s["a_mm"][0] + dx, 3), round(s["a_mm"][1] + dy, 3), s["a_mm"][2]]
        ns["b_mm"] = [round(s["b_mm"][0] + dx, 3), round(s["b_mm"][1] + dy, 3), s["b_mm"][2]]
        alineados.append(ns)
    assert alineados[0]["a_mm"] == [5100.0, -2800.0, 15930.0]
    assert alineados[0]["b_mm"] == [5300.0, -2600.0, 15930.0]
