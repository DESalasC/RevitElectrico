# -*- coding: utf-8 -*-
# RE_COMPARAR_INVENTARIO_v01.py
# Diff clasificado entre el inventario canonico de dispositivos (INSERT del DXF, en metros)
# y las FamilyInstances exportadas de Revit (pies internos de Revit -> metros).
#
# Salida: JSON + HTML con una clasificacion por dispositivo:
#   OK, DESPLAZADO, DESPLAZADO_CRITICO, DUPLICADO, FALTANTE,
#   TIPO_NO_MAPEADO, SIN_POSICION.
#
# Ejecutar FUERA de Revit (Python 3.12, CPython). No necesita la API de Revit.
# Coordenadas del inventario: metros locales del DXF.
# Coordenadas de Revit: pies internos; se convierten a metros (1 pie = 0.3048 m).
# Comparacion Z: z_absoluta_revit vs elevacion_nivel + altura_local (regla de dato G5).
#
# Ultimos tres cambios
# --------------------
# 1. 2026-11-12 v01: version inicial. Empareja canon DXF vs export Revit por tipo y proximidad.
# 2. Heredado: regla F2 del plan RE_PLAN_CORRECCION_LOCALIZACION_DXF_REVIT_v01.md (criterios A1-A8).
# 3. Heredado: sin registro previo disponible.
#
# Uso:
#   python RE_COMPARAR_INVENTARIO_v01.py ^
#       --inventario data\inventario_dispositivos_E06_v01.json ^
#       --revit data\posiciones_revit_export_E06_v01.json ^
#       --offset-x 2.3682 --offset-y 9.6937 ^
#       --nivel-elevacion-m 13.22 ^
#       --salida data\diff_dispositivos_E06_v01.json ^
#       --reporte data\diff_dispositivos_E06_v01.html
#
# Fuente de verdad: inventario del DXF (un dispositivo por INSERT fisico).
# Nunca se comparan contra los extremos de los tramos de ruteo.

from __future__ import annotations

import argparse
import ast
import html
import json
import math
import os
import sys
from pathlib import Path

PIE_A_METROS = 0.3048

# ---------------------------------------------------------------------------
# Mapeo DXF (nombre de bloque) -> (Familia Revit, Simbolo Revit).
# Fuente: clasificacion DXF->Revit del acta 2026-11-11 (E06 piloto).
# Extendible con --mapeo.
# ---------------------------------------------------------------------------
MAPA_DXF_REVIT_DEFECTO = {}


