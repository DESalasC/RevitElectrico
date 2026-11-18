with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '''# v04: placement C# recibe hostElementId específico. NO busca muros.
# Solo obtiene el elemento por ID, itera SUS caras (una sola wall), coloca.
CODIGO_COLLOCAR_V04 = r"""
var doc = document;
var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);

string familia = j["Familia"]?.ToString();
string tipo = j["Tipo"]?.ToString();
double x = (double)j["X"];
double y = (double)j["Y"];
double z = (double)j["Z"];
double rotacion = (double)j["Rotacion"];
double alturaLocalMM = (double)j["AlturaLocalMM"];
int levelIdVal = (int)j["LevelId"];
string hostTipo = j["HostTipo"]?.ToString() ?? "Muro";
int hostElementId = (int)j["HostElementId"];   // v04: Python ya encontro el host

// ─── Buscar FamilySymbol ───
FamilySymbol symbol = new FilteredElementCollector(doc)
    .OfClass(typeof(FamilySymbol))
    .Cast<FamilySymbol>()
    .FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);

if (symbol == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Familia/Tipo no encontrado: " + familia + " / " + tipo });
}
if (!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }

// ─── Buscar Level ───
Level level = doc.GetElement(new ElementId(levelIdVal)) as Level;
if (level == null) {
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Nivel no encontrado: LevelId=" + levelIdVal });
}

XYZ point = new XYZ(x / 304.8, y / 304.8, z / 304.8);  // mm a feet

FamilyInstance inst = null;
int hostId = 0;
string hostUniqueId = "";
bool usedFaceBased = false;
string placementMethod = "";"""

new = '''# v04: placement C# recibe hostElementId específico. NO busca muros.
# Solo obtiene el elemento por ID, itera SUS caras (una sola wall), coloca.
# INCLUYE: FailureHandlingOptions para suprimir diálogos + DialogBoxShowing handler
CODIGO_COLLOCAR_V04 = r"""
var doc = document;
var uiapp = new Autodesk.Revit.UI.UIApplication(doc.Application);

// ═══════════════════════════════════════════════════════════════════════════
// SUPRIMIR DIÁLOGOS: FailureHandlingOptions + DialogBoxShowing handler
// ═══════════════════════════════════════════════════════════════════════════
var failOpts = new FailureHandlingOptions();
failOpts.SetClearAfterRollback(true);
failOpts.SetForcedRollback(true);
failOpts.SetDelayedMiniWarnings(true);

var dlgHandler = new EventHandler<Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs>((sender, e) =>
{
    // Auto-dismiss "Delete duplicate instances" y otros diálogos bloqueantes
    var dlgId = e.DialogId;
    if (dlgId == "TaskDialog_Delete_Duplicate_Instances" || 
        dlgId == "TaskDialog_Identical_Instances" ||
        dlgId.Contains("Duplicate") || dlgId.Contains("Identical"))
    {
        e.OverrideResult((int)System.Windows.Forms.DialogResult.Yes);
    }
});
uiapp.DialogBoxShowing += dlgHandler;

var j = Newtonsoft.Json.Linq.JObject.Parse(deviceJson);

string familia = j["Familia"]?.ToString();
string tipo = j["Tipo"]?.ToString();
double x = (double)j["X"];
double y = (double)j["Y"];
double z = (double)j["Z"];
double rotacion = (double)j["Rotacion"];
double alturaLocalMM = (double)j["AlturaLocalMM"];
int levelIdVal = (int)j["LevelId"];
string hostTipo = j["HostTipo"]?.ToString() ?? "Muro";
int hostElementId = (int)j["HostElementId"];   // v04: Python ya encontro el host

// ─── Buscar FamilySymbol ───
FamilySymbol symbol = new FilteredElementCollector(doc)
    .OfClass(typeof(FamilySymbol))
    .Cast<FamilySymbol>()
    .FirstOrDefault(s => s.Family.Name == familia && s.Name == tipo);

if (symbol == null) {
    uiapp.DialogBoxShowing -= dlgHandler;
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Familia/Tipo no encontrado: " + familia + " / " + tipo });
}
if (!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }

// ─── Buscar Level ───
Level level = doc.GetElement(new ElementId(levelIdVal)) as Level;
if (level == null) {
    uiapp.DialogBoxShowing -= dlgHandler;
    return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Nivel no encontrado: LevelId=" + levelIdVal });
}

XYZ point = new XYZ(x / 304.8, y / 304.8, z / 304.8);  // mm a feet

FamilyInstance inst = null;
int hostId = 0;
string hostUniqueId = "";
bool usedFaceBased = false;
string placementMethod = "";

try {"""

content = content.replace(old, new)

# Also need to wrap the rest in try/finally to remove handler
old2 = '''return Newtonsoft.Json.JsonConvert.SerializeObject(new {
    success = true,
    elementId = (int)inst.Id.Value,
    uniqueId = inst.UniqueId,
    hostId = hostId,
    hostUniqueId = hostUniqueId,
    usedFaceBased = usedFaceBased,
    placementMethod = placementMethod
});'''

new2 = '''return Newtonsoft.Json.JsonConvert.SerializeObject(new {
    success = true,
    elementId = (int)inst.Id.Value,
    uniqueId = inst.UniqueId,
    hostId = hostId,
    hostUniqueId = hostUniqueId,
    usedFaceBased = usedFaceBased,
    placementMethod = placementMethod
});
}
finally {
    uiapp.DialogBoxShowing -= dlgHandler;
}'''

content = content.replace(old2, new2)

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Added DialogBoxShowing suppression + FailureHandlingOptions")