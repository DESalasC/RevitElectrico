# -*- coding: utf-8 -*-
"""F0 - Track T: sonda de disponibilidad del canal de ejecucion Revit.

Comprueba, sin bloquear y sin abrir Revit, si existe algun canal para enviar ordenes
al proceso de Revit:

1. Named pipes ``\\\\.\\pipe\\*pyrevit*`` (agent host de pyRevit).
2. Puerto TCP del puente MCP historico (127.0.0.1:19682).

El resultado se escribe en ``data/sonda_canal_v01.json``. Si no hay canal disponible,
se registra y se continua con el runbook de consola: ninguna fase se bloquea por esto.

Uso:
    .venv\\Scripts\\python.exe src\\fase-0-gobierno\\RE_F0_SONDA_CANAL_v01.py
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

PROYECTO_ROOT: Path = Path(__file__).resolve().parents[2]
SALIDA_POR_DEFECTO: Path = PROYECTO_ROOT / "data" / "sonda_canal_v01.json"

RAIZ_PIPES: str = "\\\\.\\pipe\\"
FILTRO_PIPE: str = "pyrevit"
MCP_HOST: str = "127.0.0.1"
MCP_PUERTO: int = 19682
TIMEOUT_S: float = 3.0


def listar_pipes(filtro: str = FILTRO_PIPE, raiz: str = RAIZ_PIPES) -> list[str]:
    """Devuelve los nombres de named pipes que contienen ``filtro``.

    ``raiz`` es parametrizable para poder probar la funcion con un directorio comun.
    Si el sistema no expone la raiz de pipes, devuelve lista vacia en lugar de fallar.
    """
    try:
        nombres = os.listdir(raiz)
    except OSError:
        return []
    aguja = filtro.lower()
    return sorted(n for n in nombres if aguja in n.lower())


def probar_tcp(host: str = MCP_HOST, puerto: int = MCP_PUERTO, timeout: float = TIMEOUT_S) -> dict[str, Any]:
    """Intenta una conexion TCP y devuelve el resultado con latencia en milisegundos."""
    inicio = datetime.now()
    resultado: dict[str, Any] = {
        "host": host,
        "puerto": puerto,
        "responde": False,
        "error": None,
        "latencia_ms": None,
    }
    try:
        with socket.create_connection((host, puerto), timeout=timeout):
            resultado["responde"] = True
    except OSError as exc:
        resultado["error"] = "{tipo}: {msg}".format(tipo=type(exc).__name__, msg=exc)
    finally:
        delta = (datetime.now() - inicio).total_seconds() * 1000.0
        resultado["latencia_ms"] = round(delta, 1)
    return resultado


def evaluar(pipes: list[str], tcp: dict[str, Any]) -> dict[str, Any]:
    """Consolida la disponibilidad del canal y la recomendacion operativa."""
    hay_pipe = len(pipes) > 0
    hay_tcp = bool(tcp.get("responde"))

    if hay_pipe and hay_tcp:
        modo = "pipe+tcp"
        recomendacion = "Adoptar el canal; mantener el runbook como respaldo."
    elif hay_pipe:
        modo = "pipe"
        recomendacion = "Usar el agent host de pyRevit; el puente TCP no responde."
    elif hay_tcp:
        modo = "tcp"
        recomendacion = "Usar el puente TCP; no hay agent host de pyRevit."
    else:
        modo = "ninguno"
        recomendacion = "Continuar con runbook de consola (bloques numerados). No bloquea fases."

    return {
        "disponible": hay_pipe or hay_tcp,
        "modo": modo,
        "recomendacion": recomendacion,
    }


def construir_sonda(
    pipes: list[str],
    tcp: dict[str, Any],
    evaluacion: dict[str, Any],
) -> dict[str, Any]:
    """Arma el JSON de salida de la sonda."""
    return {
        "version": "1.0",
        "proyecto": "RE",
        "fase": "F0 / Track T",
        "generado": datetime.now().isoformat(timespec="seconds"),
        "pipes": {
            "raiz": RAIZ_PIPES,
            "filtro": FILTRO_PIPE,
            "encontrados": pipes,
            "total": len(pipes),
        },
        "tcp_mcp": tcp,
        "evaluacion": evaluacion,
        "nota": (
            "Sonda no bloqueante. Si no hay canal, el trabajo continua con el runbook de "
            "consola; Track T no condiciona ninguna fase."
        ),
    }


def escribir_json(ruta: Path, datos: dict[str, Any]) -> None:
    """Escribe JSON UTF-8 con indentacion, creando el directorio si hace falta."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI. Siempre devuelve 0: la sonda informa, no bloquea."""
    parser = argparse.ArgumentParser(description="F0 - sonda del canal de ejecucion Revit.")
    parser.add_argument("--salida", default=str(SALIDA_POR_DEFECTO))
    parser.add_argument("--timeout", type=float, default=TIMEOUT_S)
    args = parser.parse_args(argv)

    print("=== F0 - SONDA DE CANAL (Track T) ===")
    print("Pipes  : {raiz}*{filtro}*".format(raiz=RAIZ_PIPES, filtro=FILTRO_PIPE))
    print("TCP MCP: {host}:{puerto}".format(host=MCP_HOST, puerto=MCP_PUERTO))

    pipes = listar_pipes()
    tcp = probar_tcp(timeout=args.timeout)
    evaluacion = evaluar(pipes, tcp)

    print("\n--- Resultado ---")
    print("  Pipes pyRevit : {}".format(len(pipes)))
    for nombre in pipes[:10]:
        print("    - {}".format(nombre))
    print("  TCP MCP       : {}".format("responde" if tcp["responde"] else "no responde"))
    print("  Modo          : {}".format(evaluacion["modo"]))
    print("  Recomendacion : {}".format(evaluacion["recomendacion"]))

    salida = Path(args.salida)
    escribir_json(salida, construir_sonda(pipes, tcp, evaluacion))
    print("\nEscrito: {}".format(salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
