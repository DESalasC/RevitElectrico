# -*- coding: utf-8 -*-
"""VALIDAR_COLLOCACION_F01_F02_v01.py - 2026-11-18 - IronPython 2.7 para pyRevit

Compara los dispositivos colocados en CENTRAL-V01 contra el DXF fuente
(validando conteos, alturas Z y rango XY). Los archivos expected_F01/F02.json
aun no existen en data/referencia/ (pendiente de minar de V02-f), asi que se
usa el DXF extraido como fuente de verdad de posiciones esperadas.

Umbrales CLAUDE.md:
  - dXY <= 0.02 m (aceptacion) / 0.05 m (aviso)
  - dZ <= 0.02 m
  - rotacion en {0, 90, 180, 270} +/- 1 deg

USO: Copiar/pegar en pyRevit Python Shell con CENTRAL-V01.rvt abierto.
"""

import json
import math
import clr
import datetime

clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (
    XYZ, BuiltInCategory, FilteredElementCollector, FamilyInstance,
    LocationPoint, Level
)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64

# ──────────────────────────────────────────────────────────────
# CONSTANTES
# ──────────────────────────────────────────────────────────────
METER_TO_FOOT = 3.28084
FOOT_TO_METER = 1.0 / METER_TO_FOOT
NIVEL5_ELEV_M = 13.22

DXF_JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_F01_F02_extraido.json"

ALTURAS_MM = {
    "M_Toma doble": 300,
    "M_Comunicaciones": 300,
    "M_Interruptores": 1100,
    "M_Pulsador - Interruptor": 1100,
    "M_Timbre": 2400,
    "EA": 1900,
    "M_ClimatizacionV": 2400,
    "M_Iluminacion": 2600,
    "Consolidation_Point": 2700,
}

UMBRAL_DXY_OK_M = 0.02
UMBRAL_DXY_WARN_M = 0.05
UMBRAL_DZ_OK_M = 0.02
UMBROT_DEG = 1.0

# ──────────────────────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────────────────────
def clean(s):
    if not s:
        return s
    return s.replace('\ufeff', '').replace('\u200b', '').strip()

def elem_id_int(elem):
    if elem is None:
        return 0
    try:
        eid = elem.Id if hasattr(elem, 'Id') else elem
        if hasattr(eid, 'IntegerValue'):
            return int(eid.IntegerValue)
        if hasattr(eid, 'Value'):
            return int(eid.Value)
        return int(str(eid))
    except Exception:
        return 0

def load_json(path):
    with open(path, 'r') as f:  # IronPython 2.7: SIN encoding=
        return json.load(f)

def dist_xy_m(p1, p2):
    dx = (p1.X - p2.X) * FOOT_TO_METER
    dy = (p1.Y - p2.Y) * FOOT_TO_METER
    return math.sqrt(dx * dx + dy * dy)

def rot_ok(rot_deg):
    """Devuelve True si rotacion esta en {0,90,180,270} +/- UMBROT_DEG."""
    for base in (0, 90, 180, 270):
        d = abs(((rot_deg - base + 180) % 360) - 180)
        if d <= UMBROT_DEG:
            return True
    return False

# ──────────────────────────────────────────────────────────────
# DOCUMENTO
# ──────────────────────────────────────────────────────────────
doc = None
try:
    doc = __revit__.ActiveUIDocument.Document
except Exception:
    try:
        from pyrevit import revit
        doc = revit.doc
    except Exception:
        pass

if not doc:
    print("[ERROR] No se pudo resolver el documento Revit. Ejecuta dentro de pyRevit.")
    raise SystemExit(1)

print("[OK] {}".format(doc.Title))

# ──────────────────────────────────────────────────────────────
# CARGAR DXF FUENTE
# ──────────────────────────────────────────────────────────────
dxf_data = load_json(DXF_JSON_PATH)
f01_expected = [d for d in dxf_data.get('F01', {}).get('devices', []) if d.get('familia_revit')]
f02_expected = [d for d in dxf_data.get('F02', {}).get('devices', []) if d.get('familia_revit')]

