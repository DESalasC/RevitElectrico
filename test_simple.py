#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test C# face-based simple para un dispositivo
"""

import socket, json

# C# simplificado para test
code = r'''
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(@"{
    ""Familia"": ""M_Toma doble"",
    ""Tipo"": ""Normal"",
    ""X"": 10465.5,
    ""Y"": 1657.8,
    ""Z"": 13520,
    ""Rotacion"": 90,
    ""AlturaLocalMM"": 300,
    ""LevelId"": 192512,
    ""HostTipo"": ""Muro""
}");

string familia = j["Familia"]?.ToString();
string tipo = j["Tipo"]?.ToString();
double x = (double)j["X"];
double y = (double)j["Y"];
double z = (double)j["Z"];
double rotacion = (double)j["Rotacion"];
double alturaLocalMM = (double)j["AlturaLocalMM"];
int levelIdVal = (int)j["LevelId"];

FamilySymbol symbol = new FilteredElementCollector(doc)
    .OfClass(typeof(FamilySymbol))
    .Cast<FamilySymbol>()
    .FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);

if (symbol == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Familia no encontrada" });
}
if (!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }

Level level = doc.GetElement(new ElementId(levelIdVal)) as Level;
if (level == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Nivel no encontrado" });
}

XYZ point = new XYZ(x / 304.8, y / 304.8, z / 304.8);

// Level-based simple
FamilyInstance inst = doc.Create.NewFamilyInstance(point, symbol, level, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);

if (inst == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "No se pudo crear" });
}

if (rotacion != 0) {
    double rad = rotacion * Math.PI / 180.0;
    foreach (Parameter p in inst.Parameters) {
        string name = p.Definition.Name;
        if (name == "Rotation" || name == "Angle") {
            if (!p.IsReadOnly) { p.Set(rad); break; }
        }
    }
}

if (alturaLocalMM > 0) {
    foreach (Parameter p in inst.Parameters) {
        string name = p.Definition.Name;
        if (name == "Elevation" || name == "Offset") {
            if (!p.IsReadOnly) { p.Set(alturaLocalMM / 304.8); break; }
        }
    }
}

return Newtonsoft.Json.JsonConvert.SerializeObject(new {
    success = true,
    elementId = (int)inst.Id.Value,
    uniqueId = inst.UniqueId
});
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
    except: continue
resp = json.loads(response.decode('utf-8'))
print(resp)
sock.close()