"""Tests de RE7_SEGMENTAR_CONDUITS_v01 (sin Revit, contra JSON reales y sinteticos)."""
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
    sys.modules[nombre] = modulo  # dataclass necesita el modulo en sys.modules
    spec.loader.exec_module(modulo)
    return modulo


SEG = _cargar_modulo(
    "RE7_SEGMENTAR_CONDUITS_v01",
    os.path.join(MOD_DIR, "RE7_SEGMENTAR_CONDUITS_v01.py"),
)


def _ejecutar(entrada_rel, salida_rel=None, **kwargs):
    entrada = os.path.join(RAIZ, entrada_rel)
    salida = (
        os.path.join(RAIZ, salida_rel)
        if salida_rel
        else os.path.join(RAIZ, "tests", "pytest_tmp", "salida_segmentar.json")
    )
    argv = ["--input", entrada, "--output", salida]
    for clave, valor in kwargs.items():
        argv.extend([f"--{clave}", str(valor)])
    codigo = SEG.main(argv)
    assert codigo == 0
    with open(salida, "r") as f:
        return json.load(f)


def test_segmenta_real_f01_f02():
    reporte = _ejecutar(
        "data/conduits_dxf_v01.json",
        "data/f7_segmentos_f01_f02_v01.json",
    )
    r = reporte["resumen"]
    assert r["polilineas_entrada"] == 63
    assert r["segmentos"] == 116, r
    assert abs(r["longitud_total_m"] - 76.86) < 0.05, r
    assert reporte["ids_unicos"] is True
    assert r["descartados"] == 0, r
    assert r["polilineas_con_quiebre"] == 36
    for s in reporte["segmentos"]:
        assert s["largo_mm"] >= 3.05
        assert s["a_mm"] != s["b_mm"]


def test_segmenta_real_e06():
    reporte = _ejecutar(
        "data/conduits_dxf_v01_E06.json",
        "data/f7_segmentos_e06_v01.json",
    )
    r = reporte["resumen"]
    assert r["polilineas_entrada"] == 40
    assert r["segmentos"] == 68, r
    assert abs(r["longitud_total_m"] - 53.37) < 0.05, r
    assert reporte["ids_unicos"] is True
    assert r["polilineas_con_quiebre"] == 26


def test_sintetico():
    sint = {
        "version": "v01_TEST",
        "conduits": [
            {
                "id": "RT-S01",
                "apartamento": "Apto Test",
                "servicio": "TOMAS",
                "diametro_mm": 15.85,
                "diametro_pulgadas": '1/2"',
                "a": [0, 0, 15930],
                "b": [5, 0, 15930],
            },
            {
                "id": "RT-S02",
                "apartamento": "Apto Test",
                "servicio": "ILUMINACION",
                "diametro_mm": 15.85,
                "diametro_pulgadas": '1/2"',
                "puntos_2d": [[0, 0], [3, 4], [6, 0]],
                "a": [0, 0, 15930],
                "b": [6, 0, 15930],
                "largo_mm": 10.0,
            },
            {
                "id": "RT-S03",
                "apartamento": "Apto Test",
                "servicio": "COMUNICACIONES",
                "diametro_mm": 21.03,
                "diametro_pulgadas": '3/4"',
                "puntos_2d": [[0, 0], [1, 0], [1.0005, 0], [2, 0]],
                "a": [0, 0, 15930],
                "b": [2, 0, 15930],
            },
            {
                "id": "RT-S04",
                "apartamento": "Apto Test",
                "servicio": "FUERZA",
                "diametro_mm": 15.85,
                "diametro_pulgadas": '1/2"',
                "puntos_2d": [[0, 0], [0, 0.002]],
                "a": [0, 0, 15930],
                "b": [0, 0.002, 15930],
            },
            {
                "id": "RT-S05",
                "apartamento": "Apto Test",
                "servicio": "TOMAS",
                "diametro_mm": 15.85,
                "diametro_pulgadas": '1/2"',
                "a": [0, 0, 15930],
                "b": [0.5, 0, 16030],
            },
        ],
    }
    reporte = SEG.segmentar_documento(
        sint, SEG.DEDUP_PUNTOS_MM_DEFAULT, SEG.MIN_SEGMENTO_MM_DEFAULT
    )
    r = reporte["resumen"]
    assert r["segmentos"] == 6, r  # 1 + 2 + 2 + 0 + 1
    assert r["descartados"] == 1, r  # RT-S04 segmento de 2 mm
    assert abs(r["longitud_total_m"] - 17.51) < 0.01, r
    assert reporte["ids_unicos"] is True
    tipos_aviso = {a["tipo"] for a in reporte["avisos"]}
    assert "largo_mm_en_metros" in tipos_aviso  # RT-S02: 10.0 m == computed
    assert "z_variable" in tipos_aviso  # RT-S05
    assert "puntos_duplicados" in tipos_aviso  # RT-S03


def test_campos_reporte():
    reporte = _ejecutar("data/conduits_dxf_v01_E06.json")
    assert reporte["version"] == "v01"
    assert reporte["script"] == "RE7_SEGMENTAR_CONDUITS_v01"
    assert "fuente" in reporte and "sha256" in reporte["fuente"]
    assert "parametros" in reporte
    for clave in ("polilineas_entrada", "segmentos", "por_servicio", "por_apto"):
        assert clave in reporte["resumen"]


def test_determinista():
    a = _ejecutar("data/conduits_dxf_v01_E06.json")
    b = _ejecutar("data/conduits_dxf_v01_E06.json")
    assert a == b
    with open(a["fuente"]["archivo"], "rb") as f:
        assert a["fuente"]["sha256"] == hashlib.sha256(f.read()).hexdigest()
