"""Tests de RE7_ANALIZAR_PREFLIGHT_v01 (sin Revit, contra fixtures sinteticos)."""
import copy
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
    "RE7_ANALIZAR_PREFLIGHT_v01",
    os.path.join(MOD_DIR, "RE7_ANALIZAR_PREFLIGHT_v01.py"),
)

FIXTURES = os.path.join(RAIZ, "tests", "fixtures")

CONFIG = {
    "version": "v01_TEST",
    "nivel": {"nombre_esperado": "Piso 5", "elevacion_m": 13.22, "tolerancia_mm": 1.0},
    "tipos_conduit": {
        "COMUNICACIONES": 5508657,
        "TOMAS": 112216,
        "ILUMINACION": 112216,
        "FUERZA": 112216,
    },
    "tolerancias": {
        "offset_mm": 50.0,
        "dispositivo_xy_mm": 300.0,
        "match_conduit_mm": 1000.0,
    },
}


def _cargar(nombre_archivo):
    with open(os.path.join(FIXTURES, nombre_archivo), "r") as f:
        return json.load(f)


def _desplazar_conduits(preflight, dx_mm=120.0):
    """Desplaza todos los extremos de conduits dx_mm en X (simula offset del modelo)."""
    pf = copy.deepcopy(preflight)
    for c in pf["conduits"]:
        for extremo in ("a_mm", "b_mm"):
            c[extremo][0] += dx_mm
    return pf


def test_apto_base():
    preflight = _cargar("f7_preflight_sintetico_base_v01.json")
    segmentos = _cargar("f7_segmentos_sintetico_v01.json")
    reporte = ANAL.evaluar(CONFIG, preflight, segmentos)
    assert reporte["veredicto"] == "APTO", reporte
    assert reporte["checks"]["nivel_piso5"]["estado"] == "OK"
    assert reporte["checks"]["tipos_conduit"]["estado"] == "OK"
    assert reporte["checks"]["offset_modelo"]["estado"] == "OK"
    assert abs(reporte["checks"]["offset_modelo"]["mediana_dx_mm"]) <= 50.0
    assert reporte["checks"]["cobertura_dispositivos"]["estado"] == "OK"
    assert reporte["checks"]["cobertura_dispositivos"]["cobertura"] == 1.0


def test_falla_offset():
    preflight = _desplazar_conduits(_cargar("f7_preflight_sintetico_base_v01.json"), 120.0)
    segmentos = _cargar("f7_segmentos_sintetico_v01.json")
    reporte = ANAL.evaluar(CONFIG, preflight, segmentos)
    assert reporte["veredicto"] == "NO_APTO", reporte
    assert reporte["checks"]["offset_modelo"]["estado"] == "FALLA"
    assert abs(reporte["checks"]["offset_modelo"]["mediana_dx_mm"] + 120.0) < 0.01


def test_falla_tipo_conduit():
    preflight = copy.deepcopy(_cargar("f7_preflight_sintetico_base_v01.json"))
    preflight["tipos_conduit"] = [t for t in preflight["tipos_conduit"] if t["id"] != 5508657]
    segmentos = _cargar("f7_segmentos_sintetico_v01.json")
    reporte = ANAL.evaluar(CONFIG, preflight, segmentos)
    assert reporte["veredicto"] == "NO_APTO"
    assert reporte["checks"]["tipos_conduit"]["estado"] == "FALLA"
    assert 5508657 in reporte["checks"]["tipos_conduit"]["faltantes"]


def test_falla_nivel():
    preflight = copy.deepcopy(_cargar("f7_preflight_sintetico_base_v01.json"))
    preflight["nivel_piso5"]["delta_mm"] = 15.0  # fuera de tolerancia 1 mm
    segmentos = _cargar("f7_segmentos_sintetico_v01.json")
    reporte = ANAL.evaluar(CONFIG, preflight, segmentos)
    assert reporte["veredicto"] == "NO_APTO"
    assert reporte["checks"]["nivel_piso5"]["estado"] == "FALLA"


def test_sin_dispositivos_no_aplica():
    preflight = copy.deepcopy(_cargar("f7_preflight_sintetico_base_v01.json"))
    preflight["dispositivos"] = []
    segmentos = _cargar("f7_segmentos_sintetico_v01.json")
    reporte = ANAL.evaluar(CONFIG, preflight, segmentos)
    assert reporte["veredicto"] == "APTO", reporte
    assert reporte["checks"]["cobertura_dispositivos"]["estado"] == "NO_APLICA"


def test_modelo_sucio_solo_aviso():
    preflight = copy.deepcopy(_cargar("f7_preflight_sintetico_base_v01.json"))
    preflight["documento"]["modificado"] = True
    segmentos = _cargar("f7_segmentos_sintetico_v01.json")
    reporte = ANAL.evaluar(CONFIG, preflight, segmentos)
    assert reporte["veredicto"] == "APTO", reporte
    assert reporte["checks"]["modelo_guardado"]["estado"] == "AVISO"


def test_sin_segmentos_cobertura_no_aplica():
    preflight = _cargar("f7_preflight_sintetico_base_v01.json")
    reporte = ANAL.evaluar(CONFIG, preflight, None)
    assert reporte["checks"]["cobertura_dispositivos"]["estado"] == "NO_APLICA"


def test_cli_main_apto(tmp_path):
    cfg = tmp_path / "config.json"
    pre = tmp_path / "preflight.json"
    seg = tmp_path / "segmentos.json"
    out = tmp_path / "reporte.json"
    cfg.write_text(json.dumps(CONFIG), encoding="utf-8")
    pre.write_text(json.dumps(_cargar("f7_preflight_sintetico_base_v01.json")), encoding="utf-8")
    seg.write_text(json.dumps(_cargar("f7_segmentos_sintetico_v01.json")), encoding="utf-8")
    codigo = ANAL.main(
        [
            "--config", str(cfg),
            "--preflight", str(pre),
            "--segmentos", str(seg),
            "--output", str(out),
        ]
    )
    assert codigo == 0
    reporte = json.loads(out.read_text(encoding="utf-8"))
    assert reporte["veredicto"] == "APTO"


def test_cli_main_no_apto(tmp_path):
    cfg = tmp_path / "config.json"
    pre = tmp_path / "preflight.json"
    seg = tmp_path / "segmentos.json"
    out = tmp_path / "reporte.json"
    cfg.write_text(json.dumps(CONFIG), encoding="utf-8")
    pre.write_text(json.dumps(_desplazar_conduits(_cargar("f7_preflight_sintetico_base_v01.json"), 120.0)), encoding="utf-8")
    seg.write_text(json.dumps(_cargar("f7_segmentos_sintetico_v01.json")), encoding="utf-8")
    codigo = ANAL.main(
        ["--config", str(cfg), "--preflight", str(pre), "--segmentos", str(seg), "--output", str(out)]
    )
    assert codigo == 1
    reporte = json.loads(out.read_text(encoding="utf-8"))
    assert reporte["veredicto"] == "NO_APTO"
