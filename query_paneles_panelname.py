#!/usr/bin/env python3
import socket, json

code = r'''
var doc = document;
var collector = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
    .WhereElementIsNotElementType();

var paneles = new List<object>();
foreach (var elem in collector) {
    var fi = elem as FamilyInstance;
    if (fi == null) continue;
    var name = fi.Symbol?.Family?.Name ?? "";
    var typeName = fi.Symbol?.Name ?? "";
    var loc = fi.Location as LocationPoint;
    if (loc == null) continue;
    var pt = loc.Point;
    
    // Leer parámetro "Panel Name"
    string panelName = "";
    var param = fi.LookupParameter("Panel Name");
    if (param != null && param.HasValue) {
        panelName = param.AsString() ?? "";
    }
    
    paneles.Add(new {
        id = (int)fi.Id.Value,
        uniqueId = fi.UniqueId,
        family = name,
        type = typeName,
        panelName = panelName,
        x = Math.Round(pt.X * 304.8, 1),
        y = Math.Round(pt.Y * 304.8, 1),
        z = Math.Round(pt.Z * 304.8, 1),
        levelId = fi.LevelId?.Value ?? 0
    });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(paneles);
'''

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code}, 'id': 1}
data = json.dumps(payload, separators=(',', ':')) + '\n'

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(15)
try:
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
        except: continue
    resp = json.loads(response.decode('utf-8'))
    result = resp.get('result', {}).get('result', '')
    if isinstance(result, str):
        paneles = json.loads(json.loads(result))
        for p in paneles:
            if 'E_Panel' in p.get('family', ''):
                pn = p.get('panelName', '(sin Panel Name)')
                print(f"{p['family']} | {p['type']} | PanelName={pn} @ X={p['x']:.1f}, Y={p['y']:.1f}, Z={p['z']:.1f} mm | LevelId={p['levelId']} | Id={p['id']}")
finally:
    sock.close()