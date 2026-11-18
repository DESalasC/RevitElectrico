import json
import socket

code = r'''
var doc = document;
var ids = new int[] { 5552880, 5552884, 5552892 };
var results = new List<object>();
foreach (int id in ids) {
    var elem = doc.GetElement(new ElementId(id));
    if (elem != null) {
        var fi = elem as FamilyInstance;
        var loc = fi?.Location as LocationPoint;
        var level = fi?.LevelId != null ? doc.GetElement(fi.LevelId) as Level : null;
        var host = fi?.Host != null ? fi.Host : null;
        results.Add(new {
            id = id,
            family = fi?.Symbol?.Family?.Name ?? "",
            type = fi?.Symbol?.Name ?? "",
            level = level?.Name ?? "null",
            locX = loc != null ? Math.Round(loc.Point.X * 304.8, 1) : 0,
            locY = loc != null ? Math.Round(loc.Point.Y * 304.8, 1) : 0,
            locZ = loc != null ? Math.Round(loc.Point.Z * 304.8, 1) : 0,
            host = host != null ? host.Id.Value : 0,
            hostType = host?.GetType().Name ?? "null"
        });
    } else {
        results.Add(new { id = id, error = "Not found" });
    }
}
return Newtonsoft.Json.JsonConvert.SerializeObject(results);
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