f01_panels_dxf = dxf_data.get('F01', {}).get('panels', {})
f02_panels_dxf = dxf_data.get('F02', {}).get('panels', {})

print("DXF fuente: F01={} dispositivos, F02={} dispositivos".format(len(f01_expected), len(f02_expected)))

# ──────────────────────────────────────────────────────────────
# RECOLECTAR DISPOSITIVOS COLOCADOS EN REVIT
# ──────────────────────────────────────────────────────────────
def collect_placed_devices(doc):
    """Recopila FamilyInstances de categorias electricas.
    Usa Location.Point cuando disponible; get_BoundingBox(None) como respaldo
    para instancias hosteadas (cielorrasos, cara de muro) que no exponen
    LocationPoint o devuelven Z no confiable (CLAUDE.md leccion #6)."""
    cats = [
        BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_ElectricalFixtures,
        BuiltInCategory.OST_LightingFixtures,
        BuiltInCategory.OST_DataDevices,
        BuiltInCategory.OST_TelephoneDevices,
        BuiltInCategory.OST_CommunicationDevices,
    ]
    placed = []
    for cat in cats:
        for fi in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements():
            if not isinstance(fi, FamilyInstance):
                continue
            loc = fi.Location
            fam = clean(fi.Symbol.FamilyName)
            sym = fi.Symbol
            typ = ""
            try:
                p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                if p and p.HasValue:
                    typ = clean(p.AsString()) or ""
            except Exception:
                pass
            pt = None
            if isinstance(loc, LocationPoint):
                pt = loc.Point
                # Z de 0 (o casi 0) indica instancia hosteada con coordenada no confiable
                if pt is not None and abs(pt.Z) < 0.01:
                    pt = None
                # Z == elevacion del nivel indica LB creado con offset: Revit devuelve
                # solo la elevacion del nivel, no nivel+offset. Usar bbox para Z real.
                if pt is not None and abs(pt.Z * FOOT_TO_METER - NIVEL5_ELEV_M) < 0.5:
                    pt = None
            if pt is None:
                # Respaldo: bounding box para instancias hosteadas (ceiling/face-based)
                try:
                    bb = fi.get_BoundingBox(None)
                    if bb is not None:
                        pt = XYZ(
                            (bb.Min.X + bb.Max.X) / 2.0,
                            (bb.Min.Y + bb.Max.Y) / 2.0,
                            (bb.Min.Z + bb.Max.Z) / 2.0,
                        )
                except Exception:
                    pass
            if pt is None:
                continue
            placed.append({
                "id": elem_id_int(fi),
                "unique_id": fi.UniqueId,
                "family": fam,
                "type": typ,
                "pt": pt,
                "level_id": elem_id_int(fi.LevelId),
            })
    return placed

placed = collect_placed_devices(doc)
print("\nDispositivos totales en modelo: {}".format(len(placed)))

# FILTRAR solo los dispositivos colocados por esta sesion (F01/F02 en area conocida)
# v2.3 coloca dispositivos en: X 30-50 ft, Y 0-60 ft (Piso 5, apartamentos F01/F02)
F01_X_MIN, F01_X_MAX = 30.0, 50.0
F01_Y_MIN, F01_Y_MAX = 0.0, 30.0
F02_X_MIN, F02_X_MAX = 30.0, 50.0
F02_Y_MIN, F02_Y_MAX = 30.0, 60.0

def in_range(dev, x_min, x_max, y_min, y_max):
    x = dev['pt'].X
    y = dev['pt'].Y
    return x_min <= x <= x_max and y_min <= y <= y_max

f01_placed = [d for d in placed if in_range(d, F01_X_MIN, F01_X_MAX, F01_Y_MIN, F01_Y_MAX)]
f02_placed = [d for d in placed if in_range(d, F02_X_MIN, F02_X_MAX, F02_Y_MIN, F02_Y_MAX)]
our_placed = f01_placed + f02_placed

print("Dispositivos F01 en area (30-50ft, 0-30ft): {}".format(len(f01_placed)))
print("Dispositivos F02 en area (30-50ft, 30-60ft): {}".format(len(f02_placed)))
print("Total dispositivos de esta sesion: {}".format(len(our_placed)))

