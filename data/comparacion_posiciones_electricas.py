#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comparacion de posiciones electricas: DXF original vs modelo generado vs archivo activo de Revit (Piso 5).

NOTA IMPORTANTE sobre sistemas de coordenadas:
  - DXF original y modelo generado comparten el sistema LOCAL del apartamento F 02
    (origen en la esquina del bloque, sin la transformacion de edificio).
  - Revit activo (estado_modelo_v01.json) usa coordenadas GLOBALES del edificio
    (origen en el cero del proyecto, Z ya en elevación real de Piso 5 = 43.3727 m).
  - No hay en los archivos un offset documentado que relacione el sistema local
    del apartamento con el sistema global de Revit, por tanto la comparacion
    directa DXF <-> Revit activo por coordenadas absolutas no es valida sin ese
    offset. Este reporte compara lo comparable y documenta el gap.

Entradas:
  - apartamento_F_02_dispositivos.json  (posiciones absolutas DXF, fuente original)
  - modelo_apt_F02_piso5.json           (modelo generado, posiciones locales)
  - estado_modelo_v01.json              (archivo activo de Revit, posiciones globales Piso 5)

Salida:
  - reporte_desviaciones_electricas.json (resultado detallado)
"""

import json
import os

BASE = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta"
PRUEBA_MODELO = os.path.join(BASE, "3.-Proceso", "_prueba_modelado")
DATA = os.path.join(BASE, "data")

# Transformacion confirmada (sesion 2026-10-20) entre DXF y sistema Revit del edificio
DX = 6.49
DY = 10.2234
ELEVACION_PISO5 = 43.3727


def cargar_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cargar_dispositivos_dxf():
    path = os.path.join(PRUEBA_MODELO, "apartamento_F_02_dispositivos.json")
    datos = cargar_json(path)
    dispositivos = []
    for d in datos.get("dispositivos_internos", []):
        dispositivos.append({
            "nombre": d.get("nombre_bloque_hijo", ""),
            "capa": d.get("capa", ""),
            "x_dxf": round(d.get("x_abs_dxf", 0), 4),
            "y_dxf": round(d.get("y_abs_dxf", 0), 4),
            "x_revit_esperado_global": round(d.get("x_abs_dxf", 0) + DX, 4),
            "y_revit_esperado_global": round(d.get("y_abs_dxf", 0) + DY, 4),
            "rotacion": d.get("rotacion", 0),
            "orden": d.get("orden", 0),
        })
    return dispositivos


def cargar_modelo_generado():
    path = os.path.join(PRUEBA_MODELO, "modelo_apt_F02_piso5.json")
    datos = cargar_json(path)
    dispositivos = []
    for e in datos.get("elementos", []):
        if e.get("tipo") == "dispositivo":
            dispositivos.append({
                "nombre": e.get("nombre", ""),
                "capa": e.get("capa", ""),
                "x_modelo": round(e.get("x", 0), 4),
                "y_modelo": round(e.get("y", 0), 4),
                "z_modelo": round(e.get("z", 0), 4),
                "altura_m": e.get("altura_m", 0),
                "anfitrion": e.get("anfitrion", ""),
                "rotacion": e.get("rotacion", 0),
                "familia": e.get("familia", ""),
                "simbolo": e.get("simbolo", ""),
                "es_marcador": e.get("es_marcador", False),
            })
    return dispositivos


def cargar_estado_revit_activo():
    path = os.path.join(DATA, "estado_modelo_v01.json")
    datos = cargar_json(path)
    dispositivos = []
    for e in datos.get("instancias_electricas", []):
        punto = e.get("punto", [0, 0, 0])
        dispositivos.append({
            "id": e.get("id", 0),
            "familia": e.get("familia", ""),
            "categoria": e.get("categoria", ""),
            "x_revit": round(punto[0], 4),
            "y_revit": round(punto[1], 4),
            "z_revit": round(punto[2], 4),
            "nivel_id": e.get("nivel_id", -1),
            "host": e.get("host"),
            "face_based": e.get("face_based", False),
            "oculto_en_vista": e.get("oculto_en_vista", False),
        })
    return dispositivos


def dist_xy(p1, p2):
    return round(((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5, 4)


def match_por_nombre(dispositivo, lista, clave_nombre="nombre"):
    """Busca coincidencia exacta por nombre normalizado."""
    nom = str(dispositivo.get(clave_nombre, "")).strip().upper()
    for item in lista:
        if str(item.get("nombre", "")).strip().upper() == nom:
            return item
    return None


def main():
    print("=== CARGANDO ARCHIVOS ===")
    dxf = cargar_dispositivos_dxf()
    modelo = cargar_modelo_generado()
    revit = cargar_estado_revit_activo()
    print(f"Dispositivos DXF originales: {len(dxf)}")
    print(f"Dispositivos en modelo generado: {len(modelo)}")
    print(f"Instancias electricas en Revit activo: {len(revit)}")

    # ---- Filtro Revit solo Piso 5 (z 43.0 - 45.0) ----
    revit_piso5 = [r for r in revit if 43.0 <= r["z_revit"] <= 45.0]
    sin_nivel = [r for r in revit if r["nivel_id"] == -1]
    con_nivel = [r for r in revit if r["nivel_id"] != -1]
    print(f"Instancias en rango Piso 5 (z 43-45): {len(revit_piso5)}")
    print(f"  Sin nivel (nivel_id=-1): {len(sin_nivel)}")
    print(f"  Con nivel: {len(con_nivel)}")

    # =========================================================
    # 1. Comparacion DXF original -> Modelo generado (mismo sistema LOCAL)
    # =========================================================
    print("\n=== 1. DXF ORIGINAL -> MODELO GENERADO (sistema local) ===")
    comp_dxf_modelo = []
    desviaciones_dm = []
    for d in dxf:
        m = match_por_nombre(d, modelo)
        if m:
            dx = m["x_modelo"] - d["x_dxf"]
            dy = m["y_modelo"] - d["y_dxf"]
            dz = m["z_modelo"] - (ELEVACION_PISO5 + (m["altura_m"] or 0))
            comp_dxf_modelo.append({
                "nombre": d["nombre"],
                "capa": d["capa"],
                "x_dxf": d["x_dxf"],
                "y_dxf": d["y_dxf"],
                "x_modelo": m["x_modelo"],
                "y_modelo": m["y_modelo"],
                "z_modelo": m["z_modelo"],
                "desv_x": round(dx, 4),
                "desv_y": round(dy, 4),
                "desv_z": round(dz, 4),
                "dist_xy": dist_xy((d["x_dxf"], d["y_dxf"]), (m["x_modelo"], m["y_modelo"])),
                "match": "nombre",
                "familia_modelo": m["familia"],
                "anfitrion": m["anfitrion"],
            })
            desviaciones_dm.append(comp_dxf_modelo[-1])
        else:
            comp_dxf_modelo.append({
                "nombre": d["nombre"],
                "capa": d["capa"],
                "x_dxf": d["x_dxf"],
                "y_dxf": d["y_dxf"],
                "x_modelo": None,
                "y_modelo": None,
                "z_modelo": None,
                "desv_x": None,
                "desv_y": None,
                "desv_z": None,
                "dist_xy": None,
                "match": "NO_ENCONTRADO_EN_MODELO",
                "familia_modelo": None,
                "anfitrion": None,
            })

    if desviaciones_dm:
        dists = [c["dist_xy"] for c in desviaciones_dm]
        desv_x = [c["desv_x"] for c in desviaciones_dm]
        desv_y = [c["desv_y"] for c in desviaciones_dm]
        resumen_dm = {
            "total": len(desviaciones_dm),
            "desv_x_media": round(sum(desv_x) / len(desv_x), 4),
            "desv_y_media": round(sum(desv_y) / len(desv_y), 4),
            "desv_x_max": round(max(desv_x), 4),
            "desv_y_max": round(max(desv_y), 4),
            "dist_xy_media": round(sum(dists) / len(dists), 4),
            "dist_xy_max": round(max(dists), 4),
            "dentro_0_15m": sum(1 for d in dists if d <= 0.15),
            "fuera_0_15m": sum(1 for d in dists if d > 0.15),
        }
    else:
        resumen_dm = {"total": 0, "error": "Sin coincidencias DXF -> Modelo"}

    print(json.dumps(resumen_dm, indent=2, ensure_ascii=False))

    # =========================================================
    # 2. Comparacion Modelo generado -> Revit activo (Piso 5)
    #    Por nombre de familia + proximidad relativa (sistemas distintos)
    # =========================================================
    print("\n=== 2. MODELO GENERADO -> REVIT ACTIVO (Piso 5) ===")
    comp_modelo_revit = []
    for m in modelo:
        if m["es_marcador"]:
            continue
        # Buscar en Revit por familia coincidente y proximidad XY relativa
        candidatos = [r for r in revit_piso5 if m["familia"] and r["familia"] and m["familia"].upper() in r["familia"].upper()]
        mejor = None
        mejor_dist = float("inf")
        for r in candidatos:
            d = dist_xy((m["x_modelo"], m["y_modelo"]), (r["x_revit"], r["y_revit"]))
            if d < mejor_dist:
                mejor_dist = d
                mejor = r
        if mejor:
            dx = mejor["x_revit"] - m["x_modelo"]
            dy = mejor["y_revit"] - m["y_modelo"]
            dz = mejor["z_revit"] - m["z_modelo"]
            comp_modelo_revit.append({
                "nombre": m["nombre"],
                "capa": m["capa"],
                "x_modelo": m["x_modelo"],
                "y_modelo": m["y_modelo"],
                "z_modelo": m["z_modelo"],
                "x_revit_activo": mejor["x_revit"],
                "y_revit_activo": mejor["y_revit"],
                "z_revit_activo": mejor["z_revit"],
                "desv_x": round(dx, 4),
                "desv_y": round(dy, 4),
                "desv_z": round(dz, 4),
                "dist_xy": mejor_dist,
                "id_revit": mejor["id"],
                "nivel_id_revit": mejor["nivel_id"],
                "host_revit": mejor["host"],
                "familia_revit": mejor["familia"],
                "match": "familia+proximidad",
            })
        else:
            comp_modelo_revit.append({
                "nombre": m["nombre"],
                "capa": m["capa"],
                "x_modelo": m["x_modelo"],
                "y_modelo": m["y_modelo"],
                "z_modelo": m["z_modelo"],
                "x_revit_activo": None,
                "y_revit_activo": None,
                "z_revit_activo": None,
                "desv_x": None,
                "desv_y": None,
                "desv_z": None,
                "dist_xy": None,
                "id_revit": None,
                "nivel_id_revit": None,
                "host_revit": None,
                "familia_revit": None,
                "match": "NO_ENCONTRADO_EN_REVIT",
            })

    # =========================================================
    # 3. Comparacion DXF original -> Revit activo (Piso 5)
    #    Se reporta el offset esperado vs real (sistemas distintos, gap documentado)
    # =========================================================
    print("\n=== 3. DXF ORIGINAL -> REVIT ACTIVO (Piso 5) ===")
    comp_dxf_revit = []
    for d in dxf:
        x_esp = d["x_revit_esperado_global"]
        y_esp = d["y_revit_esperado_global"]
        # Buscar el mas cercano en Revit Piso 5 sin restriccion de familia
        mejor = None
        mejor_dist = float("inf")
        for r in revit_piso5:
            dd = dist_xy((x_esp, y_esp), (r["x_revit"], r["y_revit"]))
            if dd < mejor_dist:
                mejor_dist = dd
                mejor = r
        if mejor:
            dx = mejor["x_revit"] - x_esp
            dy = mejor["y_revit"] - y_esp
            comp_dxf_revit.append({
                "nombre": d["nombre"],
                "capa": d["capa"],
                "x_dxf": d["x_dxf"],
                "y_dxf": d["y_dxf"],
                "x_revit_esperado_global": x_esp,
                "y_revit_esperado_global": y_esp,
                "x_revit_activo": mejor["x_revit"],
                "y_revit_activo": mejor["y_revit"],
                "z_revit_activo": mejor["z_revit"],
                "desv_x_dxf_vs_revit": round(dx, 4),
                "desv_y_dxf_vs_revit": round(dy, 4),
                "dist_xy": mejor_dist,
                "id_revit": mejor["id"],
                "nivel_id_revit": mejor["nivel_id"],
                "host_revit": mejor["host"],
                "familia_revit": mejor["familia"],
                "match": "proximidad_global",
                "nota": "Sistemas de coordenadas distintos: offset DXF->Revit no documentado en archivos",
            })
        else:
            comp_dxf_revit.append({
                "nombre": d["nombre"],
                "capa": d["capa"],
                "x_dxf": d["x_dxf"],
                "y_dxf": d["y_dxf"],
                "x_revit_esperado_global": x_esp,
                "y_revit_esperado_global": y_esp,
                "x_revit_activo": None,
                "y_revit_activo": None,
                "z_revit_activo": None,
                "desv_x_dxf_vs_revit": None,
                "desv_y_dxf_vs_revit": None,
                "dist_xy": None,
                "id_revit": None,
                "nivel_id_revit": None,
                "host_revit": None,
                "familia_revit": None,
                "match": "NO_ENCONTRADO_EN_REVIT",
            })

    # Resumen DXF -> Revit
    validos = [c for c in comp_dxf_revit if c["dist_xy"] is not None]
    if validos:
        dists = [c["dist_xy"] for c in validos]
        resumen_dr = {
            "total_comparados": len(validos),
            "dist_xy_media": round(sum(dists) / len(dists), 4),
            "dist_xy_max": round(max(dists), 4),
            "dentro_0_15m": sum(1 for d in dists if d <= 0.15),
            "fuera_0_15m": sum(1 for d in dists if d > 0.15),
            "nota": "Offset entre sistema local (DXF) y global (Revit) no documentado — desviaciones absolutas no son directamente interpretables sin ese offset",
        }
    else:
        resumen_dr = {"total_comparados": 0, "error": "Sin coincidencias DXF -> Revit activo"}

    reporte = {
        "fecha_analisis": "2026-10-27",
        "nivel": "Piso 5",
        "elevacion_nivel_m": ELEVACION_PISO5,
        "transformacion_dxf_a_revit_global": {"DX": DX, "DY": DY, "tipo": "traslacion pura sin espejo"},
        "limitacion_sistemas_coordenadas": {
            "dxf": "Local del apartamento F 02 (origen esquina bloque)",
            "modelo_generado": "Local del apartamento F 02 (mismo sistema que DXF)",
            "revit_activo": "Global del edificio (origen cero del proyecto)",
            "gap": "No hay offset documentado entre sistema local del apartamento y global de Revit",
            "implicacion": "Comparacion DXF <-> Revit activo por coordenadas absolutas no es valida sin ese offset",
        },
        "conteos": {
            "dispositivos_dxf_originales": len(dxf),
            "dispositivos_modelo_generado": len(modelo),
            "instancias_electricas_revit_activo": len(revit),
            "instancias_en_rango_piso5": len(revit_piso5),
            "instancias_sin_nivel": len(sin_nivel),
            "instancias_con_nivel": len(con_nivel),
            "conduits_en_revit": 0,
        },
        "resumen_dxf_vs_modelo": resumen_dm,
        "resumen_dxf_vs_revit": resumen_dr,
        "comparaciones_dxf_vs_modelo": comp_dxf_modelo,
        "comparaciones_modelo_vs_revit": comp_modelo_revit,
        "comparaciones_dxf_vs_revit": comp_dxf_revit,
    }

    out = os.path.join(DATA, "reporte_desviaciones_electricas.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)
    print(f"\n=== REPORTE GUARDADO: {out} ===")


if __name__ == "__main__":
    main()
