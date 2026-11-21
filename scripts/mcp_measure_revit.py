import json
import socket

csharp_code = """
// Obtener todos los paneles y sus posiciones, y calcular bounding box del modelo
var results = new System.Collections.Generic.List<string>();
var panels = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType().ToElements();

double minX = double.MaxValue, minY = double.MaxValue, minZ = double.MaxValue;
double maxX = double.MinValue, maxY = double.MinValue, maxZ = double.MinValue;

foreach (var elem in panels) {
    var fi = elem as FamilyInstance;
    if (fi == null) continue;
    var loc = fi.Location as LocationPoint;
    if (loc == null) continue;
    var pt = loc.Point;
    minX = Math.Min(minX, pt.X); minY = Math.Min(minY, pt.Y); minZ = Math.Min(minZ, pt.Z);
    maxX = Math.Max(maxX, pt.X); maxY = Math.Max(maxY, pt.Y); maxZ = Math.Max(maxZ, pt.Z);
}

results.Add(string.Format("MODEL_BOUNDS: min=({0:F3},{1:F3},{2:F3}) max=({3:F3},{4:F3},{5:F3})", minX, minY, minZ, maxX, maxY, maxZ));

// NE corner = maxX, maxY
// Paneles de Piso 5 (Z ~ 47.3 ft)
foreach (var elem in panels) {
    var fi = elem as FamilyInstance;
    if (fi == null) continue;
    var loc = fi.Location as LocationPoint;
    if (loc == null) continue;
    var pt = loc.Point;
    if (Math.Abs(pt.Z - 47.3) < 1.0) {
        string pname = "";
        var param = fi.LookupParameter("Panel Name");
        if (param != null && param.HasValue) pname = param.AsString() ?? "";
        
        double dx = maxX - pt.X;
        double dy = maxY - pt.Y;
        results.Add(string.Format("PANEL: {0} pos=({1:F3},{2:F3}) from_NE=({3:F3},{4:F3})", pname, pt.X, pt.Y, dx, dy));
    }
}

return string.Join("\n", results);
"""

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