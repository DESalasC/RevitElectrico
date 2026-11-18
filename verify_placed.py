#!/usr/bin/env python3
import socket, json

code = r'''
var doc = document;
var collector = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalFixtures).WhereElementIsNotElementType();
var dispositivos = new List<object>();
foreach (var elem in collector) {
    var fi = elem as FamilyInstance;
    if (fi == null) continue;
    var loc = fi.Location as LocationPoint;
    if (loc == null) continue;
    var pt = loc.Point;
    dispositivos.Add(new { id = (int)fi.Id.Value, family = fi.Symbol.Family.Name, type = fi.Symbol.Name, x = Math.Round(pt.X * 304.8, 1), y = Math.Round(pt.Y * 304.8, 1), z = Math.Round(pt.Z * 304.8, 1), levelId = fi.LevelId.Value });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(dispositivos);
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
    try:
        json.loads(response.decode('utf-8'))
        break
    except:
        continue
resp = json.loads(response.decode('utf-8'))
result = resp.get('result', {}).get('result', '')
if isinstance(result, str):
    dispositivos = json.loads(json.loads(result))
    nuevos = [d for d in dispositivos if d['id'] >= 5551670]
    print('Recién colocados:', len(nuevos))
    for d in nuevos[:20]:
        print('ID={id} {family}|{type} X={x:.1f} Y={y:.1f} Z={z:.1f} LevelId={levelId}'.format(**d))
sock.close()