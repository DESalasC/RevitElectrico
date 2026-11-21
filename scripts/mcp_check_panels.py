import json
import socket

csharp_code = '''
var results = new System.Collections.Generic.List<string>();
var panels = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType().ToElements();
foreach (var elem in panels) {
    var fi = elem as FamilyInstance;
    if (fi == null) continue;
    string pname = "";
    var param = fi.LookupParameter("Panel Name");
    if (param != null && param.HasValue) pname = param.AsString() ?? "";
    var loc = fi.Location as LocationPoint;
    string pos = loc != null ? string.Format("({0:F3},{1:F3},{2:F3})", loc.Point.X, loc.Point.Y, loc.Point.Z) : "null";
    results.Add(string.Format("Panel Name: '{0}' | Id: {1} | Pos: {2}", pname, fi.Id, pos));
}
return string.Join("\n", results);
'''

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': csharp_code}, 'id': 1}
data = json.dumps(payload, separators=(',', ':')) + '\n'

s = socket.socket()
s.settimeout(30)
s.connect(('127.0.0.1', 8080))
s.sendall(data.encode())

r = b''
while True:
    c = s.recv(8192)
    if not c: break
    r += c
    try:
        result = json.loads(r.decode())
        break
    except: continue

s.close()
response = json.loads(r.decode())
print(json.dumps(response, indent=2))