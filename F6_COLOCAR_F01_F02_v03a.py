#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F6_COLOCAR_F01_F02_v03.py
==========================
Coloca dispositivos de apartamentos F01/F02 en CENTRAL-V01.rvt usando MCP (puerto 8080).

Arquitectura: driver Python 3 externo que envía código C# a Revit vía MCP
(send_code_to_revit). No corre dentro de Revit — es orquestable por OpenClaw
como subproceso CLI.

FIXES v03 (2026-11-18) — sobre v02:

  1. FIX P6 (direction vector): en placement face-based de muros, usar
     direction = XYZ.BasisZ en NewFamilyInstance(face_ref, point, direction, sym).
     La rotación se aplica DESPUÉS con Location.Rotate(axis, rad) donde axis
     es una línea vertical por el punto de inserción.
     v02 usaba XYZ(cos(rot), sin(rot), 0) que puede dejar families acostadas.

  2. FIX P3 (tomas sin host): mover M_Toma doble y M_Comunicaciones a
     FAMILIAS_FACE_BASED. v02 las mandaba a level-based, reproduciendo el
     bug P3 documentado el 2026-11-14 ("todas las tomas SIN HOST").

  3. FIX TECHO (ceiling search real): cuando HostTipo=="Techo", buscar en
     OST_Ceilings (no OST_Walls) y usar placement element-hosted con
     NewFamilyInstance(point, symbol, ceiling, StructuralType.NonStructural).
     v02 usaba el código de muros para techos → siempre caía a level fallback.

HEREDADO DE v02 (sin cambios):
  - Z en mm (altura_local_mm), no en metros
  - Offset calculado desde panel en DXF local vs panel en Revit (dinámico)
  - Validación de frescura SHA256 del DXF
  - Retry logic: 3 reintentos con 0.5s delay
  - Validación contra modelo V02-f con tolerancias
  - CLI con argparse, exit codes, JSON reports
  - Multi-apartamento: mismo script para F01 y F02

Uso:
    python F6_COLOCAR_F01_F02_v03.py --inventario data/inventarios/inventario_dispositivos_F01_v1.1_20261117_190929.json
    python F6_COLOCAR_F01_F02_v03.py --inventario data/inventarios/inventario_dispositivos_F02_v1.1_20261117_190933.json

    # Solo validar frescura del inventario, no colocar:
    python F6_COLOCAR_F01_F02_v03.py --inventario ... --validar-solo

    # Saltar validación de frescura (no recomendado en producción):
    python F6_COLOCAR_F01_F02_v03.py --inventario ... --saltar-validacion
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
ARCHIVOS_BASE_DIR = REVITELECTRICO_ROOT / "ArchivosBase"
V02F_REFERENCE = DATA_DIR / "v02f" / "dispositivos_v01.json"

# Tolerancias de validación
TOL_POSICION_MM = 50
TOL_ALTURA_MM = 20
TOL_ROTACION_GRADOS = 5

# ─── Clasificación de familias (FIX v03 #2) ──────────────────────────────────
# Face-based: families WorkPlaneBased que necesitan host en muro.
# v03 agrega M_Toma doble y M_Comunicaciones (venían de v02 en level-based).
FAMILIAS_FACE_BASED = {
    "M_Interruptores",
    "M_Pulsador - Interruptor",
    "M_Timbre",
    "M_Toma doble",        # FIX v03 #2: evitar bug P3 (tomas sin host)
    "M_Comunicaciones",    # FIX v03 #2: mismo motivo
}

# Techo-based: families hosted en cielorraso.
# v03 agrega Consolidation_Point (faltaba en v02).
FAMILIAS_TECHO_BASED = {
    "M_Iluminacion",
    "M_ClimatizacionV",
    "Consolidation_Point",
}

# ─── Utilidades MCP ───────────────────────────────────────────────────────────
def mcp_send(method: str, params: dict = None, timeout: float = 10.0) -> dict:
    """Envía un mensaje JSON-RPC 2.0 al plugin MCP de Revit en puerto 8080."""
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


def mcp_send_code(code: str, timeout: float = 30.0) -> dict:
    """Envía código C# a Revit vía el comando send_code_to_revit del MCP."""
    return mcp_send("send_code_to_revit", {"code": code}, timeout)


