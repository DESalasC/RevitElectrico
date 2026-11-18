#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F7A_CARGAR_FAMILIAS_CONDUCTO.py
================================
Carga las familias de conductos "Tubo" y "Tubo Comunicaciones" desde V02-f a CENTRAL-V01.
"""

import json
import socket
import sys
import os
from pathlib import Path

MCP_HOST = "127.0.0.1"
MCP_PORT = 8080

def mcp_send(method: str, params: dict = None, timeout: float = 60.0) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    data = json.dumps(payload) + "\n"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((MCP_HOST, MCP_PORT))
        sock.sendall(data.encode("utf-8"))
        response = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk: break
            response += chunk
            try: return json.loads(response.decode("utf-8"))
            except: continue
    finally: sock.close()

def mcp_send_code(code: str, timeout: float = 60.0) -> dict:
    return mcp_send("send_code_to_revit", {"code": code}, timeout)

# Código C# para obtener familias de conductos desde V02-f y cargarlas en documento actual
# NOTA: Esto requiere que V02-f esté abierto o acceder al archivo .rfa
# Alternativa: buscar los archivos .rfa en el proyecto
CODIGO_CARGAR_DESDE_V02F = r"""
var doc = document;
var app = doc.Application;

// Rutas de las familias (ajustar según ubicación real)
string[] familyPaths = new string[] {
    @"D:\Work\PROJECTS\RevitElectrico\Familias\Tubo.rfa",
    @"D:\Work\PROJECTS\RevitElectrico\Familias\Tubo Comunicaciones.rfa"
};

var results = new List<object>();
foreach (var path in familyPaths) {
    if (System.IO.File.Exists(path)) {
        Family fam = null;
        bool loaded = doc.LoadFamily(path, out fam);
        results.Add(new {
            path = path,
            success = loaded,
            family = loaded ? fam.Name : "N/A",
            error = loaded ? "" : "LoadFamily failed"
        });
    } else {
        results.Add(new {
            path = path,
            success = false,
            family = "N/A",
            error = "File not found"
        });
    }
}
return Newtonsoft.Json.JsonConvert.SerializeObject(results);
"""

# Código para extraer familias desde V02-f si está abierto
CODIGO_EXTRAR_FAMILIAS_V02F = r"""
var doc = document;
var app = doc.Application;

// Intentar abrir V02-f y extraer familias
string v02fPath = @"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt";

var results = new List<object>();
try {
    // Abrir documento en background
    ModelPath modelPath = ModelPathUtils.ConvertUserVisiblePathToModelPath(v02fPath);
    OpenOptions openOpts = new OpenOptions();
    openOpts.Audit = true;
    
    Document v02fDoc = app.OpenDocumentFile(modelPath, openOpts);
    
    // Buscar familias "Tubo" y "Tubo Comunicaciones"
    var conduitFamilies = new FilteredElementCollector(v02fDoc)
        .OfClass(typeof(Family))
        .Cast<Family>()
        .Where(f => f.Name == "Tubo" || f.Name == "Tubo Comunicaciones")
        .ToList();
    
    foreach (var fam in conduitFamilies) {
        // Editar familia y guardar como RFA temporal
        string tempPath = System.IO.Path.Combine(System.IO.Path.GetTempPath(), fam.Name + ".rfa");
        fam.EditFamily(doc).SaveAs(tempPath);
        results.Add(new { family = fam.Name, tempPath = tempPath, success = true });
    }
    
    v02fDoc.Close(false);
} catch (Exception ex) {
    results.Add(new { error = ex.Message, success = false });
}

return Newtonsoft.Json.JsonConvert.SerializeObject(results);
"""

def main():
    print("=" * 60)
    print("CARGAR FAMILIAS DE CONDUCTOS DESDE V02-F")
    print("=" * 60)
    
    # Opción 1: Intentar cargar desde archivos RFA locales
    print("\n1. Intentando cargar desde archivos RFA locales...")
    resp = mcp_send_code(CODIGO_CARGAR_DESDE_V02F)
    if "error" in resp.get("result", {}):
        print(f"   Error: {resp['result']['errorMessage']}")
    else:
        raw = resp["result"]["result"]
        if raw:
            inner = json.loads(raw)
            result = json.loads(inner) if isinstance(inner, str) else inner
            for r in result:
                print(f"   {r['path']}: {'OK' if r['success'] else 'FALLO'} - {r.get('family', r.get('error'))}")
    
    # Opción 2: Extraer desde V02-f abierto
    print("\n2. Intentando extraer desde V02-f...")
    resp = mcp_send_code(CODIGO_EXTRAR_FAMILIAS_V02F)
    if "error" in resp.get("result", {}):
        print(f"   Error: {resp['result']['errorMessage']}")
    else:
        raw = resp["result"]["result"]
        if raw:
            inner = json.loads(raw)
            result = json.loads(inner) if isinstance(inner, str) else inner
            for r in result:
                print(f"   {r.get('family', 'N/A')}: {'OK' if r.get('success') else 'FALLO'} - {r.get('tempPath', r.get('error'))}")

if __name__ == "__main__":
    main()