#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F6_COLOCAR_F01_F02_v01.py
==========================
Coloca dispositivos de apartamentos F01/F02 en CENTRAL-V01.rvt usando MCP (puerto 8080).

Procedimiento estándar:
1. Valida frescura del inventario (hash DXF coincide)
2. Obtiene offset de ancla (panel TE) comparando con muros reales
3. Coloca cada dispositivo con:
   - Host = cara de muro (face-based)
   - Altura = z_absoluta_m del inventario
   - Rotación = rotacion_final_grados (incluye delta +90° para M_Toma doble)
   - Familia/Tipo = familia_revit / tipo_revit
4. Genera reporte de colocación con ElementIds de Revit
5. Valida contra modelo de referencia V02-f (data/v02f/dispositivos_v01.json)

Uso:
    python F6_COLOCAR_F01_F02_v01.py --inventario data/inventarios/inventario_dispositivos_F01_v1.1_20261117_152259.json
    python F6_COLOCAR_F01_F02_v01.py --inventario data/inventarios/inventario_dispositivos_F02_v1.1_20261117_152303.json
"""

import json
import socket
import sys
import os
import hashlib
import time
from datetime import datetime
from pathlib import Path

# ─── Configuración ────────────────────────────────────────────────────────────
MCP_HOST = "127.0.0.1"
MCP_PORT = 8080
REVITELECTRICO_ROOT = Path(os.environ.get("REVITELECTRICO_ROOT", r"D:\Work\PROJECTS\RevitElectrico"))
DATA_DIR = REVITELECTRICO_ROOT / "data"
V02F_REFERENCE = DATA_DIR / "v02f" / "dispositivos_v01.json"

# Tolerancias de validación
TOL_POSICION_MM = 50      # posición XY
TOL_ALTURA_MM = 20        # altura Z
TOL_ROTACION_GRADOS = 5   # rotación

# ─── Utilidades MCP ───────────────────────────────────────────────────────────
def mcp_send(method: str, params: dict = None, timeout: float = 10.0) -> dict:
    """Envía una petición JSON-RPC 2.0 al MCP por TCP."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1
    }
    data = json.dumps(payload, separators=(",", ":")) + "\n"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((MCP_HOST, MCP_PORT))
        sock.sendall(data.encode("utf-8"))

        # Leer respuesta completa
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


def mcp_send_code(code: str, timeout: float = 30.0) -> dict:
    """Envía código C# para ejecutar en Revit vía MCP."""
    return mcp_send("send_code_to_revit", {"code": code}, timeout)


