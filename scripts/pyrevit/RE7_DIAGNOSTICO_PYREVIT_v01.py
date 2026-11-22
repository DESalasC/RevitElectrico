# -*- coding: utf-8 -*-
"""
RE7_DIAGNOSTICO_PYREVIT_v01.py
Diagnostico minimo de ejecucion dentro de Revit (pyRevit).

Escribe evidencia en un archivo de log DESDE LA PRIMERA LINEA, antes de
importar clr, para que la ejecucion deje rastro aunque la consola no muestre
nada. No abre transaccion, no modifica el documento.

Uso (pyRevit Python Shell, Revit 2026):
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\scripts\\pyrevit\\RE7_DIAGNOSTICO_PYREVIT_v01.py").read())
"""
import os
import sys
import traceback

VERSION = "v01"
DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"


def _ruta_log():
    candidatos = []
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz:
        candidatos.append(os.path.join(raiz, "data"))
    candidatos.append(os.path.join(DEFAULT_ROOT, "data"))
    candidatos.append(os.environ.get("TEMP", "."))
    candidatos.append(".")
    for d in candidatos:
        try:
            if not os.path.exists(d):
                os.makedirs(d)
            return os.path.join(d, "f7_diagnostico_pyrevit.log")
        except Exception:
            continue
    return "f7_diagnostico_pyrevit.log"


LOG = _ruta_log()


def ev(msg):
    """Escribe la evidencia en consola y en archivo, sin poder fallar."""
    linea = "[DIAG {}] {}".format(VERSION, msg)
    try:
        print(linea)
    except Exception:
        pass
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        f = open(LOG, "a")
        f.write(linea + "\n")
        f.close()
    except Exception:
        pass


def run():
    ev("P0 INICIO de ejecucion del script")
    ev("P0 log_path={}".format(LOG))
    ev("P0 python={}".format(sys.version.replace("\n", " ")))
    ev("P0 __name__={!r}".format(globals().get("__name__", "<sin __name__>")))
    ev("P0 REVITELECTRICO_ROOT={!r}".format(os.environ.get("REVITELECTRICO_ROOT", None)))
    ev("P0 cwd={}".format(os.getcwd()))

    ev("P1 importando clr")
    import clr
    ev("P1 clr OK")

    ev("P2 AddReference RevitAPI")
    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import (
        BuiltInCategory,
        FilteredElementCollector,
        Level,
    )
    from Autodesk.Revit.DB.Electrical import Conduit, ConduitType
    ev("P2 imports RevitAPI OK")

    ev("P3 buscando documento activo")
    doc = None
    via = None
    try:
        app = __revit__
        ev("P3 __revit__ presente: {}".format(type(app)))
        try:
            doc = app.ActiveUIDocument.Document
            via = "__revit__.ActiveUIDocument.Document"
        except Exception as e:
            ev("P3 __revit__ presente pero sin ActiveUIDocument: {}".format(e))
    except Exception as e:
        ev("P3 __revit__ NO disponible: {}".format(e))

    if doc is None:
        try:
            from pyrevit import revit as _revit
            if getattr(_revit, "doc", None) is not None:
                doc = _revit.doc
                via = "pyrevit.revit.doc"
        except Exception as e:
            ev("P3 pyrevit.revit fallo: {}".format(e))

    if doc is None:
        try:
            clr.AddReference("RevitServices")
            from RevitServices.Persistence import DocumentManager
            inst = DocumentManager.Instance
            if inst is not None and inst.CurrentDBDocument is not None:
                doc = inst.CurrentDBDocument
                via = "RevitServices.DocumentManager"
        except Exception as e:
            ev("P3 RevitServices fallo: {}".format(e))

    if doc is None:
        ev("P3 RESULTADO: NO hay documento activo")
        ev("P5 FIN (sin documento)")
        return

    ev("P3 RESULTADO: documento via {}".format(via))
    try:
        ev("P3 titulo={!r}".format(doc.Title))
        ev("P3 ruta={!r}".format(doc.PathName))
        ev("P3 modificado={} solo_lectura={}".format(bool(doc.IsModified), bool(doc.IsReadOnly)))
    except Exception as e:
        ev("P3 error leyendo propiedades del documento: {}".format(e))

    ev("P4 contando elementos")
    try:
        niveles = FilteredElementCollector(doc).OfClass(Level).ToElements()
        ev("P4 niveles={}".format(len(list(niveles))))
    except Exception as e:
        ev("P4 niveles FALLO: {}".format(e))

    try:
        tipos = FilteredElementCollector(doc).OfClass(ConduitType).ToElements()
        tipos = list(tipos)
        ev("P4 conduit_types={}".format(len(tipos)))
        for t in tipos[:10]:
            ev("P4   tipo id={} nombre={!r}".format(t.Id, t.Name))
    except Exception as e:
        ev("P4 conduit_types FALLO: {}".format(e))

    try:
        conduits = list(FilteredElementCollector(doc).OfClass(Conduit).ToElements())
        ev("P4 conduits={}".format(len(conduits)))
    except Exception as e:
        ev("P4 conduits FALLO: {}".format(e))

    for nombre_cat, cat in (
        ("ElectricalFixtures", BuiltInCategory.OST_ElectricalFixtures),
        ("ElectricalEquipment", BuiltInCategory.OST_ElectricalEquipment),
        ("LightingFixtures", BuiltInCategory.OST_LightingFixtures),
    ):
        try:
            n = len(list(
                FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements()
            ))
            ev("P4 {}={}".format(nombre_cat, n))
        except Exception as e:
            ev("P4 {} FALLO: {}".format(nombre_cat, e))

    ev("P5 FIN del diagnostico")


try:
    run()
except Exception:
    try:
        ev("EXCEPCION NO CONTROLADA:\n" + traceback.format_exc())
    except Exception:
        pass
    raise
