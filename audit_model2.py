import json
import socket

code = r'''
var doc = document;
// Buscar SOLO nuestros elementos por ID conocido de las últimas corridas
var targetIds = new List<int> { 
    5552880, 5552884, 5552892, 5552963, 5552978, 5552980, 5553007,
    5553081, 5553085, 5553087, 5553091, 5553093, 5553095, 5553097,
    5553101, 5553104, 5553105, 5553106, 5553107, 5553108, 5553109,
    5553111, 5553113, 5553115, 5553116, 5553118, 5553121, 5553124,
    5553127, 5553141, 5553144, 5553147, 5553149, 5553151, 5553153,
    5553157, 5553159, 5553161, 5553163, 5553165, 5553167, 5553167
};

var results = new List<object>();
foreach (int id in targetIds) {
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
            levelElev = level != null ? Math.Round(level.Elevation * 304.8, 1) : 0,
            locX = loc != null ? Math.Round(loc.Point.X * 304.8, 1) : 0,
            locY = loc != null ? Math.Round(loc.Point.Y * 304.8, 1) : 0,
            locZ = loc != null ? Math.Round(loc.Point.Z * 304.8, 1) : 0,
            host = host != null ? host.Id.Value : 0,
            hostType = host?.GetType().Name ?? "null",
            facingZ = fi?.FacingOrientation != null ? Math.Round(fi.FacingOrientation.Z, 2) : 0,
            handZ = fi?.HandOrientation != null ? Math.Round(fi.HandOrientation.Z, 2) : 0
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
sock.settimeout(20)
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

print(f"Total consultados: {len(final)}")
print()
for item in final:
    if 'error' not in item:
        print(f"ID {item['id']:>7} | {item['family']:<25} | {item['type']:<15} | Level: {item['level']:<6} | XYZ=({item['locX']:>8.1f}, {item['locY']:>8.1f}, {item['locZ']:>8.1f}) | Host: {item['host']} ({item['hostType']}) | FacingZ: {item['facingZ']}")
    else:
        print(f"ID {item['id']:>7} | {item['error']}")