import json
import socket

# Test simple: crear una toma simple
code = r'''
var doc = document;
var sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == "M_Toma doble" && s.Name == "Normal");
if (sym == null) return "{\"success\":false,\"error\":\"Symbol not found\"}";
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
var lvl = doc.GetElement(new ElementId(192512)) as Level;
XYZ pt = new XYZ(10487.1/304.8, 1541.1/304.8, (13220+300)/304.8);
// Try level-based first (simpler)
var inst = doc.Create.NewFamilyInstance(pt, sym, lvl, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
return "{\"success\":true,\"id\":" + (inst?.Id.Value ?? 0) + "}";
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
print(json.dumps(r, indent=2))