import json
import socket

code = r'''
var doc = document;
var collector = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Ceilings)
    .WhereElementIsNotElementType();

var results = new List<object>();
foreach (var elem in collector) {
    var c = elem as Ceiling;
    if (c == null) continue;
    var bb = c.get_BoundingBox(null);
    if (bb == null) continue;
    double midX = (bb.Min.X + bb.Max.X) / 2 * 304.8;
    double midY = (bb.Min.Y + bb.Max.Y) / 2 * 304.8;
    double midZ = (bb.Min.Z + bb.Max.Z) / 2 * 304.8;
    if (midX > 10000 && midX < 15000 && midY > 4000 && midY < 8000) {
        results.Add(new {
            id = (int)c.Id.Value,
            midX = Math.Round(midX, 1),
            midY = Math.Round(midY, 1),
            midZ = Math.Round(midZ, 1),
            levelId = c.LevelId?.Value ?? 0,
            area = Math.Round((bb.Max.X - bb.Min.X) * (bb.Max.Y - bb.Min.Y) * 304.8 * 304.8, 1)
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

print(f"Techos en zona F01: {len(final)}")
for t in final[:20]:
    print(f"  ID {t['id']} | mid=({t['midX']:.1f}, {t['midY']:.1f}) Z={t['midZ']:.1f} level={t['levelId']} area={t['area']:.1f}")