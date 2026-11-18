import json
import socket

def mcp_send_code(code: str, timeout: float = 30.0) -> dict:
    payload = {"jsonrpc": "2.0", "method": "send_code_to_revit", "params": {"code": code}, "id": 1}
    data = json.dumps(payload, separators=(",", ":")) + "\n"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(("127.0.0.1", 8080))
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

# Test: Create at point, NO level param set, NO move
code = r'''
var doc=document;
var s=new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(x=>x.Family.Name=="M_Interruptores"&&x.Name=="Simple");
if(s==null)return"{\"s\":false}";if(!s.IsActive){s.Activate();doc.Regenerate();}
var pt=new XYZ(12830.6/304.8,7948.2/304.8,1100/304.8);
var ins=doc.Create.NewFamilyInstance(pt,s,Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
var lc=ins.Location as LocationPoint;
return"{\"s\":true,\"id\":"+ins.Id.Value+",\"loc\":\""+(lc?.Point)+"\"}";
'''
r = mcp_send_code(code, 30)
raw = r["result"]["result"]
if isinstance(raw, str):
    inner = json.loads(raw)
    if isinstance(inner, str): inner = json.loads(inner)
print(f"Created: {inner}")

eid = inner.get("id")

# Read back
code2 = f'''
var doc=document;
var d=doc.GetElement(new ElementId({eid}));
var f=d as FamilyInstance;
var l=f?.Location as LocationPoint;
double vx=0,vy=0,vz=0;
if(l!=null){{vx=Math.Round(l.Point.X*304.8,1);vy=Math.Round(l.Point.Y*304.8,1);vz=Math.Round(l.Point.Z*304.8,1);}}
return Newtonsoft.Json.JsonConvert.SerializeObject(new{{x=vx,y=vy,z=vz}});
'''
r2 = mcp_send_code(code2, 10)
raw2 = r2["result"]["result"]
if isinstance(raw2, str):
    inner2 = json.loads(raw2)
    if isinstance(inner2, str): inner2 = json.loads(inner2)
    print(f"Readback: {inner2}")
else:
    print(f"Raw2: {raw2}")