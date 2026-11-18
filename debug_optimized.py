#!/usr/bin/env python3
import socket, json

# C# OPTIMIZADO: filtro bounding box rápido antes de curve.Project
fam = "M_Toma doble"; tip = "Normal"; x_mm = 10487; y_mm = 1541; z_mm = 13520; rot = 90; alt_mm = 300; lvl = 192512

dj = json.dumps({"F":fam,"T":tip,"X":x_mm,"Y":y_mm,"Z":z_mm,"R":rot,"A":alt_mm,"L":lvl,"D":"test"}, separators=(",",":"))
dj_esc = dj.replace('"', '""')

code = f'string deviceJson = @"{dj_esc}";\n' + r'''
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; string devId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return "{\"success\":false,\"error\":\"Symbol not found\"}";
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return "{\"success\":false,\"error\":\"Level not found\"}";
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);

Wall bestWall = null; double minD = 2.0; XYZ projPt = null;
double tolFeet = 2.0; // 600mm
double tolSq = tolFeet * tolFeet;

var walls = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().Cast<Wall>().Where(w => w.LevelId.Value == lvlId);
foreach (var w in walls) {
    var loc = w.Location as LocationCurve; if (loc == null) continue;
    var bb = w.get_BoundingBox(null); if (bb == null) continue;
    // Filtro rápido: distancia al bounding box
    double dx = 0, dy = 0;
    if (pt.X < bb.Min.X) dx = bb.Min.X - pt.X; else if (pt.X > bb.Max.X) dx = pt.X - bb.Max.X;
    if (pt.Y < bb.Min.Y) dy = bb.Min.Y - pt.Y; else if (pt.Y > bb.Max.Y) dy = pt.Y - bb.Max.Y;
    if (dx*dx + dy*dy > tolSq) continue; // Muy lejos, saltar
    
    var proj = loc.Curve.Project(pt); if (proj == null) continue;
    double d = pt.DistanceTo(proj.XYZPoint); if (d < minD) { minD = d; bestWall = w; projPt = proj.XYZPoint; }
}
if (bestWall == null || projPt == null) return "{\"success\":false,\"error\":\"No wall near\"}";

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

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code}, 'id': 1}
data = json.dumps(payload, separators=(',', ':')) + '\n'

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(60)
sock.connect(('127.0.0.1', 8080))
sock.sendall(data.encode('utf-8'))
response = b''
while True:
    chunk = sock.recv(8192)
    if not chunk: break
    response += chunk
    try: json.loads(response.decode('utf-8')); break
    except: continue
resp = json.loads(response.decode('utf-8'))
print(json.dumps(resp, indent=2))
sock.close()