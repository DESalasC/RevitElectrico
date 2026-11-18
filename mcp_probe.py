#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp_probe.py
============
Diagnostico rapido: hace 3 llamadas MCP al plugin de Revit e imprime la
respuesta CRUDA (sin parsear) de cada una. Sirve para ver la estructura
exacta de success, error de C#, y error de metodo inexistente.

Uso:
    python mcp_probe.py
"""

import json
import socket

MCP_HOST = "127.0.0.1"
MCP_PORT = 8080


def mcp_call(method: str, params: dict = None, timeout: float = 15.0) -> dict:
    """Envia JSON-RPC 2.0 y devuelve la respuesta parseada."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    data = json.dumps(payload, separators=(",", ":")) + "\n"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((MCP_HOST, MCP_PORT))
        sock.sendall(data.encode("utf-8"))
        response = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            response += chunk
            try:
                json.loads(response.decode("utf-8"))
                break
            except json.JSONDecodeError:
                continue
        return json.loads(response.decode("utf-8"))
    finally:
        sock.close()


def print_response(label: str, resp: dict):
    """Imprime la respuesta con formato claro."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"Tipo: {type(resp).__name__}")
    print(f"Claves top-level: {list(resp.keys()) if isinstance(resp, dict) else 'N/A'}")
    print(f"Respuesta completa (pretty):")
    print(json.dumps(resp, indent=2, ensure_ascii=False))
    print()


# ─── Test 1: llamada read simple (deberia funcionar) ─────────────────────────
code_read = 'var doc = document; return doc.Title;'
print("\n>>> Test 1: send_code_to_revit con read simple (doc.Title)")
try:
    resp1 = mcp_call("send_code_to_revit", {"code": code_read}, timeout=15.0)
    print_response("TEST 1 — Read simple (doc.Title)", resp1)
except Exception as e:
    print(f"\n[Test 1] EXCEPCION: {type(e).__name__}: {e}")

# ─── Test 2: llamada write SIN Transaction (deberia fallar) ──────────────────
# Esto reproduce el bug de v04: intenta crear una instancia sin transaction.
# Revit deberia lanzar: "Starting a transaction from outside a transaction..."
code_write_no_tx = r'''
var doc = document;
var symbol = new FilteredElementCollector(doc)
    .OfClass(typeof(FamilySymbol))
    .Cast<FamilySymbol>()
    .FirstOrDefault();
if (symbol == null) return "No FamilySymbol found";
if (!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }
var pt = new XYZ(0, 0, 0);
// SIN Transaction → deberia lanzar exception
var inst = doc.Create.NewFamilyInstance(pt, symbol, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
return "Created: " + inst.Id.Value.ToString();
'''
print("\n>>> Test 2: send_code_to_revit con write SIN Transaction")
try:
    resp2 = mcp_call("send_code_to_revit", {"code": code_write_no_tx}, timeout=15.0)
    print_response("TEST 2 — Write sin Transaction (esperamos error)", resp2)
except Exception as e:
    print(f"\n[Test 2] EXCEPCION: {type(e).__name__}: {e}")

# ─── Test 3: metodo inexistente (deberia dar error JSON-RPC) ─────────────────
print("\n>>> Test 3: metodo inexistente (metodo_que_no_existe)")
try:
    resp3 = mcp_call("metodo_que_no_existe", {}, timeout=10.0)
    print_response("TEST 3 — Metodo inexistente", resp3)
except Exception as e:
    print(f"\n[Test 3] EXCEPCION: {type(e).__name__}: {e}")

# ─── Test 4: write CON Transaction (deberia funcionar) ───────────────────────
code_write_with_tx = r'''
var doc = document;
var symbol = new FilteredElementCollector(doc)
    .OfClass(typeof(FamilySymbol))
    .Cast<FamilySymbol>()
    .FirstOrDefault();
if (symbol == null) return "No FamilySymbol found";
if (!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }
var pt = new XYZ(0, 0, 0);
FamilyInstance inst = null;
using (var t = new Transaction(doc, "Probe test")) {
    t.Start();
    inst = doc.Create.NewFamilyInstance(pt, symbol, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
    t.Commit();
}
return "Created with tx: " + inst.Id.Value.ToString();
'''
print("\n>>> Test 4: send_code_to_revit con write CON Transaction")
try:
    resp4 = mcp_call("send_code_to_revit", {"code": code_write_with_tx}, timeout=20.0)
    print_response("TEST 4 — Write con Transaction (esperamos success)", resp4)
except Exception as e:
    print(f"\n[Test 4] EXCEPCION: {type(e).__name__}: {e}")

print(f"\n{'='*60}")
print(f"  FIN DEL DIAGNOSTICO")
print(f"{'='*60}")
print(f"\nMandame el output completo de los 4 tests.")
print(f"Con eso veo el formato exacto de success y error, y fixeo v04b.")
