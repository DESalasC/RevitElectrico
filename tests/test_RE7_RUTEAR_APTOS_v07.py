# -*- coding: utf-8 -*-
"""Tests de la logica de agrupacion de RE7_RUTEAR_APTOS_v07.py (sin Revit).

Cubre: dedup con altura, agrupacion por recinto con validacion de
apartamento, cocina por recinto y prohibicion de agrupar por radio.
"""
import io
import json
import math
import os
import re
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, "scripts", "pyrevit", "RE7_RUTEAR_APTOS_v07.py")
FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "rooms_aptos_v07.json")

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
      "DEDUP_Z_MM": 150.0,
      "CLAVES_DATOS": ("comunicacion", "datos", "telephone", "data phones",
                       "data devices", "pau")}
_FUNCIONES = ("apto_de_mark", "es_dato", "d2", "votar_room",
              "dominante_por_room", "clave_recinto", "agrupar_normales",
              "agrupar_cocina", "dedup_por_tipo", "agrupar_por_proximidad")
exec(compile("\n".join(_extraer(f) for f in _FUNCIONES), "<v07>", "exec"), NS)

apto_de_mark = NS["apto_de_mark"]
dominante_por_room = NS["dominante_por_room"]
clave_recinto = NS["clave_recinto"]
agrupar_normales = NS["agrupar_normales"]
agrupar_cocina = NS["agrupar_cocina"]
dedup_por_tipo = NS["dedup_por_tipo"]
agrupar_por_proximidad = NS["agrupar_por_proximidad"]
es_dato = NS["es_dato"]

DISP = FIX["dispositivos"]
IDS_COCINA = set(FIX["ids_cocina"])
ESP = FIX["esperado"]
F01 = [d for d in DISP if apto_de_mark(d["mark"]) == "F01"]


def test_apto_de_mark():
    assert apto_de_mark("F01|TF 01|C1") == "F01"
    assert apto_de_mark(" f17|TF 17|C2 ") == "F17"
    assert apto_de_mark("sin prefijo") is None
    assert apto_de_mark("") is None
    assert apto_de_mark(None) is None


def test_dominante_por_room():
    dom = dominante_por_room(DISP)
    obtenido = dict((str(k), v) for k, v in dom.items())
    assert obtenido == ESP["dominante_room"], obtenido


def test_clave_recinto_respeta_apartamento():
    dom = dominante_por_room(DISP)
    por_id = dict((d["id"], d) for d in DISP)
    assert list(clave_recinto(por_id[1], dom)) == ESP["clave_apto_f01_room_10"]
    assert list(clave_recinto(por_id[5], dom)) == ESP["clave_apto_f17_room_10"]
    assert clave_recinto(por_id[6], dom) is None


def test_dedup_no_colapsa_alturas_distintas():
    reps, dedup = dedup_por_tipo(F01)
    assert dedup == ESP["dedup_f01"], dedup
    # las cuatro tomas GFCI (0.70/1.05/1.65/2.80) sobreviven
    gfci = sorted(d["id"] for d in reps if d["tipo"] == "Toma GFCI")
    assert gfci == [9, 10, 11, 12], gfci


def test_agrupar_normales_por_recinto():
    dom = dominante_por_room(DISP)
    no_coc = [d for d in F01 if d["id"] not in IDS_COCINA]
    reps, _ = dedup_por_tipo(no_coc)
    normales = [d for d in reps if not es_dato(d["familia"], d["tipo"])]
    grupos, sin = agrupar_normales(normales, dom)
    assert len(grupos) == ESP["grupos_normales"], grupos
    assert len(sin) == ESP["normales_sin_recinto"], sin
    assert sorted(grupos) == [("host", 901), ("room", 10)], sorted(grupos)


def test_cocina_por_recinto():
    dom = dominante_por_room(DISP)
    coc = [d for d in F01 if d["id"] in IDS_COCINA]
    grupos = agrupar_cocina(coc, dom, "F01")
    assert len(grupos) == ESP["grupos_cocina"], [len(g) for g in grupos]
    tamanos = sorted(len(g) for g in grupos)
    assert tamanos == [1, ESP["cocina_room_12"]], tamanos
    # el grupo grande es el del room 12, con las tres alturas
    grande = max(grupos, key=len)
    assert set(d["room_id"] for d in grande) == {12}
    assert sorted(d["pt"][2] for d in grande) == [13620.0, 13920.0, 14220.0]


def test_cocina_sin_recinto_cae_a_proximidad():
    dom = dominante_por_room(DISP)
    sin_room = [
        {"id": 20, "pt": [0.0, 0.0, 13920.0], "mark": "F01|X|C1",
         "familia": "M_Toma", "tipo": "Toma", "room_id": None, "host_id": 1},
        {"id": 21, "pt": [100.0, 0.0, 14220.0], "mark": "F01|X|C1",
         "familia": "M_Toma", "tipo": "Toma", "room_id": None, "host_id": 1},
        {"id": 22, "pt": [3000.0, 0.0, 14220.0], "mark": "F01|X|C2",
         "familia": "M_Toma", "tipo": "Toma", "room_id": None, "host_id": 1},
    ]
    grupos = agrupar_cocina(sin_room, dom, "F01")
    assert sorted(len(g) for g in grupos) == [1, 2], [len(g) for g in grupos]


def test_datos_agrupados():
    reps, _ = dedup_por_tipo(F01)
    datos = [d for d in reps if es_dato(d["familia"], d["tipo"])]
    assert len(datos) == 1
    assert len(agrupar_por_proximidad(datos, 200.0)) == ESP["grupos_datos"]


def test_sin_agrupacion_por_radio():
    """Decision del operador: prohibido agrupar por radio."""
    assert "RADIO_NORMAL_MM" not in CODIGO
    assert "RUTEO_RADIO_M" not in CODIGO
