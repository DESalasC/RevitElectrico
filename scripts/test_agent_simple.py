# Script de prueba para pyrevit agent run
# Imprime el titilo del documento activo y la lista de niveles del modelo Revit

from pyrevit import revit, DB

doc = __revit__.ActiveUIDocument.Document
print("Documento activo: {}".format(doc.Title))
print("Ruta del documento: {}".format(doc.PathName))

# Listar niveles
levels = DB.FilteredElementCollector(doc) \
    .OfCategory(DB.BuiltInCategory.OST_Levels) \
    .WhereElementIsNotElementType() \
    .ToElements()

print("Niveles encontrados: {}".format(len(levels)))
for lv in levels:
    print("  - {} (elev: {})".format(lv.Name, lv.Elevation))

print("Fin del script de prueba.")
print("OK")
