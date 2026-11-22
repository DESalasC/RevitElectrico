# -*- coding: utf-8 -*-
"""Tests de RE7_SEGMENTAR_DXF_XPL_v01 (segmentacion de polilineas rectas del DXF XPL)."""
import importlib.util
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "RE7_SEGMENTAR_DXF_XPL_v01",
    os.path.join(RAIZ, "scripts", "utilities", "RE7_SEGMENTAR_DXF_XPL_v01.py"),
)
assert SPEC is not None
MOD = importlib.util.module_from_spec(SPEC)
sys.modules["RE7_SEGMENTAR_DXF_XPL_v01"] = MOD
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)


def test_dedup_punto_evita_duplicados():
    vistos = set()
    assert MOD.dedup_punto((100.0, 200.0), vistos) is False
    assert MOD.dedup_punto((100.4, 200.4), vistos) is True   # dentro de 1 mm
    assert MOD.dedup_punto((102.0, 200.0), vistos) is False   # fuera de 1 mm en X


def test_segmento_valido_filtra_cortos():
    assert MOD.segmento_valido((0.0, 0.0), (0.0, 5.0), min_mm=3.05) is True
    assert MOD.segmento_valido((0.0, 0.0), (0.0, 2.0), min_mm=3.05) is False


def test_extraer_segmentos_doc_solo_lineas_rectas():
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0))          # 1 segmento valido
    msp.add_line((0, 0), (2, 0))             # demasiado corto (< 3.05 mm)
    msp.add_lwpolyline([(0, 0), (500, 0), (500, 500)])  # 2 segmentos
    msp.add_circle((0, 0), 100)              # ignorado (no es LINE ni LWPOLYLINE)
    segs = MOD.extraer_segmentos_doc(doc)
    ids = [s["id"] for s in segs]
    assert len(segs) == 3, ids
    assert all(s["a_mm"][2] == 15930.0 for s in segs)
    assert all(s["apto"] == "Apartamento Tipo XPL" for s in segs)
    assert all(s["servicio"] == "TOMAS" for s in segs)


def test_segmentos_tienen_campos_requeridos():
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0))
    segs = MOD.extraer_segmentos_doc(doc)
    s = segs[0]
    for campo in ("id", "apto", "a_mm", "b_mm", "servicio", "tamano", "origen"):
        assert campo in s, f"falta campo {campo}"
    assert len(s["a_mm"]) == 3
    assert len(s["b_mm"]) == 3
