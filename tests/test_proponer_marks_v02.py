# -*- coding: utf-8 -*-
"""
Prueba local del proponedor de Marks (sin Revit).

Genera un inventario sintetico a partir de los propios dispositivos DXF,
con jitter de +-40 mm en XY, y comprueba que:
  * todos los dispositivos emparejan (sin_match = 0)
  * el apartamento propuesto coincide con el del DXF
  * la distancia de match es ~ el jitter aplicado

Uso: python tests/test_proponer_marks_v02.py
"""
import importlib.util
import io
import json
import math
import os
import random
import sys

BASE = r"D:\Work\PROJECTS\RevitElectrico"
SPEC = os.path.join(BASE, "scripts", "RE7_PROPONER_MARKS_TODOS_v02.py")
TMP_INV = os.path.join(BASE, "data", "_tmp_inventario_test.json")
TMP_OUT = os.path.join(BASE, "data", "_tmp_propuesta_test.json")
TMP_TXT = os.path.join(BASE, "data", "_tmp_propuesta_test.txt")

random.seed(7)

spec = importlib.util.spec_from_file_location("prop2", SPEC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# --- construir inventario sintetico desde los dispositivos DXF ---
dxf = json.load(io.open(m.DXF_DISPOSITIVOS, encoding="utf-8"))
inserts = {a["name"]: a["insert_mm"] for a in dxf["apartamentos"]}
disp = []
verdad = {}
for i, q in enumerate(dxf["dispositivos"]):
    ix, iy = inserts[q["apto_dxf"]]
    gx = ix + (q["x_mm"] - ix) * 1000.0
    gy = iy + (q["y_mm"] - iy) * 1000.0
    jx = random.uniform(-40.0, 40.0)
    jy = random.uniform(-40.0, 40.0)
    did = 900000 + i
    disp.append({
        "id": did,
        "categoria": q.get("layer") or "cat",
        "familia": q.get("familia_revit") or "?",
        "tipo": q.get("tipo_revit") or "?",
        "x": round(gx + jx, 3),
        "y": round(gy + jy, 3),
        "z": 14320.0,
        "mark": "",
        "comment": None,
        "nivel": "Piso 5",
    })
    verdad[did] = m.apto_codigo(q["apto_dxf"])

io.open(TMP_INV, "w", encoding="utf-8").write(json.dumps({
    "version": "test",
    "documento": {"titulo": "TEST", "path": "TEST"},
    "resumen": {"total": len(disp)},
    "dispositivos": disp,
}, ensure_ascii=True, indent=1))

m.INVENTARIO = TMP_INV
m.OUT_JSON = TMP_OUT
m.OUT_TXT = TMP_TXT
m.lineas = []
rc = m.main()

res = json.load(io.open(TMP_OUT, encoding="utf-8"))
props = res["propuestas"]
dists = sorted(p["match_dist_mm"] for p in props)
aciertos = sum(1 for p in props if p["apto"] == verdad.get(p["id"]))
sin_circ = sum(1 for p in props if p["circuito"] == "SIN CIRCUITO")

print("")
print("=" * 60)
print("RESULTADO TEST")
print("  propuestas:", len(props), "de", len(disp))
print("  sin_match:", len(res["sin_match"]))
print("  dist: mediana=%.1f max=%.1f mm" % (dists[len(dists) // 2], dists[-1]))
print("  apto correcto:", aciertos, "/", len(props))
print("  SIN CIRCUITO:", sin_circ)

ok = (len(props) == len(disp) and len(res["sin_match"]) == 0
      and aciertos == len(props) and dists[-1] <= 120.0)
print("  VEREDICTO:", "OK" if ok else "FALLA")

for f in (TMP_INV, TMP_OUT, TMP_TXT):
    try:
        os.remove(f)
    except Exception:
        pass

sys.exit(0 if ok else 1)
