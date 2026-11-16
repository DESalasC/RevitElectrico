# -*- coding: utf-8 -*-
"""Test de la normalizacion de texto para JSON en los scripts IronPython de F0.

Reproduce el fallo real observado en Revit:

    UnicodeDecodeError: 'unknown' codec can't decode byte 0xe1
    ... py_encode_basestring_ascii

Causa: en IronPython 2.7 los nombres de familia y tipo llegan como ``str``, que es una
cadena de BYTES en la codificacion local (cp1252). ``json.dump(..., ensure_ascii=True)``
intenta decodificarlos como ASCII y falla.

Las funciones se extraen del codigo fuente que se ejecuta en Revit (no se copian), para
que la prueba cubra el archivo real y no una reimplementacion.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2] / "src" / "fase-6-revit"

SCRIPTS = {
    "censo_benchmark": RAIZ / "RE_F0_CENSO_BENCHMARK_v01.py",
    "verificador_guid": RAIZ / "RE_F0_VERIFICAR_E06_v01.py",
    "verificador_uniqueid": RAIZ / "RE_F0_VERIFICAR_E06_v02.py",
}

FUNCIONES = ("_a_texto", "_normalizar")


def cargar_funciones(ruta: Path, nombres: tuple[str, ...] = FUNCIONES) -> dict:
    """Extrae las funciones indicadas del fuente y las compila en un espacio aislado."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    nodos = [n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name in nombres]
    faltantes = set(nombres) - set(n.name for n in nodos)
    assert not faltantes, "Faltan funciones en {ruta}: {f}".format(ruta=ruta, f=sorted(faltantes))

    modulo = ast.Module(body=nodos, type_ignores=[])
    espacio: dict = {}
    exec(compile(modulo, str(ruta), "exec"), espacio)
    return espacio


@pytest.fixture(params=sorted(SCRIPTS), ids=sorted(SCRIPTS))
def funciones(request: pytest.FixtureRequest) -> dict:
    return cargar_funciones(SCRIPTS[request.param])


def test_decodifica_cp1252(funciones: dict) -> None:
    """0xF1 = 'ñ' en cp1252, el byte que rompio el censo."""
    assert funciones["_a_texto"](b"Ba\xf1o") == "Baño"


def test_decodifica_utf8(funciones: dict) -> None:
    assert funciones["_a_texto"](b"Ba\xc3\xb1o") == "Baño"


def test_texto_ya_decodificado_pasa_intacto(funciones: dict) -> None:
    assert funciones["_a_texto"]("Baño") == "Baño"


def test_unicode_con_bom_pierde_el_bom(funciones: dict) -> None:
    """Fallo real en Revit: u'\ufeffSONO FLEX 13 trim' hacia UnicodeEncodeError."""
    assert funciones["_a_texto"]("\ufeffSONO FLEX 13 trim") == "SONO FLEX 13 trim"


def test_bytes_utf8_con_bom_pierde_el_bom(funciones: dict) -> None:
    assert funciones["_a_texto"](b"\xef\xbb\xbfSONO FLEX 10 trim") == "SONO FLEX 10 trim"


@pytest.fixture(params=sorted(SCRIPTS), ids=sorted(SCRIPTS))
def ruta_actual(request: pytest.FixtureRequest) -> Path:
    return SCRIPTS[request.param]


def _usa_isinstance_bytes(fuente: str) -> bool:
    """Detecta llamadas reales a isinstance(x, bytes) ignorando docstrings."""
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Call):
            continue
        if not isinstance(nodo.func, ast.Name) or nodo.func.id != "isinstance":
            continue
        if len(nodo.args) == 2 and isinstance(nodo.args[1], ast.Name) and nodo.args[1].id == "bytes":
            return True
    return False


def test_detecta_el_tipo_texto_del_interprete(ruta_actual: Path) -> None:
    """Regresion doble: ni hasattr(decode) ni isinstance(bytes) sirven en IronPython."""
    fuente = ruta_actual.read_text(encoding="utf-8")
    assert "tipo_texto = unicode" in fuente
    assert "except NameError" in fuente
    assert "isinstance(valor, tipo_texto)" in fuente
    assert not _usa_isinstance_bytes(fuente)


def test_decodifica_objeto_con_decode_que_no_es_texto(funciones: dict) -> None:
    """Emula el caso IronPython: un ``str`` que no es el tipo texto del interprete."""

    class FalsoBytes(object):
        def __init__(self, crudo):
            self.crudo = crudo

        def decode(self, codec):
            return self.crudo.decode(codec)

    assert funciones["_a_texto"](FalsoBytes(b"Ba\xf1o")) == "Baño"


def test_normaliza_estructura_anidada(funciones: dict) -> None:
    entrada = {b"clave\xf1": [b"valor\xe1", {"hondo": b"Comunicaci\xf3n"}]}
    salida = funciones["_normalizar"](entrada)

    assert salida == {"claveñ": ["valorá", {"hondo": "Comunicación"}]}


def test_dump_ascii_no_falla_con_cp1252(funciones: dict) -> None:
    """Esta es la operacion exacta que lanzaba UnicodeDecodeError en Revit."""
    datos = {"familias": [{"familia": b"M_Toma doble", "tipo": "Com\xfan"}]}
    texto = json.dumps(funciones["_normalizar"](datos), ensure_ascii=True, sort_keys=True)

    assert isinstance(texto, str)
    assert "\\u00fa" in texto  # 'ú' escapada: JSON ASCII puro
    assert json.loads(texto)["familias"][0]["tipo"] == "Común"


def test_los_tres_escritores_normalizan_antes_de_serializar() -> None:
    for nombre, ruta in SCRIPTS.items():
        fuente = ruta.read_text(encoding="utf-8")
        assert "_normalizar(" in fuente, "{n} no normaliza".format(n=nombre)
        serializa_normalizado = (
            "json.dump(_normalizar(" in fuente or "json.dumps(_normalizar(" in fuente
        )
        assert serializa_normalizado, "{n} no aplica la normalizacion al serializar".format(n=nombre)
