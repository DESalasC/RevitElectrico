# -*- coding: utf-8 -*-
"""Tests de F0 - reconciliacion de base documental.

Cubren: hash de archivo, descripcion de documentos presentes y ausentes, deteccion
de benchmark identico al vigente, y los dos codigos de salida del CLI.

El modulo se carga por ruta porque ``src/fase-0-gobierno`` no es un paquete instalable.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

RAIZ_TEST = Path(__file__).resolve().parents[2]
RUTA_MODULO = RAIZ_TEST / "src" / "fase-0-gobierno" / "RE_F0_RECONCILIACION_v01.py"
RUTA_FIXTURE = Path(__file__).parent / "fixture_RE_F0_RECONCILIACION_v01.json"


def cargar_modulo() -> ModuleType:
    """Importa el script de F0 por ruta de archivo."""
    spec = importlib.util.spec_from_file_location("re_f0_reconciliacion", RUTA_MODULO)
    if spec is None or spec.loader is None:  # pragma: no cover - proteccion
        raise ImportError("No se pudo cargar {ruta}".format(ruta=RUTA_MODULO))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def f0() -> ModuleType:
    return cargar_modulo()


@pytest.fixture(scope="module")
def datos_fixture() -> dict:
    with RUTA_FIXTURE.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_sha256_archivo_conocido(f0: ModuleType, tmp_path: Path) -> None:
    ruta = tmp_path / "muestra.rvt"
    contenido = b"contenido-de-prueba-123"
    ruta.write_bytes(contenido)

    esperado = hashlib.sha256(contenido).hexdigest()
    assert f0.sha256_archivo(ruta) == esperado
    assert len(f0.sha256_archivo(ruta)) == 64


def test_describir_documento_encontrado(f0: ModuleType, tmp_path: Path, datos_fixture: dict) -> None:
    nombre = datos_fixture["documentos"]["vigente"]
    contenido = datos_fixture["contenido_prueba"]["vigente"].encode("utf-8")
    (tmp_path / nombre).write_bytes(contenido)

    doc = f0.describir_documento("vigente", nombre, tmp_path)

    assert doc["encontrado"] is True
    assert doc["rol"] == "vigente"
    assert doc["bytes"] == len(contenido)
    assert doc["sha256"] == hashlib.sha256(contenido).hexdigest()
    assert doc["mtime_iso"] is not None
    assert doc["ruta_relativa"].startswith("ArchivosBase")


def test_describir_documento_ausente_no_lanza(f0: ModuleType, tmp_path: Path, datos_fixture: dict) -> None:
    nombre = datos_fixture["documentos"]["benchmark"]

    doc = f0.describir_documento("benchmark", nombre, tmp_path)

    assert doc["encontrado"] is False
    assert doc["sha256"] is None
    assert doc["bytes"] is None


def test_recolectar_asigna_roles_en_orden(f0: ModuleType, tmp_path: Path, datos_fixture: dict) -> None:
    docs = datos_fixture["documentos"]
    for nombre in [docs["vigente"], docs["benchmark"], *docs["historicos"]]:
        (tmp_path / nombre).write_bytes(b"x")

    resultado = f0.recolectar(tmp_path, docs["vigente"], docs["benchmark"], tuple(docs["historicos"]))

    assert [d["rol"] for d in resultado] == datos_fixture["esperado"]["roles"]
    assert len(resultado) == datos_fixture["esperado"]["documentos_declarados"]


def test_verificar_detecta_benchmark_identico(f0: ModuleType, tmp_path: Path, datos_fixture: dict) -> None:
    docs = datos_fixture["documentos"]
    mismo = b"mismo-contenido"
    (tmp_path / docs["vigente"]).write_bytes(mismo)
    (tmp_path / docs["benchmark"]).write_bytes(mismo)

    documentos = f0.recolectar(tmp_path, docs["vigente"], docs["benchmark"], ())
    verif = f0.verificar(documentos)

    assert verif["todos_obligatorios_presentes"] is True
    assert verif["benchmark_distinto_vigente"] is False
    assert any("mismo hash" in aviso for aviso in verif["advertencias"])


def test_main_escribe_artefactos(f0: ModuleType, tmp_path: Path, datos_fixture: dict, capsys: pytest.CaptureFixture) -> None:
    docs = datos_fixture["documentos"]
    base = tmp_path / "ArchivosBase"
    base.mkdir()
    for clave in ("vigente", "benchmark"):
        (base / docs[clave]).write_bytes(datos_fixture["contenido_prueba"][clave].encode("utf-8"))

    salida = tmp_path / "data"
    codigo = f0.main(
        [
            "--archivos-base",
            str(base),
            "--salida-dir",
            str(salida),
            "--sin-historicos",
        ]
    )

    assert codigo == datos_fixture["esperado"]["codigo_salida_ok"]
    assert (salida / "baseline_hashes.json").is_file()
    assert (salida / "baseline_manifest.json").is_file()

    manifiesto = json.loads((salida / "baseline_manifest.json").read_text(encoding="utf-8"))
    assert manifiesto["proyecto"] == "RE"
    assert "D7" in manifiesto["decision"]
    assert manifiesto["verificaciones"]["benchmark_distinto_vigente"] is True
    assert capsys.readouterr().out.strip() != ""


def test_main_falla_si_falta_vigente(f0: ModuleType, tmp_path: Path, datos_fixture: dict) -> None:
    base = tmp_path / "ArchivosBase"
    base.mkdir()
    (base / datos_fixture["documentos"]["benchmark"]).write_bytes(b"benchmark")

    codigo = f0.main(
        ["--archivos-base", str(base), "--salida-dir", str(tmp_path / "data"), "--sin-historicos"]
    )

    assert codigo == datos_fixture["esperado"]["codigo_salida_falta_vigente"]
