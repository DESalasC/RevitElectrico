import json
import socket

code = r'''
var doc = document;
var collector = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Walls)
    .WhereElementIsNotElementType();

var results = new List<object>();
foreach (var elem in collector) {
    var w = elem as Wall;
    if (w == null) continue;
    var loc = w.Location as LocationCurve;
    if (loc == null) continue;
    var c = loc.Curve;
    var p0 = c.GetEndPoint(0);
    var p1 = c.GetEndPoint(1);
    double midX = (p0.X + p1.X) / 2 * 304.8;
    double midY = (p0.Y + p1.Y) / 2 * 304.8;
    double len = c.Length * 304.8;
    if (len > 1000 && midX > 10000 && midX < 15000 && midY > 4000 && midY < 8000) {
        results.Add(new {
            id = (int)w.Id.Value,
            midX = Math.Round(midX, 1),
            midY = Math.Round(midY, 1),
            len = Math.Round(len, 1),
            levelId = w.LevelId?.Value ?? 0
        });
    }
}
return Newtonsoft.Json.JsonConvert.SerializeObject(results);
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
raw = r['result']['result']
if isinstance(raw, str):
    inner = json.loads(raw)
    if isinstance(inner, str):
        final = json.loads(inner)
    else:
        final = inner
else:
    final = raw

print(f"Muros en zona F01 (10000-15000, 4000-8000): {len(final)}")
for w in final[:20]:
    print(f"  ID {w['id']} | mid=({w['midX']:.1f}, {w['midY']:.1f}) len={w['len']:.1f} level={w['levelId']}")