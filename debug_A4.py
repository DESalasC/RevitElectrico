#!/usr/bin/env python3
"""Debug single failing interruptor with verbose C# error"""
import json
import socket

MCP_HOST = "127.0.0.1"
MCP_PORT = 8080

# Device A4 ELEC-I-S-2-5A
fam = "M_Interruptores"
tip = "Doble"
x_mm = 11760.6
y_mm = 5193.5
z_mm = 14320.0
rot = 240.0
alt_mm = 1100.0
lvl = 192512
wall_id = 4829438  # from previous successful wall-based placements
proj_x = 11760.6  # approximate
proj_y = 5193.5

code = f'''var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; 
int wallId = (int)j["W"]; double projX = (double)j["PX"]; double projY = (double)j["PY"]; string devId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return "{{\\\"success\\\":false,\\\"error\\\":\\\"Symbol not found: \\\" + familia + \\\" / \\\" + tipo}}";
if (!sym.IsActive) {{ sym.Activate(); doc.Regenerate(); }}
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return "{{\\\"success\\\":false,\\\"error\\\":\\\"Level not found\\\"}}";
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);
XYZ projPt = new XYZ(projX/304.8, projY/304.8, 0);

Wall bestWall = doc.GetElement(new ElementId(wallId)) as Wall;
if (bestWall == null) return "{{\\\"success\\\":false,\\\"error\\\":\\\"Wall not found\\\"}}";

XYZ perp = new XYZ(pt.X - projPt.X, pt.Y - projPt.Y, 0);
double pl = perp.GetLength(); if (pl < 0.001) return "{{\\\"success\\\":false,\\\"error\\\":\\\"On wall\\\"}}";
XYZ perpN = new XYZ(perp.X/pl, perp.Y/pl, 0);

Reference faceRef = null; Face fFace = null; XYZ fNorm = null;
var opts = new Options {{ ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine }};
var geom = bestWall.get_Geometry(opts);
if (geom != null) foreach (var o in geom) {{ if (!(o is Solid)) continue; foreach (Face f in (o as Solid).Faces) {{
    try {{ var bbox = f.GetBoundingBox(); var n = f.ComputeNormal(new UV((bbox.Min.U+bbox.Max.U)/2, (bbox.Min.V+bbox.Max.V)/2));
    if (Math.Abs(n.Z) > 0.1) continue; double dot = n.X*perpN.X + n.Y*perpN.Y; if (dot < -0.3) {{ faceRef = f.Reference; fFace = f; fNorm = n; break; }} }}
    catch {{ }} if (faceRef != null) break; }} if (faceRef != null) break; }}

if (faceRef == null) return "{{\\\"success\\\":false,\\\"error\\\":\\\"No facing face (dot>=-0.3)\\\"}}";
var projF = fFace.Project(pt); if (projF == null || projF.XYZPoint == null) return "{{\\\"success\\\":false,\\\"error\\\":\\\"Face project failed\\\"}}";
XYZ facePt = projF.XYZPoint;

double wallBase = 0; var bp = bestWall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT);
if (bp == null) bp = bestWall.get_Parameter(BuiltInParameter.LEVEL_PARAM);
if (bp != null && bp.HasValue) {{ var lid = bp.AsElementId(); if (lid != null && lid != ElementId.InvalidElementId) {{ var bl = doc.GetElement(lid) as Level; if (bl != null) wallBase = bl.Elevation; }} }}
double elevRel = (z/304.8) - wallBase; XYZ placePt = new XYZ(facePt.X, facePt.Y, elevRel);

XYZ dir = XYZ.BasisZ;
FamilyInstance inst = null;
try {{
    inst = doc.Create.NewFamilyInstance(faceRef, placePt, dir, sym);
}} catch (Exception exPlace) {{
    return "{{\\\"success\\\":false,\\\"error\\\":\\\"NewFamilyInstance failed: \\\" + exPlace.Message + \\\" | type=\\\" + exPlace.GetType().Name}}";
}}
if (inst == null) return "{{\\\"success\\\":false,\\\"error\\\":\\\"inst is null\\\"}}";
int hId = (int)bestWall.Id.Value;

if (rot != 0) {{
    double rad = (rot + 90.0) * Math.PI / 180.0;
    try {{ var loc = inst.Location as LocationPoint; if (loc != null) {{ var ax = Line.CreateBound(placePt, new XYZ(placePt.X, placePt.Y, placePt.Z+1)); loc.Rotate(ax, rad); }} }} catch (Exception exRot) {{ return "{{\\\"success\\\":false,\\\"error\\\":\\\"Rotate failed: \\\" + exRot.Message}}"; }}
}}

return "{{\\\"success\\\":true,\\\"elementId\\\":\\\" + (inst?.Id.Value ?? 0) + "\\\",\\\"uniqueId\\\":\\\"\\\" + (inst?.UniqueId ?? \"\") + \"\\\",\\\"hostId\\\":\" + hId + ",\\\"usedFace\\\":true,\\\"placementMethod\\\":\\\"wall_face_based\\\"}}";
'''

device_json = json.dumps({"F":fam,"T":tip,"X":x_mm,"Y":y_mm,"Z":z_mm,"R":rot,"A":alt_mm,"L":lvl,"W":wall_id,"PX":proj_x,"PY":proj_y,"D":"A4"}, separators=(",", ":"))
device_json_escaped = device_json.replace('"', '""')
code_full = 'string deviceJson = @"' + device_json_escaped + '";\n' + code

import json as json_lib
payload = {"jsonrpc": "2.0", "method": "send_code_to_revit", "params": {"code": code_full}, "id": 1}
data = json_lib.dumps(payload, separators=(",", ":")) + "\n"

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(60)
sock.connect((MCP_HOST, MCP_PORT))
sock.sendall(data.encode("utf-8"))
response = b""
while True:
    chunk = sock.recv(8192)
    if not chunk: break
    response += chunk
    try:
        json_lib.loads(response.decode("utf-8"))
        break
    except json_lib.JSONDecodeError:
        continue
sock.close()

r = json_lib.loads(response.decode("utf-8"))
print(json_lib.dumps(r, indent=2))