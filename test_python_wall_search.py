#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test: buscar muro cercano en Python, luego C# solo para face-based en ESE muro
"""

import socket, json
import math

# 1. Obtener muros (ya los tenemos en el script principal)
# Simulamos: obtener muros via MCP
def get_walls():
    code = r'''
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
    payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code}, 'id': 1}
    data = json.dumps(payload, separators=(',', ':')) + '\n'
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect(('127.0.0.1', 8080))
    sock.sendall(data.encode('utf-8'))
    resp = b''
    while True:
        chunk = sock.recv(8192)
        if not chunk: break
        resp += chunk
        try: json.loads(resp.decode('utf-8')); break
        except: continue
    sock.close()
    r = json.loads(resp.decode('utf-8'))
    return json.loads(json.loads(r["result"]["result"]))

# 2. Buscar muro más cercano en Python
def find_nearest_wall(walls, x_mm, y_mm, level_id, tol_mm=600):
    """walls: lista de dicts con x1,y1,x2,y2,levelId,id. Retorna (wall_dict, proj_point_mm, dist_mm)"""
    pt = (x_mm, y_mm)
    tol_sq = tol_mm * tol_mm
    best = None
    best_dist = float('inf')
    best_proj = None
    
    for w in walls:
        if w['levelId'] != level_id: continue
        x1, y1, x2, y2 = w['x1'], w['y1'], w['x2'], w['y2']
        # Proyectar punto a segmento
        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx*dx + dy*dy
        if seg_len_sq == 0: continue
        t = ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / seg_len_sq
        t = max(0, min(1, t))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        dist_sq = (pt[0] - proj_x)**2 + (pt[1] - proj_y)**2
        if dist_sq < best_dist and dist_sq <= tol_sq:
            best_dist = dist_sq
            best = w
            best_proj = (proj_x, proj_y)
    if best:
        return best, best_proj, math.sqrt(best_dist)
    return None, None, None

# 3. C# face-based SOLO para ese muro (rápido)
CS_FACE_WALL_SINGLE = r'''
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; 
int wallId = (int)j["W"]; double projX = (double)j["PX"]; double projY = (double)j["PY"]; string devId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return "{\"success\":false,\"error\":\"Symbol not found\"}";
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return "{\"success\":false,\"error\":\"Level not found\"}";
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);
XYZ projPt = new XYZ(projX/304.8, projY/304.8, 0);

Wall bestWall = doc.GetElement(new ElementId(wallId)) as Wall;
if (bestWall == null) return "{\"success\":false,\"error\":\"Wall not found\"}";

XYZ perp = new XYZ(pt.X - projPt.X, pt.Y - projPt.Y, 0);
double pl = perp.GetLength(); if (pl < 0.001) return "{\"success\":false,\"error\":\"On wall\"}";
XYZ perpN = new XYZ(perp.X/pl, perp.Y/pl, 0);

Reference faceRef = null; Face fFace = null; XYZ fNorm = null;
var opts = new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine };
var geom = bestWall.get_Geometry(opts);
if (geom != null) foreach (var o in geom) { if (!(o is Solid)) continue; foreach (Face f in (o as Solid).Faces) {
    try { var bbox = f.GetBoundingBox(); var n = f.ComputeNormal(new UV((bbox.Min.U+bbox.Max.U)/2, (bbox.Min.V+bbox.Max.V)/2));
    if (Math.Abs(n.Z) > 0.1) continue; double dot = n.X*perpN.X + n.Y*perpN.Y; if (dot > 0.5) { faceRef = f.Reference; fFace = f; fNorm = n; break; } }
    catch {} if (faceRef != null) break; } if (faceRef != null) break; }

if (faceRef == null) return "{\"success\":false,\"error\":\"No facing face\"}";
var projF = fFace.Project(pt); if (projF == null || projF.XYZPoint == null) return "{\"success\":false,\"error\":\"Face project failed\"}";
XYZ facePt = projF.XYZPoint;

double wallBase = 0; var bp = bestWall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT);
if (bp == null) bp = bestWall.get_Parameter(BuiltInParameter.LEVEL_PARAM);
if (bp != null && bp.HasValue) { var lid = bp.AsElementId(); if (lid != null && lid != ElementId.InvalidElementId) { var bl = doc.GetElement(lid) as Level; if (bl != null) wallBase = bl.Elevation; } }
double elevRel = (z/304.8) - wallBase; XYZ placePt = new XYZ(facePt.X, facePt.Y, elevRel);

XYZ dir = XYZ.BasisZ;
FamilyInstance inst = doc.Create.NewFamilyInstance(faceRef, placePt, dir, sym);
int hId = (int)bestWall.Id.Value;

if (fNorm != null) { double ar = Math.Atan2(fNorm.Y, fNorm.X); double ad = ar * 180 / Math.PI; int rd = (int)Math.Round(ad/90)*90; rd = ((rd%360)+360)%360;
    if (Math.Abs(rd) > 0.1) { try { var loc = inst.Location as LocationPoint; if (loc != null) { var ax = Line.CreateBound(placePt, new XYZ(placePt.X, placePt.Y, placePt.Z+1)); loc.Rotate(ax, rd*Math.PI/180); } } catch {} } }

return "{\"success\":true,\"elementId\":" + (inst?.Id.Value ?? 0) + ",\"uniqueId\":\"" + (inst?.UniqueId ?? "") + "\",\"hostId\":" + hId + ",\"usedFace\":true}";
'''

# --- EJECUCIÓN ---
print("Obteniendo muros...")
walls = get_walls()
print(f"Muros totales: {len(walls)}")

# Test con toma real
x_mm, y_mm, z_mm = 10487, 1541, 13520
level_id = 192512
pt = (x_mm, y_mm)

wall, proj, dist = find_nearest_wall(walls, x_mm, y_mm, level_id, 600)
if not wall:
    print("No se encontró muro cercano")
else:
    print(f"Muro más cercano: Id={wall['id']} Dist={dist:.1f}mm Proj=({proj[0]:.1f},{proj[1]:.1f})")
    
    # Llamar C# con ese muro
    fam, tip, rot, alt_mm = "M_Toma doble", "Normal", 90, 300
    dj = json.dumps({"F":fam,"T":tip,"X":x_mm,"Y":y_mm,"Z":z_mm,"R":rot,"A":alt_mm,"L":level_id,
                     "W":wall['id'],"PX":proj[0],"PY":proj[1],"D":"test"}, separators=(",",":"))
    dj_esc = dj.replace('"', '""')
    code = f'string deviceJson = @"{dj_esc}";\n' + CS_FACE_WALL_SINGLE
    
    payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code}, 'id': 1}
    data = json.dumps(payload, separators=(',', ':')) + '\n'
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect(('127.0.0.1', 8080))
    sock.sendall(data.encode('utf-8'))
    resp = b''
    while True:
        chunk = sock.recv(8192)
        if not chunk: break
        resp += chunk
        try: json.loads(resp.decode('utf-8')); break
        except: continue
    sock.close()
    
    r = json.loads(resp.decode('utf-8'))
    print(json.dumps(r, indent=2))