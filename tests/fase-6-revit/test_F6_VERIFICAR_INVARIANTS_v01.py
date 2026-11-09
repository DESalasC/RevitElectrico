# -*- coding: utf-8 -*-
"""
test_F6_VERIFICAR_INVARIANTS_v01.py — Tests para F6_VERIFICAR_INVARIANTS_v01.py
Proyecto: RevitElectrico / T5-SantaMarta / Fase 6
Python 3.12 + pytest (sin Revit, solo logica sobre JSON)

USO:
  pytest tests/fase-6-revit/test_F6_VERIFICAR_INVARIANTS_v01.py -v
"""
import importlib.util
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MOD = RAIZ / "src" / "fase-6-revit" / "F6_VERIFICAR_INVARIANTS_v01.py"
FIXTURE = Path(__file__).parent / "fixture_F6_VERIFICAR_INVARIANTS_v01.json"


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location("verificador", RUTA_MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _estado_base():
    return {
        "documento": {"titulo": "E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02"},
        "niveles": [
            {"nombre": "Piso 4", "elevacion_m": 32.71},
            {"nombre": "Piso 5", "elevacion_m": 43.3727},
        ],
        "instancias_electricas": [
            {"id": 1, "familia": "M_Toma doble", "nivel": "Piso 5", "nivel_id": 853351,
             "z_min": 43.6727, "z_relativo_nivel": 0.3, "oculto_en_vista": False},
            {"id": 2, "familia": "M_Interruptor bipolar", "nivel": "Piso 5", "nivel_id": 853351,
             "z_min": 44.4727, "z_relativo_nivel": 1.1, "oculto_en_vista": False},
            {"id": 3, "familia": "COMBO MOUNTING RING", "nivel": "Piso 5", "nivel_id": 853351,
             "z_min": 45.9727, "z_relativo_nivel": 2.6, "oculto_en_vista": False},
            {"id": 4, "familia": "E_Distribution Panel", "nivel": "Piso 5", "nivel_id": 853351,
             "z_min": 44.5727, "z_relativo_nivel": 1.2, "oculto_en_vista": False},
        ],
        "conduits": {"total": 0, "accesorios": 0},
    }


def test_aprueba_estado_correcto():
    mod = _cargar_modulo()
    r = mod.verificar(_estado_base(), nivel="Piso 5", min_instancias=4, min_conduits=0)
    assert r["aprobado"] is True
    assert r["errores"] == []


def test_detecta_sin_nivel():
    mod = _cargar_modulo()
    estado = _estado_base()
    estado["instancias_electricas"][0]["nivel_id"] = -1
    r = mod.verificar(estado, nivel="Piso 5", min_instancias=4)
    assert r["aprobado"] is False
    assert any("I3" in e for e in r["errores"])


def test_detecta_nivel_incorrecto():
    mod = _cargar_modulo()
    estado = _estado_base()
    estado["instancias_electricas"][1]["nivel"] = None
    r = mod.verificar(estado, nivel="Piso 5", min_instancias=4)
    assert r["aprobado"] is False
    assert any("I4" in e for e in r["errores"])


def test_detecta_altura_incorrecta():
    mod = _cargar_modulo()
    estado = _estado_base()
    # Toma a 0,3 m absolutos en vez de 43,67: el error original del proyecto
    estado["instancias_electricas"][0]["z_relativo_nivel"] = -43.0727
    r = mod.verificar(estado, nivel="Piso 5", min_instancias=4)
    assert r["aprobado"] is False
    assert any("I5" in e for e in r["errores"])


def test_falla_por_pocas_instancias():
    mod = _cargar_modulo()
    r = mod.verificar(_estado_base(), nivel="Piso 5", min_instancias=37)
    assert r["aprobado"] is False
    assert any("I2" in e for e in r["errores"])


def test_falla_si_faltan_conduits_cuando_se_exigen():
    mod = _cargar_modulo()
    r = mod.verificar(_estado_base(), nivel="Piso 5", min_instancias=4, min_conduits=1)
    assert r["aprobado"] is False
    assert any("I6" in e for e in r["errores"])


def test_fixture_real_del_proyecto():
    """El fixture replica la estructura del JSON de diagnostico real."""
    mod = _cargar_modulo()
    estado = json.loads(FIXTURE.read_text(encoding="utf-8"))
    r = mod.verificar(estado, nivel="Piso 5", min_instancias=2)
    assert r["elevacion_nivel_m"] == 43.3727
    assert r["resumen"]["instancias"] == 2