def count_by_family_type(devices):
    d = {}
    for dev in devices:
        key = (dev['family'], dev['type'])
        d[key] = d.get(key, 0) + 1
    return d

dxf_counts = count_by_family_type([
    {"family": d.get('familia_revit', ''), "type": d.get('tipo_revit', '')}
    for d in f01_expected + f02_expected
])
revit_counts = count_by_family_type(our_placed)

print("\n=== CONTEOS POR FAMILIA/TIPO ===")
all_keys = sorted(set(list(dxf_counts.keys()) + list(revit_counts.keys())))
for key in all_keys:
    dxf_n = dxf_counts.get(key, 0)
    revit_n = revit_counts.get(key, 0)
    status = "OK" if dxf_n == revit_n else "DISCREPANCIA"
    print("  {:<30} | {:<30} | DXF={} RVT={} [{}]".format(key[0], key[1], dxf_n, revit_n, status))

# ──────────────────────────────────────────────────────────────
# VALIDAR ALTURAS Z
# ──────────────────────────────────────────────────────────────
print("\n=== VALIDACION DE ALTURAS Z ===")
z_errors = 0
z_warnings = 0
for dev in our_placed:
    fam = dev['family']
    alt_mm = ALTURAS_MM.get(fam, 300)
    z_abs_ft = dev['pt'].Z
    z_abs_m = z_abs_ft * FOOT_TO_METER
    z_expected_m = NIVEL5_ELEV_M + alt_mm / 1000.0
    dz = abs(z_abs_m - z_expected_m)
    if dz > UMBRAL_DZ_OK_M:
        z_errors += 1
        print("  [ERROR Z] {} id={} Z={:.3f}m esperado={:.3f}m dz={:.3f}m".format(
            fam, dev['id'], z_abs_m, z_expected_m, dz))
    elif dz > UMBRAL_DXY_WARN_M / 10.0:  # umbral de aviso menor para Z
        z_warnings += 1
        print("  [WARN Z]  {} id={} Z={:.3f}m esperado={:.3f}m dz={:.3f}m".format(
            fam, dev['id'], z_abs_m, z_expected_m, dz))

print("Z errores: {}  Z avisos: {}".format(z_errors, z_warnings))

# ──────────────────────────────────────────────────────────────
# VALIDAR RANGE XY (rango general, no instancia por instancia
# porque expected_F01/F02.json no existen aun)
# ──────────────────────────────────────────────────────────────
print("\n=== RANGO XY DE DISPOSITIVOS DE ESTA SESION ===")
if our_placed:
    xs = [d['pt'].X * FOOT_TO_METER for d in our_placed]
    ys = [d['pt'].Y * FOOT_TO_METER for d in our_placed]
    print("  X: {:.3f} m a {:.3f} m".format(min(xs), max(xs)))
    print("  Y: {:.3f} m a {:.3f} m".format(min(ys), max(ys)))
    print("  Z: {:.3f} m a {:.3f} m".format(
        min(d['pt'].Z * FOOT_TO_METER for d in our_placed),
        max(d['pt'].Z * FOOT_TO_METER for d in our_placed)))

# ──────────────────────────────────────────────────────────────
# RESUMEN
# ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("RESUMEN DE VALIDACION")
print("=" * 60)
print("Dispositivos en DXF:     {}".format(len(f01_expected) + len(f02_expected)))
print("Dispositivos en Revit:   {}".format(len(our_placed)))
print("Conteos coinciden:       {}".format(
    "SI" if dxf_counts == revit_counts else "NO - revisar discrepancias arriba"))
print("Z errores (>0.02m):      {}".format(z_errors))
print("Z avisos:                {}".format(z_warnings))
print("\nNOTA: expected_F01.json / expected_F02.json no existen en")
print("data/referencia/. Validacion instancia-por-instancia (dXY,")
print("dZ, rotacion exacta) requiere minar esos archivos de V02-f.")

print("\n=== FIN ===")
