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
    # Config sintetica: interesa la precedencia, no el valor real de 9E en el plano.
    config_prueba = dict(config)
    config_prueba["excepciones_por_handle"] = dict(config["excepciones_por_handle"])
    config_prueba["excepciones_por_handle"]["9E"] = {"altura_m": 1.10, "nota": "prueba"}

    inventario = {
        "dispositivos": [
            {"handle": "9E", "nombre": "ELEC-T-GFCI-t-15A", "x": 0.0, "y": 0.0},
            {"handle": "ZZ", "nombre": "ELEC-T-D-t-15A", "x": 5.0, "y": 5.0},
        ]
    }
    anotaciones = [{"texto": "1.05m", "x": 0.05, "y": 0.0, "altura_m": 1.05}]

    resultado = resolver.resolver(inventario, config_prueba, anotaciones)
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


def test_aviso_lejano_no_es_conflicto_si_coincide_con_la_excepcion(resolver: ModuleType, config: dict) -> None:
    """111 tiene anotacion 1.05 a 0,42 m y excepcion 1.05: la distancia no es duda."""
    inventario = {"dispositivos": [{"handle": "111", "nombre": "ELEC-T-GFCI-t-15A", "x": 0.0, "y": 0.0}]}
    anotaciones = [{"texto": "1.05m", "x": 0.417, "y": 0.0, "altura_m": 1.05}]

    resultado = resolver.resolver(inventario, config, anotaciones)

    assert resultado["conflictos"] == []
    assert resultado["dispositivos"][0]["altura_local_m"] == 1.05


def test_anotacion_lejana_que_discrepa_si_reporta(resolver: ModuleType, config: dict) -> None:
    config_prueba = dict(config)
    config_prueba["excepciones_por_handle"] = dict(config["excepciones_por_handle"])
    config_prueba["excepciones_por_handle"]["111"] = {"altura_m": 1.30, "nota": "prueba"}

    inventario = {"dispositivos": [{"handle": "111", "nombre": "ELEC-T-GFCI-t-15A", "x": 0.0, "y": 0.0}]}
    anotaciones = [{"texto": "1.05m", "x": 0.417, "y": 0.0, "altura_m": 1.05}]

    resultado = resolver.resolver(inventario, config_prueba, anotaciones)

    assert any(c["motivo"] == "anotacion contradice excepcion" for c in resultado["conflictos"])


def test_z_absoluta_suma_la_elevacion_del_nivel(resolver: ModuleType, config: dict) -> None:
    inventario = {"dispositivos": [{"handle": "BA", "nombre": "ELEC-T-D-t-15A", "x": 0.0, "y": 0.0}]}

    resultado = resolver.resolver(inventario, config, [])

    assert resultado["dispositivos"][0]["z_absoluta_m"] == pytest.approx(13.92, abs=1e-6)


def _config_por_posicion(config: dict, altura: float = 0.70) -> dict:
    """Config sintetica: sin handles, una excepcion anclada por posicion."""
    prueba = dict(config)
    prueba["excepciones_por_handle"] = {}
    prueba["excepciones_por_apartamento"] = {
        "X 01": [
            {
                "codigo": "ELEC-T-D-t-15A",
                "x": 1.0,
                "y": 2.0,
                "altura_m": altura,
                "element_id_revit": 1,
                "nota": "prueba",
            }
        ]
    }
    return prueba


def test_anclaje_por_posicion_aplica_la_altura(resolver: ModuleType, config: dict) -> None:
    inventario = {"dispositivos": [{"handle": "ZZ", "nombre": "ELEC-T-D-t-15A", "x": 1.0, "y": 2.0}]}

    resultado = resolver.resolver(inventario, _config_por_posicion(config), [], apartamento="X 01")
    dispositivo = resultado["dispositivos"][0]

    assert dispositivo["altura_local_m"] == pytest.approx(0.70)
    assert dispositivo["origen_altura"] == "excepcion_posicion"
    assert resultado["excepciones_ancladas"]["aplicadas_por_posicion"] == 1
    assert resultado["excepciones_ancladas"]["sin_anclar"] == []


def test_anclaje_por_posicion_respeta_la_tolerancia(resolver: ModuleType, config: dict) -> None:
    """A 50 mm de la posicion esperada no se ancla: mejor no aplicar que aplicar mal."""
    inventario = {"dispositivos": [{"handle": "ZZ", "nombre": "ELEC-T-D-t-15A", "x": 1.05, "y": 2.0}]}

    resultado = resolver.resolver(inventario, _config_por_posicion(config), [], apartamento="X 01")
    dispositivo = resultado["dispositivos"][0]

    assert dispositivo["altura_local_m"] == pytest.approx(0.30)  # regla base
    assert dispositivo["origen_altura"] == "regla_base"
    assert len(resultado["excepciones_ancladas"]["sin_anclar"]) == 1


def test_la_posicion_gana_sobre_un_handle_obsoleto(resolver: ModuleType, config: dict) -> None:
    """Si el handle viejo apunta a otro aparato, manda la posicion."""
    prueba = _config_por_posicion(config, altura=0.70)
    prueba["excepciones_por_handle"] = {"ZZ": {"altura_m": 1.65, "nota": "handle de una exportacion anterior"}}
    inventario = {"dispositivos": [{"handle": "ZZ", "nombre": "ELEC-T-D-t-15A", "x": 1.0, "y": 2.0}]}

    resultado = resolver.resolver(inventario, prueba, [], apartamento="X 01")

    assert resultado["dispositivos"][0]["altura_local_m"] == pytest.approx(0.70)
    assert resultado["dispositivos"][0]["origen_altura"] == "excepcion_posicion"


def test_sin_apartamento_no_usa_la_tabla_de_posiciones(resolver: ModuleType, config: dict) -> None:
    inventario = {"dispositivos": [{"handle": "ZZ", "nombre": "ELEC-T-D-t-15A", "x": 1.0, "y": 2.0}]}

    resultado = resolver.resolver(inventario, _config_por_posicion(config), [])

    assert resultado["dispositivos"][0]["altura_local_m"] == pytest.approx(0.30)
    assert resultado["excepciones_ancladas"]["aplicadas_por_posicion"] == 0


def test_datos_ignora_la_anotacion_y_usa_el_estandar(resolver: ModuleType, config: dict) -> None:
    """ELEC-TEL esta estandarizado a 1,00: la anotacion de 1,05 del DXF no debe ganar."""
    inventario = {"dispositivos": [{"handle": "DD", "nombre": "ELEC-TEL", "x": 0.0, "y": 0.0}]}
    anotaciones = [{"texto": "1.05m", "x": 0.05, "y": 0.0, "altura_m": 1.05}]

    resultado = resolver.resolver(inventario, config, anotaciones)
    dispositivo = resultado["dispositivos"][0]

    assert dispositivo["altura_local_m"] == pytest.approx(1.00)
    assert dispositivo["origen_altura"] == "regla_base_estandarizada"
    assert resultado["anotaciones_ignoradas"], "la anotacion descartada debe quedar registrada"
    assert resultado["anotaciones_ignoradas"][0]["anotacion_m"] == pytest.approx(1.05)
