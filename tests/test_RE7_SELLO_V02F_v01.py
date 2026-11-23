# -*- coding: utf-8 -*-
"""Tests del analisis del sello V02-f y del export sellado (sin Revit)."""
import importlib.util
import io
import json
import math
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALISIS = os.path.join(RAIZ, "scripts", "RE7_ANALIZAR_SELLO_V02F_v01.py")
SELLO_PYREVIT = os.path.join(RAIZ, "scripts", "pyrevit",
                             "RE7_EXPORTAR_V02F_SELLADO_v01.py")
FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "sello_v02f_v01.json")


def _cargar_modulo(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, archivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


AN = _cargar_modulo("RE7_ANALIZAR_SELLO_V02F_v01", ANALISIS)

with io.open(FIXTURE, encoding="utf-8") as f:
    FIX = json.load(f)


def _segs(lista):
    return [(q["a"], q["b"]) for q in lista]


def test_cobertura_red_identica():
    red = _segs(FIX["red_nuestra"])
    puntos = []
    for a, b in red:
        puntos.extend(AN.muestrear(a, b, 500.0))
    cov = AN.cobertura(puntos, red)
    assert cov["pct_dentro_300"] == FIX["esperado"]["cobertura_identica_pct_300"]
    assert cov["mediana_mm"] == 0.0


def test_cobertura_tramo_lejos():
    red = _segs(FIX["red_nuestra"])
    puntos = []
    for a, b in _segs(FIX["red_v02f_lejos"]):
        puntos.extend(AN.muestrear(a, b, 500.0))
    cov = AN.cobertura(puntos, red)
    assert cov["pct_dentro_300"] == FIX["esperado"]["cobertura_tramo_extra_pct_300"]


def test_vecino_mas_cercano():
    puntos = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)]
    candidatos = [(0.0, 0.0, 0.0), (90.0, 0.0, 0.0)]
    r = AN.vecino_mas_cercano(puntos, candidatos)
    assert r["mediana_mm"] == 10.0
    assert r["pct_dentro_150"] == 100.0
    assert AN.vecino_mas_cercano([], []) is None


def test_emparejar_extremos():
    base = _segs(FIX["red_nuestra"])
    n, sin = AN.emparejar_extremos(base, base, 50.0)
    assert n == FIX["esperado"]["emparejados_identicos"], (n, sin)
    desplazados = [((a[0] + 100.0, a[1], a[2]), (b[0] + 100.0, b[1], b[2]))
                   for a, b in base]
    n2, _ = AN.emparejar_extremos(base, desplazados, 50.0)
    assert n2 == FIX["esperado"]["emparejados_desplazados"], n2


def test_bbox_y_dentro_de():
    segs = _segs(FIX["red_nuestra"])
    caja = AN.bbox(segs)
    assert caja == (0.0, 3000.0, 0.0, 2000.0, 15930.0, 15930.0)
    assert AN.dentro_de(segs[0], caja)
    assert not AN.dentro_de(segs[0], (10000, 20000, 10000, 20000, 0, 1))


def test_ascii_seguro_del_sello():
    with io.open(SELLO_PYREVIT, encoding="utf-8") as f:
        codigo = f.read()
    m = re.search(r"^def ascii_seguro\(.*?(?=^def |\Z)", codigo, re.S | re.M)
    assert m, "no se encontro ascii_seguro en el script del sello"
    ns = {"unicode": str}
    exec(compile(m.group(0), "<sello>", "exec"), ns)
    ascii_seguro = ns["ascii_seguro"]
    assert ascii_seguro("Tuberia") == "Tuberia"
    assert ascii_seguro(u"Tubería") == "Tuber?a"
    assert ascii_seguro("Tubería") == "Tuber?a"
    assert ascii_seguro(None) is None
