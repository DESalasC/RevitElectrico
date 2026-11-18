with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

# ─── CS_FACE_WALL ───
CS_FACE_WALL = r'''var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);

// ═══════════════════════════════════════════════════════════════════════════
// SUPRIMIR DIÁLOGOS BLOQUEANTES: FailureHandlingOptions + DialogBoxShowing
// ═══════════════════════════════════════════════════════════════════════════
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);

var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || 
        dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical"))
    {
        // TaskDialogResult.Yes = 6 (Autodesk.Revit.UI)
        e.OverrideResult(6);
    }
});
uiapp.DialogBoxShowing += dlgHandler;

try {
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; 
int wallId = (int)j["W"]; double projX = (double)j["PX"]; double projY = (double)j["PY"]; string devId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);
XYZ projPt = new XYZ(projX/304.8, projY/304.8, 0);

Wall bestWall = doc.GetElement(new ElementId(wallId)) as Wall;
if (bestWall == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"Wall not found\\\"}";

Reference faceRef = null; Face fFace = null; XYZ fNorm = null;
var opts = new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine };
var geom = bestWall.get_Geometry(opts);
if (geom != null) foreach (var o in geom) { if (!(o is Solid)) continue; foreach (Face f in (o as Solid).Faces) {
    try {
        var r = f.Project(pt);
        if (r != null && r.XYZPoint != null) {
            var uv = r.UVPoint; var bb = f.GetBoundingBox();
            if (bb.Min.U <= uv.U && uv.U <= bb.Max.U && bb.Min.V <= uv.V && uv.V <= bb.Max.V) {
                var n = f.ComputeNormal(uv);
                if (Math.Abs(n.Z) < 0.1) { faceRef = f.Reference; fFace = f; fNorm = n; break; }
            }
        }
    } catch {} if (faceRef != null) break; } if (faceRef != null) break; }

if (faceRef == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"No vertical face contains point\\\"}";
var projF = fFace.Project(pt); if (projF == null || projF.XYZPoint == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"Face project failed\\\"}";
XYZ facePt = projF.XYZPoint;

double wallBase = 0; var bp = bestWall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT);
if (bp == null) bp = bestWall.get_Parameter(BuiltInParameter.LEVEL_PARAM);
if (bp != null && bp.HasValue) { var lid = bp.AsElementId(); if (lid != null && lid != ElementId.InvalidElementId) { var bl = doc.GetElement(lid) as Level; if (bl != null) wallBase = bl.Elevation; } }
double elevRel = (z/304.8) - wallBase; XYZ placePt = new XYZ(facePt.X, facePt.Y, elevRel);

XYZ dir = XYZ.BasisZ;
FamilyInstance inst = null;
try { inst = doc.Create.NewFamilyInstance(faceRef, placePt, dir, sym); }
catch (Exception exPlace) { return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "NewFamilyInstance failed: " + exPlace.Message }); }
if (inst == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "inst is null" });
int hId = (int)bestWall.Id.Value;

if (rot != 0) {
    double rad = (rot + 90.0) * Math.PI / 180.0;
    try { var loc = inst.Location as LocationPoint; if (loc != null) { var ax = Line.CreateBound(placePt, new XYZ(placePt.X, placePt.Y, placePt.Z+1)); loc.Rotate(ax, rad); } }
    catch (Exception exRot) { return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Rotate failed: " + exRot.Message }); }
}

return "{\\\"success\\\":true,\\\"elementId\\\":\\"" + (inst?.Id.Value ?? 0) + "\\\",\\\"uniqueId\\\":\\"" + (inst?.UniqueId ?? "") + "\\\",\\\"hostId\\\":\\"" + hId + "\\\",\\\"usedFace\\\":true,\\\"placementMethod\\\":\\\"wall_face_based\\\"}";
}
finally {
    uiapp.DialogBoxShowing -= dlgHandler;
}'''

