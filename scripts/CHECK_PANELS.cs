using System;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Electrical;

public class PanelChecker
{
    public static string Execute(Document doc)
    {
        var results = new System.Collections.Generic.List<string>();
        var panels = new FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_ElectricalEquipment)
            .WhereElementIsNotElementType()
            .ToElements();
        
        foreach (var elem in panels)
        {
            var fi = elem as FamilyInstance;
            if (fi == null) continue;
            
            string pname = "";
            var param = fi.LookupParameter("Panel Name");
            if (param != null && param.HasValue)
                pname = param.AsString() ?? "";
            
            var loc = fi.Location as LocationPoint;
            string pos = loc != null ? string.Format("({0:F3},{1:F3},{2:F3})", loc.Point.X, loc.Point.Y, loc.Point.Z) : "null";
            
            results.Add(string.Format("Panel Name: '{0}' | Id: {1} | Pos: {2}", pname, fi.Id.IntegerValue, pos));
        }
        
        return string.Join("\n", results);
    }
}