# -*- coding: utf-8 -*-
"""Tests de la logica de agrupacion de RE7_RUTEAR_APTOS_v09.py (sin Revit).

Variante adoptada: clave de bajante (room, muro host), sin agrupar por radio.
"""
import io
import json
import math
import os
import re
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, "scripts", "pyrevit", "RE7_RUTEAR_APTOS_v09.py")
FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "rooms_aptos_v09.json")

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
exec(compile("\n".join(_extraer(f) for f in _FUNCIONES), "<v09>", "exec"), NS)

apto_de_mark = NS["apto_de_mark"]
dominante_por_room = NS["dominante_por_room"]
clave_recinto = NS["clave_recinto"]
agrupar_normales = NS["agrupar_normales"]
agrupar_cocina = NS["agrupar_cocina"]
dedup_por_tipo = NS["dedup_por_tipo"]
es_dato = NS["es_dato"]

DISP = FIX["dispositivos"]
IDS_COCINA = set(FIX["ids_cocina"])
ESP = FIX["esperado"]
F01 = [d for d in DISP if apto_de_mark(d["mark"]) == "F01"]
POR_ID = dict((d["id"], d) for d in DISP)


def test_clave_room_y_muro():
    dom = dominante_por_room(DISP)
    assert list(clave_recinto(POR_ID[1], dom)) == ESP["clave_room_con_muro"]
    assert list(clave_recinto(POR_ID[3], dom)) == ESP["clave_room_sin_muro"]
    assert list(clave_recinto(POR_ID[5], dom)) == ESP["clave_muro_de_otro_apto"]
    assert clave_recinto(POR_ID[6], dom) is None


def test_agrupar_normales_separa_por_muro():
    dom = dominante_por_room(DISP)
    no_coc = [d for d in F01 if d["id"] not in IDS_COCINA]
    reps, _ = dedup_por_tipo(no_coc)
    normales = [d for d in reps if not es_dato(d["familia"], d["tipo"])]
    grupos, sin = agrupar_normales(normales, dom)
    assert len(grupos) == ESP["grupos_normales"], sorted(grupos)
    assert len(sin) == ESP["normales_sin_recinto"], sin
    # los dos aparatos del mismo muro comparten bajante; la luminaria no
    assert len(grupos[("room", 10, 900)]) == 2
    assert len(grupos[("room", 10, None)]) == 1


def test_dedup_no_colapsa_alturas():
    reps, dedup = dedup_por_tipo(F01)
    assert dedup == ESP["dedup_f01"], dedup
    gfci = sorted(d["id"] for d in reps if d["tipo"] == "Toma GFCI")
    assert gfci == [9, 10, 11], gfci


def test_cocina_por_recinto():
    dom = dominante_por_room(DISP)
    coc = [d for d in F01 if d["id"] in IDS_COCINA]
    grupos = agrupar_cocina(coc, dom, "F01")
    assert len(grupos) == ESP["grupos_cocina"], [len(g) for g in grupos]
    assert len(grupos[0]) == ESP["cocina_room_12"], [len(g) for g in grupos]
    assert set(d["room_id"] for d in grupos[0]) == {12}


def test_sin_radio():
    assert "RADIO_NORMAL_MM" not in CODIGO
    assert "RUTEO_RADIO_M" not in CODIGO
