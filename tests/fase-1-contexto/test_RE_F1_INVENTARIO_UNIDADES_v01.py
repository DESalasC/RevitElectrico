# -*- coding: utf-8 -*-
"""Tests del inventario de unidades (RE_F1_INVENTARIO_UNIDADES_v01)."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import ezdxf
import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ / "src" / "fase-1-contexto" / "RE_F1_INVENTARIO_UNIDADES_v01.py"


def cargar_modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("re_f1_inventario", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("No se pudo cargar {r}".format(r=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MOD = cargar_modulo()
contar_aparatos = MOD.contar_aparatos
es_aparato = MOD.es_aparato
inventariar = MOD.inventariar
unidad_desde_nombre = MOD.unidad_desde_nombre


def _dxf_con_bloques(ruta: Path, bloques: list[str]) -> Path:
    doc = ezdxf.new()
    msp = doc.modelspace()
    for i, nombre in enumerate(bloques):
        if nombre not in doc.blocks:
            doc.blocks.new(name=nombre)
        msp.add_blockref(nombre, (i * 0.5, 0.0))
    doc.saveas(ruta)
    return ruta


def test_solo_cuenta_aparatos():
    assert es_aparato("ELEC-T-D-t-15A")
    assert es_aparato("Bala Stil Led 13W")
    assert es_aparato("S3C")
    assert not es_aparato("ELEC-POWER-PANEL")
    assert not es_aparato("ELEC-POWER- PIPE")
    assert not es_aparato("TB-Panel")
    assert not es_aparato("ARQ-MURO")


def test_contar_aparatos_ignora_tuberia_y_panel(tmp_path):
    ruta = _dxf_con_bloques(
        tmp_path / "Apartamento Tipo X 01.dxf",
        ["ELEC-T-D-t-15A", "ELEC-T-D-t-15A", "ELEC-POWER-PANEL",
         "ELEC-POWER- PIPE", "Bala Stil Led 13W", "S3C"],
    )
    conteo = contar_aparatos(ruta)
    assert conteo == {"ELEC-T-D-t-15A": 2, "Bala Stil Led 13W": 1, "S3C": 1}


def test_unidad_desde_nombre():
    assert unidad_desde_nombre("Apartamento Tipo E 06.dxf") == "E 06"
    assert unidad_desde_nombre("ApaRtamento Tipo E 05.dxf") == "ApaRtamento Tipo E 05"
    assert unidad_desde_nombre("ELEC-Apartamento Tipo D 13.dxf") == "D 13"
    assert unidad_desde_nombre("Apartamentos Tipo F 18a.dxf") == "F 18a"


def test_inventariar_agrega_totales(tmp_path):
    a = _dxf_con_bloques(tmp_path / "Apartamento Tipo E 06.dxf", ["ELEC-TEL"] * 3)
    b = _dxf_con_bloques(tmp_path / "Apartamento Tipo F 01.dxf",
                         ["ELEC-TEL", "Bala Stil Led 10W"])
    inv = inventariar([a, b])
    assert inv["total_unidades"] == 2
    assert inv["total_aparatos"] == 5
    assert inv["total_por_bloque"] == {"Bala Stil Led 10W": 1, "ELEC-TEL": 4}
    assert inv["unidades"]["Apartamento Tipo E 06.dxf"]["unidad"] == "E 06"


@pytest.mark.skipif(
    not (RAIZ / "data" / "inventario_unidades_v01.json").exists(),
    reason="inventario aun no generado",
)
def test_inventario_comprometido_cuadra():
    inv = json.loads((RAIZ / "data" / "inventario_unidades_v01.json").read_text(encoding="utf-8"))
    assert inv["total_unidades"] == 20
    assert sum(u["total"] for u in inv["unidades"].values()) == inv["total_aparatos"]
    assert inv["total_aparatos"] == 901
    # E 06 es la unidad de referencia: 47 aparatos.
    e06 = inv["unidades"]["Apartamento Tipo E 06.dxf"]
    assert e06["total"] == 47


def _mapeo_del_colocador() -> dict[str, tuple[str, str]]:
    """Lee MAPEO_DEFAULT sin importar el modulo (depende de clr/Revit)."""
    fuente = (RAIZ / "src" / "fase-6-revit" / "RE_COLOCAR_DISPOSITIVOS_generico.py").read_text(
        encoding="utf-8")
    arbol = ast.parse(fuente)
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
            getattr(t, "id", "") == "MAPEO_DEFAULT" for t in nodo.targets
        ):
            return ast.literal_eval(nodo.value)
    raise AssertionError("MAPEO_DEFAULT no encontrado")


@pytest.mark.skipif(
    not (RAIZ / "data" / "inventario_unidades_v01.json").exists(),
    reason="inventario aun no generado",
)
def test_bloques_sin_mapeo_son_los_declarados():
    """Guarda de regresion: si aparece un bloque nuevo sin mapeo, el test falla."""
    inv = json.loads((RAIZ / "data" / "inventario_unidades_v01.json").read_text(encoding="utf-8"))
    mapeo = _mapeo_del_colocador()
    sin_mapeo = sorted(b for b in inv["total_por_bloque"] if b not in mapeo)
    assert sin_mapeo == ["ELEC-I-S-2-5A", "S3C"], (
        "Bloques sin familia/tipo en el colocador: " + repr(sin_mapeo)
    )
