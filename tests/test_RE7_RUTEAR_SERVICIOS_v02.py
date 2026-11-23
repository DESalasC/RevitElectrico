# -*- coding: utf-8 -*-
"""Tests del resolutor de superposiciones de RE7_RUTEAR_SERVICIOS_v02.py."""
import io
import json
import math
import os
import re
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, "scripts", "pyrevit", "RE7_RUTEAR_SERVICIOS_v02.py")
FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "servicios_v02.json")

with io.open(SRC, encoding="utf-8") as f:
    CODIGO = f.read()

with io.open(FIXTURE, encoding="utf-8") as f:
    FIX = json.load(f)


def _extraer(nombre):
    patron = r"^def %s\(.*?(?=^def |\Z)" % nombre
    m = re.search(patron, CODIGO, re.S | re.M)
    assert m, "no se encontro %s" % nombre
    return m.group(0)


NS = {"math": math, "defaultdict": defaultdict, "DEDUP_MM": 150.0,
      "DEDUP_Z_MM": 150.0, "TOL_XY_MM": 5.0, "TOL_LINEA_MM": 5.0,
      "TOL_Z_MM": 2.0, "OFFSET_VERTICAL_MM": 40.0,
      "OFFSET_HORIZONTA_MM": 50.0, "LARGO_MIN_MM": 5.0,
      "OFFSET_COMMS_MM": 40.0, "PLACA_MM": 50.0,
      "COCINA_BAJA_MM": 700.0, "COCINA_MEDIA_MM": 1050.0,
      "COCINA_ALTA_MM": 1650.0, "TOL_ALTURA_COCINA_MM": 60.0,
      "Z_RED_MM": 2700.0, "Z_NIVEL_JSON_MM": 13220.0,
      "D_16_MM": 16.0, "D_19_MM": 19.0,
      "SERVICIO_POR_FAMILIA": {
          "M_Iluminacion": "ILUMINACION", "M_Interruptores": "ILUMINACION",
          "M_ClimatizacionV": "ILUMINACION", "EA": "VENTILACION",
          "M_Toma doble": "TOMAS", "M_Comunicaciones": "COMUNICACIONES"}}
_FUNCIONES = ("clasificar_servicio", "apto_de_mark", "d2", "dist_3d",
              "dedup_por_tipo", "agrupar_por_proximidad", "mst_manhattan",
              "arista_a_segmentos", "alturas_cocina", "geo_de", "clave_linea",
              "intervalo", "mismo_tramo", "detectar_solapes",
              "resolver_superposiciones", "plan_apto")
exec(compile("\n".join(_extraer(f) for f in _FUNCIONES), "<v02>", "exec"), NS)

detectar_solapes = NS["detectar_solapes"]
resolver_superposiciones = NS["resolver_superposiciones"]
plan_apto = NS["plan_apto"]
geo_de = NS["geo_de"]

DISP = [_como(q) for q in FIX["dispositivos"]] if False else [
    {"id": q["id"], "pt": [q["x"], q["y"], q["z"]], "mark": q["mark"],
     "familia": q["familia"], "tipo": q["tipo"]} for q in FIX["dispositivos"]]
ESP = FIX["esperado"]


def _seg(tipo, servicio, a, b, diam=16.0):
    return {"tipo": tipo, "servicio": servicio, "diam_mm": diam,
            "a": list(a), "b": list(b)}


def test_resolver_placa_doble_y_colineales():
    segs, info = plan_apto(DISP, set(FIX["ids_cocina"]), 13220.0, 15920.0, "F01")
    limpios, acc = resolver_superposiciones(segs)
    assert acc["solapes_restantes"] == ESP["solapes_restantes"], acc
    assert acc["verticales_descartadas"] == ESP["verticales_descartadas"], acc
    # una sola bajada por placa, hasta el interruptor mas bajo
    bajadas = [s for s in limpios if s["tipo"] == "bajada_interruptor"]
    assert len(bajadas) == ESP["bajadas_interruptor"], bajadas
    assert bajadas[0]["b"][2] == ESP["bajada_z_fin"], bajadas[0]
    # sin duplicados exactos
    claves = set()
    for s in limpios:
        k = tuple(sorted([tuple(s["a"]), tuple(s["b"])]))
        assert k not in claves, k
        claves.add(k)


def test_resolver_verticales_distinto_servicio():
    # toma y dato en la misma XY: la segunda se desfaza 40 mm en X
    segs = [
        _seg("vertical_toma", "TOMAS", (6000.0, 6000.0, 14220.0),
             (6000.0, 6000.0, 15920.0)),
        _seg("vertical_datos", "COMUNICACIONES", (6000.0, 6000.0, 14220.0),
             (6000.0, 6000.0, 15920.0), 19.0),
    ]
    limpios, acc = resolver_superposiciones(segs)
    assert acc["solapes_restantes"] == 0, acc
    xs = sorted(s["a"][0] for s in limpios)
    assert xs == [6000.0, 6040.0], xs  # uno queda en la XY, el otro +40 mm


def test_resolver_colineales_retrace():
    # dos horizontales en la misma linea, uno dentro del otro
    segs = [
        _seg("iluminacion_horizontal", "ILUMINACION",
             (1000.0, 1000.0, 15920.0), (2000.0, 1000.0, 15920.0)),
        _seg("iluminacion_horizontal", "ILUMINACION",
             (1500.0, 1000.0, 15920.0), (1800.0, 1000.0, 15920.0)),
    ]
    limpios, acc = resolver_superposiciones(segs)
    assert acc["solapes_restantes"] == 0, acc
    assert acc["horizontales_descartados"] == 1, acc
    assert len(limpios) == 1


def test_resolver_recorte_parcial():
    segs = [
        _seg("iluminacion_horizontal", "ILUMINACION",
             (1000.0, 1000.0, 15920.0), (2000.0, 1000.0, 15920.0)),
        _seg("iluminacion_horizontal", "ILUMINACION",
             (1500.0, 1000.0, 15920.0), (3000.0, 1000.0, 15920.0)),
    ]
    limpios, acc = resolver_superposiciones(segs)
    assert acc["solapes_restantes"] == 0, acc
    assert len(limpios) == 2
    # el recortado empieza donde termina el primero
    inicios = sorted(min(s["a"][0], s["b"][0]) for s in limpios)
    fines = sorted(max(s["a"][0], s["b"][0]) for s in limpios)
    assert inicios == [1000.0, 2000.0], (inicios, fines)


def test_dedup_exacto():
    segs = [
        _seg("iluminacion_horizontal", "ILUMINACION",
             (1000.0, 1000.0, 15920.0), (2000.0, 1000.0, 15920.0)),
        _seg("iluminacion_horizontal", "ILUMINACION",
             (2000.0, 1000.0, 15920.0), (1000.0, 1000.0, 15920.0)),
    ]
    limpios, acc = resolver_superposiciones(segs)
    assert acc["dedup_exacto"] == 1, acc
    assert len(limpios) == 1
    assert acc["solapes_restantes"] == 0
