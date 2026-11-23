# -*- coding: utf-8 -*-
"""Tests de RE7_RUTEAR_SERVICIOS_v01.py (funciones puras, sin Revit)."""
import io
import json
import math
import os
import re
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, "scripts", "pyrevit", "RE7_RUTEAR_SERVICIOS_v01.py")
FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "servicios_v01.json")

with io.open(SRC, encoding="utf-8") as f:
    CODIGO = f.read()

with io.open(FIXTURE, encoding="utf-8") as f:
    FIX = json.load(f)


def _extraer(nombre):
    patron = r"^def %s\(.*?(?=^def |\Z)" % nombre
    m = re.search(patron, CODIGO, re.S | re.M)
    assert m, "no se encontro %s en %s" % (nombre, SRC)
    return m.group(0)


NS = {"math": math, "defaultdict": defaultdict, "DEDUP_MM": 150.0,
      "DEDUP_Z_MM": 150.0, "COCINA_BAJA_MM": 700.0, "COCINA_MEDIA_MM": 1050.0,
      "COCINA_ALTA_MM": 1650.0, "TOL_ALTURA_COCINA_MM": 60.0,
      "SERVICIO_POR_FAMILIA": {
          "M_Iluminacion": "ILUMINACION", "M_Interruptores": "ILUMINACION",
          "M_ClimatizacionV": "ILUMINACION", "EA": "VENTILACION",
          "M_Toma doble": "TOMAS",
          "M_Toma resistente a la intemperie": "TOMAS",
          "M_Toma - 220V": "TOMAS", "M_Comunicaciones": "COMUNICACIONES"}}
_FUNCIONES = ("clasificar_servicio", "apto_de_mark", "d2",
              "dedup_por_tipo", "agrupar_por_proximidad", "mst_manhattan",
              "arista_a_segmentos", "alturas_cocina")
exec(compile("\n".join(_extraer(f) for f in _FUNCIONES), "<srv>", "exec"), NS)

clasificar_servicio = NS["clasificar_servicio"]
dedup_por_tipo = NS["dedup_por_tipo"]
agrupar_por_proximidad = NS["agrupar_por_proximidad"]
mst_manhattan = NS["mst_manhattan"]
arista_a_segmentos = NS["arista_a_segmentos"]
alturas_cocina = NS["alturas_cocina"]

DISP = FIX["dispositivos"]
IDS_COCINA = set(FIX["ids_cocina"])
ESP = FIX["esperado"]


def _como_disp(q):
    return {"id": q["id"], "pt": [q["x"], q["y"], q["z"]],
            "mark": q["mark"], "familia": q["familia"], "tipo": q["tipo"]}


def test_clasificar_servicio():
    for fam, esperado in ESP["servicios"].items():
        assert clasificar_servicio(fam) == esperado, fam


def test_mst_manhattan():
    puntos = [(1000.0, 1000.0), (4000.0, 1000.0), (2500.0, 3000.0),
              (1200.0, 800.0)]
    aristas = mst_manhattan(puntos)
    assert len(aristas) == ESP["mst_aristas_4_nodos"], aristas
    assert set(j for _, j in aristas) == {1, 2, 3}
    segs = []
    for i, j in aristas:
        segs.extend(arista_a_segmentos(puntos[i], puntos[j]))
    assert len(segs) >= ESP["segmentos_mst_min"], segs
    for (p, q) in segs:
        assert (p[0] == q[0]) != (p[1] == q[1])  # ortogonal
        assert math.hypot(q[0] - p[0], q[1] - p[1]) > 0.5


def test_arista_a_segmentos_ortogonal():
    segs = arista_a_segmentos((0.0, 0.0), (3000.0, 2000.0))
    assert len(segs) == 2
    assert segs[0] == ((0.0, 0.0), (3000.0, 0.0))
    assert segs[1] == ((3000.0, 0.0), (3000.0, 2000.0))
    assert arista_a_segmentos((1.0, 1.0), (1.0, 9.0)) == \
        [((1.0, 1.0), (1.0, 9.0))]


def test_dedup_y_cocina():
    disp = [_como_disp(q) for q in DISP]
    reps, dedup = dedup_por_tipo(disp)
    assert dedup == ESP["dedup_gfci"], dedup  # GFCI 700/1050 NO se colapsan
    gfci = sorted(d["id"] for d in reps if d["tipo"] == "Toma GFCI")
    assert gfci == [5, 6], gfci
    coc = [d for d in reps if d["id"] in IDS_COCINA]
    grupos = agrupar_por_proximidad(coc, 200.0)
    assert len(grupos) == 1
    assert alturas_cocina(grupos[0], 13220.0) == ESP["alturas_cocina"]


def test_datos_agrupados():
    disp = [_como_disp(q) for q in DISP]
    datos = [d for d in disp if d["familia"] == "M_Comunicaciones"]
    assert len(agrupar_por_proximidad(datos, 200.0)) == ESP["grupos_datos"]
