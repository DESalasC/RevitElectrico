#!/usr/bin/env python3
import socket, json

# Test simple level-based
code = r'''var doc = document;
var sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == "M_Toma doble" && s.Name == "Normal");
if (sym == null) return "{\"success\":false,\"error\":\"Symbol not found\"}";
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(192512)) as Level;
XYZ pt = new XYZ(10487/304.8, 1541/304.8, 13520/304.8);
FamilyInstance inst = doc.Create.NewFamilyInstance(pt, sym, lvl, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
return "{\"success\":true,\"elementId\":" + (inst?.Id.Value ?? 0) + ",\"uniqueId\":\"" + (inst?.UniqueId ?? "") + "\",\"hostId\":0,\"usedFace\":false}";'''

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
print('=== RESPUESTA COMPLETA ===')
print(json.dumps(r, indent=2))
print()
print('=== result.result ===')
print(repr(r['result']['result']))
print()
if isinstance(r['result']['result'], str):
    inner = json.loads(r['result']['result'])
    print('=== inner (parsed once) ===')
    print(repr(inner))
    if isinstance(inner, str):
        res = json.loads(inner)
        print('=== res (parsed twice) ===')
        print(res)