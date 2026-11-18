#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test unitario: colocar 5 dispositivos (1 de cada tipo) en F01.
Usa coordenadas REALES del inventario F01 (DXF local, metros).
"""

import json
import socket
import sys
import os
import time
from pathlib import Path

MCP_HOST = "127.0.0.1"
MCP_PORT = 8080
REVITELECTRICO_ROOT = Path(r"D:\Work\PROJECTS\RevitElectrico")
DATA_DIR = REVITELECTRICO_ROOT / "data"
ARCHIVOS_BASE_DIR = REVITELECTRICO_ROOT / "ArchivosBase"

# 5 dispositivos de prueba - COORDENADAS REALES DEL INVENTARIO F01 (metros, DXF local)
TEST_DEVICES = [
    {
        "handle": "63",  # ELEC-T-GFCI-t-15A
        "familia": "M_Toma doble",
        "tipo": "GFCI",
        "rot": 270,
        "altura_mm": 300,
        "x_m": -3.5038,
        "y_m": -6.4695,
        "expected_host": "Muro",
        "expected_method": "wall_face_based"
    },
    {
        "handle": "125",  # Bala Stil Led 22W
        "familia": "M_Iluminacion",
        "tipo": "SONO FLEX 22 trim",
        "rot": 180,
        "altura_mm": 2600,
        "x_m": -1.2549,
        "y_m": -2.1202,
        "expected_host": "Techo",
        "expected_method": "ceiling_face_based"
    },
    {
        "handle": "AF",  # ELEC-I-S-1-5A
        "familia": "M_Interruptores",
        "tipo": "Simple",
        "rot": 90,
        "altura_mm": 1100,
        "x_m": -1.1603,
        "y_m": -0.0624,
        "expected_host": "Nivel",
        "expected_method": "level_based"
    },
    {
        "handle": "C1",  # ELEC-F-VENT
        "familia": "M_ClimatizacionV",
        "tipo": "Ventilador",
        "rot": 120,
        "altura_mm": 2600,
        "x_m": -1.9745,
        "y_m": -4.7342,
        "expected_host": "Techo",
        "expected_method": "ceiling_face_based"
    },
    {
        "handle": "CA",  # ELEC-F-CONTROL
        "familia": "M_Climatizacion",
        "tipo": "Interruptor Ventilador",
        "rot": 180,
        "altura_mm": 1100,
        "x_m": -2.2193,
        "y_m": -2.9997,
        "expected_host": "Nivel",
        "expected_method": "level_based"
    }
]

FAMILIAS_FACE_BASED = {"M_Interruptores", "M_Pulsador - Interruptor", "M_Timbre", "M_Toma doble", "M_Comunicaciones"}
FAMILIAS_TECHO_BASED = {"M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"}

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

def parse_mcp_response(resp: dict):
    """Parse the double-encoded MCP response."""
    raw = resp.get("result", {}).get("result")
    if raw is None:
        return {"success": False, "error": "No result in response"}
    if isinstance(raw, str):
        try:
            inner = json.loads(raw)
            if isinstance(inner, str):
                return json.loads(inner)
            return inner
        except:
            return {"success": False, "error": f"Parse error: {raw[:100]}"}
    return raw

# ─── C# Templates ───

CS_GET_PANELS = r'''
var doc = document;
var collector = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType();
var list = new List<object>();
foreach (var elem in collector) {
    var fi = elem as FamilyInstance; if (fi == null) continue;
    var loc = fi.Location as LocationPoint; if (loc == null) continue;
    var pt = loc.Point;
    string pn = ""; var p = fi.LookupParameter("Panel Name"); if (p != null && p.HasValue) pn = p.AsString() ?? "";
    list.Add(new { id = (int)fi.Id.Value, family = fi.Symbol.Family.Name, type = fi.Symbol.Name, panelName = pn,
        x = Math.Round(pt.X * 304.8, 1), y = Math.Round(pt.Y * 304.8, 1), z = Math.Round(pt.Z * 304.8, 1), levelId = fi.LevelId?.Value ?? 0 });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(list);
'''

CS_GET_WALLS = r'''
var doc = document;
var collector = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType();
var list = new List<object>();
foreach (var elem in collector) {
    var w = elem as Wall; if (w == null) continue;
    var loc = w.Location as LocationCurve; if (loc == null) continue;
    var c = loc.Curve; var p0 = c.GetEndPoint(0); var p1 = c.GetEndPoint(1);
    list.Add(new { id = (int)w.Id.Value, x1 = Math.Round(p0.X * 304.8, 1), y1 = Math.Round(p0.Y * 304.8, 1),
        x2 = Math.Round(p1.X * 304.8, 1), y2 = Math.Round(p1.Y * 304.8, 1), levelId = w.LevelId?.Value ?? 0 });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(list);
'''

CS_GET_CEILINGS = r'''
var doc = document;
var collector = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType();
var list = new List<object>();
foreach (var elem in collector) {
    var c = elem as Ceiling; if (c == null) continue;
    var bb = c.get_BoundingBox(null); if (bb == null) continue;
    list.Add(new { id = (int)c.Id.Value, xmin = Math.Round(bb.Min.X * 304.8, 1), ymin = Math.Round(bb.Min.Y * 304.8, 1), zmin = Math.Round(bb.Min.Z * 304.8, 1),
        xmax = Math.Round(bb.Max.X * 304.8, 1), ymax = Math.Round(bb.Max.Y * 304.8, 1), zmax = Math.Round(bb.Max.Z * 304.8, 1), levelId = c.LevelId?.Value ?? 0 });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(list);
'''

CS_FACE_WALL = r'''
var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);
var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical")) { e.OverrideResult(6); }
});
uiapp.DialogBoxShowing += dlgHandler;
try {
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; 
int wallId = (int)j["W"]; double projX = (double)j["PX"]; double projY = (double)j["PY"]; string devId = j["D"]?.ToString();
FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);
XYZ projPt = new XYZ(projX/304.8, projY/304.8, 0);
Wall bestWall = doc.GetElement(new ElementId(wallId)) as Wall;
if (bestWall == null) return "{\"success\":false,\"error\":\"Wall not found\"}";
Reference faceRef = null; Face fFace = null; XYZ fNorm = null;
var opts = new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine };
var geom = bestWall.get_Geometry(opts);
if (geom != null) foreach (var o in geom) { if (!(o is Solid)) continue; foreach (Face f in (o as Solid).Faces) {
    try { var r = f.Project(pt); if (r != null && r.XYZPoint != null) {
        var uv = r.UVPoint; var bb = f.GetBoundingBox();
        if (bb.Min.U <= uv.U && uv.U <= bb.Max.U && bb.Min.V <= uv.V && uv.V <= bb.Max.V) {
            var n = f.ComputeNormal(uv);
            if (Math.Abs(n.Z) < 0.1) { faceRef = f.Reference; fFace = f; fNorm = n; break; }
        }
    } catch {} if (faceRef != null) break; } if (faceRef != null) break; }
}
if (faceRef == null) return "{\"success\":false,\"error\":\"No vertical face contains point\"}";
var projF = fFace.Project(pt); if (projF == null || projF.XYZPoint == null) return "{\"success\":false,\"error\":\"Face project failed\"}";
XYZ facePt = projF.XYZPoint;
double wallBase = 0; var bp = bestWall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT);
if (bp == null) bp = bestWall.get_Parameter(BuiltInParameter.LEVEL_PARAM);
if (bp != null && bp.HasValue) { var lid = bp.AsElementId(); if (lid != null && lid != ElementId.InvalidElementId) { var bl = doc.GetElement(lid) as Level; if (bl != null) wallBase = bl.Elevation; } }
double elevRel = (z/304.8) - wallBase; XYZ placePt = new XYZ(facePt.X, facePt.Y, elevRel);
XYZ dir = XYZ.BasisZ;
FamilyInstance inst = null;
try { inst = doc.Create.NewFamilyInstance(faceRef, placePt, dir, sym); }
catch (Exception exPlace) { return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "NewFamilyInstance failed: " + exPlace.Message }); }
if (inst == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "inst is null" });
int hId = (int)bestWall.Id.Value;
if (rot != 0) {
    double rad = (rot + 90.0) * Math.PI / 180.0;
    try { var loc = inst.Location as LocationPoint; if (loc != null) { var ax = Line.CreateBound(placePt, new XYZ(placePt.X, placePt.Y, placePt.Z+1)); loc.Rotate(ax, rad); } }
    catch (Exception exRot) { return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Rotate failed: " + exRot.Message }); }
}
return "{\"success\":true,\"elementId\":\"" + (inst?.Id.Value ?? 0) + "\",\"uniqueId\":\"" + (inst?.UniqueId ?? "") + "\",\"hostId\":\"" + hId + "\",\"usedFace\":true,\"placementMethod\":\"wall_face_based\"}";
}
finally { uiapp.DialogBoxShowing -= dlgHandler; }
'''

CS_FACE_CEILING = r'''
var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);
var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical")) { e.OverrideResult(6); }
});
uiapp.DialogBoxShowing += dlgHandler;
try {
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; string devId = j["D"]?.ToString();
FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);
Ceiling bestC = null; double bestA = double.MaxValue;
var opts = new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine };
var ceils = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType().Cast<Ceiling>().Where(c => c.LevelId.Value == lvlId);
foreach (var c in ceils) {
    var geom = c.get_Geometry(opts); if (geom == null) continue;
    foreach (var o in geom) { if (!(o is Solid)) continue; foreach (Face f in (o as Solid).Faces) {
        try { var r = f.Project(pt); if (r == null) continue; var uv = r.UVPoint; var bb = f.GetBoundingBox();
        if (bb.Min.U <= uv.U && uv.U <= bb.Max.U && bb.Min.V <= uv.V && uv.V <= bb.Max.V) {
            double a = f.Area; if (a < bestA) { bestA = a; bestC = c; } break; } } catch {} } }
}
if (bestC == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "No ceiling" });
Reference faceRef = null; XYZ placePt = pt;
var geom2 = bestC.get_Geometry(opts);
if (geom2 != null) foreach (var o in geom2) { if (!(o is Solid)) continue; foreach (Face f in (o as Solid).Faces) {
    try { var r = f.Project(pt); if (r == null) continue; var uv = r.UVPoint; var bb = f.GetBoundingBox();
    if (bb.Min.U <= uv.U && uv.U <= bb.Max.U && bb.Min.V <= uv.V && uv.V <= bb.Max.V) { faceRef = f.Reference; placePt = r.XYZPoint; break; } } catch {} if (faceRef != null) break; } if (faceRef != null) break; }
if (faceRef == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "No ceiling face" });
XYZ dir = XYZ.BasisZ;
FamilyInstance inst = doc.Create.NewFamilyInstance(faceRef, placePt, dir, sym);
int hId = (int)bestC.Id.Value;
return "{\"success\":true,\"elementId\":\"" + (inst?.Id.Value ?? 0) + "\",\"uniqueId\":\"" + (inst?.UniqueId ?? "") + "\",\"hostId\":\"" + hId + "\",\"usedFace\":true,\"placementMethod\":\"ceiling_face_based\"}";
}
finally { uiapp.DialogBoxShowing -= dlgHandler; }
'''

CS_LEVEL_BASED = r'''
var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);
var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical")) { e.OverrideResult(6); }
});
uiapp.DialogBoxShowing += dlgHandler;
try {
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; string devId = j["D"]?.ToString();
FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);
FamilyInstance inst = doc.Create.NewFamilyInstance(pt, sym, lvl, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
if (inst == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Create failed" });
var loc = inst.Location as LocationPoint;
if (loc != null) {
    XYZ currentPt = loc.Point;
    XYZ moveVec = new XYZ(pt.X - currentPt.X, pt.Y - currentPt.Y, 0);
    if (moveVec.GetLength() > 0.001) { ElementTransformUtils.MoveElement(doc, inst.Id, moveVec); }
}
if (rot != 0) { double rad = rot * Math.PI / 180; foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Rotation"||n=="Angle") { if(!p.IsReadOnly){p.Set(rad);break;} } } }
if (altMM > 0) { foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Elevation"||n=="Offset") { if(!p.IsReadOnly){p.Set(altMM/304.8);break;} } } }
return "{\"success\":true,\"elementId\":\"" + (inst?.Id.Value ?? 0) + "\",\"uniqueId\":\"" + (inst?.UniqueId ?? "") + "\",\"hostId\":0,\"usedFace\":false,\"placementMethod\":\"level_based\"}";
}
finally { uiapp.DialogBoxShowing -= dlgHandler; }
'''

# Find nearest wall in Python
def find_nearest_wall(muros, x_mm, y_mm, level_id):
    best = None
    best_dist = 610.0  # 2ft tolerance
    best_proj = (0, 0)
    for m in muros:
        if m.get("levelId") != level_id:
            continue
        x1, y1 = m["x1"], m["y1"]
        x2, y2 = m["x2"], m["y2"]
        dx = x2 - x1
        dy = y2 - y1
        seg_len_sq = dx*dx + dy*dy
        if seg_len_sq < 1e-6:
            continue
        t = ((x_mm - x1) * dx + (y_mm - y1) * dy) / seg_len_sq
        t = max(0.0, min(1.0, t))
        nx = x1 + t * dx
        ny = y1 + t * dy
        dist = ((x_mm - nx)**2 + (y_mm - ny)**2)**0.5
        if dist < best_dist:
            best_dist = dist
            best = m
            best_proj = (nx, ny)
    return best, best_proj

def find_smallest_ceiling_at(techos, x_mm, y_mm):
    best = None
    best_area = float("inf")
    for t in techos:
        if x_mm < t["xmin"] or x_mm > t["xmax"] or y_mm < t["ymin"] or y_mm > t["ymax"]:
            continue
        area = (t["xmax"] - t["xmin"]) * (t["ymax"] - t["ymin"])
        if area < best_area:
            best_area = area
            best = t
    return best

def main():
    # Load F01 inventory for metadata
    inv_path = DATA_DIR / "inventarios" / "inventario_dispositivos_F01_v1.1_20261117_190929.json"
    with open(inv_path, "r", encoding="utf-8") as f:
        inventario = json.load(f)
    
    meta = inventario["metadatos"]
    apartamento = meta["apartamento_tipo"]
    dxf_filename = meta["origen_dxf"]["archivo"]
    
    # Get panels
    print("Obteniendo paneles...")
    resp = mcp_send_code(CS_GET_PANELS, timeout=120)
    paneles = json.loads(json.loads(resp["result"]["result"]))
    target_name = "TF 01"
    panel_obj = next((p for p in paneles if p.get("panelName") == target_name), None)
    if not panel_obj:
        print(f"✗ Panel {target_name} no encontrado")
        sys.exit(1)
    print(f"Panel objetivo: {panel_obj['panelName']} @ ({panel_obj['x']:.1f}, {panel_obj['y']:.1f}) mm | LevelId: {panel_obj['levelId']}")
    
    # Panel in DXF local
    dxf_path = ARCHIVOS_BASE_DIR / dxf_filename
    import ezdxf
    doc_dxf = ezdxf.readfile(str(dxf_path))
    msp = doc_dxf.modelspace()
    panel_dxf = None
    for e in msp:
        if e.dxftype() == 'INSERT' and e.dxf.name in ('TB-Panel', 'TB-Parcial'):
            for a in e.attribs:
                if a.dxf.tag.upper() == 'TABLERO' and a.dxf.text.strip() == target_name:
                    panel_dxf = (float(e.dxf.insert.x), float(e.dxf.insert.y))
                    break
    if not panel_dxf:
        print(f"✗ Panel {target_name} no en DXF")
        sys.exit(1)
    print(f"Panel DXF local: ({panel_dxf[0]:.4f}, {panel_dxf[1]:.4f}) m")
    
    # Offset
    pdmm = (panel_dxf[0]*1000, panel_dxf[1]*1000)
    prmm = (panel_obj["x"], panel_obj["y"])
    offset_x, offset_y = prmm[0] - pdmm[0], prmm[1] - pdmm[1]
    print(f"Offset: ({offset_x:.1f}, {offset_y:.1f}) mm")
    
    level_id = panel_obj["levelId"]
    nivel_elevacion = meta["nivel_elevacion_m"]
    
    # Get walls & ceilings
    print("Obteniendo muros...")
    resp = mcp_send_code(CS_GET_WALLS, timeout=180)
    muros = json.loads(json.loads(resp["result"]["result"]))
    print(f"Muros: {len(muros)}")
    
    print("Obteniendo techos...")
    resp = mcp_send_code(CS_GET_CEILINGS, timeout=120)
    techos = json.loads(json.loads(resp["result"]["result"]))
    print(f"Techos: {len(techos)}")
    
    # Place test devices
    print(f"\n{'='*60}")
    print("TEST UNITARIO: 5 DISPOSITIVOS (1 de cada tipo)")
    print(f"{'='*60}")
    
    results = []
    
    for d in TEST_DEVICES:
        # Convert DXF local (meters) to Revit (mm) using offset
        x_mm = d["x_m"] * 1000 + offset_x
        y_mm = d["y_m"] * 1000 + offset_y
        z_mm_abs = (nivel_elevacion + d["altura_mm"]/1000) * 1000  # Z absoluto para face-based
        z_mm_rel = d["altura_mm"]  # Z relativo para level-based
        
        fam = d["familia"]
        tip = d["tipo"]
        rot = d["rot"]
        alt_mm = d["altura_mm"]
        
        print(f"  {d['handle']} ({fam} / {tip}) -> DXF=({d['x_m']:.4f}, {d['y_m']:.4f}) -> Revit=({x_mm:.1f}, {y_mm:.1f})")
        
        # Determine template and host
        if fam in FAMILIAS_FACE_BASED:
            cs_template = CS_FACE_WALL
            z_mm = z_mm_abs
            wall, proj = find_nearest_wall(muros, x_mm, y_mm, level_id)
            if not wall:
                print(f"    NO WALL FOUND near ({x_mm:.0f}, {y_mm:.0f}) -> fallback level")
                cs_template = CS_LEVEL_BASED
                z_mm = z_mm_rel
                host_elem_id = 0
                proj_x, proj_y = 0, 0
            else:
                host_elem_id = wall["id"]
                proj_x, proj_y = proj
                print(f"    Wall found: ID={host_elem_id} proj=({proj_x:.1f}, {proj_y:.1f})")
        elif fam in FAMILIAS_TECHO_BASED:
            cs_template = CS_FACE_CEILING
            z_mm = z_mm_abs
            ceiling = find_smallest_ceiling_at(techos, x_mm, y_mm)
            if not ceiling:
                print(f"    NO CEILING FOUND at ({x_mm:.0f}, {y_mm:.0f}) -> fallback level")
                cs_template = CS_LEVEL_BASED
                z_mm = z_mm_rel
                host_elem_id = 0
            else:
                host_elem_id = ceiling["id"]
                print(f"    Ceiling found: ID={host_elem_id}")
        else:
            cs_template = CS_LEVEL_BASED
            z_mm = z_mm_rel
            host_elem_id = 0
        
        device_input = {
            "F": fam, "T": tip, "X": x_mm, "Y": y_mm, "Z": z_mm,
            "R": rot, "A": alt_mm, "L": level_id, "D": d["handle"]
        }
        if cs_template == CS_FACE_WALL:
            device_input["W"] = host_elem_id
            device_input["PX"] = proj_x
            device_input["PY"] = proj_y
        
        device_json = json.dumps(device_input, separators=(",", ":"))
        device_json_escaped = device_json.replace('"', '""')
        code = 'string deviceJson = @"' + device_json_escaped + '";\n' + cs_template
        
        print(f"    Colocando...")
        resp = mcp_send_code(code, timeout=30)
        
        if "error" in resp.get("result", {}):
            err = resp["result"]["errorMessage"]
            print(f"    ✗ ERROR MCP: {err[:120]}")
            results.append({**d, "success": False, "error": err})
            continue
        
        res = parse_mcp_response(resp)
        
        if res.get("success"):
            element_id = res.get("elementId")
            host_id = res.get("hostId")
            method = res.get("placementMethod")
            used_face = res.get("usedFace")
            
            # Verify position by reading back
            verify_code = f'''
            var doc = document;
            var elem = doc.GetElement(new ElementId({element_id}));
            var fi = elem as FamilyInstance;
            var loc = fi?.Location as LocationPoint;
            return Newtonsoft.Json.JsonConvert.SerializeObject(new {{
                x = loc != null ? Math.Round(loc.Point.X * 304.8, 1) : 0,
                y = loc != null ? Math.Round(loc.Point.Y * 304.8, 1) : 0,
                z = loc != null ? Math.Round(loc.Point.Z * 304.8, 1) : 0,
                hostId = fi?.Host?.Id?.Value ?? 0
            }});
            '''
            vresp = mcp_send_code(verify_code, timeout=10)
            vres = parse_mcp_response(vresp)
            
            vx, vy, vz = vres.get("x", 0), vres.get("y", 0), vres.get("z", 0)
            vhost = vres.get("hostId", 0)
            
            # Check
            dx = abs(vx - x_mm)
            dy = abs(vy - y_mm)
            pos_ok = dx <= 50 and dy <= 50
            host_ok = (vhost > 0) == (d["expected_host"] != "Nivel")
            
            status = "✓" if (pos_ok and host_ok) else "⚠"
            print(f"    {status} id={element_id} pos=({vx:.1f},{vy:.1f},{vz:.1f}) host={vhost} method={method} dx={dx:.1f} dy={dy:.1f}")
            results.append({**d, "success": True, "elementId": element_id, "hostId": vhost, "verifiedX": vx, "verifiedY": vy, "verifiedZ": vz, "method": method, "pos_ok": pos_ok, "host_ok": host_ok})
        else:
            print(f"    ✗ FALLO: {res.get('error')}")
            results.append({**d, "success": False, "error": res.get("error"), "method": res.get("placementMethod")})
    
    # Summary
    print(f"\n{'='*60}")
    print("RESUMEN TEST UNITARIO")
    print(f"{'='*60}")
    ok = sum(1 for r in results if r.get("success") and r.get("pos_ok") and r.get("host_ok"))
    for r in results:
        if r.get("success"):
            status = "✓" if (r.get("pos_ok") and r.get("host_ok")) else "⚠"
            print(f"  {status} {r['handle']:12s} | {r['familia']:25s} | {r['method']:20s} | pos_ok={r.get('pos_ok')} host_ok={r.get('host_ok')}")
        else:
            print(f"  ✗ {r['handle']:12s} | {r['familia']:25s} | ERROR: {r.get('error', 'unknown')[:60]}")
    print(f"\nTotal: {len(results)} | Correctos: {ok} | Fallos: {len(results)-ok}")
    
    if ok == 5:
        print("\n✅ TEST UNITARIO PASÓ - Proceder con colocación completa F01/F02")
        return 0
    else:
        print("\n❌ TEST UNITARIO FALLÓ - Revisar antes de continuar")
        return 1

if __name__ == "__main__":
    sys.exit(main())