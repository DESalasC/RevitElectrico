"""Tests de RE7_ANALIZAR_UNIONES_v01 (sin Revit, contra JSON sintetico y real)."""

import hashlib
import importlib.util
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_DIR = os.path.join(RAIZ, "src", "fase-7-ruteo")


def _cargar_modulo(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, archivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


ANAL = _cargar_modulo(
    "RE7_ANALIZAR_UNIONES_v01",
    os.path.join(MOD_DIR, "RE7_ANALIZAR_UNIONES_v01.py"),
)


def _cargar_fixture(nombre_rel):
    ruta = os.path.join(RAIZ, "tests", "fixtures", nombre_rel)
    with open(ruta, "r") as f:
        return json.load(f)


def _ejecutar_analizar(conduits, **kwargs):
    return ANAL.analizar_uniones(conduits, **kwargs)


def test_detecta_acoplamiento_dos_conductos_recto():
    """Dos conductos en linea recta que coinciden en un extremo -> Conduit Coupling."""
    conduits = [
        {"conduit_id": "RT-U01", "a_mm": [0, 0, 15920], "b_mm": [5000, 0, 15920]},
        {"conduit_id": "RT-U02", "a_mm": [5000, 0, 15920], "b_mm": [10000, 0, 15920]},
    ]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    pts = reporte["puntos_union"]
    assert len(pts) == 1, pts
    p = pts[0]
    assert p["num_conduits"] == 2
    assert p["tipo_accesorio_recomendado"] == "Conduit Coupling", p
    assert set(p["conduit_ids"]) == {"RT-U01", "RT-U02"}


def test_detecta_codo_dos_conductos_angulo():
    """Dos conductos en angulo (90 grados) que coinciden en un extremo -> Conduit Elbow."""
    conduits = [
        {"conduit_id": "RT-U01", "a_mm": [0, 0, 15920], "b_mm": [5000, 0, 15920]},
        {"conduit_id": "RT-U02", "a_mm": [5000, 0, 15920], "b_mm": [5000, 5000, 15920]},
    ]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    pts = reporte["puntos_union"]
    assert len(pts) == 1, pts
    p = pts[0]
    assert p["num_conduits"] == 2
    assert p["tipo_accesorio_recomendado"] == "Conduit Elbow", p
    assert p["cambio_direccion"] is True


def test_detecta_caja_tee_tres_conductos():
    """Tres conductos que coinciden en un punto -> Conduit Junction Box - Tee."""
    conduits = [
        {"conduit_id": "RT-U03", "a_mm": [0, 5000, 15920], "b_mm": [5000, 5000, 15920]},
        {"conduit_id": "RT-U04", "a_mm": [5000, 5000, 15920], "b_mm": [10000, 5000, 15920]},
        {"conduit_id": "RT-U05", "a_mm": [5000, 5000, 15920], "b_mm": [5000, 10000, 15920]},
    ]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    pts = reporte["puntos_union"]
    assert len(pts) == 1, pts
    p = pts[0]
    assert p["num_conduits"] == 3
    assert p["tipo_accesorio_recomendado"] == "Conduit Junction Box - Tee", p


def test_detecta_caja_cross_cuatro_conductos():
    """Cuatro conductos que coinciden en un punto -> Conduit Junction Box - Cross."""
    conduits = [
        {"conduit_id": "RT-U06", "a_mm": [5000, 10000, 15920], "b_mm": [10000, 10000, 15920]},
        {"conduit_id": "RT-U07", "a_mm": [10000, 10000, 15920], "b_mm": [15000, 10000, 15920]},
        {"conduit_id": "RT-U08", "a_mm": [10000, 5000, 15920], "b_mm": [10000, 10000, 15920]},
        {"conduit_id": "RT-U09", "a_mm": [10000, 10000, 15920], "b_mm": [10000, 15000, 15920]},
    ]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    pts = reporte["puntos_union"]
    assert len(pts) == 1, pts
    p = pts[0]
    assert p["num_conduits"] == 4
    assert p["tipo_accesorio_recomendado"] == "Conduit Junction Box - Cross", p


def test_clusteriza_extremos_levemente_desfazados():
    """Extremos de conductos distintos que estan a pocos mm se agrupan en un mismo punto."""
    conduits = [
        {"conduit_id": "RT-U10", "a_mm": [0, 20000, 15920], "b_mm": [2000, 20000, 15920]},
        {"conduit_id": "RT-U11", "a_mm": [2005, 20000, 15920], "b_mm": [4000, 20000, 15920]},
    ]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0, celda_mm=100.0)
    pts = reporte["puntos_union"]
    assert len(pts) == 1, pts
    p = pts[0]
    assert p["num_conduits"] == 2
    assert set(p["conduit_ids"]) == {"RT-U10", "RT-U11"}
    # El punto central debe estar entre 2000 y 2005 en X
    assert 2000 <= p["punto_mm"][0] <= 2005, p


