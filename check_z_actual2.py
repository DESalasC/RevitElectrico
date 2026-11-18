import json
import socket

code = r'''
var doc = document;
var inst = doc.GetElement(new ElementId(5552980)) as FamilyInstance;
var loc = inst.Location as LocationPoint;
var elevParam = inst.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM);
var levelParam = inst.get_Parameter(BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM);
return Newtonsoft.Json.JsonConvert.SerializeObject(new { 
    locZ_mm = Math.Round(loc.Point.Z * 304.8, 1),
    elevParam_mm = elevParam != null ? Math.Round(elevParam.AsDouble() * 304.8, 1) : 0,
    levelId = levelParam != null ? levelParam.AsElementId().Value : 0,
    name = inst.Symbol.Family.Name + " " + inst.Symbol.Name
});
'''

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code}, 'id': 1}
data = json.dumps(payload, separators=(',', ':')) + '\n'

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
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
inner = json.loads(r['result']['result'])
print(json.dumps(inner, indent=2))