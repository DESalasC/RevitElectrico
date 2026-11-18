#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificar coordenadas reales de dispositivos colocados en F01/F02
"""

import socket, json

code = r'''
var doc = document;
var collector = new FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_ElectricalFixtures)
    .WhereElementIsNotElementType();

var dispositivos = new List<object>();
foreach (var elem in collector) {
    var fi = elem as FamilyInstance;
    if (fi == null) continue;
    var name = fi.Symbol?.Family?.Name ?? "";
    var typeName = fi.Symbol?.Name ?? "";
    var loc = fi.Location as LocationPoint;
    if (loc == null) continue;
    var pt = loc.Point;
    // Leer parámetro Elevation/Offset
    double elev = 0;
    var pElev = fi.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM);
    if (pElev != null && pElev.HasValue) elev = pElev.AsDouble();
    var pOffset = fi.get_Parameter(BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM);
    if (pOffset != null && pOffset.HasValue) elev = pOffset.AsDouble();
    
    dispositivos.Add(new {
        id = (int)fi.Id.Value,
        uniqueId = fi.UniqueId,
        family = name,
        type = typeName,
        x = Math.Round(pt.X * 304.8, 1),
        y = Math.Round(pt.Y * 304.8, 1),
        z = Math.Round(pt.Z * 304.8, 1),
        elevParam = Math.Round(elev * 304.8, 1),
        levelId = fi.LevelId?.Value ?? 0,
        levelElev = fi.Level != null ? Math.Round(fi.Level.Elevation * 304.8, 1) : 0
    });
}
return Newtonsoft.Json.JsonConvert.SerializeObject(dispositivos);
'''

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': code}, 'id': 1}
data = json.dumps(payload, separators=(',', ':')) + '\n'

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(30)
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
        dispositivos = json.loads(json.loads(result))
        print(f"Total dispositivos eléctricos: {len(dispositivos)}")
        # Filtrar los recién colocados (IDs > 5551670)
        nuevos = [d for d in dispositivos if d['id'] >= 5551670]
        print(f"Recién colocados (F01/F02): {len(nuevos)}")
        for d in nuevos[:10]:
            print(f"  ID={d['id']} {d['family']}|{d['type']} @ X={d['x']:.1f}, Y={d['y']:.1f}, Z={d['z']:.1f}mm | ElevParam={d['elevParam']:.1f}mm | LevelId={d['levelId']} LevelElev={d['levelElev']:.1f}mm")
        if len(nuevos) > 10:
            print(f"  ... y {len(nuevos)-10} más")
finally:
    sock.close()