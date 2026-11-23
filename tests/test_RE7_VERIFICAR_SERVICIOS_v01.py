# -*- coding: utf-8 -*-
"""Tests de la verificacion por servicios (funciones puras, sin Revit)."""
import io
import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, "scripts", "pyrevit", "RE7_VERIFICAR_SERVICIOS_v01.py")
FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "servicios_v01.json")

with io.open(SRC, encoding="utf-8") as f:
    CODIGO = f.read()

with io.open(FIXTURE, encoding="utf-8") as f:
    FIX = json.load(f)


def _extraer(nombre):
    patron = r"^def %s\(.*?(?=^def |\Z)" % nombre
    m = re.search(patron, CODIGO, re.S | re.M)
    assert m, "no se encontro %s" % nombre
    return m.group(0)


NS = {"TOL_MM": 2.0, "math": __import__("math")}
exec(compile("\n".join(_extraer(f) for f in ("cerca", "verificar")), "<v>", "exec"), NS)
verificar = NS["verificar"]
cerca = NS["cerca"]


def test_cerca():
    assert cerca([0.0, 0.0, 0.0], [1.5, -1.5, 1.0])
    assert not cerca([0.0, 0.0, 0.0], [3.0, 0.0, 0.0])


def test_verificar_ok():
    tramos = [{"conduit_id": 10, "tipo": "vertical_toma", "servicio": "TOMAS",
               "diam_mm": 16.0, "a": [0.0, 0.0, 14220.0],
               "b": [0.0, 0.0, 15920.0]}]
    modelo = {10: {"a": [0.0, 0.0, 14220.0], "b": [0.0, 0.0, 15920.0],
                   "diam": 16.0, "servicio": "TOMAS"}}
    r = verificar(tramos, modelo)
    assert r["ok"] == 1 and not r["sin_conduit"] and not r["mal_diam"]
    assert not r["mal_extremos"] and not r["mal_servicio"] and not r["sobrantes"]


def test_verificar_detecta_todo():
    tramos = [{"conduit_id": 1, "tipo": "t", "servicio": "TOMAS",
               "diam_mm": 16.0, "a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 100.0]},
              {"conduit_id": 2, "tipo": "t", "servicio": "TOMAS",
               "diam_mm": 16.0, "a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 100.0]},
              {"conduit_id": 3, "tipo": "t", "servicio": "TOMAS",
               "diam_mm": 16.0, "a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 100.0]},
              {"conduit_id": 4, "tipo": "t", "servicio": "TOMAS",
               "diam_mm": 16.0, "a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 100.0]}]
    modelo = {1: {"a": [50.0, 0.0, 0.0], "b": [50.0, 0.0, 100.0],
                  "diam": 16.0, "servicio": "TOMAS"},          # extremos mal
              2: {"a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 100.0],
                  "diam": 19.0, "servicio": "TOMAS"},          # diametro mal
              3: {"a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 100.0],
                  "diam": 16.0, "servicio": "ILUMINACION"},    # servicio mal
              5: {"a": [9.0, 9.0, 9.0], "b": [9.0, 9.0, 10.0],
                  "diam": 16.0, "servicio": "TOMAS"}}          # sobrante
    r = verificar(tramos, modelo)
    assert r["ok"] == 0
    assert [e["id"] for e in r["mal_extremos"]] == [1]
    assert [e["id"] for e in r["mal_diam"]] == [2]
    assert [e["id"] for e in r["mal_servicio"]] == [3]
    assert r["sin_conduit"][0]["conduit_id"] == 4
    assert r["sobrantes"] == [5]
