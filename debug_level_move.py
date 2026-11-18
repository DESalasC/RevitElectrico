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

# 1. Test level-based con MoveElement - debug
code = r'''
var doc=document;
var s=new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(x=>x.Family.Name=="M_Interruptores"&&x.Name=="Simple");
if(s==null)return"{\"s\":false,\"e\":\"Sym: \"+s?.Family?.Name+\" / \"+s?.Name}";
if(!s.IsActive){s.Activate();doc.Regenerate();}
var lv=doc.GetElement(new ElementId(192512)) as Level;
var pt=new XYZ(12830.6/304.8,7948.2/304.8,1100/304.8);
var ins=doc.Create.NewFamilyInstance(pt,s,lv,Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
var lc1=ins.Location as LocationPoint;var p1=lc1?.Point;
var mv=new XYZ(pt.X-p1.X,pt.Y-p1.Y,0);ElementTransformUtils.MoveElement(doc,ins.Id,mv);
var lc2=ins.Location as LocationPoint;var p2=lc2?.Point;
return"{\"s\":true,\"id\":"+ins.Id.Value+",\"before\":\""+p1+"\",\"after\":\""+p2+"\",\"move\":\""+mv+"\"}";
'''
r = mcp_send_code(code, 30)
raw = r["result"]["result"]
if isinstance(raw, str):
    inner = json.loads(raw)
    if isinstance(inner, str): inner = json.loads(inner)
print("Level-based test:")
print(json.dumps(inner, indent=2))