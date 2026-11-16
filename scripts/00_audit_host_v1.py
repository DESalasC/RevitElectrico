# -*- coding: utf-8 -*-
# =====================================================================
# 00_audit_host_v1.py   |  SCRIPT_ID = AUD-HOST  |  VERSION 1.0.0
# Lectura pura. Resuelve el documento Revit en cualquier contexto
# (pyRevit pushbutton / MCP exec / consola) y audita TODO lo que
# determina la estrategia de colocacion y ruteo.
# =====================================================================
import sys, os, io, json, platform, datetime

SCRIPT_ID = "AUD-HOST"
VERSION   = "1.0.0"

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import UIApplication, UIDocument

OUT_DIR = r"D:\Work\PROJECTS\RevitElectrico\data"
DOC_TITLE_FILTER = ""      # opcional: substring del titulo del .rvt objetivo

FT2M = 0.3048

def banner(doc):
    print("=" * 78)
    print("SCRIPT {}  v{}   (AUDITORIA HOST - SOLO LECTURA)".format(SCRIPT_ID, VERSION))
    print("Ejecutado : {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("Motor     : {} {}".format(platform.python_implementation(), sys.version.split()[0]))
    print("Documento : {}".format(doc.Title if doc else "<NONE>"))
    print("=" * 78)

# ---------------------------------------------------------------------
# RESOLUCION ROBUSTA DEL DOCUMENTO  (clave del fallo actual)
# ---------------------------------------------------------------------
def resolve_uiapp():
    G = globals()
    a = G.get("__revit__", None)
    if isinstance(a, UIApplication):
        return a, "global __revit__"
    try:
        import __builtin__ as B
    except Exception:
        try:
            import builtins as B
        except Exception:
            B = None
    if B is not None:
        a = getattr(B, "__revit__", None)
        if isinstance(a, UIApplication):
            return a, "builtins.__revit__"
    try:
        from pyrevit import HOST_APP
        if HOST_APP.uiapp is not None:
            return HOST_APP.uiapp, "pyrevit HOST_APP.uiapp"
    except Exception:
        pass
    try:
        from RevitServices.Persistence import DocumentManager
        a = DocumentManager.Instance.CurrentUIApplication
        if a is not None:
            return a, "RevitServices (Dynamo)"
    except Exception:
        pass
    return None, "no-disponible"

def resolve_doc():
    log = []
    uiapp, src = resolve_uiapp()
    log.append("UIApplication via: " + src)
    doc = None
    if uiapp is not None:
        try:
            ud = uiapp.ActiveUIDocument
            if ud is not None:
                doc = ud.Document
                log.append("doc via ActiveUIDocument")
        except Exception as e:
            log.append("ActiveUIDocument fallo: " + str(e))
    if doc is None:
        d = globals().get("doc", None)
        if isinstance(d, Document):
            doc = d
            log.append("doc via global inyectada (MCP)")
    if doc is None:
        try:
            from RevitServices.Persistence import DocumentManager
            d = DocumentManager.Instance.CurrentDBDocument
            if d is not None:
                doc = d
                log.append("doc via RevitServices")
        except Exception:
            pass
    if doc is None and uiapp is not None:
        try:
            for d in uiapp.Application.Documents:
                if not d.IsFamilyDocument:
                    if (not DOC_TITLE_FILTER) or (DOC_TITLE_FILTER.lower() in d.Title.lower()):
                        doc = d
                        log.append("doc via Application.Documents")
                        break
        except Exception as e:
            log.append("Application.Documents fallo: " + str(e))
    return doc, uiapp, log

def eid(e):
    try:
        return int(e.Value)          # Revit 2024+
    except Exception:
        try:
            return int(e.IntegerValue)
        except Exception:
            return -1

def num(x, n=4):
    try:
        return round(float(x), n)
    except Exception:
        return None

def p3(pt):
    return {"x_ft": num(pt.X), "y_ft": num(pt.Y), "z_ft": num(pt.Z),
            "x_m": num(pt.X * FT2M), "y_m": num(pt.Y * FT2M), "z_m": num(pt.Z * FT2M)}

# ---------------------------------------------------------------------
doc, uiapp, ctxlog = resolve_doc()
banner(doc)
for l in ctxlog:
    print("  [ctx] " + l)
if doc is None:
    print("\n[ERROR] No se pudo resolver ningun Document.")
    print("Ejecuta este archivo como pushbutton de pyRevit, o asegurate de que el")
    print("MCP inyecte 'doc' / '__revit__' en el namespace de ejecucion.")
    raise SystemExit(1)

R = {"script": SCRIPT_ID, "version": VERSION,
     "timestamp": datetime.datetime.now().isoformat(),
     "contexto": ctxlog,
     "documento": {"titulo": doc.Title, "ruta": doc.PathName,
                   "workshared": doc.IsWorkshared}}

# ---------------------------------------------------------------------
# 1. NIVELES
# ---------------------------------------------------------------------
print("\n" + "-" * 78 + "\n1. NIVELES\n" + "-" * 78)
levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
levels.sort(key=lambda l: l.Elevation)
R["niveles"] = []
for l in levels:
    d = {"nombre": l.Name, "id": eid(l.Id), "uuid": l.UniqueId,
         "elev_ft": num(l.Elevation), "elev_m": num(l.Elevation * FT2M)}
    R["niveles"].append(d)
    print("  {:<28} id={:<10} {:>8} m".format(l.Name, d["id"], d["elev_m"]))

# ---------------------------------------------------------------------
# 2. LINKS  (¿donde estan los muros/cielorrasos?)
# ---------------------------------------------------------------------
print("\n" + "-" * 78 + "\n2. REVIT LINKS\n" + "-" * 78)
R["links"] = []
links = list(FilteredElementCollector(doc).OfClass(RevitLinkInstance).ToElements())
for li in links:
    try:
        ldoc = li.GetLinkDocument()
        tr = li.GetTotalTransform()
        info = {"id": eid(li.Id), "uuid": li.UniqueId, "nombre": li.Name,
                "cargado": ldoc is not None,
                "origen_transform": p3(tr.Origin),
                "rotacion_rad": num(tr.BasisX.AngleTo(XYZ.BasisX) if tr.BasisX.IsAlmostEqualTo(XYZ.BasisX) else 0)}
        if ldoc is not None:
            info["doc_titulo"] = ldoc.Title
            info["doc_ruta"] = ldoc.PathName
            for tag, bic in (("muros", BuiltInCategory.OST_Walls),
                             ("cielorrasos", BuiltInCategory.OST_Ceilings),
                             ("pisos", BuiltInCategory.OST_Floors),
                             ("rooms", BuiltInCategory.OST_Rooms)):
                try:
                    info[tag] = FilteredElementCollector(ldoc).OfCategory(bic)\
                                .WhereElementIsNotElementType().GetElementCount()
                except Exception:
                    info[tag] = None
            try:
                info["niveles"] = [{"nombre": l.Name, "elev_m": num(l.Elevation * FT2M)}
                                   for l in FilteredElementCollector(ldoc).OfClass(Level).ToElements()]
            except Exception:
                pass
        R["links"].append(info)
        print("  link id={} '{}' cargado={} muros={} cielorrasos={}".format(
            info["id"], info["nombre"], info["cargado"],
            info.get("muros"), info.get("cielorrasos")))
    except Exception as e:
        print("  [WARN] link ilegible: " + str(e))

# ---------------------------------------------------------------------
# 3. HOSTS LOCALES
# ---------------------------------------------------------------------
print("\n" + "-" * 78 + "\n3. HOSTS EN EL DOCUMENTO LOCAL\n" + "-" * 78)
R["hosts_locales"] = {}
for tag, bic in (("muros", BuiltInCategory.OST_Walls),
                 ("cielorrasos", BuiltInCategory.OST_Ceilings),
                 ("pisos", BuiltInCategory.OST_Floors)):
    try:
        n = FilteredElementCollector(doc).OfCategory(bic)\
            .WhereElementIsNotElementType().GetElementCount()
    except Exception:
        n = None
    R["hosts_locales"][tag] = n
    print("  {:<14}: {}".format(tag, n))

# ---------------------------------------------------------------------
# 4. TABLA DE MAPEO -> SIMBOLOS REALES + PLACEMENT TYPE
# ---------------------------------------------------------------------
print("\n" + "-" * 78 + "\n4. FAMILIAS DEL MAPEO\n" + "-" * 78)
MAPPING = [
    ("M_Interruptores",        "Simple conmutable",  "ELEC-I-S-C1-5A"),
    ("M_Interruptores",        "Simple",             "ELEC-I-S-1-5A"),
    ("M_Interruptores",        "Triple",             "S3"),
    ("M_Climatizacion",        "Interruptor Ventilador", "ELEC-F-CONTROL"),
    ("M_ClimatizacionV",       "Ventilador",         "ELEC-F-VENT"),
    ("M_Pulsador - Interruptor","Timbre",            "ELEC-TIMBRE"),
    ("M_Toma doble",           "GFCI",               "ELEC-T-GFCI-t-15A"),
    ("M_Toma doble",           "Normal",             "ELEC-T-D-t-15A"),
    ("M_Zumbador",             "Campana timbre",     "ELEC-CAMPANA"),
    ("Consolidation_Point",    "CPB6L",              "ELEC-NET-PAU"),
    ("M_Comunicaciones",       "Datos",              "ELEC-TEL"),
    ("M_Iluminacion",          "SONO FLEX 10 trim",  "Bala Stil Led 10W"),
    ("M_Iluminacion",          "SONO FLEX 13 trim",  "Bala Stil Led 13W"),
    ("M_Iluminacion",          "SONO FLEX 22 trim",  "Bala Stil Led 22W"),
    ("EA",                     "M_Extractor",        "ELEC-EXT"),
    ("E_Panel Distribucion",   "EPB25-304C",         "TB-Panel"),
]
all_syms = list(FilteredElementCollector(doc).WhereElementIsElementType()
                .OfClass(FamilySymbol).ToElements())
R["mapeo"] = []
for fam, typ, dxfname in MAPPING:
    hit = None
    for s in all_syms:
        try:
            if s.Family.Name == fam and s.Name == typ:
                hit = s
                break
        except Exception:
            pass
    if hit is None:
        for s in all_syms:
            try:
                if s.Family.Name == fam:
                    hit = s
                    break
            except Exception:
                pass
    rec = {"dxf": dxfname, "familia": fam, "tipo_buscado": typ, "encontrado": hit is not None}
    if hit is not None:
        f = hit.Family
        conns = 0
        try:
            cm = hit.MEPModel
            if cm is not None and cm.ConnectorManager is not None:
                conns = cm.ConnectorManager.ConnectorSet.Size
        except Exception:
            pass
        rec.update({"tipo_real": hit.Name, "id": eid(hit.Id), "uuid": hit.UniqueId,
                    "categoria": hit.Category.Name if hit.Category else None,
                    "placement_type": str(f.FamilyPlacementType),
                    "activo": hit.IsActive, "conectores_mep_fase": conns})
        print("  [OK]   {:<26}/{:<22} {:<24} cat={}".format(
            fam, hit.Name, rec["placement_type"], rec["categoria"]))
    else:
        print("  [FALTA] {} / {}".format(fam,