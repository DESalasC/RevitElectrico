# -*- coding: utf-8 -*-
# RE_INVENTARIO_DISPOSITIVOS_v01.py
# Construye el inventario canónico de dispositivos eléctricos de un apartamento
# a partir de los INSERT de su archivo DXF.
#
# Salida: JSON con un dispositivo por INSERT físico (sin marcadores ni panel ancla),
#         incluyendo handle, bloque, capa, coordenadas, rotación y altura de tabla.
#
# Ejecutar fuera de Revit (Python 3 estándar, requiere ezdxf).
#
# Uso:
#   python RE_INVENTARIO_DISPOSITIVOS_v01.py \
#       --dxf ArchivosBase\Apartamento Tipo E 06.dxf \
#       --salida data/inventario_dispositivos_E06_v01.json \
#       [--tabla data/alturas_dispositivos_v01.json]
#
# Fuente de verdad: los INSERT del DXF (uno por aparato físico).
# Nunca se usan los extremos de los tramos de ruteo como lista de dispositivos.

import argparse
import json
import math
import os
import sys

try:
    import ezdxf
except Exception as exc:
    print("ERROR: se requiere ezdxf (pip install ezdxf): {}".format(exc))
    sys.exit(1)

# ---------------------------------------------------------------------------
# Bloques que son marcadores de conductor (no dispositivos físicos)
# ---------------------------------------------------------------------------
MARCARES_CONDUCTOR = (
    "1FTN", "2FT2N", "1FTR", "1FTN2R", "1FTNR", "1TNR", "2F2N1T1R",
)

# ---------------------------------------------------------------------------
# Carga y guardado de JSON (Python 3)
# ---------------------------------------------------------------------------
def cargar_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_json(path, datos):
    directorio = os.path.dirname(path)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# Altura nominal por tipo de dispositivo (metros sobre el piso/techo de referencia)
# Puede sobreescribirse con una tabla externa.
# ---------------------------------------------------------------------------
ALTURAS_DEFAULT = {
    "ELEC-T-D-t-15A": 1.10,
    "ELEC-T-GFCI-t-15A": 1.10,
    "ELEC-TEL": 0.30,
    "ELEC-I-S-1-5A": 1.10,
    "ELEC-I-S-C1-5A": 1.10,
    "Bala Stil Led 10W": 2.60,
    "Bala Stil Led 13W": 2.60,
    "Bala Stil Led 22W": 2.60,
    "ELEC-F-VENT": 2.60,
    "ELEC-F-CONTROL": 1.20,
    "ELEC-TIMBRE": 1.20,
    "ELEC-CAMPANA": 1.20,
    "S3": 1.10,
    "ELEC-NET-PAU": 1.10,
}

# ---------------------------------------------------------------------------
# Extraer dispositivos del DXF
# ---------------------------------------------------------------------------
def extraer_dispositivos(dxf_path, alturas=None):
    if alturas is None:
        alturas = ALTURAS_DEFAULT

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    dispositivos = []
    descartados = []

    for e in msp.query("INSERT"):
        nombre = e.dxf.name
        insert = e.dxf.insert

        # Clasificación
        if nombre in MARCARES_CONDUCTOR:
            descartados.append({"nombre": nombre, "motivo": "marcador de conductor", "handle": str(e.dxf.handle)})
            continue
        if nombre == "TB-Panel":
            descartados.append({"nombre": nombre, "motivo": "panel ancla de referencia", "handle": str(e.dxf.handle)})
            continue

        rot = round(e.dxf.get("rotation", 0), 1)
        altura = alturas.get(nombre, 0.0)

        dispositivos.append({
            "handle": str(e.dxf.handle),
            "nombre": nombre,
            "capa": e.dxf.layer,
            "x": round(float(insert.x), 4),
            "y": round(float(insert.y), 4),
            "z": round(float(insert.z), 4),
            "rotacion_grados": rot,
            "altura_nominal_m": altura,
        })

    # Ordenar por coordenadas para lectura estable (Y descendente, luego X)
    dispositivos.sort(key=lambda d: (-d["y"], d["x"]))

    return dispositivos, descartados

# ---------------------------------------------------------------------------
# Detectar pares cercanos del mismo bloque (candidatos a duplicados de dibujo)
# ---------------------------------------------------------------------------
def detectar_pares_cercanos(dispositivos, umbral_m=0.20):
    pares = []
    for i in range(len(dispositivos)):
        for j in range(i + 1, len(dispositivos)):
            a, b = dispositivos[i], dispositivos[j]
            if a["nombre"] != b["nombre"]:
                continue
            dist = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            if dist < umbral_m:
                pares.append({
                    "tipo": a["nombre"],
                    "dist_m": round(dist, 4),
                    "a": {"handle": a["handle"], "x": a["x"], "y": a["y"]},
                    "b": {"handle": b["handle"], "x": b["x"], "y": b["y"]},
                })
    pares.sort(key=lambda p: p["dist_m"])
    return pares

# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Inventario canónico de dispositivos desde INSERT del DXF")
    parser.add_argument("--dxf", required=True, help="Ruta al archivo DXF del apartamento")
    parser.add_argument("--salida", required=True, help="Ruta de salida del JSON de inventario")
    parser.add_argument("--tabla", default=None, help="JSON con alturas por tipo (opcional)")
    parser.add_argument("--umbral-pares", type=float, default=0.20, help="Umbral m para pares cercanos")
    args = parser.parse_args()

    alturas = ALTURAS_DEFAULT
    if args.tabla:
        try:
            tabla = cargar_json(args.tabla)
            if isinstance(tabla, dict):
                alturas.update({k: float(v) for k, v in tabla.items()})
        except Exception as exc:
            print("ADVERTENCIA: no se pudo cargar tabla de alturas: {}".format(exc))

    dispositivos, descartados = extraer_dispositivos(args.dxf, alturas)
    pares = detectar_pares_cercanos(dispositivos, umbral_m=args.umbral_pares)

    inventario = {
        "fecha": "2026-11-11",
        "dxf": os.path.abspath(args.dxf),
        "fuente": "INSERT del DXF",
        "regla": "un dispositivo por INSERT fisico, nunca por extremos de tramos de ruteo",
        "umbral_pares_cercanos_m": args.umbral_pares,
        "resumen": {
            "inserts_leidos": len(dispositivos) + len(descartados),
            "dispositivos": len(dispositivos),
            "marcadores_descartados": len([d for d in descartados if d["motivo"] == "marcador de conductor"]),
            "paneles_descartados": len([d for d in descartados if d["motivo"] == "panel ancla de referencia"]),
            "pares_cercanos": len(pares),
        },
        "dispositivos": dispositivos,
        "descartados": descartados,
        "pares_cercanos": pares,
    }

    guardar_json(args.salida, inventario)

    print("=== RE_INVENTARIO_DISPOSITIVOS_v01 ===")
    print("DXF: {}".format(args.dxf))
    print("Inserts leidos: {}".format(inventario["resumen"]["inserts_leidos"]))
    print("Dispositivos: {}".format(inventario["resumen"]["dispositivos"]))
    print("Marcadores descartados: {}".format(inventario["resumen"]["marcadores_descartados"]))
    print("Paneles descartados: {}".format(inventario["resumen"]["paneles_descartados"]))
    print("Pares cercanos (<{} m): {}".format(args.umbral_pares, inventario["resumen"]["pares_cercanos"]))
    print("JSON guardado en: {}".format(args.salida))
    return inventario


if __name__ == "__main__":
    main()