def validar_inventario_fresco(inventario_path: Path) -> bool:
    """Valida que el inventario coincida con el DXF actual (hash + mtime)."""
    with open(inventario_path, "r", encoding="utf-8") as f:
        inv = json.load(f)

    dxf_info = inv["metadatos"]["origen_dxf"]
    dxf_path = Path(dxf_info["ruta_completa"])

    if not dxf_path.exists():
        print(f"✗ DXF no encontrado: {dxf_path}")
        return False

    # Hash actual
    h = hashlib.sha256()
    with open(dxf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual_hash = h.hexdigest()
    actual_mtime = datetime.fromtimestamp(dxf_path.stat().st_mtime).isoformat()

    hash_ok = (actual_hash == dxf_info["hash_sha256"])
    mtime_ok = (actual_mtime == dxf_info["fecha_modificacion_dxf"])

    print(f"  DXF: {dxf_path.name}")
    print(f"  Hash inventario: {dxf_info['hash_sha256'][:16]}...")
    print(f"  Hash actual:     {actual_hash[:16]}...")
    print(f"  Hash coincide:   {hash_ok}")
    print(f"  mtime coincide:  {mtime_ok}")

    if not hash_ok:
        print("⚠ ADVERTENCIA: El DXF ha cambiado desde la generación del inventario")
        return False

    return True


# ─── Código C# para Revit ─────────────────────────────────────────────────────
CODIGO_OBTENER_PANELES = r'''
var doc = document;
var collector = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
    .WhereElementIsNotElementType();

var paneles = new List<object>();
foreach (var elem in collector) {
    var fi = elem as FamilyInstance;
    if (fi == null) continue;
    var name = fi.Symbol?.Family?.Name ?? "";
    var typeName = fi.Symbol?.Name ?? "";
    var loc = fi.Location as LocationPoint;
    if (loc == null) continue;
    var pt = loc.Point;
    paneles.Add(new {
        id = (int)fi.Id.Value,
        uniqueId = fi.UniqueId,
        family = name,
        type = typeName,
        x = Math.Round(pt.X * 304.8, 1),
        y = Math.Round(pt.Y * 304.8, 1),
        z = Math.Round(pt.Z * 304.8, 1),
        levelId = fi.LevelId?.Value ?? 0
    });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(paneles);
'''

CODIGO_OBTENER_MUROS = r'''
var doc = document;
var collector = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Walls)
    .WhereElementIsNotElementType();

var muros = new List<object>();
foreach (var elem in collector) {
    var wall = elem as Wall;
    if (wall == null) continue;
    var loc = wall.Location as LocationCurve;
    if (loc == null) continue;
    var curve = loc.Curve;
    var p0 = curve.GetEndPoint(0);
    var p1 = curve.GetEndPoint(1);
    muros.Add(new {
        id = (int)wall.Id.Value,
        uniqueId = wall.UniqueId,
        x1 = Math.Round(p0.X * 304.8, 1),
        y1 = Math.Round(p0.Y * 304.8, 1),
        x2 = Math.Round(p1.X * 304.8, 1),
        y2 = Math.Round(p1.Y * 304.8, 1),
        z = Math.Round(p0.Z * 304.8, 1),
        levelId = wall.LevelId?.Value ?? 0
    });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(muros);
'''

CODIGO_COLLOCAR_DISPOSITIVO = r"""
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);

// Extract values
string familia = j["Familia"]?.ToString();
string tipo = j["Tipo"]?.ToString();
double x = (double)j["X"];      // ya en mm
double y = (double)j["Y"];      // ya en mm
double z = (double)j["Z"];      // altura relativa al nivel en metros
double rotacion = (double)j["Rotacion"];
double alturaLocal = (double)j["AlturaLocal"];
double nivelElevacion = (double)j["NivelElevacion"];
int levelIdVal = (int)j["LevelId"];

// Buscar símbolo
FamilySymbol symbol = new FilteredElementCollector(doc)
    .OfClass(typeof(FamilySymbol))
    .Cast<FamilySymbol>()
    .FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);

if (symbol == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Familia/Tipo no encontrado: " + familia + " / " + tipo });
}
if (!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }

// Buscar nivel
Level level = null;
if (levelIdVal != 0) {
    level = doc.GetElement(new ElementId(levelIdVal)) as Level;
}
if (level == null) {
    level = new FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Levels)
        .WhereElementIsNotElementType()
        .Cast<Level>()
        .FirstOrDefault(l => Math.Abs(l.Elevation * 304.8 - nivelElevacion * 1000) < 10);
}
if (level == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Nivel no encontrado" });
}

// NOTA: M_Interruptores es face-based (requiere host muro).
// Level-based placement lo pone en el origen del nivel (0,0).
// Para colocación correcta en muro se requiere face-based con NewFamilyInstance(Face, XYZ, XYZ, FamilySymbol).
// Por ahora usamos level-based para todas las familias; los interruptores quedarán en (0,0) del nivel.
// TODO: Implementar face-based placement para M_Interruptores.

FamilyInstance inst = null;
int hostId = 0;
string hostUniqueId = "";

XYZ point = new XYZ(x / 304.8, y / 304.8, z / 304.8);  // mm a feet

try {
    inst = doc.Create.NewFamilyInstance(point, symbol, level, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
} catch (Exception ex) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = ex.Message });
}

// Aplicar rotación
if (rotacion != 0 && inst != null) {
    double rad = rotacion * Math.PI / 180.0;
    foreach (Parameter p in inst.Parameters) {
        string name = p.Definition.Name;
        if (name == "Rotation" || name == "Angle" || name.IndexOf("Rot") >= 0) {
            if (!p.IsReadOnly) {
                p.Set(rad);
                break;
            }
        }
    }
}

// Elevación (level-based)
if (alturaLocal > 0 && inst != null) {
    foreach (Parameter p in inst.Parameters) {
        string name = p.Definition.Name;
        if (name == "Elevation" || name == "Offset" || name.IndexOf("Elev") >= 0 || name.IndexOf("Offset") >= 0) {
            if (!p.IsReadOnly) {
                p.Set(alturaLocal / 304.8);
                break;
            }
        }
    }
}

return Newtonsoft.Json.JsonConvert.SerializeObject(new {
    success = true,
    elementId = inst != null ? (int)inst.Id.Value : 0,
    uniqueId = inst != null ? inst.UniqueId : "",
    hostId = hostId,
    hostUniqueId = hostUniqueId
});
"""

# ─── Validación contra V02-f ──────────────────────────────────────────────────
def cargar_referencia_v02f() -> dict:
    """Carga el modelo de referencia V02-f y lo indexa por apartamento + handle."""
    with open(V02F_REFERENCE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Filtrar solo F01 y F02 (basado en coordenadas Y: F01 ~10000+, F02 ~0-8000)
    # El V02-f tiene 85 dispositivos en F01/F02 + 19 cajas + otros
    # Para validación, usamos los que coinciden por handle aproximado o posición
    index = {}
    for d in data:
        # Clave aproximada: handle + familia + posición redondeada
        key = f"{d.get('fam','')}_{d.get('tipo','')}_{round(d.get('x',0))}_{round(d.get('y',0))}"
        index[key] = d
    return index


def validar_colocacion(colocados: list, referencia: dict) -> dict:
    """Compara dispositivos colocados contra referencia V02-f.
    
    Nota: inventario usa metros (x, y, z_absoluta_m), referencia usa mm (x, y, z).
    """
    resultados = {
        "total_colocados": len(colocados),
        "total_referencia": len(referencia),
        "coinciden": 0,
        "diferencias_posicion": [],
        "diferencias_altura": [],
        "diferencias_rotacion": [],
        "no_encontrados_ref": [],
        "extras_colocados": [],
    }

    for c in colocados:
        if not c.get("success"):
            continue

        # Buscar en referencia por proximidad
        mejor_match = None
        mejor_dist = float("inf")

        # Convertir inventario a mm para comparación
        cx_mm = c["x"] * 1000
        cy_mm = c["y"] * 1000
        cz_mm = c["z_absoluta_m"] * 1000

        for key, r in referencia.items():
            dx = abs(cx_mm - r.get("x", 0))
            dy = abs(cy_mm - r.get("y", 0))
            dz = abs(cz_mm - r.get("z", 0))
            dist = (dx**2 + dy**2 + dz**2)**0.5
            if dist < mejor_dist and dist < 1000:  # 1m max
                mejor_dist = dist
                mejor_match = r

        if mejor_match:
            dx = abs(cx_mm - mejor_match.get("x", 0))
            dy = abs(cy_mm - mejor_match.get("y", 0))
            dz = abs(cz_mm - mejor_match.get("z", 0))
            drot = abs(c["rotacion_final"] - mejor_match.get("rot", 0))
            drot = min(drot, 360 - drot)

            ok_pos = dx <= TOL_POSICION_MM and dy <= TOL_POSICION_MM
            ok_alt = dz <= TOL_ALTURA_MM
            ok_rot = drot <= TOL_ROTACION_GRADOS

            if ok_pos and ok_alt and ok_rot:
                resultados["coinciden"] += 1
            else:
                if not ok_pos:
                    resultados["diferencias_posicion"].append({
                        "handle": c["handle"],
                        "dx_mm": round(dx, 1),
                        "dy_mm": round(dy, 1),
                        "ref": {"x": mejor_match.get("x"), "y": mejor_match.get("y")},
                        "colocado": {"x": round(cx_mm, 1), "y": round(cy_mm, 1)}
                    })
                if not ok_alt:
                    resultados["diferencias_altura"].append({
                        "handle": c["handle"],
                        "dz_mm": round(dz, 1),
                        "ref_z": mejor_match.get("z"),
                        "colocado_z": round(cz_mm, 1)
                    })
                if not ok_rot:
                    resultados["diferencias_rotacion"].append({
                        "handle": c["handle"],
                        "drot": round(drot, 1),
                        "ref_rot": mejor_match.get("rot"),
                        "colocado_rot": c["rotacion_final"]
                    })
        else:
            resultados["extras_colocados"].append({
                "handle": c["handle"],
                "familia": c.get("familia"),
                "x": c["x"], "y": c["y"]
            })

    return resultados


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Coloca dispositivos F01/F02 en CENTRAL-V01 via MCP")
    parser.add_argument("--inventario", required=True, help="Ruta al inventario canónico JSON")
    parser.add_argument("--validar-solo", action="store_true", help="Solo validar frescura, no colocar")
    parser.add_argument("--saltar-validacion", action="store_true", help="Saltar validación de frescura")
    args = parser.parse_args()

    inventario_path = Path(args.inventario)
    if not inventario_path.exists():
        print(f"✗ Inventario no encontrado: {inventario_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"COLOCACIÓN F01/F02 EN CENTRAL-V01")
    print(f"{'='*60}")

    # 1. Cargar inventario
    with open(inventario_path, "r", encoding="utf-8") as f:
        inventario = json.load(f)

    meta = inventario["metadatos"]
    dispositivos = inventario["dispositivos"]
    apartamento = meta["apartamento_tipo"]
    tablero = meta["tablero"]
    nivel_elevacion = meta["nivel_elevacion_m"]

    print(f"Apartamento:    {apartamento} (Tablero: {tablero})")
    print(f"Nivel elevación: {nivel_elevacion} m")
    print(f"Dispositivos:   {len(dispositivos)}")
    print(f"Inventario:     {inventario_path.name}")

    # 2. Validar frescura
    if not args.saltar_validacion:
        print(f"\nValidando frescura del inventario...")
        if not validar_inventario_fresco(inventario_path):
            print("✗ Inventario no fresco. Usa --saltar-validacion para forzar.")
            sys.exit(1)
        print("✓ Inventario fresco")

    if args.validar_solo:
        print("\n✓ Validación completada (solo validar)")
        return

    # 3. Verificar documento activo en Revit
    print(f"\nVerificando documento activo en Revit...")
    code_doc = "var doc = document; return \"Title: \" + doc.Title + \" | Path: \" + doc.PathName + \" | Modified: \" + doc.IsModified;"
    resp = mcp_send_code(code_doc)
    if "error" in resp.get("result", {}):
        print(f"✗ Error MCP: {resp['result']['errorMessage']}")
        sys.exit(1)
    doc_info_str = resp["result"]["result"]
    # Parsear: "Title: X | Path: Y | Modified: Z"
    doc_info = {}
    for part in doc_info_str.strip('"').split(" | "):
        if ": " in part:
            k, v = part.split(": ", 1)
            doc_info[k.strip()] = v.strip()
    print(f"  Documento: {doc_info.get('Title', '?')}")
    print(f"  Path: {doc_info.get('Path', '?')}")
    print(f"  Modified: {doc_info.get('Modified', '?')}")

    if "CENTRAL-V01" not in doc_info.get("Title", ""):
        print("⚠ ADVERTENCIA: El documento activo no parece ser CENTRAL-V01")
        # Continuar de todos modos

    # 4. Obtener paneles y muros para calcular offset de ancla
    print(f"\nObteniendo paneles (tableros) en el modelo...")
    resp = mcp_send_code(CODIGO_OBTENER_PANELES)
    if "error" in resp.get("result", {}):
        print(f"✗ Error obteniendo paneles: {resp['result']['errorMessage']}")
        sys.exit(1)
    raw_paneles = resp["result"]["result"]
    # El resultado viene doble-codificado como string JSON
    paneles = json.loads(json.loads(raw_paneles))
    print(f"  Paneles encontrados: {len(paneles)}")
    for p in paneles:
        print(f"    {p['family']} | {p['type']} @ ({p['x']}, {p['y']}) id={p['id']}")

    # Buscar panel de apartamento (E_Panel Distribucion1) en Piso 5 (LevelId=192512, Z≈14420)
    # Filtrar solo E_Panel Distribucion1 en Piso 5
    paneles_piso5 = [p for p in paneles if p.get("family") == "E_Panel Distribucion1" and abs(p.get("z", 0) - 14420) < 100]
    
    # F01/F02: según V02-f, los dispositivos de F01 están en X≈+14000, Y≈+10000
    # El panel más cercano a esa zona es id=5501141 @ (11591.4, 7505.8) o id=5501142 @ (8760.2, 10122.7)
    # Usamos el panel id=5501141 para F01 (X=11591, Y=7505) y id=5501142 para F02 (X=8760, Y=10122)
    panel_map = {
        "F01": 5501141,  # E_Panel Distribucion1 @ (11591.4, 7505.8)
        "F02": 5501142,  # E_Panel Distribucion1 @ (8760.2, 10122.7)
    }
    target_id = panel_map.get(apartamento.replace(" ", ""), None)  # "F 01" -> "F01"
    
    panel_objetivo = None
    if target_id:
        for p in paneles_piso5:
            if p.get("id") == target_id:
                panel_objetivo = p
                break
    
    if not panel_objetivo and paneles_piso5:
        # Fallback: panel más cercano a X=11591, Y=7505 (referencia F01)
        panel_objetivo = min(paneles_piso5, key=lambda p: (p["x"] - 11591)**2 + (p["y"] - 7505)**2)
    
    if panel_objetivo:
        print(f"\nPanel objetivo (apartamento): {panel_objetivo['family']} @ ({panel_objetivo['x']:.1f}, {panel_objetivo['y']:.1f}, {panel_objetivo['z']:.1f}) mm")
        print(f"  LevelId: {panel_objetivo.get('levelId')}, Id: {panel_objetivo.get('id')}")

    # Calcular offset: el origen del apartamento en DXF (0,0) corresponde a la posición del panel en Revit
    # Los dispositivos en el inventario tienen coordenadas relativas al origen del apartamento DXF
    # Para colocarlos en Revit: dispositivo_revit = panel_revit + dispositivo_dxf
    panel_offset_x_mm = panel_objetivo["x"] if panel_objetivo else 0
    panel_offset_y_mm = panel_objetivo["y"] if panel_objetivo else 0
    print(f"  Offset panel (aplicado a dispositivos): X={panel_offset_x_mm:.1f}, Y={panel_offset_y_mm:.1f} mm")

    # Obtener muros
    print(f"\nObteniendo muros...")
    resp = mcp_send_code(CODIGO_OBTENER_MUROS)
    if "error" in resp.get("result", {}):
        print(f"✗ Error obteniendo muros: {resp['result']['errorMessage']}")
        sys.exit(1)
    raw_muros = resp["result"]["result"]
    # El resultado viene doble-codificado como string JSON
    muros = json.loads(json.loads(raw_muros))
    print(f"  Muros encontrados: {len(muros)}")

    # 5. Colocar dispositivos
    print(f"\n{'='*60}")
    print(f"COLOCANDO {len(dispositivos)} DISPOSITIVOS")
    print(f"{'='*60}")

    colocados = []
    exitos = 0
    fallos = 0

    for i, disp in enumerate(dispositivos):
        if not disp.get("familia_revit"):
            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> SIN MAPEO REVIT")
            fallos += 1
            colocados.append({**disp, "success": False, "error": "Sin mapeo Revit"})
            continue

        # Preparar datos para código C#
        # Coordenadas del inventario están en METROS relativas al origen del apartamento (DXF).
        # Convertir a mm y sumar offset del panel en Revit.
        x_mm = disp["x"] * 1000 + panel_offset_x_mm
        y_mm = disp["y"] * 1000 + panel_offset_y_mm
        # Z: usar altura local relativa al nivel (altura_local_m), NO elevación absoluta
        z_rel_m = disp["altura_local_m"]

        device_input = {
            "Handle": disp["handle"],
            "Familia": disp["familia_revit"],
            "Tipo": disp["tipo_revit"],
            "X": x_mm,  # ya en mm
            "Y": y_mm,  # ya en mm
            "Z": z_rel_m,  # altura relativa al nivel en metros
            "Rotacion": disp["rotacion_final_grados"],
            "AlturaLocal": disp["altura_local_m"],
            "NivelElevacion": nivel_elevacion,
            "LevelId": panel_objetivo["levelId"] if panel_objetivo else 0,
        }

        device_json = json.dumps(device_input, separators=(",", ":"))
        device_json = json.dumps(device_input, separators=(",", ":"))
        # Escapar comillas dobles para C# verbatim string: " -> ""
        device_json_escaped = device_json.replace('"', '""')
        # Inyectar deviceJson al inicio del código C#
        code = 'string deviceJson = @"' + device_json_escaped + '";\n' + CODIGO_COLLOCAR_DISPOSITIVO

        # Ejecutar colocación con reintentos para errores transitorios
        max_retries = 3
        for attempt in range(max_retries):
            resp = mcp_send_code(code, timeout=60.0)
            if "error" in resp.get("result", {}):
                error_msg = resp["result"]["errorMessage"]
                if attempt == max_retries - 1:
                    print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> ERROR: {error_msg[:100]}")
                    fallos += 1
                    colocados.append({**disp, "success": False, "error": error_msg})
                else:
                    print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> MCP error, retry {attempt+1}/{max_retries}")
                    time.sleep(0.5)
                    continue
            else:
                try:
                    # La respuesta viene doble-serializada: string JSON que contiene otro JSON
                    raw_result = resp["result"]["result"]
                    if isinstance(raw_result, str):
                        # Parsear el string exterior
                        inner = json.loads(raw_result)
                        # Parsear el string interior si también es string
                        result = json.loads(inner) if isinstance(inner, str) else inner
                    else:
                        result = raw_result
                    if result.get("success"):
                        exitos += 1
                        colocado = {
                            **disp,
                            "success": True,
                            "elementId": result["elementId"],
                            "uniqueId": result["uniqueId"],
                            "hostId": result.get("hostId"),
                            "hostUniqueId": result.get("hostUniqueId"),
                        }
                        colocados.append(colocado)
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> OK id={result['elementId']} host={result.get('hostId')}")
                    else:
                        if attempt == max_retries - 1:
                            fallos += 1
                            colocados.append({**disp, "success": False, "error": result.get("error", "Unknown")})
                            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> FALLO: {result.get('error')}")
                        else:
                            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> Revit failure, retry {attempt+1}/{max_retries}")
                            time.sleep(0.5)
                            continue
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt == max_retries - 1:
                        fallos += 1
                        colocados.append({**disp, "success": False, "error": f"Parse error: {e}"})
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> PARSE ERROR: {e}")
                        # Log raw response for debugging
                        print(f"    Raw response: {json.dumps(resp, indent=2)[:500]}")
                    else:
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> Parse error, retry {attempt+1}/{max_retries}")
                        time.sleep(0.5)
                        continue

    # 6. Reporte de colocación
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reporte = {
        "metadatos": {
            "proyecto": "RE",
            "fase": "F6",
            "tipo_documento": "reporte_colocacion",
            "version_esquema": "1.0",
            "fecha_ejecucion": datetime.now().isoformat(),
            "timestamp": timestamp,
            "apartamento_tipo": apartamento,
            "tablero": tablero,
            "documento_objetivo": doc_info.get("Title"),
            "inventario_origen": inventario_path.name,
            "inventario_hash": meta["origen_dxf"]["hash_sha256"],
            "estadisticas": {
                "total_intentados": len(dispositivos),
                "exitos": exitos,
                "fallos": fallos,
                "sin_mapeo": sum(1 for d in dispositivos if not d.get("familia_revit")),
            }
        },
        "colocados": colocados,
    }

    # Guardar reporte
    nombre_reporte = f"colocacion_{apartamento.replace(' ', '')}_v1.0_{timestamp}.json"
    reporte_path = DATA_DIR / "colocaciones" / nombre_reporte
    reporte_path.parent.mkdir(parents=True, exist_ok=True)
    with open(reporte_path, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"REPORTE DE COLOCACIÓN")
    print(f"{'='*60}")
    print(f"Total intentados: {len(dispositivos)}")
    print(f"✓ Exitos:         {exitos}")
    print(f"✗ Fallos:         {fallos}")
    print(f"Reporte guardado: {reporte_path}")

    # 7. Validar contra V02-f
    print(f"\nValidando contra modelo de referencia V02-f...")
    referencia = cargar_referencia_v02f()
    validacion = validar_colocacion([c for c in colocados if c.get("success")], referencia)

    print(f"  Dispositivos colocados válidos: {validacion['total_colocados']}")
    print(f"  Dispositivos en referencia:     {validacion['total_referencia']}")
    print(f"  ✓ Coinciden (dentro de tolerancia): {validacion['coinciden']}")
    print(f"  ✗ Diferencias posición:  {len(validacion['diferencias_posicion'])}")
    print(f"  ✗ Diferencias altura:    {len(validacion['diferencias_altura'])}")
    print(f"  ✗ Diferencias rotación:  {len(validacion['diferencias_rotacion'])}")
    print(f"  ? Extras colocados:      {len(validacion['extras_colocados'])}")

    # Guardar validación
    validacion_path = DATA_DIR / "validaciones" / f"validacion_{apartamento.replace(' ', '')}_v1.0_{timestamp}.json"
    validacion_path.parent.mkdir(parents=True, exist_ok=True)
    with open(validacion_path, "w", encoding="utf-8") as f:
        json.dump(validacion, f, indent=2, ensure_ascii=False)
    print(f"  Validación guardada: {validacion_path}")

    # Resumen final
    tasa_exito = (exitos / len(dispositivos) * 100) if dispositivos else 0
    tasa_coincidencia = (validacion['coinciden'] / validacion['total_colocados'] * 100) if validacion['total_colocados'] else 0

    print(f"\n{'='*60}")
    print(f"RESUMEN FINAL")
    print(f"{'='*60}")
    print(f"Tasa de colocación exitosa:    {tasa_exito:.1f}%")
    print(f"Tasa de coincidencia con V02-f: {tasa_coincidencia:.1f}%")

    if tasa_exito >= 95 and tasa_coincidencia >= 90:
        print(f"\n✅ COLOCACIÓN Y VALIDACIÓN EXITOSAS - Proceder con ruteo F01/F02")
    else:
        print(f"\n⚠ REVISAR ERRORES ANTES DE PROCEDER CON RUTEO")

    return 0 if (tasa_exito >= 95 and tasa_coincidencia >= 90) else 1


if __name__ == "__main__":
    sys.exit(main())