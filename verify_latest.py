import json
import socket

code = r'''
var doc = document;
var ids = new List<int> { 5552863, 5552865, 5552875, 5552878, 5552880, 5552884, 5552892, 5552894, 5552900 };
var result = new List<object>();
foreach (int id in ids) {
    var elem = doc.GetElement(new ElementId(id));
    if (elem != null) {
        var fi = elem as FamilyInstance;
        var loc = fi?.Location as LocationPoint;
        var level = fi?.LevelId != null ? doc.GetElement(fi.LevelId) as Level : null;
        var host = fi?.Host != null ? fi.Host : null;
        result.Add(new {
            id = id,
            name = fi?.Symbol?.Family?.Name + " " + fi?.Symbol?.Name,
            level = level?.Name,
            levelElev = level != null ? Math.Round(level.Elevation * 304.8, 1) : 0,
            locZ = loc != null ? Math.Round(loc.Point.Z * 304.8, 1) : 0,
            locX = loc != null ? Math.Round(loc.Point.X * 304.8, 1) : 0,
            locY = loc != null ? Math.Round(loc.Point.Y * 304.8, 1) : 0,
            host = host != null ? host.Id.Value : 0,
            hostType = host?.GetType().Name,
            facing = fi?.FacingOrientation != null ? "Z=" + Math.Round(fi.FacingOrientation.Z, 2) : "null",
            hand = fi?.HandOrientation != null ? "Z=" + Math.Round(fi.HandOrientation.Z, 2) : "null"
        });
    } else {
        result.Add(new { id = id, error = "Not found" });
    }
}
return Newtonsoft.Json.JsonConvert.SerializeObject(result);
'''

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code}, 'id': 1}
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
# The result is double-encoded, need to parse twice
raw = r['result']['result']
if isinstance(raw, str):
    inner = json.loads(raw)
    if isinstance(inner, str):
        final = json.loads(inner)
    else:
        final = inner
else:
    final = raw

for item in final:
    print(json.dumps(item, indent=2, ensure_ascii=False))