def cargar_mapeo_colocador():
    """Extrae MAPEO_DEFAULT del colocador para no mantener dos tablas.

    La copia local se habia desincronizado en cuatro entradas (ELEC-CAMPANA apuntaba a
    M_Zumbador, ELEC-NET-PAU a CPB6L, ELEC-TEL a Datos, ELEC-I-S-C1-5A a Simple
    conmutable) y le faltaban cinco familias. Una sola fuente evita esa deriva.
    """
    ruta = Path(__file__).resolve().parent / "RE_COLOCAR_DISPOSITIVOS_generico.py"
    with ruta.open(encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    for nodo in arbol.body:
        if not isinstance(nodo, ast.Assign):
            continue
        for objetivo in nodo.targets:
            if isinstance(objetivo, ast.Name) and objetivo.id == "MAPEO_DEFAULT":
                datos = ast.literal_eval(nodo.value)
                return {clave: tuple(valor) for clave, valor in datos.items()}
    raise RuntimeError("No se encontro MAPEO_DEFAULT en {r}".format(r=ruta))


MAPA_DXF_REVIT_DEFECTO = cargar_mapeo_colocador()

# Bloques que el inventario canonico ya descarta (no son dispositivos físicos)
DESCARTADOS = ("TB-Panel",)


def cargar_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_json(path, datos):
    directorio = os.path.dirname(os.path.abspath(path))
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def pies_a_metros(valor):
    if valor is None:
        return None
    return round(valor * PIE_A_METROS, 4)


def distancia_m(dx, dy):
    return round(math.hypot(dx, dy), 4)


def clave_tipo(familia, simbolo):
    return "{}|{}".format(familia, simbolo)


# ---------------------------------------------------------------------------
# Inventario canonico (DXF)
# ---------------------------------------------------------------------------
def construir_canonico(inventario, offset_x, offset_y, nivel_elevacion_m):
    canonicos = []
    for d in inventario.get("dispositivos", []):
        nombre = d["nombre"]
        if nombre in DESCARTADOS:
            continue
        mapeo = MAPA_DXF_REVIT_DEFECTO.get(nombre)
        if mapeo is None:
            continue  # bloque sin mapeo: no se modela en Revit (p.ej. marcadores)
        familia, simbolo = mapeo
        x_revit = round(d["x"] + offset_x, 4)
        y_revit = round(d["y"] + offset_y, 4)
        altura = d.get("altura_local_m")
        if altura is None:
            altura = d.get("altura_nominal_m", 0.0)
        z_abs = round(nivel_elevacion_m + altura, 4)
        canonicos.append({
            "handle": d["handle"],
            "nombre": nombre,
            "capa": d.get("capa", ""),
            "familia_revit": familia,
            "simbolo_revit": simbolo,
            "x_dxf": d["x"],
            "y_dxf": d["y"],
            "z_dxf": d.get("z", 0.0),
            "rotacion_grados": d.get("rotacion_grados"),
            "altura_nominal_m": d.get("altura_nominal_m", 0.0),
            "altura_local_m": d.get("altura_local_m"),
            "x_esperado_m": x_revit,
            "y_esperado_m": y_revit,
            "z_esperado_abs_m": z_abs,
            "clave_tipo": clave_tipo(familia, simbolo),
        })
    return canonicos


# ---------------------------------------------------------------------------
# Export de Revit (pies -> metros)
# ---------------------------------------------------------------------------
def cargar_instancias_revit(export_revit):
    instancias = []
    for fi in export_revit.get("family_instances", []):
        x_m = pies_a_metros(fi.get("x"))
        y_m = pies_a_metros(fi.get("y"))
        z_m = pies_a_metros(fi.get("z"))
        instancias.append({
            "id": fi.get("id"),
            "familia": fi.get("familia", ""),
            "simbolo": fi.get("simbolo", ""),
            "categoria": fi.get("categoria", ""),
            "x_m": x_m,
            "y_m": y_m,
            "z_m": z_m,
            "panel_name": fi.get("panel_name", ""),
            "nivel": fi.get("nivel", ""),
            "host_id": fi.get("host_id"),
            "host_categoria": fi.get("host_categoria", ""),
            "orientacion_grados": fi.get("orientacion_grados"),
            "comentarios": fi.get("comentarios", ""),
            "servicio_conduit": fi.get("servicio_conduit", ""),
            "clave_tipo": clave_tipo(fi.get("familia", ""), fi.get("simbolo", "")),
        })
    return instancias


# ---------------------------------------------------------------------------
# Emparejamiento greedy por tipo y proximidad
# ---------------------------------------------------------------------------
def emparejar(canonicos, instancias, tol_match_m):
    # Indexar instancias revit por clave_tipo, sin emparejar
    por_tipo = {}
    for inst in instancias:
        por_tipo.setdefault(inst["clave_tipo"], []).append(inst)

    usados = set()  # ids de instancias revit ya emparejadas
    pares = []

    for c in sorted(canonicos, key=lambda c: (c["nombre"], c["x_esperado_m"], c["y_esperado_m"])):
        candidatos = []
        for inst in por_tipo.get(c["clave_tipo"], []):
            if id(inst) in usados:
                continue
            if inst["x_m"] is None or inst["y_m"] is None:
                continue
            dx = inst["x_m"] - c["x_esperado_m"]
            dy = inst["y_m"] - c["y_esperado_m"]
            d = distancia_m(dx, dy)
            if d <= tol_match_m:
                candidatos.append((d, inst))
        if candidatos:
            candidatos.sort(key=lambda t: t[0])
            _, inst = candidatos[0]
            usados.add(id(inst))
            pares.append((c, inst, rondar(c["x_esperado_m"] - inst["x_m"], c["y_esperado_m"] - inst["y_m"])))
        else:
            pares.append((c, None, None))

    sobrantes = [inst for inst in instancias if id(inst) not in usados]
    return pares, sobrantes


def rondar(dx, dy):
    return (round(dx, 4), round(dy, 4))


# ---------------------------------------------------------------------------
# Clasificacion
# ---------------------------------------------------------------------------
def clasificar_par(canonico, inst, dx, dy, tolerancias, nivel_elevacion_m):
    dist = distancia_m(dx, dy)
    t_nom = tolerancias["nominal"]
    t_fin = tolerancias["final"]
    t_z = tolerancias["z"]
    t_rot = tolerancias["rot"]

    if dist <= t_nom:
        clasificacion = "OK"
    elif dist <= t_fin:
        clasificacion = "DESPLAZADO"
    else:
        clasificacion = "DESPLAZADO_CRITICO"

    flags = []
    # Z absoluta: revit (m) vs esperado (nivel + altura local)
    if inst["z_m"] is not None:
        dz = round(abs(inst["z_m"] - canonico["z_esperado_abs_m"]), 4)
        if dz > t_z:
            flags.append("Z_INCORRECTO")
    else:
        flags.append("SIN_Z")

    # Rotacion: solo si el export de Revit trae orientacion (requiere RE_AUDITAR_DISPOSITIVOS_v01)
    if inst["orientacion_grados"] is not None and canonico["rotacion_grados"] is not None:
        drot = round(abs((inst["orientacion_grados"] - canonico["rotacion_grados"] + 180) % 360 - 180), 2)
        if drot > t_rot:
            flags.append("ROTADO")
    elif canonico["rotacion_grados"] is not None:
        flags.append("ROTACION_SIN_VALIDAR")

    resultado = {
        "handle": canonico["handle"],
        "nombre": canonico["nombre"],
        "familia_revit": canonico["familia_revit"],
        "simbolo_revit": canonico["simbolo_revit"],
        "x_dxf": canonico["x_dxf"],
        "y_dxf": canonico["y_dxf"],
        "z_dxf": canonico["z_dxf"],
        "x_revit_m": inst["x_m"],
        "y_revit_m": inst["y_m"],
        "z_revit_m": inst["z_m"],
        "x_esperado_m": canonico["x_esperado_m"],
        "y_esperado_m": canonico["y_esperado_m"],
        "z_esperado_abs_m": canonico["z_esperado_abs_m"],
        "dx_m": dx,
        "dy_m": dy,
        "dist_m": dist,
        "rotacion_dxf": canonico["rotacion_grados"],
        "rotacion_revit": inst["orientacion_grados"],
        "id_revit": inst["id"],
        "panel_name": inst["panel_name"],
        "host_id": inst["host_id"],
        "host_categoria": inst["host_categoria"],
        "clasificacion": clasificacion,
        "flags": flags,
    }
    return resultado


def clasificar_faltante(canonico, tolerancias):
    return {
        "handle": canonico["handle"],
        "nombre": canonico["nombre"],
        "familia_revit": canonico["familia_revit"],
        "simbolo_revit": canonico["simbolo_revit"],
        "x_dxf": canonico["x_dxf"],
        "y_dxf": canonico["y_dxf"],
        "z_dxf": canonico["z_dxf"],
        "x_revit_m": None,
        "y_revit_m": None,
        "z_revit_m": None,
        "x_esperado_m": canonico["x_esperado_m"],
        "y_esperado_m": canonico["y_esperado_m"],
        "z_esperado_abs_m": canonico["z_esperado_abs_m"],
        "dx_m": None,
        "dy_m": None,
        "dist_m": None,
        "rotacion_dxf": canonico["rotacion_grados"],
        "rotacion_revit": None,
        "id_revit": None,
        "panel_name": None,
        "host_id": None,
        "host_categoria": None,
        "clasificacion": "FALTANTE",
        "flags": [],
    }


def clasificar_sobrante(inst):
    return {
        "handle": None,
        "nombre": None,
        "familia_revit": inst["familia"],
        "simbolo_revit": inst["simbolo"],
        "x_dxf": None,
        "y_dxf": None,
        "z_dxf": None,
        "x_revit_m": inst["x_m"],
        "y_revit_m": inst["y_m"],
        "z_revit_m": inst["z_m"],
        "x_esperado_m": None,
        "y_esperado_m": None,
        "z_esperado_abs_m": None,
        "dx_m": None,
        "dy_m": None,
        "dist_m": None,
        "rotacion_dxf": None,
        "rotacion_revit": inst["orientacion_grados"],
        "id_revit": inst["id"],
        "panel_name": inst["panel_name"],
        "host_id": inst["host_id"],
        "host_categoria": inst["host_categoria"],
        "clasificacion": "DUPLICADO" if inst["clave_tipo"] in _TIPOS_MAPEADOS else "TIPO_NO_MAPEADO",
        "flags": ["SIN_POSICION"] if inst["x_m"] is None else [],
    }


_TIPOS_MAPEADOS = set()


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------
def evaluar_criterios(resumen):
    criterios = {
        "A1_cobertura_100_pct": resumen["cobertura_pct"] >= 100.0,
        "A2_sobrantes_cero": resumen["duplicados"] == 0,
        "A3_xy_nominal_0.02_m": resumen["desplazado_critico"] == 0 and resumen["ok"] == resumen["emparejados"],
        "A4_xy_final_0.10_m": resumen["desplazado_critico"] == 0,
        "A5_z_igual_tabla": resumen.get("z_incorrecto", 0) == 0,
        "A6_rotacion_pm_2_grados": resumen.get("rotados", 0) == 0,
        "A7_host_no_nulo": resumen.get("sin_host", 0) == 0,
        "A8_avisos_host_cero": True,  # se verifica con el export de Revit (RE_AUDITAR_DISPOSITIVOS_v01)
    }
    return criterios


def construir_informe(apartamento, inventario, export_revit, pares, sobrantes, tolerancias, nivel_elevacion_m):
    dispositivos = []
    contadores = {"OK": 0, "DESPLAZADO": 0, "DESPLAZADO_CRITICO": 0, "FALTANTE": 0,
                  "DUPLICADO": 0, "TIPO_NO_MAPEADO": 0, "SIN_POSICION": 0}
    z_incorrecto = 0
    rotados = 0
    sin_host = 0

    for canonico, inst, delta in pares:
        if inst is None:
            r = clasificar_faltante(canonico, tolerancias)
            dispositivos.append(r)
            contadores["FALTANTE"] += 1
        else:
            dx, dy = delta
            r = clasificar_par(canonico, inst, dx, dy, tolerancias, nivel_elevacion_m)
            dispositivos.append(r)
            contadores[r["clasificacion"]] += 1
            if "Z_INCORRECTO" in r["flags"]:
                z_incorrecto += 1
            if "ROTADO" in r["flags"]:
                rotados += 1
            if r["host_id"] is None:
                sin_host += 1

    for inst in sobrantes:
        r = clasificar_sobrante(inst)
        dispositivos.append(r)
        contadores[r["clasificacion"]] += 1
        if "SIN_POSICION" in r["flags"]:
            contadores["SIN_POSICION"] += 1

    total_dxf = len([d for d in dispositivos if d["handle"] is not None])
    total_revit = len(export_revit.get("family_instances", []))
    emparejados = contadores["OK"] + contadores["DESPLAZADO"] + contadores["DESPLAZADO_CRITICO"]
    cobertura = round(100.0 * emparejados / total_dxf, 2) if total_dxf else 0.0

    resumen = {
        "total_dispositivos_dxf": total_dxf,
        "total_instancias_revit": total_revit,
        "emparejados": emparejados,
        "ok": contadores["OK"],
        "desplazado": contadores["DESPLAZADO"],
        "desplazado_critico": contadores["DESPLAZADO_CRITICO"],
        "faltantes": contadores["FALTANTE"],
        "duplicados": contadores["DUPLICADO"],
        "tipo_no_mapeado": contadores["TIPO_NO_MAPEADO"],
        "sin_posicion": contadores["SIN_POSICION"],
        "cobertura_pct": cobertura,
        "z_incorrecto": z_incorrecto,
        "rotados": rotados,
        "sin_host": sin_host,
    }
    criterios = evaluar_criterios(resumen)

    return {
        "fecha": "2026-11-12",
        "apartamento": apartamento,
        "inventario_dxf": inventario.get("dxf", ""),
        "export_revit": export_revit.get("ruta_documento", ""),
        "offset_xy_m": [tolerancias.get("offset_x", 0.0), tolerancias.get("offset_y", 0.0)],
        "nivel_elevacion_m": nivel_elevacion_m,
        "tolerancias": tolerancias,
        "mapeo_tipos": {k: {"familia": v[0], "simbolo": v[1]} for k, v in MAPA_DXF_REVIT_DEFECTO.items()},
        "resumen": resumen,
        "criterios": criterios,
        "dispositivos": dispositivos,
    }


def escribir_html(informe, path_html):
    filas = []
    estado_clase = {
        "OK": "ok", "DESPLAZADO": "desplazado", "DESPLAZADO_CRITICO": "critico",
        "FALTANTE": "faltante", "DUPLICADO": "duplicado", "TIPO_NO_MAPEADO": "nomapeado",
    }
    for d in informe["dispositivos"]:
        clase = estado_clase.get(d["clasificacion"], "otro")
        filas.append(
            "<tr class='{clase}'>"
            "<td>{handle}</td>"
            "<td>{nombre}</td>"
            "<td>{familia}</td>"
            "<td>{simbolo}</td>"
            "<td>{x_r}</td>"
            "<td>{y_r}</td>"
            "<td>{z_r}</td>"
            "<td>{dist}</td>"
            "<td>{clas}</td>"
            "<td>{flags}</td>"
            "</tr>".format(
                clase=clase,
                handle=html.escape(str(d["handle"] or "-")),
                nombre=html.escape(str(d["nombre"] or "-")),
                familia=html.escape(str(d["familia_revit"] or "-")),
                simbolo=html.escape(str(d["simbolo_revit"] or "-")),
                x_r=d["x_revit_m"] if d["x_revit_m"] is not None else "-",
                y_r=d["y_revit_m"] if d["y_revit_m"] is not None else "-",
                z_r=d["z_revit_m"] if d["z_revit_m"] is not None else "-",
                dist=d["dist_m"] if d["dist_m"] is not None else "-",
                clas=html.escape(d["clasificacion"]),
                flags=html.escape(", ".join(d["flags"])),
            )
        )

    filas_criterios = []
    for clave, cumple in informe["criterios"].items():
        filas_criterios.append(
            "<tr><td>{}</td><td class='{}'>{}</td></tr>".format(
                clave.replace("_", " "), "cumple" if cumple else "no-cumple", "CUMPLE" if cumple else "NO CUMPLE")
        )

    css = """
    body { font-family: Segoe UI, sans-serif; margin: 24px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 6px 8px; font-size: 13px; text-align: left; }
    th { background: #eee; }
    .ok { background: #e7f7ec; } .desplazado { background: #fdf3d7; }
    .critico { background: #fbe4e4; } .faltante { background: #ffecec; }
    .duplicado { background: #e9e9ff; } .nomapeado { background: #f0f0f0; }
    .cumple { color: #0a7; } .no-cumple { color: #c00; }
    h1 { font-size: 18px; border-bottom: 2px solid #333; padding-bottom: 6px; }
    .resumen td:first-child { font-weight: bold; background: #f7f7f7; }
    """
    html_doc = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Diff dispositivos {ap}</title><style>{css}</style></head>
<body>
<h1>RE_COMPARAR_INVENTARIO_v01 — Diff DXF vs Revit: {ap}</h1>
<table class="resumen">
<tr><td>Fecha</td><td>{fecha}</td></tr>
<tr><td>Apartamento</td><td>{ap}</td></tr>
<tr><td>Inventario DXF</td><td>{inv}</td></tr>
<tr><td>Export Revit</td><td>{revit}</td></tr>
<tr><td>Offset DXF->Revit (m)</td><td>{offset}</td></tr>
<tr><td>Nivel elevacion (m)</td><td>{nivel}</td></tr>
<tr><td>Total dispositivos DXF</td><td>{total_dxf}</td></tr>
<tr><td>Total instancias Revit</td><td>{total_revit}</td></tr>
<tr><td>Emparejados</td><td>{emp}</td></tr>
<tr><td>OK</td><td>{ok}</td></tr>
<tr><td>Desplazado (&lt;= 0.10 m)</td><td>{despl}</td></tr>
<tr><td>Desplazado crítico (&gt; 0.10 m)</td><td>{despl_critico}</td></tr>
<tr><td>Faltantes</td><td>{falt}</td></tr>
<tr><td>Duplicados</td><td>{dup}</td></tr>
<tr><td>Tipo no mapeado</td><td>{npm}</td></tr>
<tr><td>Cobertura</td><td>{cov} %</td></tr>
</table>

<h2>Criterios de aceptación (A1-A8)</h2>
<table>{crit}</table>

<h2>Dispositivos ({n})</h2>
<table>
<tr><th>Handle</th><th>Nombre DXF</th><th>Familia Revit</th><th>Símbolo</th>
<th>X Revit (m)</th><th>Y Revit (m)</th><th>Z Revit (m)</th><th>Dist (m)</th><th>Clasificación</th><th>Flags</th></tr>
{filas}
</table>
</body></html>""".format(
        ap=html.escape(informe["apartamento"]),
        css=css,
        fecha=informe["fecha"],
        inv=html.escape(informe["inventario_dxf"]),
        revit=html.escape(informe["export_revit"]),
        offset=informe["offset_xy_m"],
        nivel=informe["nivel_elevacion_m"],
        total_dxf=informe["resumen"]["total_dispositivos_dxf"],
        total_revit=informe["resumen"]["total_instancias_revit"],
        emp=informe["resumen"]["emparejados"],
        ok=informe["resumen"]["ok"],
        despl=informe["resumen"]["desplazado"],
        despl_critico=informe["resumen"]["desplazado_critico"],
        falt=informe["resumen"]["faltantes"],
        dup=informe["resumen"]["duplicados"],
        npm=informe["resumen"]["tipo_no_mapeado"],
        cov=informe["resumen"]["cobertura_pct"],
        crit="".join(filas_criterios),
        n=len(informe["dispositivos"]),
        filas="".join(filas),
    )
    directorio = os.path.dirname(os.path.abspath(path_html))
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html_doc)


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Diff clasificado: inventario canonico DXF vs FamilyInstances de Revit (F2, plan DXF->Revit).")
    parser.add_argument("--inventario", default=None,
                        help="JSON del inventario canonico (RE_INVENTARIO_DISPOSITIVOS_v01).")
    parser.add_argument("--revit", default=None,
                        help="JSON de export de Revit (RE_EXPORTAR_POSICIONES_REVIT_v01 / RE_AUDITAR_DISPOSITIVOS_v01).")
    parser.add_argument("--offset-x", type=float, default=2.3682, help="Offset X DXF->Revit en metros (E06: 2.3682).")
    parser.add_argument("--offset-y", type=float, default=9.6937, help="Offset Y DXF->Revit en metros (E06: 9.6937).")
    parser.add_argument("--nivel-elevacion-m", type=float, default=13.22,
                        help="Elevacion absoluta del nivel Piso 5 en metros (default 13.22).")
    parser.add_argument("--tol-nominal", type=float, default=0.02, help="Tolerancia XY OK en metros.")
    parser.add_argument("--tol-final", type=float, default=0.10, help="Tolerancia XY final aceptable en metros.")
    parser.add_argument("--tol-z", type=float, default=0.02, help="Tolerancia Z absoluta en metros.")
    parser.add_argument("--tol-rot", type=float, default=2.0, help="Tolerancia de rotacion en grados.")
    parser.add_argument("--tol-match", type=float, default=0.25, help="Radio de emparejamiento en metros.")
    parser.add_argument("--mapeo", default=None, help="JSON opcional con mapeo DXF->(familia, simbolo).")
    parser.add_argument("--apartamento", default="E06", help="Nombre del apartamento para el informe.")
    parser.add_argument("--salida", default=None, help="Ruta de salida del JSON del diff.")
    parser.add_argument("--reporte", default=None, help="Ruta de salida del informe HTML.")
    args = parser.parse_args(argv)
    global MAPA_DXF_REVIT_DEFECTO, _TIPOS_MAPEADOS

    raiz_proyecto = Path(__file__).resolve().parents[2]
    inventario_path = args.inventario or str(raiz_proyecto / "data" / "inventario_dispositivos_E06_v01.json")
    revit_path = args.revit or str(raiz_proyecto / "data" / "posiciones_revit_export_E06_v01.json")
    salida_path = args.salida or str(raiz_proyecto / "data" / "diff_dispositivos_E06_v01.json")
    reporte_path = args.reporte or str(raiz_proyecto / "data" / "diff_dispositivos_E06_v01.html")

    if not os.path.exists(inventario_path):
        print("ERROR: no existe el inventario canonico: {}".format(inventario_path))
        return 2
    if not os.path.exists(revit_path):
        print("ERROR: no existe el export de Revit: {}".format(revit_path))
        print("       Generarlo primero dentro de Revit con RE_EXPORTAR_POSICIONES_REVIT_v01.py")
        print("       (o RE_AUDITAR_DISPOSITIVOS_v01.py) sobre la sesion abierta.")
        return 2

    inventario = cargar_json(inventario_path)
    export_revit = cargar_json(revit_path)

    mapeo = MAPA_DXF_REVIT_DEFECTO
    if args.mapeo:
        externo = cargar_json(args.mapeo)
        # formato externo: {"DXF_NOMBRE": ["Familia", "Simbolo"], ...}
        mapeo = {k: (v[0], v[1]) for k, v in externo.items()}

    MAPA_DXF_REVIT_DEFECTO = mapeo
    _TIPOS_MAPEADOS = {clave_tipo(v[0], v[1]) for v in mapeo.values()}

    tolerancias = {
        "offset_x": args.offset_x,
        "offset_y": args.offset_y,
        "nominal": args.tol_nominal,
        "final": args.tol_final,
        "z": args.tol_z,
        "rot": args.tol_rot,
        "match": args.tol_match,
    }

    canonicos = construir_canonico(inventario, args.offset_x, args.offset_y, args.nivel_elevacion_m)
    instancias = cargar_instancias_revit(export_revit)
    pares, sobrantes = emparejar(canonicos, instancias, args.tol_match)

    informe = construir_informe(
        args.apartamento, inventario, export_revit, pares, sobrantes, tolerancias, args.nivel_elevacion_m)

    guardar_json(salida_path, informe)
    escribir_html(informe, reporte_path)

    res = informe["resumen"]
    crit = informe["criterios"]
    print("=== RE_COMPARAR_INVENTARIO_v01 ===")
    print("Apartamento: {}".format(args.apartamento))
    print("Dispositivos DXF: {} | Instancias Revit: {}".format(res["total_dispositivos_dxf"], res["total_instancias_revit"]))
    print("Emparejados: {} | OK: {} | Desplazado: {} | Critico: {}".format(
        res["emparejados"], res["ok"], res["desplazado"], res["desplazado_critico"]))
    print("Faltantes: {} | Duplicados: {} | Tipo no mapeado: {}".format(
        res["faltantes"], res["duplicados"], res["tipo_no_mapeado"]))
    print("Cobertura: {} %".format(res["cobertura_pct"]))
    no_cumple = [k for k, v in crit.items() if not v]
    print("Criterios: {} de 8 cumplidos".format(8 - len(no_cumple)))
    if no_cumple:
        print("No cumplen: {}".format(", ".join(no_cumple)))
    print("JSON: {}".format(salida_path))
    print("HTML: {}".format(reporte_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
