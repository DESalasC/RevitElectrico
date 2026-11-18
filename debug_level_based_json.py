import json
import socket

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

// DEBUG: return the parsed values
return Newtonsoft.Json.JsonConvert.SerializeObject(new { 
    success = true, 
    parsedX_mm = x, 
    parsedY_mm = y, 
    parsedZ_mm = z,
    ptX_ft = pt.X,
    ptY_ft = pt.Y,
    ptZ_ft = pt.Z,
    levelElev_ft = lvl.Elevation
});
'''

# Device A4 ELEC-I-S-2-5A
device_json = json.dumps({"F":"M_Interruptores","T":"Doble","X":11760.6,"Y":5193.5,"Z":1100,"R":240,"A":1100,"L":192512,"D":"A4"}, separators=(",", ":"))
device_json_escaped = device_json.replace('"', '""')
code_full = 'string deviceJson = @"' + device_json_escaped + '";\n' + code

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code_full}, 'id': 1}
data = json.dumps(payload, separators=(',', ':')) + '\n'

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(15)
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
raw = r['result']['result']
if isinstance(raw, str):
    inner = json.loads(raw)
    if isinstance(inner, str):
        final = json.loads(inner)
    else:
        final = inner
else:
    final = raw

print(json.dumps(final, indent=2, ensure_ascii=False))