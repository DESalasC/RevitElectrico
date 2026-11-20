# -*- coding: utf-8 -*-
"""
generar_maestro_colocacion.py
=============================
Genera maestro_colocacion_piso5.json cruzando:
  - inventario_apartamentos_v01.json  (paneles ya ubicados en Revit: insert_revit)
  - dxf_master_global_all.json        (base DXF por apto + dispositivos)

Offset = panel_revit_pos - apto_dxf_base_pos
Unidades: todo en metros (panel en metros, base DXF en pies -> convertir)
"""

import json
import os

REVITELECTRICO_ROOT = r"D:\Work\PROJECTS\RevitElectrico"
DATA_DIR = os.path.join(REVITELECTRICO_ROOT, "data")

FT_TO_M = 0.3048

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# 1. Cargar inventario de apartamentos (tiene paneles con insert_revit en metros)
inv_apto = load_json(os.path.join(DATA_DIR, "inventario_apartamentos_v01.json"))

# 2. Cargar maestro DXF global (tiene base_x_ft, base_y_ft en pies + dispositivos)
dxf_master = load_json(os.path.join(DATA_DIR, "dxf_master_global_all.json"))

# 3. Construir mapa: apto_key -> {panel_revit_x_m, panel_revit_y_m, panel_name}
panel_map = {}
for apto in inv_apto["apartamentos"]:
    key = apto["identificador_apartamento"]  # ej: "APT-B-15-P5"
    panel = apto.get("tablero", {})
    insert_revit = apto.get("insert_revit", {})
    panel_name = panel.get("nombre_panel_atributo") or panel.get("panel_name_revit_sugerido") or panel.get("identificador_ancla")
    if panel_name and insert_revit:
        panel_map[key] = {
            "panel_name": panel_name,
            "panel_x_m": insert_revit.get("x", 0),
            "panel_y_m": insert_revit.get("y", 0),
            "tipo": apto["tipo"],
            "nro": apto["nro"],
            "piso": apto["piso"],
        }

print("[INFO] Paneles encontrados en inventario_apartamentos:")
for k, v in panel_map.items():
    print("  {} -> panel='{}' @ ({:.3f}, {:.3f}) m".format(k, v["panel_name"], v["panel_x_m"], v["panel_y_m"]))

# 4. Construir mapa: apto_key (DXF) -> {base_x_m, base_y_m, devices, panel_name_dxf}
# Las claves en dxf_master son: "F01", "F02", "F17", "F18", "E06", etc.
# Necesitamos mapearlas a las claves de inventario: "APT-B-15-P5", etc.

# Mapeo manual DXF key -> inventario key
dxf_to_inv_key = {
    "F01": "APT-F-01-P5",
    "F01a": "APT-F-01a-P5",  # verificar si existe en inventario
    "F01b": "APT-F-01b-P5",
    "F02": "APT-F-02-P5",
    "F02a": "APT-F-02a-P5",
    "F02b": "APT-F-02b-P5",
    "F17": "APT-F-17-P5",
    "F17a": "APT-F-17a-P5",
    "F18": "APT-F-18-P5",
    "F18a": "APT-F-18a-P5",
    "E05": "APT-E-05-P5",
    "E06": "APT-E-06-P5",
    "E07": "APT-E-07-P5",
    "E07a": "APT-E-07a-P5",
    "E08": "APT-E-08-P5",
    "E08a": "APT-E-08a-P5",
    "B15": "APT-B-15-P5",
    "B16": "APT-B-16-P5",
    "C14": "APT-C-14-P5",
    "D13": "APT-D-13-P5",
}

# Verificar cuáles existen en inventario
print("\n[INFO] Verificando claves en inventario:")
for dxf_key, inv_key in dxf_to_inv_key.items():
    exists = inv_key in panel_map
    print("  DXF '{}' -> INV '{}' : {}".format(dxf_key, inv_key, "OK" if exists else "NO ENCONTRADO"))

# 5. Generar maestro de colocación
maestro = {
    "version": "v01",
    "fecha_generacion": "2026-11-19",
    "proyecto": "RevitElectrico - T5-SantaMarta",
    "nivel": "Piso 5",
    "elevacion_nivel_m": 13.22,
    "apartamentos": {}
}

