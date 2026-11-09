# -*- coding: utf-8 -*-
"""Tests del pipeline de ruteo (sin Revit, sin DXF real)."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTEO = os.path.join(RAIZ, "src", "fase-6-revit", "ruteo")
sys.path.insert(0, RUTEO)

from config import ConfigError, cargar_config            # noqa: E402
from dimensionamiento import dimensionar, dimensionar_servicio   # noqa: E402
from dxf_lector import ContenidoDXF, cables_desde_nombre  # noqa: E402
from modelos import Dispositivo, Marcador, Polilinea      # noqa: E402
from ruteador import (                                    # noqa: E402
    detectar_cruces, dist_punto_polilinea, dist_punto_segmento,
    interseccion_segmentos, rutear,
)
from servicio import resolver_servicio                    # noqa: E402
from modelos import ExtremoTramo, Tramo                   # noqa: E402

CONFIG = os.path.join(RAIZ, "config", "ruteo_config_v04.json")


@pytest.fixture(scope="module")
def cfg():
    return cargar_config(CONFIG, RAIZ)


# --- nomenclatura de marcadores ---------------------------------------
@pytest.mark.parametrize("nombre,cables", [
    ("1FTN", 3), ("1FTNR", 4), ("1FTR", 3), ("2F2N1T1R", 6),
    ("1TNR", 3), ("2FT2N", 5), ("3F2N1T", 6),
    ("Bala Stil Led 12W", None), ("", None), ("1FTNX", None), ("FTN", None),
])
def test_cables_desde_nombre(nombre, cables):
    assert cables_desde_nombre(nombre) == cables


# --- configuracion -----------------------------------------------------
def test_config_carga_tablas(cfg):
    assert set(cfg.tablas) == {"PVC", "PVC-SCH40", "EMT"}
    assert cfg.capacidad("PVC", "12 AWG").capacidades['1/2"'] == 11
    assert cfg.capacidad("EMT", "12 AWG").capacidades['2"'] == 97
    assert cfg.capacidad("PVC-SCH40", "10 AWG").capacidades['3/4"'] == 10


def test_config_servicios_validos(cfg):
    assert cfg.servicio_de_capa_tuberia("ELEC-LIGHT-PIPE") == "ILUMINACION"
    assert cfg.servicio_de_capa_dispositivo("ELEC-APPL-TOMAS") == "TOMAS"
    assert cfg.servicio_de_capa_tuberia("NO-EXISTE") is None


def test_config_altura_y_cota(cfg):
    assert cfg.altura_dispositivo("ELEC-BALA LED 13 W") == 2.65
    assert cfg.altura_dispositivo("CAPA-DESCONOCIDA") == cfg.datos["altura_default_dispositivo_m"]
    assert cfg.cota_banda("ILUMINACION") == 2.65


# --- dimensionamiento --------------------------------------------------
@pytest.mark.parametrize("cables,pulgadas", [
    (1, '1/2"'), (3, '1/2"'), (6, '1/2"'), (11, '1/2"'),
    (12, '3/4"'), (19, '3/4"'), (20, '1"'), (32, '1"'),
    (33, '1-1/4"'), (53, '1-1/4"'), (54, '1-1/2"'), (71, '2"'), (109, '2"'),
])
def test_dimensionar_pvc_12awg(cfg, cables, pulgadas):
    assert dimensionar(cfg, cables).pulgadas == pulgadas


def test_dimensionar_fuera_de_tabla(cfg):
    with pytest.raises(ConfigError):
        dimensionar(cfg, 200)


def test_dimensionar_cables_invalidos(cfg):
    with pytest.raises(ValueError):
        dimensionar(cfg, 0)


def test_diametros_mm(cfg):
    assert dimensionar(cfg, 3).mm == 12.70
    assert dimensionar(cfg, 12).mm == 19.05


# --- geometria ---------------------------------------------------------
def test_dist_punto_segmento():
    assert dist_punto_segmento((1, 1), (0, 0), (2, 0)) == pytest.approx(1.0)
    assert dist_punto_segmento((0, 0), (0, 0), (2, 0)) == pytest.approx(0.0)
    assert dist_punto_segmento((3, 0), (0, 0), (2, 0)) == pytest.approx(1.0)


def test_dist_punto_polilinea():
    puntos = ((0, 0), (2, 0), (2, 2))
    assert dist_punto_polilinea((1, 0.5), puntos) == pytest.approx(0.5)
    assert dist_punto_polilinea((2, 1), puntos) == pytest.approx(0.0)


# --- servicio ----------------------------------------------------------
def _ext(tipo, servicio=None, capa="X", altura=1.2):
    return ExtremoTramo(tipo=tipo, x=0, y=0, distancia_m=0.0,
                        servicio=servicio, capa=capa, altura_m=altura)


def test_servicio_por_extremos(cfg):
    s, avisos = resolver_servicio(cfg, "ELEC-Powr-service", [_ext("dispositivo", "TOMAS"), _ext("dispositivo", "TOMAS")])
    assert s == "TOMAS"
    assert any("difiere de la capa" in a for a in avisos)


def test_power_pipe_es_tomas_en_apartamento(cfg):
    """Decision del operador 2026-11-09: los tramos de tomas van como TOMAS."""
    assert cfg.servicio_de_capa_tuberia("ELEC-POWER- PIPE") == "TOMAS"


def test_servicio_por_capa_si_no_hay_extremos(cfg):
    s, avisos = resolver_servicio(cfg, "ELEC-LIGHT-PIPE", [_ext("libre"), _ext("libre")])
    assert s == "ILUMINACION"
    assert avisos == []


def test_servicio_desempate_por_prioridad(cfg):
    s, avisos = resolver_servicio(
        cfg, "ELEC-POWER- PIPE",
        [_ext("dispositivo", "TOMAS"), _ext("dispositivo", "COMUNICACIONES")])
    assert s == "COMUNICACIONES"
    assert any("prioridad" in a for a in avisos)


def test_servicio_capa_no_mapeada(cfg):
    s, avisos = resolver_servicio(cfg, "CAPA-RARA", [_ext("libre"), _ext("libre")])
    assert s == "FUERZA"
    assert any("no mapeada" in a for a in avisos)


# --- pipeline completo con datos sinteticos ---------------------------
def _contenido_sintetico():
    disp = [
        Dispositivo(handle="D1", nombre="Bala", capa="ELEC-BALA LED 13 W", x=0.0, y=0.0),
        Dispositivo(handle="D2", nombre="Bala", capa="ELEC-BALA LED 13 W", x=4.0, y=0.0),
        Dispositivo(handle="D3", nombre="Toma", capa="ELEC-APPL-TOMAS", x=0.0, y=3.0),
        Dispositivo(handle="D4", nombre="Toma", capa="ELEC-APPL-TOMAS", x=3.0, y=3.0),
    ]
    marcadores = [
        Marcador(handle="M1", nombre="1FTNR", capa="Elec-Lite-Wire", x=2.0, y=0.0, cables=4),
        Marcador(handle="M2", nombre="1FTN", capa="Elec-Lite-Wire", x=1.5, y=3.0, cables=3),
    ]
    polilineas = [
        Polilinea(handle="P1", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 0.0), (4.0, 0.0))),
        Polilinea(handle="P2", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 3.0), (3.0, 3.0))),
    ]
    return ContenidoDXF(ruta="sintetico.dxf", dispositivos=disp,
                        marcadores=marcadores, polilineas=polilineas)


def test_pipeline_sintetico(cfg):
    res = rutear(cfg, _contenido_sintetico())
    assert len(res.tramos) == 2
    por_handle = {t.handle_dxf: t for t in res.tramos}

    p1 = por_handle["P1"]
    assert p1.cables == 4 and p1.cables_origen == "marcador"
    assert p1.diametro_pulgadas == '1/2"'
    assert p1.servicio == "ILUMINACION"
    assert p1.largo_m == pytest.approx(4.0)   # 2 bajantes 2.65->2.65: no aplica (misma cota)

    p2 = por_handle["P2"]
    assert p2.cables == 3
    assert p2.servicio == "TOMAS"             # gana el servicio de los extremos
    assert any("difiere de la capa" in a for a in p2.avisos)


def test_pipeline_puntos_3d_tienen_cota(cfg):
    """Cada punto 3D debe estar entre la altura del dispositivo y la banda de su servicio."""
    res = rutear(cfg, _contenido_sintetico())
    for t in res.tramos:
        zetas = [p[2] for p in t.puntos_3d]
        assert min(zetas) >= 0.30 - 1e-6
        assert max(zetas) <= cfg.cota_banda(t.servicio) + 1e-6


def test_pipeline_bajante_a_toma(cfg):
    """Un toma a 0.30 m debe generar bajante desde la banda de 2.65 m."""
    contenido = ContenidoDXF(
        ruta="sintetico.dxf",
        dispositivos=[
            Dispositivo(handle="D3", nombre="Toma", capa="ELEC-APPL-TOMAS", x=0.0, y=3.0),
            Dispositivo(handle="D4", nombre="Toma", capa="ELEC-APPL-TOMAS", x=3.0, y=3.0),
        ],
        marcadores=[Marcador(handle="M2", nombre="1FTN", capa="Elec-Lite-Wire", x=1.5, y=3.0, cables=3)],
        polilineas=[Polilinea(handle="P2", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 3.0), (3.0, 3.0)))],
    )
    res = rutear(cfg, contenido)
    t = res.tramos[0]
    banda = cfg.cota_banda("TOMAS")
    zetas = [p[2] for p in t.puntos_3d]
    assert min(zetas) == pytest.approx(0.30)
    assert max(zetas) == pytest.approx(banda)
    # 3 m horizontales + 2 bajantes de (banda - 0.30)
    assert t.largo_m == pytest.approx(3.0 + 2 * (banda - 0.30), abs=0.01)


def test_tramo_corto_se_omite(cfg):
    contenido = ContenidoDXF(
        ruta="sintetico.dxf", dispositivos=[], marcadores=[],
        polilineas=[Polilinea(handle="PX", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 0.0), (0.01, 0.0)))],
    )
    res = rutear(cfg, contenido)
    assert len(res.tramos) == 0
    assert any("omitido" in a for a in res.avisos)


def test_tramo_sin_marcador_usa_default(cfg):
    contenido = ContenidoDXF(
        ruta="sintetico.dxf",
        dispositivos=[
            Dispositivo(handle="D1", nombre="Bala", capa="ELEC-BALA LED 13 W", x=0.0, y=0.0),
            Dispositivo(handle="D2", nombre="Bala", capa="ELEC-BALA LED 13 W", x=2.0, y=0.0),
        ],
        marcadores=[],
        polilineas=[Polilinea(handle="P1", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 0.0), (2.0, 0.0)))],
    )
    res = rutear(cfg, contenido)
    t = res.tramos[0]
    assert t.cables_origen == "default"
    assert t.cables == cfg.datos["reglas_cables"]["cables_default_sin_marcador"]
    assert any("se asume" in a for a in t.avisos)


def test_tramo_hereda_de_vecino(cfg):
    contenido = ContenidoDXF(
        ruta="sintetico.dxf",
        dispositivos=[
            Dispositivo(handle="D1", nombre="Bala", capa="ELEC-BALA LED 13 W", x=0.0, y=0.0),
            Dispositivo(handle="D2", nombre="Bala", capa="ELEC-BALA LED 13 W", x=2.0, y=0.0),
            Dispositivo(handle="D3", nombre="Bala", capa="ELEC-BALA LED 13 W", x=4.0, y=0.0),
        ],
        marcadores=[Marcador(handle="M1", nombre="1FTNR", capa="Elec-Lite-Wire", x=1.0, y=0.0, cables=4)],
        polilineas=[
            Polilinea(handle="P1", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 0.0), (2.0, 0.0))),
            Polilinea(handle="P2", capa="ELEC-LIGHT-PIPE", puntos=((2.0, 0.0), (4.0, 0.0))),
        ],
    )
    res = rutear(cfg, contenido)
    por_handle = {t.handle_dxf: t for t in res.tramos}
    assert por_handle["P1"].cables_origen == "marcador"
    assert por_handle["P2"].cables_origen == "heredado"
    assert por_handle["P2"].cables == 4


def test_resumen_coherente(cfg):
    res = rutear(cfg, _contenido_sintetico())
    s = res.resumen()
    assert s["tramos"] == 2
    # P1: 4.0 m horizontales (ambas luminarias a la banda) -> 4.0
    # P2: 3.0 m + 2 bajantes de (cota TOMAS - 0.30)
    esperado = 4.0 + 3.0 + 2 * (cfg.cota_banda("TOMAS") - 0.30)
    assert s["longitud_total_m"] == pytest.approx(esperado, abs=0.01)
    assert s["por_servicio"]["ILUMINACION"] == 1
    assert s["por_servicio"]["TOMAS"] == 1


# --- cajas de conexion -------------------------------------------------
def test_extremo_libre_genera_caja(cfg):
    """Un extremo sin aparato cerca de una luminaria se resuelve como caja."""
    contenido = ContenidoDXF(
        ruta="sintetico.dxf",
        dispositivos=[
            # Luminaria en el inicio (fija el servicio del tramo en ILUMINACION)
            Dispositivo(handle="L0", nombre="Bala", capa="ELEC-BALA LED 13 W", x=0.0, y=0.0),
            # La tuberia termina a 0.80 m de la segunda luminaria (mas alla de 0.50)
            Dispositivo(handle="L1", nombre="Bala", capa="ELEC-BALA LED 13 W", x=2.80, y=0.0),
        ],
        marcadores=[Marcador(handle="M1", nombre="1FTNR", capa="Elec-Lite-Wire", x=1.0, y=0.0, cables=4)],
        polilineas=[Polilinea(handle="P1", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 0.0), (2.0, 0.0)))],
    )
    res = rutear(cfg, contenido)
    assert len(res.cajas) == 1
    caja = res.cajas[0]
    assert caja.aparato_handle == "L1"
    assert caja.distancia_m == pytest.approx(0.80)
    assert caja.cota_m == pytest.approx(cfg.datos["cajas_conexion"]["cota_m"])
    extremo = res.tramos[0].extremos[1]
    assert extremo.tipo == "caja"


def test_caja_respeta_radio_de_busqueda(cfg):
    contenido = ContenidoDXF(
        ruta="sintetico.dxf",
        dispositivos=[
            Dispositivo(handle="L1", nombre="Bala", capa="ELEC-BALA LED 13 W", x=5.0, y=0.0),
        ],
        marcadores=[Marcador(handle="M1", nombre="1FTN", capa="Elec-Lite-Wire", x=1.0, y=0.0, cables=3)],
        polilineas=[Polilinea(handle="P1", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 0.0), (2.0, 0.0)))],
    )
    res = rutear(cfg, contenido)
    assert res.cajas == []
    assert any("ni caja" in a for t in res.tramos for a in t.avisos)


# --- cruces en planta --------------------------------------------------
def test_interseccion_segmentos():
    p = interseccion_segmentos((0, 0), (2, 0), (1, -1), (1, 1))
    assert p == pytest.approx((1.0, 0.0))
    assert interseccion_segmentos((0, 0), (1, 0), (2, 0), (3, 0)) is None
    assert interseccion_segmentos((0, 0), (1, 0), (2, 1), (3, 1)) is None


def test_detectar_cruces_entre_servicios(cfg):
    a = Tramo(id="A", handle_dxf="A", capa="ELEC-LIGHT-PIPE", servicio="ILUMINACION",
              cables=3, cables_origen="marcador", material="PVC", calibre="12 AWG",
              diametro_pulgadas='1/2"', diametro_mm=12.7, largo_m=2.0, cota_m=2.65,
              puntos_2d=[(0.0, 0.0), (2.0, 0.0)])
    b = Tramo(id="B", handle_dxf="B", capa="ELEC-POWER- PIPE", servicio="TOMAS",
              cables=3, cables_origen="marcador", material="PVC", calibre="12 AWG",
              diametro_pulgadas='1/2"', diametro_mm=12.7, largo_m=2.0, cota_m=2.68,
              puntos_2d=[(1.0, -1.0), (1.0, 1.0)])
    cruces = detectar_cruces([a, b])
    assert len(cruces) == 1
    assert cruces[0].separacion_m == pytest.approx(0.03)


def test_cruces_mismo_servicio_no_se_reportan(cfg):
    a = Tramo(id="A", handle_dxf="A", capa="ELEC-LIGHT-PIPE", servicio="ILUMINACION",
              cables=3, cables_origen="marcador", material="PVC", calibre="12 AWG",
              diametro_pulgadas='1/2"', diametro_mm=12.7, largo_m=2.0, cota_m=2.65,
              puntos_2d=[(0.0, 0.0), (2.0, 0.0)])
    b = Tramo(id="B", handle_dxf="B", capa="ELEC-LIGHT-PIPE", servicio="ILUMINACION",
              cables=3, cables_origen="marcador", material="PVC", calibre="12 AWG",
              diametro_pulgadas='1/2"', diametro_mm=12.7, largo_m=2.0, cota_m=2.65,
              puntos_2d=[(1.0, -1.0), (1.0, 1.0)])
    assert detectar_cruces([a, b]) == []


def test_banda_dentro_de_rango(cfg):
    banda = cfg.datos["banda"]
    for servicio in cfg.datos["servicios_permitidos"]:
        cota = cfg.cota_banda(servicio)
        assert banda["cota_min_m"] - 1e-9 <= cota <= banda["cota_max_m"] + 1e-9


# --- comunicaciones y ancla -------------------------------------------
def test_comunicaciones_diametro_fijo(cfg):
    """Decision del operador: COMUNICACIONES va en 3/4" sin importar los cables."""
    dim, origen, motivo = dimensionar_servicio(cfg, "COMUNICACIONES", 3)
    assert dim.pulgadas == '3/4"'
    assert dim.mm == pytest.approx(19.05)
    assert origen == "fijo_servicio"
    assert motivo


