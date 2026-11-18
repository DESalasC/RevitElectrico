#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test unitario minimalista: 5 dispositivos con C# compacto y correcto.
"""

import json
import socket
import sys
from pathlib import Path

MCP_HOST = "127.0.0.1"
MCP_PORT = 8080
REVITELECTRICO_ROOT = Path(r"D:\Work\PROJECTS\RevitElectrico")
DATA_DIR = REVITELECTRICO_ROOT / "data"
ARCHIVOS_BASE_DIR = REVITELECTRICO_ROOT / "ArchivosBase"

# SOLO estas 2 familias son WorkPlaneBased (face-based)
FAMILIAS_MURO_FACE = {"M_Toma doble", "M_Comunicaciones"}

# 5 dispositivos de prueba - COORDENADAS REALES DEL INVENTARIO F01
TEST_DEVICES = [
    {"handle": "63", "familia": "M_Toma doble", "tipo": "GFCI", "rot": 270, "altura_mm": 300, "x_m": -3.5038, "y_m": -6.4695, "expected_method": "wall_face_based"},
    {"handle": "125", "familia": "M_Iluminacion", "tipo": "SONO FLEX 22 trim", "rot": 180, "altura_mm": 2600, "x_m": -1.2549, "y_m": -2.1202, "expected_method": "level_based"},
    {"handle": "AF", "familia": "M_Interruptores", "tipo": "Simple", "rot": 90, "altura_mm": 1100, "x_m": -1.1603, "y_m": -0.0624, "expected_method": "level_based"},
    {"handle": "C1", "familia": "M_ClimatizacionV", "tipo": "Ventilador", "rot": 120, "altura_mm": 2600, "x_m": -1.9745, "y_m": -4.7342, "expected_method": "level_based"},
    {"handle": "CA", "familia": "M_Climatizacion", "tipo": "Interruptor Ventilador", "rot": 180, "altura_mm": 1100, "x_m": -2.2193, "y_m": -2.9997, "expected_method": "level_based"},
]

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

def mcp_send_code(code: str, timeout: float = 30.0) -> dict:
    return mcp_send("send_code_to_revit", {"code": code}, timeout)

def parse_mcp(resp: dict):
    raw = resp.get("result", {}).get("result")
    if raw is None: return {"success": False, "error": "No result"}
    if isinstance(raw, str):
        try:
            inner = json.loads(raw)
            if isinstance(inner, str): return json.loads(inner)
            return inner
        except: return {"success": False, "error": f"Parse: {raw[:100]}"}
    return raw

# Get data - FIXED: cast Location to LocationPoint
CS_GET_PANELS = 'var doc=document;var c=new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalEquipment).WhereElementIsNotElementType();var l=new List<object>();foreach(var e in c){var f=e as FamilyInstance;if(f==null)continue;var lp=f.Location as LocationPoint;if(lp==null)continue;var p=f.LookupParameter("Panel Name");l.Add(new{id=(int)f.Id.Value,panelName=p?.AsString()??"",x=Math.Round(lp.Point.X*304.8,1),y=Math.Round(lp.Point.Y*304.8,1),levelId=f.LevelId?.Value??0});}return Newtonsoft.Json.JsonConvert.SerializeObject(l);'

CS_GET_WALLS = 'var doc=document;var c=new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType();var l=new List<object>();foreach(var e in c){var w=e as Wall;if(w==null)continue;var lc=w.Location as LocationCurve;if(lc==null)continue;var p0=lc.Curve.GetEndPoint(0);var p1=lc.Curve.GetEndPoint(1);l.Add(new{id=(int)w.Id.Value,x1=Math.Round(p0.X*304.8,1),y1=Math.Round(p0.Y*304.8,1),x2=Math.Round(p1.X*304.8,1),y2=Math.Round(p1.Y*304.8,1),levelId=w.LevelId?.Value??0});}return Newtonsoft.Json.JsonConvert.SerializeObject(l);'

CS_GET_CEILINGS = 'var doc=document;var c=new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType();var l=new List<object>();foreach(var e in c){var cl=e as Ceiling;if(cl==null)continue;var bb=cl.get_BoundingBox(null);if(bb==null)continue;l.Add(new{id=(int)cl.Id.Value,xmin=Math.Round(bb.Min.X*304.8,1),ymin=Math.Round(bb.Min.Y*304.8,1),xmax=Math.Round(bb.Max.X*304.8,1),ymax=Math.Round(bb.Max.Y*304.8,1),levelId=cl.LevelId?.Value??0});}return Newtonsoft.Json.JsonConvert.SerializeObject(l);'

# Face-based WALL - compact
CS_FACE_WALL = r'''
var doc=document;var j=Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string f=j["F"]?.ToString();string t=j["T"]?.ToString();
double x=(double)j["X"];double y=(double)j["Y"];double z=(double)j["Z"];double r=(double)j["R"];int l=(int)j["L"];int w=(int)j["W"];double px=(double)j["PX"];double py=(double)j["PY"];
var s=new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(x=>x.Family.Name==f&&x.Name==t);
if(s==null)return"{\"s\":false,\"e\":\"Sym\"}";if(!s.IsActive){s.Activate();doc.Regenerate();}
var lv=doc.GetElement(new ElementId(l)) as Level;if(lv==null)return"{\"s\":false,\"e\":\"Lvl\"}";
var pt=new XYZ(x/304.8,y/304.8,z/304.8);var wl=doc.GetElement(new ElementId(w)) as Wall;if(wl==null)return"{\"s\":false,\"e\":\"Wall\"}";
var op=new Options{ComputeReferences=true,DetailLevel=ViewDetailLevel.Fine};var gm=wl.get_Geometry(op);Reference rf=null;Face ff=null;
if(gm!=null)foreach(var o in gm){if(!(o is Solid))continue;foreach(Face fc in (o as Solid).Faces){try{var p=fc.Project(pt);if(p!=null&&p.XYZPoint!=null){var uv=p.UVPoint;var bb=fc.GetBoundingBox();if(bb.Min.U<=uv.U&&uv.U<=bb.Max.U&&bb.Min.V<=uv.V&&uv.V<=bb.Max.V){var n=fc.ComputeNormal(uv);if(Math.Abs(n.Z)<0.1){rf=fc.Reference;ff=fc;break;}}}}catch{}if(rf!=null)break;}if(rf!=null)break;}
if(rf==null)return"{\"s\":false,\"e\":\"NoFace\"}";var pf=ff.Project(pt);if(pf==null)return"{\"s\":false,\"e\":\"Proj\"}";var fpt=pf.XYZPoint;
double wb=0;var bp=wl.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)??wl.get_Parameter(BuiltInParameter.LEVEL_PARAM);
if(bp!=null&&bp.HasValue){var id=bp.AsElementId();if(id!=ElementId.InvalidElementId){var bl=doc.GetElement(id) as Level;if(bl!=null)wb=bl.Elevation;}}
var pl=new XYZ(fpt.X,fpt.Y,(z/304.8)-wb);var ins=doc.Create.NewFamilyInstance(rf,pl,XYZ.BasisZ,s);
if(r!=0){var rd=(r+90)*Math.PI/180;var lc=ins.Location as LocationPoint;if(lc!=null){var ax=Line.CreateBound(pl,new XYZ(pl.X,pl.Y,pl.Z+1));lc.Rotate(ax,rd);}}
return"{\"s\":true,\"id\":"+ins.Id.Value+",\"hid\":"+wl.Id.Value+",\"m\":\"wall_face\"}";
'''

# Level-based - compact
CS_LEVEL = r'''
var doc=document;var j=Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string f=j["F"]?.ToString();string t=j["T"]?.ToString();
double x=(double)j["X"];double y=(double)j["Y"];double z=(double)j["Z"];double r=(double)j["R"];double a=(double)j["A"];int l=(int)j["L"];
var s=new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(x=>x.Family.Name==f&&x.Name==t);
if(s==null)return"{\"s\":false,\"e\":\"Sym\"}";if(!s.IsActive){s.Activate();doc.Regenerate();}
var lv=doc.GetElement(new ElementId(l)) as Level;if(lv==null)return"{\"s\":false,\"e\":\"Lvl\"}";
var pt=new XYZ(x/304.8,y/304.8,z/304.8);
var ins=doc.Create.NewFamilyInstance(pt,s,lv,Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
var lc=ins.Location as LocationPoint;if(lc!=null){var mv=new XYZ(pt.X-lc.Point.X,pt.Y-lc.Point.Y,0);if(mv.GetLength()>0.001)ElementTransformUtils.MoveElement(doc,ins.Id,mv);}
if(r!=0){var rd=r*Math.PI/180;foreach(Parameter p in ins.Parameters){var n=p.Definition.Name;if(n=="Rotation"||n=="Angle"){if(!p.IsReadOnly){p.Set(rd);break;}}}}
if(a>0){foreach(Parameter p in ins.Parameters){var n=p.Definition.Name;if(n=="Elevation"||n=="Offset"){if(!p.IsReadOnly){p.Set(a/304.8);break;}}}}
return"{\"s\":true,\"id\":"+ins.Id.Value+",\"hid\":0,\"m\":\"level\"}";
'''

def find_wall(muros, x, y, lvl):
    best=None;bd=610;bp=(0,0)
    for m in muros:
        if m.get("levelId")!=lvl:continue
        x1,y1,x2,y2=m["x1"],m["y1"],m["x2"],m["y2"]
        dx,dy=x2-x1,y2-y1;ls=dx*dx+dy*dy
        if ls<1e-6:continue
        t=max(0,min(1,((x-x1)*dx+(y-y1)*dy)/ls))
        nx,ny=x1+t*dx,y1+t*dy;d=((x-nx)**2+(y-ny)**2)**0.5
        if d<bd:bd=d;best=m;bp=(nx,ny)
    return best,bp

def find_ceil(techos, x, y):
    best=None;ba=float("inf")
    for t in techos:
        if x<t["xmin"]or x>t["xmax"]or y<t["ymin"]or y>t["ymax"]:continue
        ar=(t["xmax"]-t["xmin"])*(t["ymax"]-t["ymin"])
        if ar<ba:ba=ar;best=t
    return best

def main():
    inv=json.load(open(DATA_DIR/"inventarios"/"inventario_dispositivos_F01_v1.1_20261117_190929.json"))
    meta=inv["metadatos"];dxf=meta["origen_dxf"]["archivo"]
    
    # Panels
    print("Obteniendo paneles...")
    r=mcp_send_code(CS_GET_PANELS,120)
    print("Response:", json.dumps(r, indent=2)[:500])
    p=json.loads(json.loads(r["result"]["result"]))
    po=next(x for x in p if x.get("panelName")=="TF 01")
    print(f"Panel: {po['panelName']} @ ({po['x']:.1f},{po['y']:.1f}) Lvl={po['levelId']}")
    
    # Offset
    import ezdxf
    d=ezdxf.readfile(str(ARCHIVOS_BASE_DIR/dxf))
    pd=None
    for e in d.modelspace():
        if e.dxftype()=='INSERT' and e.dxf.name in('TB-Panel','TB-Parcial'):
            for a in e.attribs:
                if a.dxf.tag.upper()=='TABLERO' and a.dxf.text.strip()=="TF 01":
                    pd=(float(e.dxf.insert.x),float(e.dxf.insert.y));break
    ox,oy=po['x']-pd[0]*1000,po['y']-pd[1]*1000
    print(f"Offset: ({ox:.1f},{oy:.1f})")
    
    lvl=po["levelId"];niv=meta["nivel_elevacion_m"]
    
    # Walls & Ceilings
    muros=json.loads(json.loads(mcp_send_code(CS_GET_WALLS,180)["result"]["result"]))
    techos=json.loads(json.loads(mcp_send_code(CS_GET_CEILINGS,120)["result"]["result"]))
    print(f"Muros:{len(muros)} Techos:{len(techos)}")
    
    print("\n=== TEST 5 DISPOSITIVOS ===")
    ok=0
    for d in TEST_DEVICES:
        x=d["x_m"]*1000+ox;y=d["y_m"]*1000+oy
        fam=d["familia"];tip=d["tipo"];rot=d["rot"];alt=d["altura_mm"]
        z_abs=(niv+alt/1000)*1000;z_rel=alt
        
        print(f"\n{d['handle']} {fam}/{tip} -> ({x:.0f},{y:.0f})")
        
        if fam in FAMILIAS_MURO_FACE:
            w,proj=find_wall(muros,x,y,lvl)
            if not w:print("  No wall -> level");cs=CS_LEVEL;z=z_rel
            else:
                cs=CS_FACE_WALL;z=z_abs;j={"F":fam,"T":tip,"X":x,"Y":y,"Z":z,"R":rot,"W":w["id"],"PX":proj[0],"PY":proj[1],"L":lvl}
        else:
            cs=CS_LEVEL;z=z_rel;j={"F":fam,"T":tip,"X":x,"Y":y,"Z":z,"R":rot,"A":alt,"L":lvl}
        
        dj=json.dumps(j,separators=(",",":")).replace('"','""')
        code='string deviceJson=@"'+dj+'";\n'+cs
        r=parse_mcp(mcp_send_code(code,30))
        
        if r.get("s") or r.get("success"):
            eid=r.get("id") or r.get("elementId")
            hid=r.get("hid") or r.get("hostId",0)
            meth=r.get("m") or r.get("placementMethod","")
            # Verify
            vr=parse_mcp(mcp_send_code(f'var d=document.GetElement(new ElementId({eid}));var f=d as FamilyInstance;var l=f?.Location as LocationPoint;return Newtonsoft.Json.JsonConvert.SerializeObject(new{{x=l?Math.Round(l.Point.X*304.8,1):0,y=l?Math.Round(l.Point.Y*304.8,1):0,z=l?Math.Round(l.Point.Z*304.8,1):0,h=f?.Host?.Id?.Value??0}});',10))
            vx,vy,vz,vh=vr.get("x",0),vr.get("y",0),vr.get("z",0),vr.get("h",0)
            dx=abs(vx-x);dy=abs(vy-y);pos=dx<=50 and dy<=50;host=(vh>0)==(fam in FAMILIAS_MURO_FACE)
            status="✓" if pos and host else "⚠"
            print(f"  {status} id={eid} pos=({vx:.0f},{vy:.0f},{vz:.0f}) host={vh} meth={meth} d=({dx:.0f},{dy:.0f})")
            if pos and host:ok+=1
        else:
            print(f"  ✗ {r.get('e') or r.get('error')}")
    
    print(f"\n=== RESULT: {ok}/5 OK ===")
    return 0 if ok==5 else 1

if __name__=="__main__":sys.exit(main())