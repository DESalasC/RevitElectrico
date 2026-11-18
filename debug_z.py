import json
import socket

# Test single device A4 (interruptor) with debug
code = r'''
var doc = document;
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

// Get actual location after placement
var loc = inst.Location as LocationPoint;
double actualZ = loc != null ? Math.Round(loc.Point.Z * 304.8, 1) : 0;

return Newtonsoft.Json.JsonConvert.SerializeObject(new { 
    success = true, 
    elementId = (int)inst.Id.Value, 
    uniqueId = inst.UniqueId, 
    hostId = 0, 
    usedFace = false, 
    placementMethod = "level_based",
    inputZ_mm = z,
    inputZ_ft = z/304.8,
    levelElevation_ft = lvl.Elevation,
    levelElevation_mm = Math.Round(lvl.Elevation * 304.8, 1),
    actualZ_mm = actualZ
});
'''

# Device A4: x=11760.6, y=5193.5, z=14320, rot=240, alt=1100, lvl=192512
device_json = json.dumps({"F":"M_Interruptores","T":"Doble","X":11760.6,"Y":5193.5,"Z":14320,"R":240,"A":1100,"L":192512,"D":"A4"}, separators=(",", ":"))
device_json_escaped = device_json.replace('"', '""')
code_full = 'string deviceJson = @"' + device_json_escaped + '";\n' + code

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code_full}, 'id': 1}
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