# -*- coding: utf-8 -*-
"""Tests del resolvedor de alturas (F1).

Cubren la precedencia (excepcion > anotacion > regla base), el parseo de las
anotaciones del DXF y el reporte de conflictos. Usan un DXF minimo generado al vuelo,
sin depender del plano real.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import ezdxf
import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ / "src" / "fase-1-contexto" / "RE_F1_RESOLVER_ALTURAS_v01.py"
RUTA_CONFIG = RAIZ / "config" / "alturas_tomas_v01.json"


def cargar_modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("re_f1_resolver_alturas", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("No se pudo cargar {r}".format(r=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def resolver() -> ModuleType:
    return cargar_modulo()


@pytest.fixture(scope="module")
def config() -> dict:
    with RUTA_CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


def _dxf_con_textos(ruta: Path, textos: list[tuple[float, float, str]]) -> Path:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for x, y, contenido in textos:
        msp.add_text(contenido, dxfattribs={"insert": (x, y, 0.0), "height": 0.2})
    doc.saveas(str(ruta))
    return ruta


def test_parsea_alturas_de_anotaciones(resolver: ModuleType, config: dict, tmp_path: Path) -> None:
    plano = _dxf_con_textos(
        tmp_path / "plano.dxf",
        [(0.0, 0.0, "0.7m"), (1.0, 0.0, "1.65m"), (2.0, 0.0, "h-0.3"), (3.0, 0.0, "TE-01")],
    )

    anotaciones = resolver.extraer_anotaciones(plano, config["anotaciones_dxf"]["patrones"])
    valores = sorted(a["altura_m"] for a in anotaciones)

    assert valores == [0.3, 0.7, 1.65]


def test_asignacion_no_repite_anotacion(resolver: ModuleType, config: dict) -> None:
    dispositivos = [
        {"handle": "A", "x": 0.0, "y": 0.0},
        {"handle": "B", "x": 0.10, "y": 0.0},
    ]
    anotaciones = [{"texto": "1.05m", "x": 0.02, "y": 0.0, "altura_m": 1.05}]

    asignadas, _ = resolver.asignar_anotaciones(
        dispositivos, anotaciones, config["anotaciones_dxf"]["radio_asignacion_m"]
    )

    assert list(asignadas) == ["A"]


def test_precedencia_excepcion_sobre_anotacion(resolver: ModuleType, config: dict) -> None:
    inventario = {
        "dispositivos": [
            {"handle": "9E", "nombre": "ELEC-T-GFCI-t-15A", "x": 0.0, "y": 0.0},
            {"handle": "ZZ", "nombre": "ELEC-T-D-t-15A", "x": 5.0, "y": 5.0},
        ]
    }
    anotaciones = [{"texto": "1.05m", "x": 0.05, "y": 0.0, "altura_m": 1.05}]

    resultado = resolver.resolver(inventario, config, anotaciones)
    por_handle = {d["handle"]: d for d in resultado["dispositivos"]}

    assert por_handle["9E"]["altura_local_m"] == 1.10
    assert por_handle["9E"]["origen_altura"] == "excepcion"
    assert por_handle["ZZ"]["altura_local_m"] == 0.30
    assert any(c["motivo"] == "anotacion contradice excepcion" for c in resultado["conflictos"])


def test_regla_base_y_sin_regla(resolver: ModuleType, config: dict) -> None:
    inventario = {
        "dispositivos": [
            {"handle": "L1", "nombre": "Bala Stil Led 13W", "x": 9.0, "y": 9.0},
            {"handle": "X1", "nombre": "DESCONOCIDO", "x": 9.0, "y": 9.0},
        ]
    }

    resultado = resolver.resolver(inventario, config, [])
    por_handle = {d["handle"]: d for d in resultado["dispositivos"]}

    assert por_handle["L1"]["altura_local_m"] == 2.60
    assert por_handle["L1"]["origen_altura"] == "regla_base"
    assert por_handle["X1"]["altura_local_m"] is None
    assert por_handle["X1"]["origen_altura"] == "sin_regla"


def test_z_absoluta_suma_la_elevacion_del_nivel(resolver: ModuleType, config: dict) -> None:
    inventario = {"dispositivos": [{"handle": "BA", "nombre": "ELEC-T-D-t-15A", "x": 0.0, "y": 0.0}]}

    resultado = resolver.resolver(inventario, config, [])

    assert resultado["dispositivos"][0]["z_absoluta_m"] == pytest.approx(13.92, abs=1e-6)
