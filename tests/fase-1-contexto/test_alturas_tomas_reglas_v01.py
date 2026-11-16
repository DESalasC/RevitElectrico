# -*- coding: utf-8 -*-
"""Tests de las reglas de altura de montaje (E06).

Estos tests no tocan Revit: convierten ``config/alturas_tomas_v01.json`` en un contrato.
Cubren dos clases de defecto que ya ocurrieron en el proyecto:

1. Contradiccion interna: una excepcion por handle y la ``validacion_esperada`` decian
   alturas distintas para el mismo aparato (9E y 103).
2. Valor obsoleto: la campana y el punto de consolidacion estaban a 1,10 y 1,05 cuando el
   operador confirmo 2,40 y 2,70.

Si alguien vuelve a mover estos valores sin cambiar la evidencia, el test falla.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUTA_CONFIG = RAIZ / "config" / "alturas_tomas_v01.json"
RUTA_DECISIONES = RAIZ / "data" / "referencia" / "decisiones_alturas_E06_v01.json"

CLAVES_REQUERIDAS = (
    "regla_base_altura_m",
    "excepciones_por_handle",
    "validacion_esperada",
    "validacion_esperada_altura_m",
    "offset_bbox_insercion_m",
)


@pytest.fixture(scope="module")
def config() -> dict:
    with RUTA_CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def decisiones() -> dict:
    with RUTA_DECISIONES.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_config_tiene_las_claves_del_contrato(config: dict) -> None:
    for clave in CLAVES_REQUERIDAS:
        assert clave in config, "falta {c} en alturas_tomas_v01.json".format(c=clave)
    assert config["offset_bbox_insercion_m"] == pytest.approx(0.057)


def test_cada_excepcion_es_utilizable(config: dict) -> None:
    excepciones = config["excepciones_por_handle"]
    assert excepciones, "no hay excepciones declaradas"
    for handle, datos in excepciones.items():
        assert isinstance(datos.get("altura_m"), (int, float)), handle
        assert 0.2 <= float(datos["altura_m"]) <= 3.0, handle
        assert isinstance(datos.get("element_id_revit"), int), handle
        assert datos["element_id_revit"] > 0, handle
        assert datos.get("nota"), "la excepcion {h} no explica su motivo".format(h=handle)


def test_validacion_esperada_no_contradice_las_excepciones(config: dict) -> None:
    """Un mismo aparato no puede tener dos alturas esperadas."""
    esperadas = config["validacion_esperada_altura_m"]
    for handle, datos in config["excepciones_por_handle"].items():
        clave = str(datos["element_id_revit"])
        if clave in esperadas:
            assert esperadas[clave] == pytest.approx(float(datos["altura_m"]), abs=1e-6), (
                "handle {h} (element {e}): excepcion {a} m != validacion {b} m".format(
                    h=handle, e=clave, a=datos["altura_m"], b=esperadas[clave]
                )
            )


def test_validacion_esperada_solo_contiene_elementos_conocidos(config: dict) -> None:
    """Todo element_id esperado debe salir de una excepcion o de las dos cotas del operador."""
    ids_excepciones = {str(d["element_id_revit"]) for d in config["excepciones_por_handle"].values()}
    ids_por_regla_base = {"5529820", "5529858"}  # punto de consolidacion y timbre
    desconocidos = set(config["validacion_esperada_altura_m"]) - ids_excepciones - ids_por_regla_base
    assert not desconocidos, "ids sin regla que los respalde: {d}".format(d=sorted(desconocidos))


def test_valores_confirmados_por_el_operador(config: dict) -> None:
    base = config["regla_base_altura_m"]
    esperadas = config["validacion_esperada_altura_m"]
    assert base["ELEC-CAMPANA"] == pytest.approx(2.40)
    assert base["ELEC-NET-PAU"] == pytest.approx(2.70)
    assert base["ELEC-TIMBRE"] == pytest.approx(1.10)
    assert base["ELEC-TEL"] == pytest.approx(1.00)
    assert esperadas["5529844"] == pytest.approx(2.40)  # campana
    assert esperadas["5529820"] == pytest.approx(2.70)  # punto de consolidacion
    assert esperadas["5529858"] == pytest.approx(1.10)  # timbre


def test_las_tomas_de_datos_estan_estandarizadas(config: dict) -> None:
    """Decision 2026-11-16: las diez tomas de datos a 1,00, ignorando la anotacion de 1,05."""
    assert config["regla_base_altura_m"]["ELEC-TEL"] == pytest.approx(1.00)
    ignoradas = config.get("anotaciones_ignoradas_por_codigo", {})
    assert "ELEC-TEL" in ignoradas, "sin esta clave el plano vuelve a imponer 1,05"
    assert ignoradas["ELEC-TEL"].strip(), "la excepcion debe explicar por que se ignora"


def test_las_tres_tomas_de_cocina_conservan_su_cota(config: dict) -> None:
    esperadas = config["validacion_esperada_altura_m"]
    assert esperadas["5529846"] == pytest.approx(0.70)  # conexion de estufa
    assert esperadas["5529849"] == pytest.approx(1.65)  # sobre el extractor
    assert esperadas["5529855"] == pytest.approx(1.05)  # GFCI sobre el meson


def test_prosa_de_validacion_no_contradice_las_excepciones(config: dict) -> None:
    """El texto de ``validacion_esperada`` tambien manda para un humano: si dice otra cota, falla.

    Este es el defecto original: la prosa decia ``9E 1.10`` y ``103 a 1.10`` mientras las
    excepciones de esos mismos handles decian 1,05.
    """
    import re

    prosa = " ".join(str(v) for v in config["validacion_esperada"].values())
    revisados = 0
    for handle, datos in config["excepciones_por_handle"].items():
        patron = re.compile(r"\b{h}\b\s+(?:a\s+)?(\d+[.,]\d+)".format(h=re.escape(handle)))
        for encontrado in patron.finditer(prosa):
            valor = float(encontrado.group(1).replace(",", "."))
            assert valor == pytest.approx(float(datos["altura_m"]), abs=1e-6), (
                "la prosa dice {v} para {h} y la excepcion dice {e}".format(
                    v=valor, h=handle, e=datos["altura_m"]
                )
            )
            revisados += 1
    assert revisados >= 3, "la prosa dejo de mencionar handles con cota: el test ya no vigila nada"


def test_decisiones_del_operador_son_coherentes_con_las_reglas(config: dict, decisiones: dict) -> None:
    """Las decisiones registradas y el contrato de alturas no pueden divergir."""
    assert decisiones["regla"].startswith("El valor del operador prevalece")
    esperadas = config["validacion_esperada_altura_m"]
    for cota in decisiones["cotas"]:
        clave = str(cota["element_id"])
        if clave in esperadas:
            assert esperadas[clave] == pytest.approx(float(cota["altura_correcta_m"]), abs=1e-6)
    for host in decisiones["hosts_perdidos"]:
        assert host["accion"] == "restaurar_host"
        assert host["altura_correcta_m"] > 0