def validar_inventario_fresco(inventario_path: Path) -> bool:
    """Verifica que el DXF fuente no haya cambiado desde la generación del inventario."""
    with open(inventario_path, "r", encoding="utf-8") as f:
        inv = json.load(f)
    dxf_info = inv["metadatos"]["origen_dxf"]
    dxf_path = Path(dxf_info["ruta_completa"])
    if not dxf_path.exists():
        print(f"✗ DXF no encontrado: {dxf_path}")
        return False
    h = hashlib.sha256()
    with open(dxf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual_hash = h.hexdigest()
    actual_mtime = datetime.fromtimestamp(dxf_path.stat().st_mtime).isoformat()
    hash_ok = (actual_hash == dxf_info["hash_sha256"])
    mtime_ok = (actual_mtime == dxf_info["fecha_modificacion_dxf"])
    print(f"  DXF: {dxf_path.name}")
    print(f"  Hash coincide: {hash_ok} | mtime coincide: {mtime_ok}")
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
    string panelName = "";
    var param = fi.LookupParameter("Panel Name");
    if (param != null && param.HasValue) {
        panelName = param.AsString() ?? "";
    }
    paneles.Add(new {
        id = (int)fi.Id.Value,
        uniqueId = fi.UniqueId,
        family = name,
        type = typeName,
        panelName = panelName,
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

# ─── Placement unificado v03 (FIX #1 + FIX #3) ───────────────────────────────
# Maneja tres estrategias en un solo bloque C#:
#   - HostTipo="Muro"  → face-based con wall face_ref + XYZ.BasisZ + rotación post-placement
#   - HostTipo="Techo" → element-hosted por cielorraso (OST_Ceilings)
#   - fallback         → level-based (sin host)
CODIGO_COLLOCAR_V03 = r'''
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);

string familia = j["Familia"]?.ToString();
string tipo = j["Tipo"]?.ToString();
double x = (double)j["X"];            // mm
double y = (double)j["Y"];            // mm
double z = (double)j["Z"];            // mm (altura relativa al nivel)
double rotacion = (double)j["Rotacion"];
double alturaLocalMM = (double)j["AlturaLocalMM"];
int levelIdVal = (int)j["LevelId"];
string hostTipo = j["HostTipo"]?.ToString() ?? "Muro";  // "Muro", "Techo", "Nivel"

// ─── Buscar FamilySymbol ───
FamilySymbol symbol = new FilteredElementCollector(doc)
    .OfClass(typeof(FamilySymbol))
    .Cast<FamilySymbol>()
    .FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);

if (symbol == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Familia/Tipo no encontrado: " + familia + " / " + tipo });
}
if (!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }

// ─── Buscar Level ───
Level level = doc.GetElement(new ElementId(levelIdVal)) as Level;
if (level == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Nivel no encontrado: LevelId=" + levelIdVal });
}

XYZ point = new XYZ(x / 304.8, y / 304.8, z / 304.8);  // mm a feet

FamilyInstance inst = null;
int hostId = 0;
string hostUniqueId = "";
bool usedFaceBased = false;
string placementMethod = "";

// ═══════════════════════════════════════════════════════════════════════════
// ESTRATEGIA 1: TECHO (HostTipo == "Techo")  — FIX v03 #3
// Buscar cielorraso que contenga el punto XY y usar element-hosted placement.
// ═══════════════════════════════════════════════════════════════════════════
if (inst == null && hostTipo == "Techo") {
    var ceilingCollector = new FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Ceilings)
        .WhereElementIsNotElementType();

    Element closestCeiling = null;
    double minCeilingDist = double.MaxValue;
    var geomOpts = new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine };

    foreach (var elem in ceilingCollector) {
        try {
            // Filtro rápido por bounding box
            var bbox = elem.get_BoundingBox(null);
            if (bbox == null) continue;
            double tol = 2.0;  // 2 pies ~ 600mm de tolerancia
            if (point.X < bbox.Min.X - tol || point.X > bbox.Max.X + tol) continue;
            if (point.Y < bbox.Min.Y - tol || point.Y > bbox.Max.Y + tol) continue;

            // Proyectar el punto sobre las caras del cielorraso
            var geomElem = elem.get_Geometry(geomOpts);
            if (geomElem == null) continue;
            foreach (var geomObj in geomElem) {
                if (!(geomObj is Solid solid)) continue;
                if (solid.Faces.Size == 0) continue;
                foreach (Face face in solid.Faces) {
                    var proj = face.Project(point);
                    if (proj != null && proj.XYZPoint != null) {
                        double dist = point.DistanceTo(proj.XYZPoint);
                        if (dist < minCeilingDist && dist < 3.0) {  // 3 pies ~ 900mm
                            minCeilingDist = dist;
                            closestCeiling = elem;
                        }
                        break;
                    }
                }
            }
        } catch { continue; }
    }

    if (closestCeiling != null) {
        try {
            // Element-hosted: la familia se hospeda en el cielorraso
            inst = doc.Create.NewFamilyInstance(point, symbol, closestCeiling, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
            hostId = (int)closestCeiling.Id.Value;
            hostUniqueId = closestCeiling.UniqueId;
            usedFaceBased = true;
            placementMethod = "ceiling_hosted";
        } catch (Exception exCeil) {
            // Anotar el error pero continuar a fallback
            placementMethod = "ceiling_failed:" + exCeil.Message;
        }
    } else {
        placementMethod = "ceiling_not_found";
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// ESTRATEGIA 2: MURO face-based (HostTipo == "Muro")  — FIX v03 #1 (P6)
// direction = XYZ.BasisZ + rotación post-placement con Location.Rotate.
// ═══════════════════════════════════════════════════════════════════════════
if (inst == null && hostTipo == "Muro") {
    // Buscar muro más cercano al punto XY en el nivel
    var wallCollector = new FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Walls)
        .WhereElementIsNotElementType()
        .Cast<Wall>()
        .Where(w => w.LevelId.Value == levelIdVal);

    double minDist = double.MaxValue;
    Wall closestWall = null;
    foreach (var wall in wallCollector) {
        var loc = wall.Location as LocationCurve;
        if (loc == null) continue;
        var curve = loc.Curve;
        var proj = curve.Project(point);
        if (proj != null) {
            double dist = point.DistanceTo(proj.XYZPoint);
            if (dist < minDist && dist < 2.0) {  // 2 pies ~ 600mm
                minDist = dist;
                closestWall = wall;
            }
        }
    }

    Reference hostFaceRef = null;
    if (closestWall != null) {
        // Iterar caras del muro, buscar la que enfrenta al punto
        var geomElem = closestWall.get_Geometry(new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine, IncludeNonVisibleObjects = true });
        foreach (var geomObj in geomElem) {
            if (!(geomObj is Solid solid)) continue;
            foreach (Face face in solid.Faces) {
                var faceRef = face.Reference;
                if (faceRef == null) continue;
                var proj = face.Project(point);
                if (proj != null && proj.XYZPoint != null) {
                    double faceDist = point.DistanceTo(proj.XYZPoint);
                    if (faceDist < 0.5) {  // 0.5 pies ~ 150mm
                        hostFaceRef = faceRef;
                        break;
                    }
                }
            }
            if (hostFaceRef != null) break;
        }

        if (hostFaceRef != null) {
            try {
                // FIX P6: direction = XYZ.BasisZ (vertical), NO usar la normal de la cara
                // ni un vector horizontal derivado de la rotación.
                XYZ direction = XYZ.BasisZ;
                inst = doc.Create.NewFamilyInstance(hostFaceRef, point, direction, symbol);
                hostId = (int)closestWall.Id.Value;
                hostUniqueId = closestWall.UniqueId;
                usedFaceBased = true;
                placementMethod = "wall_face_based";

                // Aplicar rotación post-placement con Location.Rotate sobre eje vertical
                if (rotacion != 0) {
                    double rad = rotacion * Math.PI / 180.0;
                    var locPt = inst.Location as LocationPoint;
                    if (locPt != null) {
                        var pt = locPt.Point;
                        var axis = Line.CreateBound(pt, new XYZ(pt.X, pt.Y, pt.Z + 1.0));
                        locPt.Rotate(axis, rad);
                    }
                }
            } catch (Exception exWall) {
                placementMethod = "wall_face_failed:" + exWall.Message;
            }
        } else {
            placementMethod = "wall_face_not_found";
        }
    } else {
        placementMethod = "wall_not_found";
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// ESTRATEGIA 3: FALLBACK level-based (sin host)
// Se activa si las estrategias 1 y 2 fallaron o si HostTipo == "Nivel".
// ═══════════════════════════════════════════════════════════════════════════
if (inst == null) {
    try {
        inst = doc.Create.NewFamilyInstance(point, symbol, level, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
        if (placementMethod == "") placementMethod = "level_default";
        else placementMethod = "level_fallback_from:" + placementMethod;
    } catch (Exception exLvl) {
        return Newtonsoft.Json.JsonConvert.SerializeObject(new {
            success = false,
            error = "Level-based fallback failed: " + exLvl.Message,
            placementMethod = placementMethod
        });
    }
}

if (inst == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new {
        success = false,
        error = "No se pudo crear instancia por ninguna estrategia",
        placementMethod = placementMethod
    });
}

// Para level-based: aplicar rotación y elevación via parámetros
if (!usedFaceBased) {
    if (rotacion != 0) {
        double rad = rotacion * Math.PI / 180.0;
        foreach (Parameter p in inst.Parameters) {
            string name = p.Definition.Name;
            if (name == "Rotation" || name == "Angle" || name.IndexOf("Rot") >= 0) {
                if (!p.IsReadOnly) { p.Set(rad); break; }
            }
        }
    }
    if (alturaLocalMM > 0) {
        foreach (Parameter p in inst.Parameters) {
            string name = p.Definition.Name;
            if (name == "Elevation" || name == "Offset" || name.IndexOf("Elev") >= 0 || name.IndexOf("Offset") >= 0) {
                if (!p.IsReadOnly) { p.Set(alturaLocalMM / 304.8); break; }
            }
        }
    }
}

return Newtonsoft.Json.JsonConvert.SerializeObject(new {
    success = true,
    elementId = (int)inst.Id.Value,
    uniqueId = inst.UniqueId,
    hostId = hostId,
    hostUniqueId = hostUniqueId,
    usedFaceBased = usedFaceBased,
    placementMethod = placementMethod
});
'''

# ─── Validación contra V02-f ──────────────────────────────────────────────────
def cargar_referencia_v02f() -> dict:
    """Carga el modelo de referencia V02-f para validación."""
    with open(V02F_REFERENCE, "r", encoding="utf-8") as f:
        data = json.load(f)
    index = {}
    for d in data:
        key = f"{d.get('fam','')}_{d.get('tipo','')}_{round(d.get('x',0))}_{round(d.get('y',0))}"
        index[key] = d
    return index


def validar_colocacion(colocados: list, referencia: dict) -> dict:
    """Compara dispositivos colocados contra referencia V02-f con tolerancias."""
    resultados = {
        "total_colocados": len(colocados),
        "total_referencia": len(referencia),
        "coinciden": 0,
        "diferencias_posicion": [],
        "diferencias_altura": [],
        "diferencias_rotacion": [],
        "no_encontrados_ref": [],
        "extras_colocados": [],
        "sin_host": [],
    }
    for c in colocados:
        if not c.get("success"):
            continue
        cx_mm = c["x"] * 1000
        cy_mm = c["y"] * 1000
        cz_mm = c["z_absoluta_m"] * 1000 if "z_absoluta_m" in c else c.get("z", 0) * 1000

        # FIX v03: reportar dispositivos sin host (para detectar bug P3)
        if c.get("hostId") == 0 or not c.get("hostUniqueId"):
            resultados["sin_host"].append({
                "handle": c.get("handle"),
                "familia": c.get("familia") or c.get("familia_revit"),
                "placementMethod": c.get("placementMethod", ""),
            })

        mejor_match = None
        mejor_dist = float("inf")
        for key, r in referencia.items():
            dx = abs(cx_mm - r.get("x", 0))
            dy = abs(cy_mm - r.get("y", 0))
            dz = abs(cz_mm - r.get("z", 0))
            dist = (dx**2 + dy**2 + dz**2)**0.5
            if dist < mejor_dist and dist < 1000:
                mejor_dist = dist
                mejor_match = r
        if mejor_match:
            dx = abs(cx_mm - mejor_match.get("x", 0))
            dy = abs(cy_mm - mejor_match.get("y", 0))
            dz = abs(cz_mm - mejor_match.get("z", 0))
            drot = abs(c["rotacion_final"] - mejor_match.get("rot", 0)) if "rotacion_final" in c else 0
            drot = min(drot, 360 - drot)
            ok_pos = dx <= TOL_POSICION_MM and dy <= TOL_POSICION_MM
            ok_alt = dz <= TOL_ALTURA_MM
            ok_rot = drot <= TOL_ROTACION_GRADOS
            if ok_pos and ok_alt and ok_rot:
                resultados["coinciden"] += 1
            else:
                if not ok_pos:
                    resultados["diferencias_posicion"].append({
                        "handle": c.get("handle"), "dx_mm": round(dx, 1), "dy_mm": round(dy, 1)
                    })
                if not ok_alt:
                    resultados["diferencias_altura"].append({
                        "handle": c.get("handle"), "dz_mm": round(dz, 1)
                    })
                if not ok_rot:
                    resultados["diferencias_rotacion"].append({
                        "handle": c.get("handle"), "drot": round(drot, 1)
                    })
        else:
            resultados["extras_colocados"].append({
                "handle": c.get("handle"), "familia": c.get("familia")
            })
    return resultados


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Coloca dispositivos F01/F02 en CENTRAL-V01 via MCP (v03 con fixes P3, P6, Techo)"
    )
    parser.add_argument("--inventario", required=True, help="Ruta al inventario canónico JSON")
    parser.add_argument("--validar-solo", action="store_true", help="Solo validar frescura, no colocar")
    parser.add_argument("--saltar-validacion", action="store_true", help="Saltar validación de frescura")
    args = parser.parse_args()

    inventario_path = Path(args.inventario)
    if not inventario_path.exists():
        print(f"✗ Inventario no encontrado: {inventario_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"COLOCACIÓN F01/F02 EN CENTRAL-V01 (v03)")
    print(f"{'='*60}")
    print(f"Fixes aplicados: P6 (direction=BasisZ), P3 (tomas face-based), Techo (ceiling search)")

    with open(inventario_path, "r", encoding="utf-8") as f:
        inventario = json.load(f)

    meta = inventario["metadatos"]
    dispositivos = inventario["dispositivos"]
    apartamento = meta["apartamento_tipo"]  # "F 01" o "F 02"
    tablero = meta["tablero"]               # "T01" o "T02"
    nivel_elevacion = meta["nivel_elevacion_m"]

    print(f"Apartamento:    {apartamento} (Tablero: {tablero})")
    print(f"Nivel elevación: {nivel_elevacion} m")
    print(f"Dispositivos:   {len(dispositivos)}")
    print(f"Inventario:     {inventario_path.name}")

    if not args.saltar_validacion:
        print(f"\nValidando frescura del inventario...")
        if not validar_inventario_fresco(inventario_path):
            print("✗ Inventario no fresco. Usa --saltar-validacion para forzar.")
            sys.exit(1)
        print("✓ Inventario fresco")

    if args.validar_solo:
        print("\n✓ Validación completada (solo validar)")
        return

    # ─── Verificar documento activo ───
    print(f"\nVerificando documento activo en Revit...")
    code_doc = 'var doc = document; return "Title: " + doc.Title + " | Path: " + doc.PathName + " | Modified: " + doc.IsModified;'
    resp = mcp_send_code(code_doc)
    if "error" in resp.get("result", {}):
        print(f"✗ Error MCP: {resp['result']['errorMessage']}")
        sys.exit(1)
    doc_info_str = resp["result"]["result"]
    doc_info = {}
    for part in doc_info_str.strip('"').split(" | "):
        if ": " in part:
            k, v = part.split(": ", 1)
            doc_info[k.strip()] = v.strip()
    print(f"  Documento: {doc_info.get('Title', '?')}")
    print(f"  Modified: {doc_info.get('Modified', '?')}")

    # ─── Obtener paneles y muros ───
    print(f"\nObteniendo paneles (tableros) en el modelo...")
    resp = mcp_send_code(CODIGO_OBTENER_PANELES)
    if "error" in resp.get("result", {}):
        print(f"✗ Error obteniendo paneles: {resp['result']['errorMessage']}")
        sys.exit(1)
    raw_paneles = resp["result"]["result"]
    paneles = json.loads(json.loads(raw_paneles))
    print(f"  Paneles encontrados: {len(paneles)}")

    # Buscar panel por PanelName = "TF 01" o "TF 02"
    panel_name_map = {"F 01": "TF 01", "F 02": "TF 02"}
    target_panel_name = panel_name_map.get(apartamento)
    panel_objetivo = None
    for p in paneles:
        if p.get("panelName") == target_panel_name:
            panel_objetivo = p
            break
    if not panel_objetivo:
        print(f"✗ No se encontró panel con PanelName='{target_panel_name}' en CENTRAL-V01")
        sys.exit(1)
    print(f"  Panel objetivo: {panel_objetivo['family']} | PanelName={panel_objetivo['panelName']} @ ({panel_objetivo['x']:.1f}, {panel_objetivo['y']:.1f}, {panel_objetivo['z']:.1f}) mm")
    print(f"  LevelId: {panel_objetivo.get('levelId')}, Id: {panel_objetivo.get('id')}")

    # ─── Leer panel en DXF local ───
    dxf_filename = meta["origen_dxf"]["archivo"]
    dxf_path = ARCHIVOS_BASE_DIR / dxf_filename
    import ezdxf
    doc_dxf = ezdxf.readfile(str(dxf_path))
    msp = doc_dxf.modelspace()
    panel_dxf_local = None
    for entity in msp:
        if entity.dxftype() == 'INSERT' and entity.dxf.name in ('TB-Panel', 'TB-Parcial'):
            for attrib in entity.attribs:
                if attrib.dxf.tag.upper() == 'TABLERO' and attrib.dxf.text.strip() == target_panel_name:
                    panel_dxf_local = (float(entity.dxf.insert.x), float(entity.dxf.insert.y))
                    print(f"  Panel en DXF local: {entity.dxf.name} @ ({panel_dxf_local[0]:.4f}, {panel_dxf_local[1]:.4f}) m")
                    break
    if not panel_dxf_local:
        print(f"✗ No se encontró panel {target_panel_name} en DXF")
        sys.exit(1)

    # ─── Calcular offset ───
    panel_dxf_mm = (panel_dxf_local[0] * 1000, panel_dxf_local[1] * 1000)
    panel_revit_mm = (panel_objetivo["x"], panel_objetivo["y"])
    offset_x = panel_revit_mm[0] - panel_dxf_mm[0]
    offset_y = panel_revit_mm[1] - panel_dxf_mm[1]
    print(f"  Offset calculado: X={offset_x:.1f}, Y={offset_y:.1f} mm")

    # ─── Obtener muros (para info, no para placement directo) ───
    print(f"\nObteniendo muros...")
    resp = mcp_send_code(CODIGO_OBTENER_MUROS)
    if "error" in resp.get("result", {}):
        print(f"✗ Error obteniendo muros: {resp['result']['errorMessage']}")
        sys.exit(1)
    raw_muros = resp["result"]["result"]
    muros = json.loads(json.loads(raw_muros))
    print(f"  Muros encontrados: {len(muros)}")

    # ─── Colocar dispositivos ───
    print(f"\n{'='*60}")
    print(f"COLOCANDO {len(dispositivos)} DISPOSITIVOS (v03)")
    print(f"{'='*60}")

    colocados = []
    exitos = 0
    fallos = 0
    # Estadísticas por método de placement (novedad v03)
    stats_method = {"wall_face_based": 0, "ceiling_hosted": 0, "level_fallback_from:wall_not_found": 0,
                    "level_default": 0, "other": 0}
    stats_sin_host = 0

    for i, disp in enumerate(dispositivos):
        if not disp.get("familia_revit"):
            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> SIN MAPEO REVIT")
            fallos += 1
            colocados.append({**disp, "success": False, "error": "Sin mapeo Revit"})
            continue

        # Coordenadas: inventario en metros (DXF local) -> mm + offset
        x_mm = disp["x"] * 1000 + offset_x
        y_mm = disp["y"] * 1000 + offset_y
        z_mm = disp["altura_local_m"] * 1000  # Z en mm relativos al nivel

        familia = disp["familia_revit"]
        tipo = disp["tipo_revit"]
        rotacion = disp["rotacion_final_grados"]
        level_id = panel_objetivo["levelId"]

        # Determinar HostTipo según familia (FIX v03 #2)
        if familia in FAMILIAS_FACE_BASED:
            host_tipo = "Muro"
        elif familia in FAMILIAS_TECHO_BASED:
            host_tipo = "Techo"
        else:
            host_tipo = "Nivel"

        device_input = {
            "Familia": familia,
            "Tipo": tipo,
            "X": x_mm,
            "Y": y_mm,
            "Z": z_mm,
            "Rotacion": rotacion,
            "AlturaLocalMM": z_mm,
            "LevelId": level_id,
            "HostTipo": host_tipo,
        }

        device_json = json.dumps(device_input, separators=(",", ":"))
        device_json_escaped = device_json.replace('"', '""')
        code = 'string deviceJson = @"' + device_json_escaped + '";\n' + CODIGO_COLLOCAR_V03

        # Ejecutar con reintentos
        max_retries = 3
        placed_ok = False
        for attempt in range(max_retries):
            resp = mcp_send_code(code, timeout=60.0)
            if "error" in resp.get("result", {}):
                error_msg = resp["result"]["errorMessage"]
                if attempt == max_retries - 1:
                    print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> ERROR: {error_msg[:100]}")
                    fallos += 1
                    colocados.append({**disp, "success": False, "error": error_msg, "host_tipo": host_tipo})
                else:
                    print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> MCP error, retry {attempt+1}/{max_retries}")
                    time.sleep(0.5)
                continue
            else:
                try:
                    raw_result = resp["result"]["result"]
                    if isinstance(raw_result, str):
                        inner = json.loads(raw_result)
                        result = json.loads(inner) if isinstance(inner, str) else inner
                    else:
                        result = raw_result
                    if result.get("success"):
                        exitos += 1
                        method = result.get("placementMethod", "")
                        # Actualizar stats por método
                        if method in stats_method:
                            stats_method[method] += 1
                        else:
                            stats_method["other"] += 1
                        if result.get("hostId") == 0 or not result.get("hostUniqueId"):
                            stats_sin_host += 1

                        colocado = {
                            **disp,
                            "success": True,
                            "elementId": result["elementId"],
                            "uniqueId": result["uniqueId"],
                            "hostId": result.get("hostId"),
                            "hostUniqueId": result.get("hostUniqueId"),
                            "usedFaceBased": result.get("usedFaceBased", False),
                            "placementMethod": method,
                            "host_tipo": host_tipo,
                        }
                        colocados.append(colocado)
                        host_str = f" host={result.get('hostId')}" if result.get("hostId") else " NO_HOST"
                        method_str = f" [{method}]"
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> OK id={result['elementId']}{host_str}{method_str}")
                        placed_ok = True
                        break
                    else:
                        if attempt == max_retries - 1:
                            fallos += 1
                            colocados.append({
                                **disp, "success": False,
                                "error": result.get("error", "Unknown"),
                                "placementMethod": result.get("placementMethod", ""),
                                "host_tipo": host_tipo,
                            })
                            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> FALLO: {result.get('error')} [{result.get('placementMethod','')}]")
                        else:
                            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> Revit failure, retry {attempt+1}/{max_retries}")
                            time.sleep(0.5)
                            continue
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        fallos += 1
                        colocados.append({**disp, "success": False, "error": f"Parse error: {e}"})
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> PARSE ERROR: {e}")
                    else:
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> Parse error, retry {attempt+1}/{max_retries}")
                        time.sleep(0.5)
                        continue

    # ─── Reporte ───
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reporte = {
        "metadatos": {
            "proyecto": "RE",
            "fase": "F6",
            "tipo_documento": "reporte_colocacion",
            "version_esquema": "1.0",
            "version_script": "v03",
            "fixes_aplicados": ["P6_direction_basisZ", "P3_tomas_face_based", "ceiling_search_real"],
            "fecha_ejecucion": datetime.now().isoformat(),
            "timestamp": timestamp,
            "apartamento_tipo": apartamento,
            "tablero": tablero,
            "documento_objetivo": doc_info.get("Title"),
            "inventario_origen": inventario_path.name,
            "inventario_hash": meta["origen_dxf"]["hash_sha256"],
            "panel_dxf_local": {"x_m": panel_dxf_local[0], "y_m": panel_dxf_local[1]},
            "panel_revit_mm": {"x": panel_revit_mm[0], "y": panel_revit_mm[1]},
            "offset_mm": {"x": offset_x, "y": offset_y},
            "estadisticas": {
                "total_intentados": len(dispositivos),
                "exitos": exitos,
                "fallos": fallos,
                "sin_mapeo": sum(1 for d in dispositivos if not d.get("familia_revit")),
                "sin_host": stats_sin_host,
                "por_metodo": stats_method,
            }
        },
        "colocados": colocados,
    }

    nombre_reporte = f"colocacion_{apartamento.replace(' ', '')}_v03_{timestamp}.json"
    reporte_path = DATA_DIR / "colocaciones" / nombre_reporte
    reporte_path.parent.mkdir(parents=True, exist_ok=True)
    with open(reporte_path, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"REPORTE DE COLOCACIÓN v03")
    print(f"{'='*60}")
    print(f"Total intentados: {len(dispositivos)}")
    print(f"✓ Exitos:         {exitos}")
    print(f"✗ Fallos:         {fallos}")
    print(f"⚠ Sin host:       {stats_sin_host}  (debería ser 0 con fixes P3+Techo)")
    print(f"\nEstadísticas por método de placement:")
    for method, count in stats_method.items():
        if count > 0 or method in ("wall_face_based", "ceiling_hosted"):
            print(f"  {method:40s} : {count}")
    print(f"\nReporte guardado: {reporte_path}")

    # ─── Validar contra V02-f ───
    print(f"\nValidando contra modelo de referencia V02-f...")
    try:
        referencia = cargar_referencia_v02f()
        validacion = validar_colocacion([c for c in colocados if c.get("success")], referencia)

        print(f"  Dispositivos colocados válidos: {validacion['total_colocados']}")
        print(f"  Dispositivos en referencia:     {validacion['total_referencia']}")
        print(f"  ✓ Coinciden (dentro de tolerancia): {validacion['coinciden']}")
        print(f"  ✗ Diferencias posición:  {len(validacion['diferencias_posicion'])}")
        print(f"  ✗ Diferencias altura:    {len(validacion['diferencias_altura'])}")
        print(f"  ✗ Diferencias rotación:  {len(validacion['diferencias_rotacion'])}")
        print(f"  ⚠ Sin host (P3 check):   {len(validacion['sin_host'])}")

        validacion_path = DATA_DIR / "validaciones" / f"validacion_{apartamento.replace(' ', '')}_v03_{timestamp}.json"
        validacion_path.parent.mkdir(parents=True, exist_ok=True)
        with open(validacion_path, "w", encoding="utf-8") as f:
            json.dump(validacion, f, indent=2, ensure_ascii=False)
        print(f"  Validación guardada: {validacion_path}")

        tasa_coincidencia = (validacion['coinciden'] / validacion['total_colocados'] * 100) if validacion['total_colocados'] else 0
        print(f"\n  Tasa de coincidencia con V02-f: {tasa_coincidencia:.1f}%")
    except Exception as e:
        print(f"  ⚠ No se pudo validar contra V02-f: {e}")
        validacion = {"error": str(e)}

    tasa_exito = (exitos / len(dispositivos) * 100) if dispositivos else 0

    print(f"\n{'='*60}")
    print(f"RESUMEN FINAL v03")
    print(f"{'='*60}")
    print(f"Tasa de colocación exitosa:    {tasa_exito:.1f}%")
    print(f"Dispositivos sin host:         {stats_sin_host} (meta: 0)")
    if stats_sin_host == 0 and tasa_exito >= 95:
        print(f"✓ Fixes P3+P6+Techo verificados: todos los dispositivos tienen host")
        return 0
    elif stats_sin_host > 0:
        print(f"⚠ Hay {stats_sin_host} dispositivos sin host. Revisar reporte para detalles.")
        return 1
    else:
        print(f"⚠ Tasa de éxito < 95%. Revisar fallos en reporte.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
