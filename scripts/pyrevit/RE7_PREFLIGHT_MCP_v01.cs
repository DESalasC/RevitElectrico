// RE7_PREFLIGHT_MCP_v01.cs
// Etapa 0 del ruteo F7 - SOLO LECTURA. Canal MCP (C#) del add-in de Revit.
// Devuelve un JSON con: documento, niveles, tipos de conduit, conduits existentes
// y dispositivos electricos (fixtures/equipment/lighting). No crea ni borra nada.
var doc = document;
var sb = new System.Text.StringBuilder();
var ci = System.Globalization.CultureInfo.InvariantCulture;
System.Func<double, string> mm = d => System.Math.Round(d * 304.8, 3).ToString(ci);
System.Func<string, string> js = s => Newtonsoft.Json.JsonConvert.SerializeObject(s);

sb.Append("{\"titulo\":").Append(js(doc.Title));
sb.Append(",\"ruta\":").Append(js(doc.PathName));
sb.Append(",\"modificado\":").Append(doc.IsModified ? "true" : "false");
sb.Append(",\"solo_lectura\":").Append(doc.IsReadOnly ? "true" : "false");

sb.Append(",\"niveles\":[");
var niv = new Autodesk.Revit.DB.FilteredElementCollector(doc).OfClass(typeof(Autodesk.Revit.DB.Level)).ToElements();
bool f = true;
foreach (Autodesk.Revit.DB.Level l in niv)
{
    if (!f) sb.Append(",");
    f = false;
    sb.Append("{\"id\":").Append(l.Id.Value);
    sb.Append(",\"nombre\":").Append(js(l.Name));
    sb.Append(",\"elev_mm\":").Append(mm(l.Elevation)).Append("}");
}
sb.Append("]");

sb.Append(",\"tipos_conduit\":[");
var tipos = new Autodesk.Revit.DB.FilteredElementCollector(doc).OfClass(typeof(Autodesk.Revit.DB.Electrical.ConduitType)).ToElements();
f = true;
foreach (Autodesk.Revit.DB.Electrical.ConduitType t in tipos)
{
    if (!f) sb.Append(",");
    f = false;
    sb.Append("{\"id\":").Append(t.Id.Value);
    sb.Append(",\"nombre\":").Append(js(t.Name));
    sb.Append(",\"valido\":").Append(Autodesk.Revit.DB.Electrical.Conduit.IsValidConduitType(doc, t.Id) ? "true" : "false").Append("}");
}
sb.Append("]");

var cd = new Autodesk.Revit.DB.FilteredElementCollector(doc).OfClass(typeof(Autodesk.Revit.DB.Electrical.Conduit)).ToElements();
sb.Append(",\"conduits\":[");
f = true;
foreach (Autodesk.Revit.DB.Electrical.Conduit c in cd)
{
    if (!f) sb.Append(",");
    f = false;
    sb.Append("{\"id\":").Append(c.Id.Value);
    sb.Append(",\"tipo_id\":").Append(c.GetTypeId().Value);
    var lc = c.Location as Autodesk.Revit.DB.LocationCurve;
    if (lc != null)
    {
        var p0 = lc.Curve.GetEndPoint(0);
        var p1 = lc.Curve.GetEndPoint(1);
        sb.Append(",\"a_mm\":[").Append(mm(p0.X)).Append(",").Append(mm(p0.Y)).Append(",").Append(mm(p0.Z)).Append("]");
        sb.Append(",\"b_mm\":[").Append(mm(p1.X)).Append(",").Append(mm(p1.Y)).Append(",").Append(mm(p1.Z)).Append("]");
    }
    else { sb.Append(",\"a_mm\":null,\"b_mm\":null"); }
    sb.Append("}");
}
sb.Append("]");

sb.Append(",\"dispositivos\":[");
var cats = new Autodesk.Revit.DB.BuiltInCategory[]
{
    Autodesk.Revit.DB.BuiltInCategory.OST_ElectricalFixtures,
    Autodesk.Revit.DB.BuiltInCategory.OST_ElectricalEquipment,
    Autodesk.Revit.DB.BuiltInCategory.OST_LightingFixtures
};
f = true;
foreach (var cat in cats)
{
    var insts = new Autodesk.Revit.DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements();
    foreach (Autodesk.Revit.DB.Element e in insts)
    {
        if (!f) sb.Append(",");
        f = false;
        var fi = e as Autodesk.Revit.DB.FamilyInstance;
        string fam = "";
        string tip = "";
        if (fi != null) { fam = fi.Symbol.Family.Name; tip = fi.Symbol.Name; }
        var lp = e.Location as Autodesk.Revit.DB.LocationPoint;
        sb.Append("{\"id\":").Append(e.Id.Value);
        sb.Append(",\"categoria\":").Append(js(cat.ToString()));
        sb.Append(",\"familia\":").Append(js(fam));
        sb.Append(",\"tipo\":").Append(js(tip));
        if (lp != null)
        {
            sb.Append(",\"x_mm\":").Append(mm(lp.Point.X));
            sb.Append(",\"y_mm\":").Append(mm(lp.Point.Y));
            sb.Append(",\"z_mm\":").Append(mm(lp.Point.Z));
            sb.Append(",\"fuente_posicion\":\"LocationPoint\"");
        }
        else { sb.Append(",\"x_mm\":null,\"y_mm\":null,\"z_mm\":null,\"fuente_posicion\":null"); }
        sb.Append("}");
    }
}
sb.Append("]");
sb.Append("}");
return sb.ToString();
