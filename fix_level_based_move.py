with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '''# Level-based fallback
CS_LEVEL_BASED = r"""
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; string devId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);

FamilyInstance inst = doc.Create.NewFamilyInstance(pt, sym, lvl, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
if (inst == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Create failed" });

if (rot != 0) { double rad = rot * Math.PI / 180; foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Rotation"||n=="Angle") { if(!p.IsReadOnly){p.Set(rad);break;} } } }
if (altMM > 0) { foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Elevation"||n=="Offset") { if(!p.IsReadOnly){p.Set(altMM/304.8);break;} } } }

return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = true, elementId = (inst?.Id.Value ?? 0), uniqueId = (inst?.UniqueId ?? ""), hostId = 0, usedFace = false, placementMethod = "level_based" });
}"""'''

new = '''# Level-based fallback - FIX: NewFamilyInstance ignora X,Y, usar ElementTransformUtils.MoveElement
CS_LEVEL_BASED = r"""
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; string devId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);

FamilyInstance inst = doc.Create.NewFamilyInstance(pt, sym, lvl, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
if (inst == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Create failed" });

// FIX: NewFamilyInstance con Level ignora X,Y del point -> mover manualmente
var loc = inst.Location as LocationPoint;
if (loc != null) {
    XYZ currentPt = loc.Point;
    XYZ moveVec = new XYZ(pt.X - currentPt.X, pt.Y - currentPt.Y, 0);
    if (moveVec.GetLength() > 0.001) {
        ElementTransformUtils.MoveElement(doc, inst.Id, moveVec);
    }
}

// Rotación y elevación via parámetros
if (rot != 0) { double rad = rot * Math.PI / 180; foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Rotation"||n=="Angle") { if(!p.IsReadOnly){p.Set(rad);break;} } } }
if (altMM > 0) { foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Elevation"||n=="Offset") { if(!p.IsReadOnly){p.Set(altMM/304.8);break;} } } }

return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = true, elementId = (inst?.Id.Value ?? 0), uniqueId = (inst?.UniqueId ?? ""), hostId = 0, usedFace = false, placementMethod = "level_based" });
}"""'''

content = content.replace(old, new)

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed CS_LEVEL_BASED with ElementTransformUtils.MoveElement")