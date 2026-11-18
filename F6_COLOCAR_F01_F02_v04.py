#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F6_COLOCAR_F01_F02_v04.py
==========================
Coloca dispositivos de apartamentos F01/F02 en CENTRAL-V01.rvt usando MCP (puerto 8080).

Arquitectura: Python-busca / C#-coloca.

  - Python obtiene TODOS los muros y techos una sola vez al inicio (2 llamadas MCP).
  - Python busca el host más cercano a cada dispositivo IN-MEMORY (O(M) una sola vez,
    no por dispositivo).
  - C# solo recibe el hostElementId específico y coloca sobre ese elemento.
    No hace FilteredElementCollector ni loop de muros → O(1) por dispositivo.

Esto resuelve el bug de performance de v03a: con 21,405 muros en el modelo,
v03a hacía >2M de iteraciones de muros en C# (timeout sistemático).
v04 hace exactamente 2 + N llamadas MCP (N = dispositivos).

FIXES v04 (sobre v03a):

  1. Performance: Python busca host, C# solo coloca con hostElementId.
     Elimina el loop de muros en C# por dispositivo.

  2. FIX P6 (direction vector): direction = XYZ.BasisZ en NewFamilyInstance
     face-based. Rotación post-placement con Location.Rotate(axis, rad).

  3. FIX P3 (tomas sin host): M_Toma doble y M_Comunicaciones en
     FAMILIAS_FACE_BASED (v02 las mandaba a level-based).

  4. FIX TECHO (ceiling search real): OST_Ceilings search en Python,
     element-hosted placement en C#.

OBSERVABILIDAD (heredada de v03a):

  - stats_method: conteo por placementMethod (wall_face_based, ceiling_hosted,
    level_fallback, level_default)
  - stats_sin_host: dispositivos con hostId=0 (meta: 0)
  - Validación V02-f con reporte de sin_host (detecta bug P3 automáticamente)
  - Exit codes semánticos: 0=ok, 1=sin_host>0 o tasa<95%
  - Cada dispositivo reporta placementMethod en el reporte JSON

HEREDADO DE v02/v03a (sin cambios):
  - Z en mm (altura_local_mm)
  - Offset dinámico panel DXF vs panel Revit
  - Validación SHA256 frescura
  - Retry logic 3× con 0.5s delay
  - CLI argparse, multi-apartamento F01/F02

Uso:
    python F6_COLOCAR_F01_F02_v04.py --inventario data/inventarios/inventario_dispositivos_F01_v1.1_20261117_190929.json
    python F6_COLOCAR_F01_F02_v04.py --inventario data/inventarios/inventario_dispositivos_F02_v1.1_20261117_190933.json
