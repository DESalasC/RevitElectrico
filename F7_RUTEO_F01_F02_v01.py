#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F7_RUTEO_F01_F02_v01.py - Versión final con C# inline
Rutea conductos F01/F02 usando ModelLines (placeholders).
"""

import json
import socket
import sys
import os
from pathlib import Path

MCP_HOST = "127.0.0.1"
MCP_PORT = 8080
TECHO_Z_MM = 15920
DIAMETROS_SERVICIO = {"TOMAS": 21, "ILUMINACION": 21, "COMUNICACIONES": 21, "FUERZA": 27}

def mcp_send(method: str, params: dict = None, timeout: float = 30.0) -> dict:
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

# C# code as a template function
def crear_codigo_modelline(x1, y1, z1, x2, y2, z2, servicio, diametro, level_id):
    return f"""
var doc = document;

double x1 = {x1}; double y1 = {y1}; double z1 = {z1};
double x2 = {x2}; double y2 = {y2}; double z2 = {z2};
string servicio = "{servicio}";
int diam = {diametro};
int levelIdVal = {level_id};

Level level = doc.GetElement(new ElementId(levelIdVal)) as Level;
if (level == null) {{
    return Newtonsoft.Json.JsonConvert.SerializeObject(new {{ success = false, error = "Nivel no encontrado" }});
}}

XYZ p1 = new XYZ(x1 / 304.8, y1 / 304.8, z1 / 304.8);
XYZ p2 = new XYZ(x2 / 304.8, y2 / 304.8, z2 / 304.8);
Line line = Line.CreateBound(p1, p2);

bool esVertical = Math.Abs(p1.Z - p2.Z) > 0.001;

SketchPlane sketchPlane;
if (esVertical) {{
    XYZ dir = (p2 - p1).Normalize();
    XYZ normal = XYZ.BasisZ.CrossProduct(dir);
    if (normal.GetLength() < 0.001) normal = XYZ.BasisY.CrossProduct(dir);
    Plane plane = Plane.CreateByNormalAndOrigin(normal.Normalize(), p1);
    sketchPlane = SketchPlane.Create(doc, plane);
}} else {{
    // Horizontal: verificar si Z coincide con nivel
    double levelZ = level.Elevation * 304.8;
    if (Math.Abs(p1.Z - levelZ / 304.8) > 0.01) {{
        // Línea en altura distinta (techo): crear plano a esa Z
        XYZ origin = new XYZ(0, 0, p1.Z);
        Plane plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, origin);
        sketchPlane = SketchPlane.Create(doc, plane);
    }} else {{
        sketchPlane = SketchPlane.Create(doc, level.Id);
    }}
}}

ModelLine ml = null;
try {{
    ml = doc.Create.NewModelCurve(line, sketchPlane) as ModelLine;
}} catch (Exception ex) {{
    return Newtonsoft.Json.JsonConvert.SerializeObject(new {{ success = false, error = ex.Message }});
}}

if (ml != null) {{
    var svcParam = ml.LookupParameter("Servicio");
    if (svcParam != null && !svcParam.IsReadOnly) svcParam.Set(servicio);
    var diamParam = ml.LookupParameter("Diametro");
    if (diamParam != null && !diamParam.IsReadOnly) diamParam.Set(diam);
}}

return Newtonsoft.Json.JsonConvert.SerializeObject(new {{
    success = true,
    elementId = ml != null ? (int)ml.Id.Value : 0,
    uniqueId = ml != null ? ml.UniqueId : ""
}});
"""

CODIGO_OBTENER_NIVEL_PISO5 = r"""
var doc = document;
var level = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Levels)
    .WhereElementIsNotElementType()
    .Cast<Level>()
    .FirstOrDefault(l => l.Name == "Piso 5");
if (level != null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new {
        id = (int)level.Id.Value,
        name = level.Name,
        elevation = level.Elevation * 304.8
    });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(null);
