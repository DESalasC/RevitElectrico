import json
import socket

payload = {'jsonrpc': '2.0', 'method': 'send_code_to_revit', 'params': {'code': 'return "OK";'}, 'id': 1}
data = json.dumps(payload, separators=(',', ':')) + '\n'

s = socket.socket()
s.settimeout(5)
s.connect(('127.0.0.1', 8080))
s.sendall(data.encode())
r = b''
while True:
    c = s.recv(8192)
    if not c:
        break
    r += c
    try:
        json.loads(r.decode())
        break
    except:
        continue
s.close()
print(json.loads(r.decode()))