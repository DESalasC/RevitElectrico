# -*- coding: utf-8 -*-
"""Tests del resolvedor de cielorraso.

Cubren el defecto que motivo el modulo: elegir techo por cercania en XY ignorando el nivel.
En CENTRAL-V01 hay 21 techos apilados sobre la misma vertical, asi que el nivel es el primer
filtro, no un detalle.

Se prueba tambien la condicion del operador: `ELEC-NET-PAU` queda por encima del cielorraso.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ / "src" / "fase-6-revit" / "RE_RESOLVER_TECHO_v01.py"


def cargar_modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("re_resolver_techo", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("No se pudo cargar {r}".format(r=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def resolver() -> ModuleType:
    return cargar_modulo()


def techo(id_, nivel, bbox, z_inf=15.82, z_sup=15.84):
    return {"id": id_, "nivel_id": nivel, "bbox": bbox, "z_inferior_m": z_inf, "z_superior_m": z_sup}


# --- seleccion -----------------------------------------------------------------------------

def test_prefiere_el_techo_del_mismo_nivel(resolver: ModuleType) -> None:
    """El de otro nivel esta mas cerca del punto, pero el del nivel del aparato manda."""
    candidatos = [
        techo(1, 100, (0.0, 0.0, 1.0, 1.0)),        # otro nivel, contiene el punto
        techo(2, 200, (0.6, 0.6, 2.6, 2.6)),        # nivel correcto, no lo contiene pero esta cerca
    ]
    elegido = resolver.elegir_techo(candidatos, 0.5, 0.5, nivel_id=200)
    assert elegido is not None
    assert elegido["id"] == 2
    assert elegido["motivo"] == "mas_cercano_del_nivel"


def test_entre_varios_del_nivel_elige_el_que_contiene_el_punto(resolver: ModuleType) -> None:
    candidatos = [
        techo(1, 200, (0.0, 0.0, 2.0, 2.0)),
        techo(2, 200, (2.0, 0.0, 6.0, 4.0)),
    ]
    elegido = resolver.elegir_techo(candidatos, 3.0, 1.5, nivel_id=200)
    assert elegido["id"] == 2
    assert elegido["motivo"] == "contiene_el_punto"
    assert elegido["candidatos_que_contienen"] == 1


def test_si_dos_contienen_elige_el_de_centro_mas_cercano(resolver: ModuleType) -> None:
    candidatos = [
        techo(1, 200, (0.0, 0.0, 10.0, 10.0)),
        techo(2, 200, (4.0, 0.0, 6.0, 2.0)),
    ]
    elegido = resolver.elegir_techo(candidatos, 4.5, 1.5, nivel_id=200)
    assert elegido["id"] == 2


def test_sin_techo_del_nivel_devuelve_none(resolver: ModuleType) -> None:
    """No inventa: si el nivel no tiene techo, el aparato se queda sin host."""
    candidatos = [techo(1, 100, (0.0, 0.0, 10.0, 10.0))]
    assert resolver.elegir_techo(candidatos, 5.0, 5.0, nivel_id=200) is None


def test_fuera_de_radio_devuelve_none(resolver: ModuleType) -> None:
    candidatos = [techo(1, 200, (50.0, 50.0, 51.0, 51.0))]
    assert resolver.elegir_techo(candidatos, 0.0, 0.0, nivel_id=200, radio_maximo_m=2.0) is None


def test_sin_nivel_conocido_usa_todos_los_candidatos(resolver: ModuleType) -> None:
    candidatos = [techo(1, 200, (0.0, 0.0, 4.0, 4.0))]
    elegido = resolver.elegir_techo(candidatos, 1.0, 1.0, nivel_id=None)
    assert elegido["id"] == 1


def test_lista_vacia(resolver: ModuleType) -> None:
    assert resolver.elegir_techo([], 0.0, 0.0, nivel_id=200) is None


# --- altura ----------------------------------------------------------------------------------

def test_aparato_a_ras_del_techo(resolver: ModuleType) -> None:
    t = techo(1, 200, (0.0, 0.0, 1.0, 1.0), z_inf=15.72, z_sup=15.74)
    assert resolver.altura_sobre_techo(t, codigo="Bala Stil Led 13W") == pytest.approx(15.72)


def test_aparato_con_offset_bajo_el_techo(resolver: ModuleType) -> None:
    t = techo(1, 200, (0.0, 0.0, 1.0, 1.0), z_inf=15.72, z_sup=15.74)
    assert resolver.altura_sobre_techo(t, codigo="ELEC-F-VENT", offset_m=0.05) == pytest.approx(15.67)


def test_punto_de_consolidacion_queda_por_encima_del_cielorraso(resolver: ModuleType) -> None:
    t = techo(1, 200, (0.0, 0.0, 1.0, 1.0), z_inf=15.72, z_sup=15.74)
    z = resolver.altura_sobre_techo(t, codigo="ELEC-NET-PAU")
    assert z == pytest.approx(15.82)
    assert resolver.cumple_estar_sobre_cielorraso(t, "ELEC-NET-PAU", z) is True


def test_la_cota_de_consolidacion_sube_con_el_techo(resolver: ModuleType) -> None:
    """Con el techo de E07 (2,50) el punto de consolidacion no puede quedarse en 2,70 fijo."""
    e06 = techo(1, 200, (0.0, 0.0, 1.0, 1.0), z_inf=15.82, z_sup=15.84)
    e07 = techo(2, 200, (0.0, 0.0, 1.0, 1.0), z_inf=15.72, z_sup=15.74)
    z6 = resolver.altura_sobre_techo(e06, codigo="ELEC-NET-PAU")
    z7 = resolver.altura_sobre_techo(e07, codigo="ELEC-NET-PAU")
    assert z7 < z6
    assert resolver.cumple_estar_sobre_cielorraso(e07, "ELEC-NET-PAU", z7) is True


def test_detecta_un_consolidation_point_mal_colocado(resolver: ModuleType) -> None:
    """Si alguien lo deja bajo el techo, la comprobacion debe cazarlo."""
    t = techo(1, 200, (0.0, 0.0, 1.0, 1.0), z_inf=15.72, z_sup=15.74)
    assert resolver.cumple_estar_sobre_cielorraso(t, "ELEC-NET-PAU", 15.70) is False


def test_sin_techo_no_hay_altura(resolver: ModuleType) -> None:
    assert resolver.altura_sobre_techo(None, codigo="Bala Stil Led 13W") is None