# ─── CS_FACE_CEILING ───
CS_FACE_CEILING = r'''var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);

// ═══════════════════════════════════════════════════════════════════════════
// SUPRIMIR DIÁLOGOS BLOQUEANTES: FailureHandlingOptions + DialogBoxShowing
// ═══════════════════════════════════════════════════════════════════════════
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);

var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || 
        dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical"))
    {
        // TaskDialogResult.Yes = 6 (Autodesk.Revit.UI)
        e.OverrideResult(6);
    }
});
uiapp.DialogBoxShowing += dlgHandler;

try {
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; string devId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);

Ceiling bestC = null; double bestA = double.MaxValue;
var opts = new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine };
var ceils = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType().Cast<Ceiling>().Where(c => c.LevelId.Value == lvlId);
foreach (var c in ceils) {
    var geom = c.get_Geometry(opts); if (geom == null) continue;
    foreach (var o in geom) { if (!(o is Solid)) continue; foreach (Face f in (o as Solid).Faces) {
        try { var r = f.Project(pt); if (r == null) continue; var uv = r.UVPoint; var bb = f.GetBoundingBox();
        if (bb.Min.U <= uv.U && uv.U <= bb.Max.U && bb.Min.V <= uv.V && uv.V <= bb.Max.V) {
            double a = f.Area; if (a < bestA) { bestA = a; bestC = c; } break; } } catch {} } }
}
if (bestC == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "No ceiling" });

Reference faceRef = null; XYZ placePt = pt;
var geom2 = bestC.get_Geometry(opts);
if (geom2 != null) foreach (var o in geom2) { if (!(o is Solid)) continue; foreach (Face f in (o as Solid).Faces) {
    try { var r = f.Project(pt); if (r == null) continue; var uv = r.UVPoint; var bb = f.GetBoundingBox();
    if (bb.Min.U <= uv.U && uv.U <= bb.Max.U && bb.Min.V <= uv.V && uv.V <= bb.Max.V) { faceRef = f.Reference; placePt = r.XYZPoint; break; } } catch {} if (faceRef != null) break; } if (faceRef != null) break; }

if (faceRef == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "No ceiling face" });
XYZ dir = XYZ.BasisZ;
FamilyInstance inst = doc.Create.NewFamilyInstance(faceRef, placePt, dir, sym);
int hId = (int)bestC.Id.Value;

return "{\\\"success\\\":true,\\\"elementId\\\":\\"" + (inst?.Id.Value ?? 0) + "\\\",\\\"uniqueId\\\":\\"" + (inst?.UniqueId ?? "") + "\\\",\\\"hostId\\\":\\"" + hId + "\\\",\\\"usedFace\\\":true,\\\"placementMethod\\\":\\\"ceiling_face_based\\\"}";
}
finally {
    uiapp.DialogBoxShowing -= dlgHandler;
}'''

# ─── CS_LEVEL_BASED ───
CS_LEVEL_BASED = r'''var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);

// ═══════════════════════════════════════════════════════════════════════════
// SUPRIMIR DIÁLOGOS BLOQUEANTES: FailureHandlingOptions + DialogBoxShowing
// ═══════════════════════════════════════════════════════════════════════════
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);

var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || 
        dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical"))
    {
        // TaskDialogResult.Yes = 6 (Autodesk.Revit.UI)
        e.OverrideResult(6);
    }
});
uiapp.DialogBoxShowing += dlgHandler;

try {
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);
string familia = j["F"]?.ToString(); string tipo = j["T"]?.ToString();
double x = (double)j["X"]; double y = (double)j["Y"]; double z = (double)j["Z"];
double rot = (double)j["R"]; double altMM = (double)j["A"]; int lvlId = (int)j["L"]; string devId = j["D"]?.ToString();

FamilySymbol sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>().FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);
if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });
if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
Level lvl = doc.GetElement(new ElementId(lvlId)) as Level; if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });
XYZ pt = new XYZ(x/304.8, y/304.8, z/304.8);

// FIX level-based: NewFamilyInstance(pt, sym, level) IGNORA X,Y del point -> crear en origen y mover
FamilyInstance inst = doc.Create.NewFamilyInstance(pt, sym, lvl, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
if (inst == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Create failed" });

// Mover a posición correcta (NewFamilyInstance con Level usa Z relativo al nivel, ignora X,Y)
var loc = inst.Location as LocationPoint;
if (loc != null) {
    XYZ currentPt = loc.Point;
    XYZ moveVec = new XYZ(pt.X - currentPt.X, pt.Y - currentPt.Y, 0);
    if (moveVec.GetLength() > 0.001) {
        ElementTransformUtils.MoveElement(doc, inst.Id, moveVec);
    }
}

if (rot != 0) { double rad = rot * Math.PI / 180; foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Rotation"||n=="Angle") { if(!p.IsReadOnly){p.Set(rad);break;} } } }
if (altMM > 0) { foreach (Parameter p in inst.Parameters) { var n = p.Definition.Name; if (n=="Elevation"||n=="Offset") { if(!p.IsReadOnly){p.Set(altMM/304.8);break;} } } }

return "{\\\"success\\\":true,\\\"elementId\\\":\\"" + (inst?.Id.Value ?? 0) + "\\\",\\\"uniqueId\\\":\\"" + (inst?.UniqueId ?? "") + "\\\",\\\"hostId\\\":0,\\\"usedFace\\\":false,\\\"placementMethod\\\":\\\"level_based\\\"}";
}
finally {
    uiapp.DialogBoxShowing -= dlgHandler;
}'''

# Now replace the three template definitions in the file
import re

for name, new_template in [('CS_FACE_WALL', CS_FACE_WALL), ('CS_FACE_CEILING', CS_FACE_CEILING), ('CS_LEVEL_BASED', CS_LEVEL_BASED)]:
    # Find the pattern: NAME = r""" ... """
    pattern = rf'{name}\s*=\s*r"""[\s\S]*?"""'
    replacement = f'{name} = r"""{new_template}"""'
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    print(f"Replaced {name}")

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("All three templates rewritten correctly.")