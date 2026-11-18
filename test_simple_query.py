#!/usr/bin/env python3
import socket, json

code = r'var doc = document; return "Walls: " + new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().GetElementCount();'
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
print(json.loads(resp.decode('utf-8')))
sock.close()