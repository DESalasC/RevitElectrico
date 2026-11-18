#!/usr/bin/env python3
import socket, json

# C# corregido - más simple y sin errores
code = r'''
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(@"{
    ""F"": ""M_Toma doble"",
    ""T"": ""Normal"",
    ""X"": 10465.5,
    ""Y"": 1657.8,
    ""Z"": 13520,
    ""R"": 90,
    ""A"": 300,
    ""L"": 192512,
    ""D"": ""test""
}");

string familia = j["F"]?.ToString();
string tipo = j["T"]?.ToString();
double x = (double)j["X"];
double y = (double)j["Y"];
double z = (double)j["Z"];
double rot = (double)j["R"];
double altMM = (double)j["A"];
int lvlId = (int)j["L"];
string deviceId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return "{\"success\":false,\"error\":\"Symbol not found\"}";
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return "{\"success\":false,\"error\":\"Level not found\"}";
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);

// Level-based simple (para test)
FamilyInstance inst = doc.Create.NewFamilyInstance(pt, sym, lvl, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
if (inst == null) return "{\"success\":false,\"error\":\"Create failed\"}";

if (rot != 0) { double rad = rot * Math.PI / 180; foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Rotation"||n=="Angle") { if(!p.IsReadOnly){p.Set(rad);break;} } } }
if (altMM > 0) { foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Elevation"||n=="Offset") { if(!p.IsReadOnly){p.Set(altMM/304.8);break;} } } }

return "{\"success\":true,\"elementId\":" + (inst?.Id.Value ?? 0) + ",\"uniqueId\":\"" + (inst?.UniqueId ?? "") + "\",\"hostId\":0,\"usedFace\":false}";
'''

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code}, 'id': 1}
data = json.dumps(payload, separators=(',', ':')) + '\n'

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(30)
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