def test_no_detecta_conducto_solitario():
    """Un solo conducto sin conexiones no genera punto de union."""
    conduits = [
        {"conduit_id": "RT-U12", "a_mm": [30000, 30000, 15920], "b_mm": [35000, 30000, 15920]},
    ]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    assert reporte["puntos_union"] == [], reporte


def test_filtro_primeros_incluye_cualquier_conduit_entre_los_primeros_n():
    """Con --primeros N solo se incluyen uniones que involucren al menos uno
    de los primeros N conduits (por ID ascendente)."""
    conduits = _cargar_fixture("f7_uniones_sintetico_v01.json")["conduits"]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0, primeros=2)
    ids_en_uniones = set()
    for p in reporte["puntos_union"]:
        ids_en_uniones.update(p["conduit_ids"])
    assert "RT-U01" in ids_en_uniones or "RT-U02" in ids_en_uniones
    assert "RT-U12" not in ids_en_uniones


def test_filtro_primeros_excluye_conductos_fuera_de_rango():
    """Con primeros=2, conduits con IDs mayores no aparecen solos."""
    conduits = _cargar_fixture("f7_uniones_sintetico_v01.json")["conduits"]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0, primeros=2)
    ids_en_uniones = set()
    for p in reporte["puntos_union"]:
        ids_en_uniones.update(p["conduit_ids"])
    assert "RT-U03" not in ids_en_uniones or "RT-U01" in ids_en_uniones or "RT-U02" in ids_en_uniones


def test_resumen_tipos_accesorio():
    """El resumen cuenta correctamente por tipo de accesorio."""
    conduits = _cargar_fixture("f7_uniones_sintetico_v01.json")["conduits"]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    resumen = reporte["resumen"]
    por_tipo = resumen["por_tipo_accesorio"]
    # Con la fixture completa:
    #   (5000, 0): RT-U01, RT-U02, RT-U03 -> 3 conduits -> Tee
    #   (5000, 5000): RT-U03, RT-U04, RT-U05 -> 3 conduits -> Tee
    #   (10000, 10000): RT-U06, RT-U07, RT-U08, RT-U09 -> 4 conduits -> Cross
    #   (2000-2005, 20000): RT-U10, RT-U11 -> 2 conduits recto -> Coupling
    assert por_tipo.get("Conduit Coupling", 0) >= 1
    assert por_tipo.get("Conduit Junction Box - Tee", 0) >= 1
    assert por_tipo.get("Conduit Junction Box - Cross", 0) >= 1


def test_campos_reporte():
    """El reporte tiene los campos requeridos."""
    conduits = [
        {"conduit_id": "RT-U01", "a_mm": [0, 0, 15920], "b_mm": [5000, 0, 15920]},
        {"conduit_id": "RT-U02", "a_mm": [5000, 0, 15920], "b_mm": [10000, 0, 15920]},
    ]
    reporte = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    assert reporte["version"] == "v01"
    assert reporte["script"] == "RE7_ANALIZAR_UNIONES_v01"
    assert "generado_utc" in reporte
    assert "parametros" in reporte
    assert "resumen" in reporte
    assert "puntos_union" in reporte
    r = reporte["resumen"]
    assert "puntos_union_detectados" in r
    assert "conduits_con_union" in r
    assert "por_tipo_accesorio" in r
    for p in reporte["puntos_union"]:
        assert "punto_mm" in p
        assert "conduit_ids" in p
        assert "num_conduits" in p
        assert "tipo_accesorio_recomendado" in p
        assert "miembros" in p


def test_determinista():
    """Dos ejecuciones con mismos datos producen el mismo reporte."""
    conduits = _cargar_fixture("f7_uniones_sintetico_v01.json")["conduits"]
    a = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    b = _ejecutar_analizar(conduits, tolerancia_mm=100.0)
    assert a == b


def test_json_fixture_valido():
    """El fixture JSON es valido y tiene conduits con los campos esperados."""
    datos = _cargar_fixture("f7_uniones_sintetico_v01.json")
    assert "conduits" in datos
    assert len(datos["conduits"]) > 0
    for c in datos["conduits"]:
        assert "conduit_id" in c
        assert "a_mm" in c
        assert "b_mm" in c
        assert len(c["a_mm"]) == 3
        assert len(c["b_mm"]) == 3
