import json
import socket

code = r'''
var doc = document;
var lvl = doc.GetElement(new ElementId(192512)) as Level;
if (lvl != null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { 
        name = lvl.Name, 
        elevation = Math.Round(lvl.Elevation * 304.8, 1), 
        id = lvl.Id.Value 
    });
}
return "Level not found";
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
print(json.dumps(r, indent=2))