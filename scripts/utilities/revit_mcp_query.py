"""revit_mcp_query.py

Cliente JSON-RPC para el canal MCP del add-in de Revit (TCP 127.0.0.1:8080).
Envia un fragmento de codigo C# al metodo `send_code_to_revit` y devuelve la
respuesta JSON-RPC ya parseada.

El codigo C# corre dentro de Revit con la variable `document` disponible y debe
terminar en `return <string>;`.

Uso:
    python revit_mcp_query.py --file consulta.cs
    python revit_mcp_query.py --file consulta.cs --out data/respuesta.json
    python revit_mcp_query.py --ping
"""
from __future__ import annotations

import argparse
import datetime
import json
import socket
import sys
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8080
MAX_BYTES = 8192


def enviar(code: str, host: str = HOST, port: int = PORT, timeout: float = 90.0) -> dict:
    """Envia el codigo C# y devuelve la respuesta JSON-RPC."""
    if len(code.encode("utf-8")) > MAX_BYTES:
        raise ValueError(
            f"el codigo supera {MAX_BYTES} bytes ({len(code.encode('utf-8'))}); dividir la consulta"
        )
    payload = {
        "jsonrpc": "2.0",
        "method": "send_code_to_revit",
        "params": {"code": code},
        "id": 1,
    }
    data = json.dumps(payload, separators=(",", ":")) + "\n"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        sock.sendall(data.encode("utf-8"))
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                json.loads(buf.decode("utf-8"))
                break
            except Exception:
                continue
    finally:
        sock.close()

    if not buf:
        raise RuntimeError("respuesta vacia del canal MCP")
    return json.loads(buf.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cliente JSON-RPC del canal MCP de Revit")
    ap.add_argument("--file", help="archivo .cs con el codigo a ejecutar")
    ap.add_argument("--code", help="codigo C# en linea")
    ap.add_argument("--out", help="guardar la respuesta cruda en este JSON")
    ap.add_argument("--ping", action="store_true", help="consulta minima de salud")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args(argv)

    if args.ping:
        code = 'return "pong " + document.Title;'
    elif args.file:
        code = Path(args.file).read_text(encoding="utf-8")
    elif args.code:
        code = args.code
    else:
        ap.error("indicar --file, --code o --ping")

    inicio = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        resp = enviar(code, port=args.port, timeout=args.timeout)
    except Exception as exc:  # noqa: BLE001 - se reporta tal cual al usuario
        print(f"[{inicio}] ERROR de transporte: {exc}", file=sys.stderr)
        return 2

    resultado = resp.get("result") if isinstance(resp, dict) else None
    if isinstance(resultado, str):
        try:
            resultado = json.loads(resultado)
        except Exception:
            pass

    salida = {
        "consultado": inicio,
        "bytes_codigo": len(code.encode("utf-8")),
        "resultado": resultado,
        "error_rpc": resp.get("error") if isinstance(resp, dict) else None,
    }
    print(json.dumps(salida, indent=2, ensure_ascii=False))

    if args.out:
        destino = Path(args.out)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nGuardado en: {destino}")
    return 0 if salida["error_rpc"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
