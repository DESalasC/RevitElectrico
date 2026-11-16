# -*- coding: utf-8 -*-
"""F0 - Reconciliacion de la base documental del proyecto RevitElectrico.

Calcula el SHA256 de los documentos RVT declarados (vigente, benchmark e historicos),
verifica su integridad basica y escribe dos artefactos de linea base:

    data/baseline_hashes.json     -> hashes, bytes y fecha de modificacion
    data/baseline_manifest.json   -> manifiesto con la decision D7 y el rol de cada archivo

No abre Revit, no copia, no mueve y no borra nada. Es de solo lectura sobre
``ArchivosBase``.

Uso:
    .venv\\Scripts\\python.exe src\\fase-0-gobierno\\RE_F0_RECONCILIACION_v01.py
    .venv\\Scripts\\python.exe src\\fase-0-gobierno\\RE_F0_RECONCILIACION_v01.py --sin-historicos

Codigos de salida:
    0  todos los documentos obligatorios existen y son legibles
    2  falta el documento vigente o el benchmark (no se puede fijar linea base)
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Raiz del proyecto derivada del propio archivo: src/fase-0-gobierno/<este>.py
PROYECTO_ROOT: Path = Path(__file__).resolve().parents[2]
ARCHIVOS_BASE_POR_DEFECTO: Path = PROYECTO_ROOT / "ArchivosBase"
SALIDA_POR_DEFECTO: Path = PROYECTO_ROOT / "data"

VIGENTE: str = "STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt"
BENCHMARK: str = "E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt"
HISTORICOS: tuple[str, ...] = (
    "E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V03.rvt",
    "E06_BASE_LIMPIO_2026-11-12.rvt",
)

CHUNK_BYTES: int = 1024 * 1024


def sha256_archivo(ruta: Path, chunk: int = CHUNK_BYTES) -> str:
    """Devuelve el SHA256 en hexadecimal de un archivo, leido por bloques."""
    digest = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(chunk), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _fecha_local(ts: float) -> str:
    """Convierte un timestamp POSIX a ISO 8601 local, sin microsegundos."""
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def describir_documento(rol: str, nombre: str, base: Path) -> dict[str, Any]:
    """Describe un documento: rol, existencia, tamano, fecha y hash.

    Si el archivo no existe devuelve una entrada con ``encontrado=False`` y
    ``sha256=None``; no lanza excepcion, para que el informe refleje el estado real.
    """
    ruta = base / nombre
    entrada: dict[str, Any] = {
        "rol": rol,
        "archivo": nombre,
        "ruta_relativa": str(Path("ArchivosBase") / nombre),
        "encontrado": False,
        "bytes": None,
        "mtime_iso": None,
        "sha256": None,
    }
    if not ruta.is_file():
        return entrada

    stat = ruta.stat()
    entrada.update(
        {
            "encontrado": True,
            "bytes": stat.st_size,
            "mtime_iso": _fecha_local(stat.st_mtime),
            "sha256": sha256_archivo(ruta),
        }
    )
    return entrada


def recolectar(
    base: Path,
    vigente: str = VIGENTE,
    benchmark: str = BENCHMARK,
    historicos: tuple[str, ...] = HISTORICOS,
) -> list[dict[str, Any]]:
    """Construye la lista de documentos con su rol: vigente, benchmark, historico."""
    documentos: list[dict[str, Any]] = [
        describir_documento("vigente", vigente, base),
        describir_documento("benchmark", benchmark, base),
    ]
    for nombre in historicos:
        documentos.append(describir_documento("historico", nombre, base))
    return documentos


def verificar(documentos: list[dict[str, Any]]) -> dict[str, Any]:
    """Evalua las condiciones minimas de una linea base confiable."""
    por_rol: dict[str, dict[str, Any]] = {}
    for doc in documentos:
        por_rol.setdefault(doc["rol"], doc)

    vigente = por_rol.get("vigente", {})
    benchmark = por_rol.get("benchmark", {})

    encontrados = [d for d in documentos if d["encontrado"]]
    hashes = [d["sha256"] for d in encontrados]
    duplicados = len(hashes) != len(set(hashes))

    benchmark_distinto = (
        vigente.get("sha256") is not None
        and benchmark.get("sha256") is not None
        and vigente["sha256"] != benchmark["sha256"]
    )

    advertencias: list[str] = []
    for doc in documentos:
        if not doc["encontrado"]:
            advertencias.append(
                "No encontrado: {rol} -> {archivo}".format(rol=doc["rol"], archivo=doc["archivo"])
            )
        elif doc["rol"] != "historico" and (doc["bytes"] or 0) == 0:
            advertencias.append("Archivo vacio: {archivo}".format(archivo=doc["archivo"]))

    if duplicados:
        advertencias.append("Hay documentos con el mismo SHA256 (revisar roles o copias).")
    if not benchmark_distinto and vigente.get("encontrado") and benchmark.get("encontrado"):
        advertencias.append("El benchmark y el vigente tienen el mismo hash: no son comparables.")

    return {
        "todos_obligatorios_presentes": bool(
            vigente.get("encontrado") and benchmark.get("encontrado")
        ),
        "benchmark_distinto_vigente": benchmark_distinto,
        "sin_hashes_duplicados": not duplicados,
        "documentos_encontrados": len(encontrados),
        "documentos_declarados": len(documentos),
        "advertencias": advertencias,
    }


def construir_manifiesto(
    documentos: list[dict[str, Any]],
    verificaciones: dict[str, Any],
    base: Path,
) -> dict[str, Any]:
    """Arma el manifiesto de linea base con la decision D7 y los roles declarados."""
    return {
        "version": "1.0",
        "proyecto": "RE",
        "decision": "D7 (aprobada 2026-11-15)",
        "regla": (
            "CENTRAL-V01 es el documento vigente; V03 y E06_BASE_LIMPIO pasan a historico "
            "con hash registrado. El benchmark manual V02-f es la referencia de contraste."
        ),
        "raiz_proyecto": str(PROYECTO_ROOT),
        "carpeta_documentos": str(base),
        "documentos": [
            {
                "rol": doc["rol"],
                "archivo": doc["archivo"],
                "sha256": doc["sha256"],
                "bytes": doc["bytes"],
            }
            for doc in documentos
        ],
        "verificaciones": verificaciones,
        "generado": datetime.now().isoformat(timespec="seconds"),
    }


def escribir_json(ruta: Path, datos: dict[str, Any]) -> None:
    """Escribe JSON UTF-8 con indentacion, creando el directorio si hace falta."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI. Devuelve 0 si la linea base queda fijada, 2 si falta lo esencial."""
    parser = argparse.ArgumentParser(description="F0 - Reconciliacion de la base documental.")
    parser.add_argument("--archivos-base", default=str(ARCHIVOS_BASE_POR_DEFECTO))
    parser.add_argument("--salida-dir", default=str(SALIDA_POR_DEFECTO))
    parser.add_argument(
        "--sin-historicos",
        action="store_true",
        help="Omite los documentos historicos (solo vigente y benchmark).",
    )
    args = parser.parse_args(argv)

    base = Path(args.archivos_base)
    salida = Path(args.salida_dir)
    historicos: tuple[str, ...] = () if args.sin_historicos else HISTORICOS

    print("=== F0 - RECONCILIACION DE BASE ===")
    print("Raiz proyecto : {}".format(PROYECTO_ROOT))
    print("Documentos    : {}".format(base))
    print("Salida        : {}".format(salida))

    documentos = recolectar(base, VIGENTE, BENCHMARK, historicos)
    verificaciones = verificar(documentos)

    print("\n--- Documentos ---")
    for doc in documentos:
        if doc["encontrado"]:
            print(
                "  [{rol:9}] {archivo}\n             {mb:8.1f} MB  {sha}".format(
                    rol=doc["rol"],
                    archivo=doc["archivo"],
                    mb=(doc["bytes"] or 0) / (1024 * 1024),
                    sha=doc["sha256"],
                )
            )
        else:
            print("  [{rol:9}] {archivo}  -> NO ENCONTRADO".format(rol=doc["rol"], archivo=doc["archivo"]))

    print("\n--- Verificaciones ---")
    for clave, valor in verificaciones.items():
        if clave != "advertencias":
            print("  {clave}: {valor}".format(clave=clave, valor=valor))

    if verificaciones["advertencias"]:
        print("\n--- Advertencias ---")
        for aviso in verificaciones["advertencias"]:
            print("  ! {aviso}".format(aviso=aviso))

    hashes = {
        "version": "1.0",
        "proyecto": "RE",
        "generado": datetime.now().isoformat(timespec="seconds"),
        "documentos": documentos,
        "verificaciones": verificaciones,
    }
    manifiesto = construir_manifiesto(documentos, verificaciones, base)

    ruta_hashes = salida / "baseline_hashes.json"
    ruta_manifiesto = salida / "baseline_manifest.json"
    escribir_json(ruta_hashes, hashes)
    escribir_json(ruta_manifiesto, manifiesto)

    print("\nEscrito: {}".format(ruta_hashes))
    print("Escrito: {}".format(ruta_manifiesto))

    if not verificaciones["todos_obligatorios_presentes"]:
        print("\nRESULTADO: FALLA - falta el vigente o el benchmark.")
        return 2

    print("\nRESULTADO: linea base fijada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