for dxf_key, inv_key in dxf_to_inv_key.items():
    if dxf_key not in dxf_master["apartamentos"]:
        print("[WARN] DXF key '{}' no está en dxf_master_global_all.json".format(dxf_key))
        continue
    if inv_key not in panel_map:
        print("[WARN] Inventario key '{}' no tiene panel en inventario_apartamentos".format(inv_key))
        continue

    dxf_data = dxf_master["apartamentos"][dxf_key]
    panel_info = panel_map[inv_key]

    # Base DXF en pies -> metros
    base_x_m = dxf_data.get("base_x_ft", 0) * FT_TO_M
    base_y_m = dxf_data.get("base_y_ft", 0) * FT_TO_M

    # Panel en Revit (ya en metros)
    panel_x_m = panel_info["panel_x_m"]
    panel_y_m = panel_info["panel_y_m"]

    # Offset = panel_revit - base_dxf (en metros)
    offset_x_m = panel_x_m - base_x_m
    offset_y_m = panel_y_m - base_y_m

    # Dispositivos: convertir coords de pies a metros relativos a base DXF
    devices = []
    for dev in dxf_data.get("devices", []):
        # Coordenadas en dxf_master están en pies relativas al origen del bloque DXF
        x_m = dev.get("x", 0) * FT_TO_M
        y_m = dev.get("y", 0) * FT_TO_M
        devices.append({
            "nombre_dxf": dev.get("name", ""),
            "familia_revit": dev.get("familia_revit", ""),
            "tipo_revit": dev.get("tipo_revit", ""),
            "rotacion_grados": dev.get("rotation", 0),
            "posicion": {"x_m": x_m, "y_m": y_m},
            "altura_local_m": None,  # se llenará después según familia
        })

    # Alturas por familia (norma del proyecto)
    ALTURAS = {
        "M_Toma doble": 0.30,      # tomas 0.30 m (30 cm) - verificar: memoria dice 1.00 m para tomas de datos, 0.30 para tomas de corriente?
        "M_Comunicaciones": 0.30,  # datos 0.30 m (memoria: tomas de datos 1.00 m)
        "M_Interruptores": 1.10,   # interruptores 1.10 m
        "M_Pulsador - Interruptor": 1.10,  # timbre pulsador 1.10 m
        "M_Timbre": 2.40,          # campana 2.40 m
        "M_ClimatizacionV": 2.60,  # ventilador en techo ~2.60 m
        "M_Iluminacion": 2.60,     # luminarias en techo ~2.60 m
        "Consolidation_Point": 2.70,  # CP 2.70 m
        "EA": 1.50,                # extintor ~1.50 m
        "M_Caja de conexiones hexagonal": 0.30,
        "M_Toma de telefono - Datos": 0.30,
    }

    for dev in devices:
        fam = dev["familia_revit"]
        dev["altura_local_m"] = ALTURAS.get(fam, 0.30)

    maestro["apartamentos"][dxf_key] = {
        "inventario_key": inv_key,
        "panel_name": panel_info["panel_name"],
        "panel_revit_m": {"x": panel_x_m, "y": panel_y_m},
        "base_dxf_m": {"x": base_x_m, "y": base_y_m},
        "offset_m": {"x": offset_x_m, "y": offset_y_m},
        "offset_mm": {"x": round(offset_x_m * 1000), "y": round(offset_y_m * 1000)},
        "dispositivos": devices,
        "total_dispositivos": len(devices),
    }

    print("\n[INFO] {} (inv: {}):".format(dxf_key, inv_key))
    print("  Panel '{}' @ ({:.3f}, {:.3f}) m".format(panel_info["panel_name"], panel_x_m, panel_y_m))
    print("  Base DXF @ ({:.3f}, {:.3f}) m".format(base_x_m, base_y_m))
    print("  Offset = ({:.3f}, {:.3f}) m  ->  ({}, {}) mm".format(
        offset_x_m, offset_y_m, round(offset_x_m*1000), round(offset_y_m*1000)))
    print("  Dispositivos: {}".format(len(devices)))

# 6. Guardar
output_path = os.path.join(DATA_DIR, "maestro_colocacion_piso5.json")
save_json(maestro, output_path)
print("\n[OK] Maestro guardado en: {}".format(output_path))

# 7. Resumen
total_devs = sum(a["total_dispositivos"] for a in maestro["apartamentos"].values())
print("\n=== RESUMEN ===")
print("Apartamentos procesados: {}".format(len(maestro["apartamentos"])))
print("Total dispositivos: {}".format(total_devs))
for k, v in maestro["apartamentos"].items():
    print("  {}: {} dispositivos, offset=({},{}) mm, panel='{}'".format(
        k, v["total_dispositivos"], v["offset_mm"]["x"], v["offset_mm"]["y"], v["panel_name"]))