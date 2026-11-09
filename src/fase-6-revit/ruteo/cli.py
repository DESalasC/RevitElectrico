# -*- coding: utf-8 -*-
"""CLI del pipeline de ruteo.

Uso:
  python cli.py --dxf <plano.dxf> --out data/ruteo_F02_v01.json --html data/ruteo_F02_v01.html

Sin argumentos usa los defaults del proyecto (apartamento F 02, PVC, 12 AWG).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

from config import ConfigError, cargar_config
from dxf_lector import leer_dxf, resumen_contenido
from modelos import Punto2D
from reporte import escribir_html, imprimir_resumen
from ruteador import dist_punto_punto, rutear
from visor import escribir_visor
from visor_3d import escribir_visor_3d

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DEF_DXF = os.path.join(RAIZ, "ArchivosBase", "Apartamento Tipo F 02.dxf")
DEF_CONFIG = os.path.join(RAIZ, "config", "ruteo_config_v04.json")
DEF_OUT = os.path.join(RAIZ, "data", "ruteo_apartamento_F02_v03.json")
DEF_HTML = os.path.join(RAIZ, "data", "ruteo_apartamento_F02_v03.html")
DEF_VISOR = os.path.join(RAIZ, "data", "visor_ruteo_F02_v03.html")


def _resolver(ruta: str) -> str:
    return ruta if os.path.isabs(ruta) else os.path.join(RAIZ, ruta)


def validar_contra_modelo(contenido, ruta_json_mapa: str, tolerancia: float = 0.20) -> dict:
    """Cruza los dispositivos del DXF con los ya modelados en Revit (JSON del mapa)."""
    with open(ruta_json_mapa, "r", encoding="utf-8-sig") as f:
        mapa = json.load(f)
    esperados = mapa.get("acciones_modelar", [])
    puntos_dxf = [(d.x, d.y) for d in contenido.dispositivos]
    encontrados = 0
    faltantes = []
    for item in esperados:
        p: Punto2D = (float(item.get("x_revit", 0.0)), float(item.get("y_revit", 0.0)))
        d_min = min((dist_punto_punto(p, q) for q in puntos_dxf), default=float("inf"))
        if d_min <= tolerancia:
            encontrados += 1
        else:
            faltantes.append({
                "nombre": item.get("nombre_bloque", "?"),
                "x": p[0], "y": p[1], "dist_min_m": round(d_min, 3),
            })
    resultado = {
        "json_mapa": os.path.basename(ruta_json_mapa),
        "esperados": len(esperados),
        "encontrados": encontrados,
        "faltantes": len(faltantes),
        "tolerancia_m": tolerancia,
        "coherente": len(esperados) > 0 and encontrados / float(len(esperados)) >= 0.5,
        "detalle_faltantes": faltantes[:25],
    }
    if not resultado["coherente"]:
        resultado["diagnostico"] = (
            "El JSON de referencia no es coherente con este DXF: %d/%d coincidencias. "
            "Sus coordenadas no se corresponden ni por traslacion simple, asi que no sirve "
            "como ground truth. Validar contra el RVT (RE_RUTEAR_CONDUITS_v01.py --dry-run)."
            % (encontrados, len(esperados))
        )
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ruteo de conduit desde DXF electrico")
    parser.add_argument("--dxf", default=DEF_DXF, help="DXF de entrada")
    parser.add_argument("--config", default=DEF_CONFIG, help="Configuracion de ruteo")
    parser.add_argument("--out", default=DEF_OUT, help="JSON de salida")
    parser.add_argument("--html", default=DEF_HTML, help="Reporte HTML ('' para omitir)")
    parser.add_argument("--visor", default=DEF_VISOR,
                        help="Visor interactivo del plano ('' para omitir)")
    parser.add_argument("--visor-3d", default=None,
                        help="Visor interactivo en 3D ('' para omitir)")
    parser.add_argument("--marcar-revision", default=None,
                        help="Servicio a forzar en tramos sin resolver (p.ej. FUERZA) "
                             "para localizarlos visualmente en Revit")
    parser.add_argument("--zona", default=None,
                        help="Zona: apartamento | corredor_emt | corredor_pvc_sch40")
    parser.add_argument("--modo-altura", default=None,
                        help="horizontal_con_bajantes | directo")
    parser.add_argument("--nivel", default="Piso 5", help="Nombre del nivel en Revit")
    parser.add_argument("--elevacion-nivel", type=float, default=43.3727,
                        help="Elevacion del nivel en metros")
    parser.add_argument("--validar-dispositivos", default=None,
                        help="JSON con acciones_modelar para cruzar coordenadas")
    parser.add_argument("--silencioso", action="store_true")
    args = parser.parse_args(argv)

    try:
        cfg = cargar_config(_resolver(args.config), RAIZ)
    except ConfigError as exc:
        print("ERROR de configuracion: %s" % exc, file=sys.stderr)
        return 2

    if args.zona:
        zonas = cfg.datos.get("zonas_alternativas", {})
        if args.zona not in zonas:
            print("ERROR: zona '%s' no existe en zonas_alternativas (%s)"
                  % (args.zona, sorted(zonas)), file=sys.stderr)
            return 2
        cfg.datos["zona"] = dict(zonas[args.zona], nombre=args.zona)

    if args.modo_altura:
        cfg.datos["reglas_geometria"]["modo_altura"] = args.modo_altura

    cfg.datos["nivel"] = args.nivel
    cfg.datos["elevacion_nivel_m"] = args.elevacion_nivel

    capas_tuberia = list(cfg.datos["mapeo_capa_tuberia_a_servicio"])
    capas_dispositivo = list(cfg.datos["mapeo_capa_dispositivo_a_servicio"])

    dxf = _resolver(args.dxf)
    if not os.path.exists(dxf):
        print("ERROR: no existe el DXF %s" % dxf, file=sys.stderr)
        return 2

    if not args.silencioso:
        print("Leyendo %s ..." % os.path.basename(dxf))
    contenido = leer_dxf(dxf, capas_tuberia, capas_dispositivo)
    resumen_dxf = resumen_contenido(contenido)
    if not args.silencioso:
        print("   polilineas=%d  dispositivos=%d  marcadores=%d  cables=%s"
              % (resumen_dxf["polilineas"], resumen_dxf["dispositivos"],
                 resumen_dxf["marcadores"], resumen_dxf["cables_distintos"]))

    resultado = rutear(cfg, contenido, marcar_revision=args.marcar_revision)

    salida = resultado.a_dict()
    salida["generado"] = datetime.datetime.now().isoformat(timespec="seconds")
    salida["config"] = os.path.basename(args.config)
    salida["config_cajas"] = cfg.datos.get("cajas_conexion") or {}
    salida["extraccion"] = resumen_dxf

    if args.validar_dispositivos:
        ruta_mapa = _resolver(args.validar_dispositivos)
        if os.path.exists(ruta_mapa):
            salida["validacion_modelo"] = validar_contra_modelo(
                contenido, ruta_mapa, cfg.tolerancia("cruce_coordenadas_revit_m"))
        else:
            salida["validacion_modelo"] = {"error": "no existe %s" % ruta_mapa}

    out = _resolver(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=1, ensure_ascii=False)

    if args.html:
        escribir_html(resultado, _resolver(args.html))

    if args.visor:
        escribir_visor(resultado, contenido, _resolver(args.visor))

    if args.visor_3d:
        escribir_visor_3d(resultado, contenido, _resolver(args.visor_3d))

    if not args.silencioso:
        imprimir_resumen(resultado)
        if "validacion_modelo" in salida and "error" not in salida["validacion_modelo"]:
            v = salida["validacion_modelo"]
            print("Validacion contra modelo Revit: %d/%d dispositivos coinciden (tol %.2f m)"
                  % (v["encontrados"], v["esperados"], v["tolerancia_m"]))
            if not v["coherente"]:
                print("   AVISO: %s" % v["diagnostico"])
        print("JSON -> %s" % out)
        if args.html:
            print("HTML -> %s" % _resolver(args.html))
        if args.visor:
            print("VISOR -> %s" % _resolver(args.visor))
        if args.visor_3d:
            print("VISOR 3D -> %s" % _resolver(args.visor_3d))

    return 0


if __name__ == "__main__":
    sys.exit(main())
