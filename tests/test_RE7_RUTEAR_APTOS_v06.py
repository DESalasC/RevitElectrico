# -*- coding: utf-8 -*-
"""Tests de la logica de agrupacion de RE7_RUTEAR_APTOS_v06.py (sin Revit).

Levanta las funciones puras del script pyRevit por texto (mismo patron que
tests/test_red_todos_aptos.py) y las contrasta con el fixture JSON.
"""
import io
import json
import math
import os
import re
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, "scripts", "pyrevit", "RE7_RUTEAR_APTOS_v06.py")
FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "rooms_aptos_v06.json")

with io.open(SRC, encoding="utf-8") as f:
    CODIGO = f.read()

with io.open(FIXTURE, encoding="utf-8") as f:
    FIX = json.load(f)


def _extraer(nombre):
    patron = r"^def %s\(.*?(?=^def |\Z)" % nombre
    m = re.search(patron, CODIGO, re.S | re.M)
    assert m, "no se encontro la funcion %s en %s" % (nombre, SRC)
    return m.group(0)


NS = {"math": math, "defaultdict": defaultdict, "DEDUP_MM": 150.0,
      "CLAVES_DATOS": ("comunicacion", "datos", "telephone", "data phones",
                       "data devices", "pau")}
_FUNCIONES = ("apto_de_mark", "es_dato", "d2", "votar_room",
              "dominante_por_room", "clave_recinto", "agrupar_normales",
              "dedup_por_tipo", "agrupar_por_proximidad")
exec(compile("\n".join(_extraer(f) for f in _FUNCIONES), "<v06>", "exec"), NS)

apto_de_mark = NS["apto_de_mark"]
dominante_por_room = NS["dominante_por_room"]
clave_recinto = NS["clave_recinto"]
agrupar_normales = NS["agrupar_normales"]
dedup_por_tipo = NS["dedup_por_tipo"]
agrupar_por_proximidad = NS["agrupar_por_proximidad"]
votar_room = NS["votar_room"]

DISP = FIX["dispositivos"]
IDS_COCINA = set(FIX["ids_cocina"])
ESP = FIX["esperado"]


def test_apto_de_mark():
    assert apto_de_mark("F01|TF 01|C1") == "F01"
    assert apto_de_mark(" f17|TF 17|C2 ") == "F17"
    assert apto_de_mark("sin prefijo") is None
    assert apto_de_mark("") is None
    assert apto_de_mark(None) is None
    assert ESP["apto_mark"]["F17|TF 17|C1"] == apto_de_mark("F17|TF 17|C1")


def test_votar_room():
    assert votar_room([10, 10, 11]) == 10
    assert votar_room([None, None, 12]) == 12
    assert votar_room([11, 12]) == 11
    assert votar_room([]) is None


def test_dominante_por_room():
    dom = dominante_por_room(DISP)
    obtenido = dict((str(k), v) for k, v in dom.items())
    assert obtenido == ESP["dominante_room"], obtenido


def test_clave_recinto_respeta_apartamento():
    dom = dominante_por_room(DISP)
    por_id = dict((d["id"], d) for d in DISP)
    # aparato F01 dentro de un room F01 -> room
    assert list(clave_recinto(por_id[1], dom)) == ESP["clave_apto_f01_room_10"]
    # aparato F17 dentro de un room dominado por F01 -> vuelve al muro host
    assert list(clave_recinto(por_id[5], dom)) == ESP["clave_apto_f17_room_10"]
    # sin room y sin host -> sin recinto
    assert clave_recinto(por_id[6], dom) is None


def test_agrupar_normales_por_recinto():
    dom = dominante_por_room(DISP)
    f01 = [d for d in DISP if apto_de_mark(d["mark"]) == "F01"
           and d["id"] not in IDS_COCINA]
    reps, _ = dedup_por_tipo(f01)
    normales = [d for d in reps if not NS["es_dato"](d["familia"], d["tipo"])]
    grupos, sin = agrupar_normales(normales, dom)
    assert len(grupos) == ESP["grupos_normales"], grupos
    assert len(sin) == ESP["normales_sin_recinto"], sin
    claves = sorted(grupos)
    assert claves == [("host", 901), ("room", 10)], claves
    for clave, miembros in grupos.items():
        assert all(apto_de_mark(m["mark"]) == "F01" for m in miembros)


def test_dedup_y_grupos_cocina_datos():
    f01 = [d for d in DISP if apto_de_mark(d["mark"]) == "F01"]
    reps, dedup = dedup_por_tipo(f01)
    assert dedup == 2, dedup  # comunicaciones 7/8 (40 mm) + GFCI 9/10 (misma XY)
    coc = [d for d in reps if d["id"] in IDS_COCINA]
    assert [d["id"] for d in coc] == [10], [d["id"] for d in coc]
    assert len(agrupar_por_proximidad(coc, 200.0)) == ESP["grupos_cocina"]
    datos = [d for d in reps if NS["es_dato"](d["familia"], d["tipo"])]
    assert len(datos) == 1
    assert len(agrupar_por_proximidad(datos, 200.0)) == ESP["grupos_datos"]


def test_sin_agrupacion_por_radio():
    """Decision del operador: prohibido agrupar por radio."""
    assert "RADIO_NORMAL_MM" not in CODIGO
    assert "RUTEO_RADIO_M" not in CODIGO