"""

def cargar_inventario(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def agrupar_por_servicio(dispositivos: list) -> dict:
    grupos = {"TOMAS": [], "ILUMINACION": [], "COMUNICACIONES": [], "FUERZA": []}
    for d in dispositivos:
        if not d.get("familia_revit"): continue
        nombre = d.get("nombre_dxf", "")
        if ("ELEC-T" in nombre and "TEL" not in nombre) or "ELEC-EXT" in nombre or \
           "ELEC-I" in nombre or "ELEC-CAMPANA" in nombre or "ELEC-F-CONTROL" in nombre or \
           "ELEC-TIMBRE" in nombre or "ELEC-ZUMBADOR" in nombre:
            grupos["TOMAS"].append(d)
        elif "Bala Stil" in nombre or "ELEC-F-VENT" in nombre:
            grupos["ILUMINACION"].append(d)
        elif "ELEC-TEL" in nombre or "ELEC-NET" in nombre:
            grupos["COMUNICACIONES"].append(d)
        else:
            grupos["TOMAS"].append(d)
    return grupos

def calcular_centroide(dispositivos: list) -> tuple:
    if not dispositivos: return (0, 0)
    x_sum = sum(d["x"] * 1000 for d in dispositivos)
    y_sum = sum(d["y"] * 1000 for d in dispositivos)
    return (x_sum / len(dispositivos), y_sum / len(dispositivos))

def main():
    if len(sys.argv) < 5:
        print("Uso: python F7_RUTEO_F01_F02_v01.py --inventario <F01.json> --inventario <F02.json>")
        sys.exit(1)
    
    inventarios = []
    for i, arg in enumerate(sys.argv):
        if arg == "--inventario" and i + 1 < len(sys.argv):
            inventarios.append(Path(sys.argv[i + 1]))
    
    if len(inventarios) != 2:
        print("Se requieren 2 inventarios")
        sys.exit(1)
    
    print("=" * 60)
    print("RUTEO F01/F02 (ModelLines placeholders)")
    print("=" * 60)
    
    datos = {}
    for inv_path in inventarios:
        data = cargar_inventario(inv_path)
        apto = data["metadatos"]["apartamento_tipo"]
        datos[apto] = data
        print(f"Cargado: {apto} - {len(data['dispositivos'])} dispositivos")
    
    print("\nObteniendo nivel Piso 5...")
    resp = mcp_send_code(CODIGO_OBTENER_NIVEL_PISO5)
    if "error" in resp.get("result", {}):
        print(f"Error: {resp['result']['errorMessage']}")
        sys.exit(1)
    raw = resp["result"]["result"]
    if raw:
        inner = json.loads(raw)
        nivel = json.loads(inner) if isinstance(inner, str) else inner
        level_id = nivel["id"]
        print(f"  Nivel: {nivel['name']} (Id={level_id}, Elev={nivel['elevation']:.1f}mm)")
    else:
        print("  Nivel Piso 5 no encontrado")
        sys.exit(1)
    
    paneles = {
        "F 01": {"x": 11591.4, "y": 7505.8, "z": 14420.0},
        "F 02": {"x": 8760.2, "y": 10122.7, "z": 14420.0},
    }
    
    all_lines = []
    
    for apto, data in datos.items():
        print(f"\n{'='*60}")
        print(f"RUTEO {apto}")
        print(f"{'='*60}")
        
        panel = paneles[apto]
        panel_x, panel_y, panel_z = panel["x"], panel["y"], panel["z"]
        
        grupos = agrupar_por_servicio(data["dispositivos"])
        for servicio, dispositivos in grupos.items():
            print(f"  {servicio}: {len(dispositivos)} dispositivos")
        
        # 1. Vertical panel -> techo
        all_lines.append(("VERTICAL_PANEL", apto, {
            "x1": panel_x, "y1": panel_y, "z1": panel_z,
            "x2": panel_x, "y2": panel_y, "z2": TECHO_Z_MM,
            "diametro": 27, "servicio": "PRINCIPAL", "level_id": level_id
        }))
        print(f"  Vertical: ({panel_x:.1f},{panel_y:.1f},{panel_z:.1f}) -> ({panel_x:.1f},{panel_y:.1f},{TECHO_Z_MM})")
        
        # 2. Horizontales
        for servicio, dispositivos in grupos.items():
            if not dispositivos: continue
            cx, cy = calcular_centroide(dispositivos)
            diam = DIAMETROS_SERVICIO.get(servicio, 21)
            all_lines.append((f"HORIZONTAL_{servicio}", apto, {
                "x1": panel_x, "y1": panel_y, "z1": TECHO_Z_MM,
                "x2": cx, "y2": cy, "z2": TECHO_Z_MM,
                "diametro": diam, "servicio": servicio, "level_id": level_id
            }))
            print(f"  Horizontal {servicio}: ({panel_x:.1f},{panel_y:.1f}) -> ({cx:.1f},{cy:.1f}) diam={diam}")
        
        # 3. Bajadas
        for servicio, dispositivos in grupos.items():
            if not dispositivos: continue
            diam = 16
            for d in dispositivos:
                x_mm = d["x"] * 1000
                y_mm = d["y"] * 1000
                z_disp = d["altura_local_m"] * 1000
                all_lines.append((f"DROP_{servicio}_{d['handle']}", apto, {
                    "x1": x_mm, "y1": y_mm, "z1": TECHO_Z_MM,
                    "x2": x_mm, "y2": y_mm, "z2": z_disp,
                    "diametro": diam, "servicio": servicio, "level_id": level_id
                }))
    
    print(f"\n{'='*60}")
    print(f"TOTAL LINES A CREAR: {len(all_lines)}")
    print(f"{'='*60}")
    
    # Crear ModelLines
    creados = 0
    fallos = 0
    for i, (nombre, apto, line_data) in enumerate(all_lines):
        code = crear_codigo_modelline(**line_data)
        resp = mcp_send_code(code)
        if "error" in resp.get("result", {}):
            print(f"  [{i+1}/{len(all_lines)}] {nombre} ({apto}) -> ERROR: {resp['result']['errorMessage'][:80]}")
            fallos += 1
        elif resp["result"].get("success") is False:
            print(f"  [{i+1}/{len(all_lines)}] {nombre} ({apto}) -> FALLO: {resp['result'].get('errorMessage')[:80]}")
            fallos += 1
        else:
            try:
                raw = resp["result"]["result"]
                if isinstance(raw, str):
                    inner = json.loads(raw)
                    result = json.loads(inner) if isinstance(inner, str) else inner
                else:
                    result = raw
                if result.get("success"):
                    creados += 1
                    print(f"  [{i+1}/{len(all_lines)}] {nombre} ({apto}) -> OK id={result['elementId']}")
                else:
                    fallos += 1
                    print(f"  [{i+1}/{len(all_lines)}] {nombre} ({apto}) -> FALLO: {result.get('error')}")
            except Exception as e:
                fallos += 1
                print(f"  [{i+1}/{len(all_lines)}] {nombre} ({apto}) -> PARSE ERROR: {e}")
    
    print(f"\n{'='*60}")
    print(f"RESUMEN RUTEO (ModelLines)")
    print(f"{'='*60}")
    print(f"Total: {len(all_lines)}")
    print(f"Creados: {creados}")
    print(f"Fallos: {fallos}")
    print(f"\n⚠ PRÓXIMO PASO: Convertir ModelLines a conductos reales:")
    print(f"   1. Cargar familias 'Tubo.rfa' y 'Tubo Comunicaciones.rfa' desde V02-f")
    print(f"   2. Usar herramienta 'Convertir a conductos' o recrear con familias correctas")
    print(f"   3. Asignar diámetros en instancias (parámetro Diameter)")

if __name__ == "__main__":
    main()