def test_iluminacion_usa_cables(cfg):
    dim, origen, _ = dimensionar_servicio(cfg, "ILUMINACION", 4)
    assert origen == "cables"
    assert dim.pulgadas == '1/2"'


def test_servicio_fijado_por_capa(cfg):
    """ELEC-Data-Service manda sobre los extremos: siempre COMUNICACIONES."""
    s, avisos = resolver_servicio(
        cfg, "ELEC-Data-Service",
        [_ext("dispositivo", "ILUMINACION"), _ext("dispositivo", "TOMAS")])
    assert s == "COMUNICACIONES"
    assert any("fijado por capa" in a for a in avisos)


def test_ancla_detectada(cfg):
    contenido = ContenidoDXF(
        ruta="sintetico.dxf",
        dispositivos=[
            Dispositivo(handle="P1", nombre="TB-Parcial", capa="ELEC-POWER-PANEL", x=-2.472, y=0.506),
            Dispositivo(handle="D1", nombre="Bala", capa="ELEC-BALA LED 13 W", x=0.0, y=0.0),
            Dispositivo(handle="D2", nombre="Bala", capa="ELEC-BALA LED 13 W", x=2.0, y=0.0),
        ],
        marcadores=[Marcador(handle="M1", nombre="1FTN", capa="Elec-Lite-Wire", x=1.0, y=0.0, cables=3)],
        polilineas=[Polilinea(handle="L1", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 0.0), (2.0, 0.0)))],
    )
    res = rutear(cfg, contenido)
    assert res.ancla["bloque_dxf"] == "TB-Parcial"
    assert res.ancla["x_dxf"] == pytest.approx(-2.472)
    assert res.ancla["y_dxf"] == pytest.approx(0.506)


def test_marcar_revision_fuerza(cfg):
    """--marcar-revision FUERZA reetiqueta los tramos con extremos libres."""
    contenido = ContenidoDXF(
        ruta="sintetico.dxf",
        dispositivos=[
            Dispositivo(handle="D1", nombre="Bala", capa="ELEC-BALA LED 13 W", x=0.0, y=0.0),
        ],
        marcadores=[Marcador(handle="M1", nombre="1FTN", capa="Elec-Lite-Wire", x=2.0, y=0.0, cables=3)],
        polilineas=[Polilinea(handle="L1", capa="ELEC-LIGHT-PIPE", puntos=((0.0, 0.0), (4.0, 0.0)))],
    )
    res = rutear(cfg, contenido, marcar_revision="FUERZA")
    assert len(res.tramos_en_revision()) >= 1
    assert res.tramos[0].servicio == "FUERZA"
    assert any("Marcado para revision" in a for a in res.tramos[0].avisos)
