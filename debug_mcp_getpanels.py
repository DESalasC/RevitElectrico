import json
import socket

MCP_HOST = "127.0.0.1"
MCP_PORT = 8080

def mcp_send(method: str, params: dict = None, timeout: float = 10.0) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    data = json.dumps(payload, separators=(",", ":")) + "\n"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((MCP_HOST, MCP_PORT))
        sock.sendall(data.encode("utf-8"))
        response = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk: break
            response += chunk
            try: json.loads(response.decode("utf-8")); break
            except: continue
        return json.loads(response.decode("utf-8"))
    finally: sock.close()

CS_GET_PANELS = 'var doc=document;var c=new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType();var l=new List<object>();foreach(var e in c){var f=e as FamilyInstance;if(f==null)continue;var p=f.LookupParameter("Panel Name");l.Add(new{id=(int)f.Id.Value,panelName=p?.AsString()??"",x=Math.Round(f.Location.Point.X*304.8,1),y=Math.Round(f.Location.Point.Y*304.8,1),levelId=f.LevelId?.Value??0});}return Newtonsoft.Json.JsonConvert.SerializeObject(l);'

r = mcp_send("send_code_to_revit", {"code": CS_GET_PANELS}, 120)
print(json.dumps(r, indent=2))