"""

import json
import socket
import sys
import os
import hashlib
import time
import math
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

# Tolerancia de búsqueda de muro en Python (mm)
# 2 pies = 609.6mm, redondeado a 610mm para coincidir con el check original
TOL_MURO_MM = 610.0

# ─── Clasificación de familias (FIX P3) ──────────────────────────────────────
FAMILIAS_FACE_BASED = {
    "M_Interruptores",
    "M_Pulsador - Interruptor",
    "M_Timbre",
    "M_Toma doble",
    "M_Comunicaciones",
}

FAMILIAS_TECHO_BASED = {
    "M_Iluminacion",
    "M_ClimatizacionV",
    "Consolidation_Point",
}


# ─── Utilidades MCP ───────────────────────────────────────────────────────────
def mcp_send(method: str, params: dict = None, timeout: float = 10.0) -> dict:
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
    return mcp_send("send_code_to_revit", {"code": code}, timeout)


def validar_inventario_fresco(inventario_path: Path) -> bool:
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


# ─── C# blocks: solo para fetch de datos y placement puntual ──────────────────
# v04: C# NO busca muros ni techos. Python busca y pasa hostElementId.

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

# NEW v04: fetch de techos una sola vez (bounding box en mm)
CODIGO_OBTENER_TECHOS = r'''
var doc = document;
var collector = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Ceilings)
    .WhereElementIsNotElementType();

var techos = new List<object>();
foreach (var elem in collector) {
    var bbox = elem.get_BoundingBox(null);
    if (bbox == null) continue;
    techos.Add(new {
        id = (int)elem.Id.Value,
        uniqueId = elem.UniqueId,
        minX = Math.Round(bbox.Min.X * 304.8, 1),
        minY = Math.Round(bbox.Min.Y * 304.8, 1),
        minZ = Math.Round(bbox.Min.Z * 304.8, 1),
        maxX = Math.Round(bbox.Max.X * 304.8, 1),
        maxY = Math.Round(bbox.Max.Y * 304.8, 1),
        maxZ = Math.Round(bbox.Max.Z * 304.8, 1)
    });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(techos);
'''

# v04: placement C# recibe hostElementId específico. NO busca muros.
# Solo obtiene el elemento por ID, itera SUS caras (una sola wall), coloca.
CODIGO_COLLOCAR_V04 = r'''
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);

string familia = j["Familia"]?.ToString();
string tipo = j["Tipo"]?.ToString();
double x = (double)j["X"];
double y = (double)j["Y"];
double z = (double)j["Z"];
double rotacion = (double)j["Rotacion"];
double alturaLocalMM = (double)j["AlturaLocalMM"];
int levelIdVal = (int)j["LevelId"];
string hostTipo = j["HostTipo"]?.ToString() ?? "Muro";
int hostElementId = (int)j["HostElementId"];   // v04: Python ya encontro el host

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
// ESTRATEGIA 1: TECHO — hostElementId es un Ceiling
// Element-hosted: NewFamilyInstance(point, symbol, ceiling, NonStructural)
// ═══════════════════════════════════════════════════════════════════════════
if (inst == null && hostTipo == "Techo" && hostElementId > 0) {
    var ceiling = doc.GetElement(new ElementId(hostElementId));
    if (ceiling != null) {
        try {
            inst = doc.Create.NewFamilyInstance(point, symbol, ceiling, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
            hostId = (int)ceiling.Id.Value;
            hostUniqueId = ceiling.UniqueId;
            usedFaceBased = true;
            placementMethod = "ceiling_hosted";
        } catch (Exception exCeil) {
            placementMethod = "ceiling_failed:" + exCeil.Message;
        }
    } else {
        placementMethod = "ceiling_element_not_found";
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// ESTRATEGIA 2: MURO face-based — hostElementId es un Wall
// FIX P6: direction = XYZ.BasisZ. Rotacion post-placement con Location.Rotate.
// Solo itera las caras de ESTE muro (no FilteredElementCollector, no loop de muros).
// ═══════════════════════════════════════════════════════════════════════════
if (inst == null && hostTipo == "Muro" && hostElementId > 0) {
    var wall = doc.GetElement(new ElementId(hostElementId)) as Wall;
    if (wall != null) {
        // Iterar caras de ESTE muro solamente
        var geomElem = wall.get_Geometry(new Options {
            ComputeReferences = true,
            DetailLevel = ViewDetailLevel.Fine,
            IncludeNonVisibleObjects = true
        });

        Reference hostFaceRef = null;
        if (geomElem != null) {
            foreach (var geomObj in geomElem) {
                if (!(geomObj is Solid solid)) continue;
                if (solid.Faces.Size == 0) continue;
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
        }

        if (hostFaceRef != null) {
            try {
                // FIX P6: direction = XYZ.BasisZ (vertical)
                XYZ direction = XYZ.BasisZ;
                inst = doc.Create.NewFamilyInstance(hostFaceRef, point, direction, symbol);
                hostId = (int)wall.Id.Value;
                hostUniqueId = wall.UniqueId;
                usedFaceBased = true;
                placementMethod = "wall_face_based";

                // Rotacion post-placement con Location.Rotate sobre eje vertical
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
        placementMethod = "wall_element_not_found";
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// ESTRATEGIA 3: FALLBACK level-based (sin host)
// ═══════════════════════════════════════════════════════════════════════════
if (inst == null) {
    try {
        inst = doc.Create.NewFamilyInstance(point, symbol, level, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
        if (string.IsNullOrEmpty(placementMethod)) placementMethod = "level_default";
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
            string pname = p.Definition.Name;
            if (pname == "Rotation" || pname == "Angle" || pname.IndexOf("Rot") >= 0) {
                if (!p.IsReadOnly) { p.Set(rad); break; }
            }
        }
    }
    if (alturaLocalMM > 0) {
        foreach (Parameter p in inst.Parameters) {
            string pname = p.Definition.Name;
            if (pname == "Elevation" || pname == "Offset" || pname.IndexOf("Elev") >= 0 || pname.IndexOf("Offset") >= 0) {
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


# ─── Búsqueda de host en Python (O(M) una sola vez por dispositivo) ──────────

def find_nearest_wall(muros: list, x_mm: float, y_mm: float, level_id: int) -> dict:
    """Busca el muro más cercano a (x_mm, y_mm) en el nivel dado.
    
    muros: lista de dicts con campos {id, x1, y1, x2, y2, levelId, ...} (en mm).
    Usa proyección punto-línea sobre el segmento del muro y clamp a los extremos.
    
    Returns: dict del muro encontrado o None.
    """
    best_wall = None
    best_dist = TOL_MURO_MM
    for m in muros:
        if m.get("levelId") != level_id:
            continue
        x1, y1 = m["x1"], m["y1"]
        x2, y2 = m["x2"], m["y2"]
        dx = x2 - x1
        dy = y2 - y1
        wall_len_sq = dx * dx + dy * dy
        if wall_len_sq < 1e-6:
            continue
        # Proyección del punto sobre la línea del muro
        px = x_mm - x1
        py = y_mm - y1
        t = (px * dx + py * dy) / wall_len_sq
        t = max(0.0, min(1.0, t))  # clamp al segmento
        nx = x1 + t * dx
        ny = y1 + t * dy
        dist = math.sqrt((x_mm - nx) ** 2 + (y_mm - ny) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_wall = m
    return best_wall


def find_smallest_ceiling_at(techos: list, x_mm: float, y_mm: float) -> dict:
    """Busca el cielorraso más pequeño cuyo bounding box contiene (x_mm, y_mm).
    
    techos: lista de dicts con campos {id, minX, minY, maxX, maxY, ...} (en mm).
    Returns: dict del techo encontrado o None.
    """
    best_ceiling = None
    best_area = float("inf")
    for t in techos:
        if x_mm < t["minX"] or x_mm > t["maxX"]:
            continue
        if y_mm < t["minY"] or y_mm > t["maxY"]:
            continue
        area = (t["maxX"] - t["minX"]) * (t["maxY"] - t["minY"])
        if area < best_area:
            best_area = area
            best_ceiling = t
    return best_ceiling


# ─── Validación contra V02-f ──────────────────────────────────────────────────
def cargar_referencia_v02f() -> dict:
    with open(V02F_REFERENCE, "r", encoding="utf-8") as f:
        data = json.load(f)
    index = {}
    for d in data:
        key = f"{d.get('fam','')}_{d.get('tipo','')}_{round(d.get('x',0))}_{round(d.get('y',0))}"
        index[key] = d
    return index


def validar_colocacion(colocados: list, referencia: dict) -> dict:
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

        # Detectar dispositivos sin host (bug P3 check)
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
            dist = (dx ** 2 + dy ** 2 + dz ** 2) ** 0.5
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
        description="Coloca dispositivos F01/F02 via MCP (v04: Python-busca/C#-coloca)"
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
    print(f"COLOCACIÓN F01/F02 EN CENTRAL-V01 (v04)")
    print(f"{'='*60}")
    print(f"Arquitectura: Python-busca / C#-coloca (sin loop de muros en C#)")

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

    # ─── Obtener paneles ───
    print(f"\nObteniendo paneles (tableros) en el modelo...")
    resp = mcp_send_code(CODIGO_OBTENER_PANELES, timeout=120.0)
    if "error" in resp.get("result", {}):
        print(f"✗ Error obteniendo paneles: {resp['result']['errorMessage']}")
        sys.exit(1)
    raw_paneles = resp["result"]["result"]
    paneles = json.loads(json.loads(raw_paneles))
    print(f"  Paneles encontrados: {len(paneles)}")

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

    panel_dxf_mm = (panel_dxf_local[0] * 1000, panel_dxf_local[1] * 1000)
    panel_revit_mm = (panel_objetivo["x"], panel_objetivo["y"])
    offset_x = panel_revit_mm[0] - panel_dxf_mm[0]
    offset_y = panel_revit_mm[1] - panel_dxf_mm[1]
    print(f"  Offset calculado: X={offset_x:.1f}, Y={offset_y:.1f} mm")

    # ─── Fetch ONE-TIME: muros y techos ───
    print(f"\nObteniendo muros (one-shot)...")
    t0 = time.time()
    resp = mcp_send_code(CODIGO_OBTENER_MUROS, timeout=180.0)
    if "error" in resp.get("result", {}):
        print(f"✗ Error obteniendo muros: {resp['result']['errorMessage']}")
        sys.exit(1)
    raw_muros = resp["result"]["result"]
    muros = json.loads(json.loads(raw_muros))
    print(f"  Muros obtenidos: {len(muros)} en {time.time()-t0:.1f}s")

    print(f"Obteniendo techos (one-shot)...")
    t0 = time.time()
    resp = mcp_send_code(CODIGO_OBTENER_TECHOS, timeout=120.0)
    if "error" in resp.get("result", {}):
        print(f"⚠ Error obteniendo techos: {resp['result']['errorMessage']}")
        techos = []
    else:
        raw_techos = resp["result"]["result"]
        techos = json.loads(json.loads(raw_techos))
    print(f"  Techos obtenidos: {len(techos)} en {time.time()-t0:.1f}s")

    level_id = panel_objetivo["levelId"]

    # ─── Colocar dispositivos ───
    print(f"\n{'='*60}")
    print(f"COLOCANDO {len(dispositivos)} DISPOSITIVOS (v04: Python-busca/C#-coloca)")
    print(f"{'='*60}")

    colocados = []
    exitos = 0
    fallos = 0
    # Observabilidad (heredada de v03a)
    stats_method = {
        "wall_face_based": 0,
        "ceiling_hosted": 0,
        "level_fallback_from:wall_not_found": 0,
        "level_fallback_from:wall_face_not_found": 0,
        "level_fallback_from:ceiling_not_found": 0,
        "level_default": 0,
        "other": 0,
    }
    stats_sin_host = 0

    for i, disp in enumerate(dispositivos):
        if not disp.get("familia_revit"):
            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} -> SIN MAPEO REVIT")
            fallos += 1
            colocados.append({**disp, "success": False, "error": "Sin mapeo Revit"})
            continue

        # Coordenadas en mm + offset
        x_mm = disp["x"] * 1000 + offset_x
        y_mm = disp["y"] * 1000 + offset_y
        z_mm = disp["altura_local_m"] * 1000

        familia = disp["familia_revit"]
        tipo = disp["tipo_revit"]
        rotacion = disp["rotacion_final_grados"]

        # Determinar HostTipo y buscar host en Python
        host_element_id = 0
        host_tipo = "Nivel"
        host_search_info = ""

        if familia in FAMILIAS_FACE_BASED:
            host_tipo = "Muro"
            wall = find_nearest_wall(muros, x_mm, y_mm, level_id)
            if wall:
                host_element_id = wall["id"]
                host_search_info = f"wall_id={wall['id']}"
            else:
                host_search_info = "no_wall_found"

        elif familia in FAMILIAS_TECHO_BASED:
            host_tipo = "Techo"
            ceiling = find_smallest_ceiling_at(techos, x_mm, y_mm)
            if ceiling:
                host_element_id = ceiling["id"]
                host_search_info = f"ceiling_id={ceiling['id']}"
            else:
                host_search_info = "no_ceiling_found"

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
            "HostElementId": host_element_id,   # v04: Python ya encontro el host
        }

        device_json = json.dumps(device_input, separators=(",", ":"))
        device_json_escaped = device_json.replace('"', '""')
        code = 'string deviceJson = @"' + device_json_escaped + '";\n' + CODIGO_COLLOCAR_V04

        # Ejecutar con reintentos
        max_retries = 3
        for attempt in range(max_retries):
            resp = mcp_send_code(code, timeout=30.0)
            if "error" in resp.get("result", {}):
                error_msg = resp["result"]["errorMessage"]
                if attempt == max_retries - 1:
                    print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} [{host_search_info}] -> ERROR: {error_msg[:80]}")
                    fallos += 1
                    colocados.append({**disp, "success": False, "error": error_msg,
                                      "host_tipo": host_tipo, "host_element_id": host_element_id,
                                      "host_search_info": host_search_info})
                else:
                    print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} [{host_search_info}] -> MCP retry {attempt+1}/{max_retries}")
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
                        method = result.get("placementMethod", "unknown")
                        # Observabilidad: stats por método
                        if method in stats_method:
                            stats_method[method] += 1
                        else:
                            stats_method["other"] += 1
                        # Observabilidad: sin_host tracking
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
                            "host_element_id": host_element_id,
                            "host_search_info": host_search_info,
                        }
                        colocados.append(colocado)
                        host_str = f" host={result.get('hostId')}" if result.get("hostId") else " NO_HOST"
                        method_str = f" [{method}]"
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} {disp['nombre_dxf']} [{host_search_info}] -> OK id={result['elementId']}{host_str}{method_str}")
                        break
                    else:
                        if attempt == max_retries - 1:
                            fallos += 1
                            colocados.append({
                                **disp, "success": False,
                                "error": result.get("error", "Unknown"),
                                "placementMethod": result.get("placementMethod", ""),
                                "host_tipo": host_tipo,
                                "host_element_id": host_element_id,
                                "host_search_info": host_search_info,
                            })
                            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} [{host_search_info}] -> FALLO: {result.get('error')} [{result.get('placementMethod','')}]")
                        else:
                            print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} [{host_search_info}] -> Revit retry {attempt+1}/{max_retries}")
                            time.sleep(0.5)
                            continue
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        fallos += 1
                        colocados.append({**disp, "success": False, "error": f"Parse error: {e}"})
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} -> PARSE ERROR: {e}")
                    else:
                        print(f"  [{i+1}/{len(dispositivos)}] {disp['handle']} -> Parse retry {attempt+1}/{max_retries}")
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
            "version_script": "v04",
            "arquitectura": "python-busca-csharp-coloca",
            "fixes_aplicados": ["performance_python_host_search", "P6_direction_basisZ", "P3_tomas_face_based", "ceiling_search_real"],
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
            "modelo_counts": {
                "muros_totales": len(muros),
                "techos_totales": len(techos),
            },
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

    nombre_reporte = f"colocacion_{apartamento.replace(' ', '')}_v04_{timestamp}.json"
    reporte_path = DATA_DIR / "colocaciones" / nombre_reporte
    reporte_path.parent.mkdir(parents=True, exist_ok=True)
    with open(reporte_path, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"REPORTE DE COLOCACIÓN v04")
    print(f"{'='*60}")
    print(f"Total intentados: {len(dispositivos)}")
    print(f"✓ Exitos:         {exitos}")
    print(f"✗ Fallos:         {fallos}")
    print(f"⚠ Sin host:       {stats_sin_host}  (meta: 0)")
    print(f"\nEstadísticas por método de placement:")
    for method, count in sorted(stats_method.items()):
        if count > 0 or method in ("wall_face_based", "ceiling_hosted", "level_default"):
            print(f"  {method:50s} : {count}")
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

        validacion_path = DATA_DIR / "validaciones" / f"validacion_{apartamento.replace(' ', '')}_v04_{timestamp}.json"
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
    print(f"RESUMEN FINAL v04")
    print(f"{'='*60}")
    print(f"Tasa de colocación exitosa:    {tasa_exito:.1f}%")
    print(f"Dispositivos sin host:         {stats_sin_host} (meta: 0)")

    # Exit codes semánticos
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
