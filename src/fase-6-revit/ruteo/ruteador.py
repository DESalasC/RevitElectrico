# -*- coding: utf-8 -*-
"""Nucleo del ruteo: convierte polilineas 2D + marcadores de cables en tramos 3D.

El DXF ya trae el ruteo dibujado (polilineas en las capas *-PIPE-*). Este modulo NO
inventa trazados: levanta esos trazados a 3D, les asigna servicio y diametro, y
reporta los casos dudosos para que el operador los valide.
"""
from __future__ import annotations

import math
from typing import Any

from config import ConfigRuteo
from dimensionamiento import dimensionar_servicio
from dxf_lector import ContenidoDXF
from modelos import Caja, Cruce, ExtremoTramo, Punto2D, Punto3D, ResultadoRuteo, Tramo
from servicio import resolver_servicio


# --- geometria ---------------------------------------------------------
def dist_punto_punto(a: Punto2D, b: Punto2D) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def dist_punto_segmento(p: Punto2D, a: Punto2D, b: Punto2D) -> float:
    """Distancia perpendicular de p al segmento ab (0 si cae dentro)."""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def dist_punto_polilinea(p: Punto2D, puntos: tuple[Punto2D, ...]) -> float:
    return min(dist_punto_segmento(p, puntos[i], puntos[i + 1]) for i in range(len(puntos) - 1))


def _orientacion(a: Punto2D, b: Punto2D, c: Punto2D) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def interseccion_segmentos(a1: Punto2D, a2: Punto2D, b1: Punto2D, b2: Punto2D,
                           tol: float = 1e-9):
    """Punto de cruce de dos segmentos en planta, o None si no se cruzan."""
    d1 = _orientacion(b1, b2, a1)
    d2 = _orientacion(b1, b2, a2)
    d3 = _orientacion(a1, a2, b1)
    d4 = _orientacion(a1, a2, b2)
    if ((d1 > tol and d2 < -tol) or (d1 < -tol and d2 > tol)) and \
       ((d3 > tol and d4 < -tol) or (d3 < -tol and d4 > tol)):
        den = (a1[0] - a2[0]) * (b1[1] - b2[1]) - (a1[1] - a2[1]) * (b1[0] - b2[0])
        if abs(den) < 1e-12:
            return None
        t = ((a1[0] - b1[0]) * (b1[1] - b2[1]) - (a1[1] - b1[1]) * (b1[0] - b2[0])) / den
        return (a1[0] + t * (a2[0] - a1[0]), a1[1] + t * (a2[1] - a1[1]))
    return None


def detectar_cruces(tramos: list[Tramo], avisar_misma_cota_m: float = 0.02) -> list[Cruce]:
    """Cruces en planta entre tramos de distinto servicio.

    El reparto de cotas por servicio dentro de la banda (2,65-2,75 m) debe hacer
    que dos sistemas que se cruzan queden a distinta altura. Aqui se verifica.
    """
    cruces: list[Cruce] = []
    for i in range(len(tramos)):
        ta = tramos[i]
        for j in range(i + 1, len(tramos)):
            tb = tramos[j]
            if ta.servicio == tb.servicio:
                continue
            encontrado = None
            for s in range(len(ta.puntos_2d) - 1):
                for r in range(len(tb.puntos_2d) - 1):
                    p = interseccion_segmentos(ta.puntos_2d[s], ta.puntos_2d[s + 1],
                                               tb.puntos_2d[r], tb.puntos_2d[r + 1])
                    if p is not None:
                        encontrado = p
                        break
                if encontrado is not None:
                    break
            if encontrado is not None:
                cruces.append(Cruce(
                    tramo_a=ta.id, tramo_b=tb.id,
                    servicio_a=ta.servicio, servicio_b=tb.servicio,
                    x=encontrado[0], y=encontrado[1],
                    cota_a=ta.cota_m, cota_b=tb.cota_m,
                ))
    return cruces


# --- resolucion de extremos --------------------------------------------
def _extremo_mas_cercano(
    cfg: ConfigRuteo,
    punto: Punto2D,
    contenido: ContenidoDXF,
    tolerancia: float,
) -> ExtremoTramo:
    mejor = None
    mejor_d = float("inf")
    for disp in contenido.dispositivos:
        d = dist_punto_punto(punto, disp.punto)
        if d < mejor_d:
            mejor_d = d
            mejor = disp
    if mejor is None or mejor_d > tolerancia:
        return ExtremoTramo(
            tipo="libre", x=punto[0], y=punto[1],
            distancia_m=(mejor_d if mejor is not None else float("inf")),
            nombre=(mejor.nombre if mejor is not None else ""),
        )
    return ExtremoTramo(
        tipo="dispositivo",
        x=punto[0], y=punto[1],
        distancia_m=mejor_d,
        handle=mejor.handle,
        nombre=mejor.nombre,
        capa=mejor.capa,
        servicio=cfg.servicio_de_capa_dispositivo(mejor.capa),
        altura_m=cfg.altura_aparato(mejor.nombre, mejor.capa),
    )


# --- resolucion de cables ----------------------------------------------
def _marcador_mas_cercano(
    polilinea_puntos: tuple[Punto2D, ...],
    contenido: ContenidoDXF,
    tolerancia: float,
):
    mejor = None
    mejor_d = float("inf")
    for marc in contenido.marcadores:
        d = dist_punto_polilinea(marc.punto, polilinea_puntos)
        if d < mejor_d:
            mejor_d = d
            mejor = marc
    if mejor is None or mejor_d > tolerancia:
        return None, (mejor_d if mejor is not None else float("inf"))
    return mejor, mejor_d


def _heredar_cables(
    puntos: tuple[Punto2D, ...],
    resueltos: list[tuple[tuple[Punto2D, ...], int]],
    radio: float,
) -> int | None:
    """Toma los cables de la polilinea resuelta mas cercana (extremos compartidos)."""
    mejor = None
    mejor_d = float("inf")
    for vecinos, cables in resueltos:
        d = float("inf")
        for extremo in (puntos[0], puntos[-1]):
            for vecino_extremo in (vecinos[0], vecinos[-1]):
                d = min(d, dist_punto_punto(extremo, vecino_extremo))
        if d <= radio and d < mejor_d:
            mejor_d = d
            mejor = cables
    return mejor


# --- asociacion de textos de circuito/red -----------------------------------
def _asociar_circuitos(
    tramos: list[Tramo],
    textos_circuito: list[dict[str, Any]],
    tolerancia_m: float,
) -> None:
    """Asigna a cada tramo el circuito (red) del texto de capa Iden mas cercano.

    Los textos de circuito (p.ej. TF-01, TF-03) viven en la capa Elec-Power-Iden
    y se leen como entidades TEXT del DXF. Se asocia cada tramo al texto de
    circuito mas cercano dentro de la tolerancia, sin mover el texto.
    """
    if not textos_circuito:
        return
    for t in tramos:
        if not t.puntos_2d:
            continue
        # Punto medio del tramo como referencia de asociacion
        xs = [p[0] for p in t.puntos_2d]
        ys = [p[1] for p in t.puntos_2d]
        pm = (sum(xs) / len(xs), sum(ys) / len(ys))
        mejor = None
        mejor_d = float("inf")
        for txtobj in textos_circuito:
            d = math.hypot(txtobj["x"] - pm[0], txtobj["y"] - pm[1])
            if d <= tolerancia_m and d < mejor_d:
                mejor_d = d
                mejor = txtobj["texto"].strip().upper()
        if mejor:
            t.red = mejor


# --- construccion 3D ---------------------------------------------------
def _puntos_3d(
    cfg: ConfigRuteo,
    puntos: tuple[Punto2D, ...],
    cota_banda: float,
    extremos: list[ExtremoTramo],
    modo: str,
) -> tuple[list[Punto3D], float]:
    """Devuelve (puntos_3d, largo_total). Incluye bajantes verticales."""
    z_ini = cota_banda
    z_fin = cota_banda
    if modo == "directo":
        if extremos and extremos[0].altura_m is not None:
            z_ini = extremos[0].altura_m
        if len(extremos) > 1 and extremos[1].altura_m is not None:
            z_fin = extremos[1].altura_m

    salida: list[Punto3D] = []
    if modo == "horizontal_con_bajantes":
        # bajante al inicio
        if extremos and extremos[0].altura_m is not None and abs(extremos[0].altura_m - cota_banda) > 1e-6:
            salida.append((puntos[0][0], puntos[0][1], extremos[0].altura_m))
        salida.append((puntos[0][0], puntos[0][1], cota_banda))
        for x, y in puntos[1:-1]:
            salida.append((x, y, cota_banda))
        salida.append((puntos[-1][0], puntos[-1][1], cota_banda))
        if len(extremos) > 1 and extremos[1].altura_m is not None and abs(extremos[1].altura_m - cota_banda) > 1e-6:
            salida.append((puntos[-1][0], puntos[-1][1], extremos[1].altura_m))
    else:
        # interpolacion lineal de cota entre los dos extremos
        n = len(puntos)
        for i, (x, y) in enumerate(puntos):
            t = 0.0 if n == 1 else i / float(n - 1)
            salida.append((x, y, z_ini + (z_fin - z_ini) * t))

    largo = 0.0
    for i in range(len(salida) - 1):
        ax, ay, az = salida[i]
        bx, by, bz = salida[i + 1]
        largo += math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)
    return salida, largo


# --- cajas de conexion ---------------------------------------------------
def _resolver_caja(
    cfg: ConfigRuteo,
    tramo_id: str,
    servicio: str,
    extremo: ExtremoTramo,
    contenido: ContenidoDXF,
    indice: int,
) -> Caja | None:
    """Si el extremo quedo libre, busca el aparato que alimenta y crea la caja.

    En obra, la tuberia no llega a la luminaria: termina en una caja
    octogonal/hexagonal y desde ahi sale la conexion corta al aparato.
    """
    cc = cfg.datos.get("cajas_conexion") or {}
    if not cc.get("habilitado") or extremo.tipo != "libre":
        return None

    radio = float(cc.get("radio_busqueda_m", 2.0))
    capas = set(cc.get("capas_aparato_destino") or [])
    mejor = None
    mejor_d = radio
    for disp in contenido.dispositivos:
        if capas and disp.capa not in capas:
            continue
        # La caja solo tiene sentido si el aparato pertenece al mismo sistema
        # que la tuberia (caja de luminaria para iluminacion, caja de ventilador
        # para fuerza). Evita cajas absurdas en tramos de otra red.
        servicio_disp = cfg.servicio_de_capa_dispositivo(disp.capa)
        if servicio_disp is not None and servicio_disp != servicio:
            continue
        d = dist_punto_punto((extremo.x, extremo.y), disp.punto)
        if d <= mejor_d:
            mejor_d = d
            mejor = disp
    if mejor is None:
        return None

    cota = float(cc.get("cota_m", cfg.cota_banda(servicio)))
    extremo.tipo = "caja"
    extremo.handle = mejor.handle
    extremo.nombre = mejor.nombre
    extremo.capa = mejor.capa
    extremo.distancia_m = mejor_d
    extremo.altura_m = None   # la tuberia termina en la caja, no baja al aparato
    extremo.servicio = extremo.servicio or cfg.servicio_de_capa_dispositivo(mejor.capa)

    return Caja(
        id="CJ-%04d" % indice,
        tramo_id=tramo_id,
        x=extremo.x,
        y=extremo.y,
        cota_m=cota,
        servicio=servicio,
        aparato_handle=mejor.handle,
        aparato_nombre=mejor.nombre,
        aparato_capa=mejor.capa,
        distancia_m=mejor_d,
        altura_aparato_m=cfg.altura_aparato(mejor.nombre, mejor.capa),
    )


# --- pipeline ----------------------------------------------------------
def rutear(cfg: ConfigRuteo, contenido: ContenidoDXF,
           marcar_revision: str | None = None) -> ResultadoRuteo:
    """Ejecuta el pipeline completo sobre el contenido del DXF.

    marcar_revision: si se indica un servicio (p.ej. "FUERZA"), los tramos con
    extremos sin resolver se emiten con ese Servicio_Conduit para localizarlos
    visualmente en Revit. No altera el diametro.
    """
    tol_marcador = cfg.tolerancia("asociacion_marcador_polilinea_m")
    tol_extremo = cfg.tolerancia("asociacion_extremo_dispositivo_m")
    reglas = cfg.datos["reglas_cables"]
    cables_default = int(reglas["cables_default_sin_marcador"])
    radio_herencia = float(reglas["heredar_de_polilinea_vecina_m"])
    modo = str(cfg.datos["reglas_geometria"].get("modo_altura", "horizontal_con_bajantes"))
    largo_min = float(cfg.datos["reglas_geometria"].get("longitud_minima_tramo_m", 0.05))

    resultado = ResultadoRuteo(
        dxf=contenido.ruta,
        zona=cfg.zona,
        material=cfg.material,
        calibre=cfg.calibre,
        nivel=str(cfg.datos.get("nivel", "")),
        elevacion_nivel_m=float(cfg.datos.get("elevacion_nivel_m", 0.0)),
    )

    # Ancla de coordenadas: el panel define el origen para el offset contra Revit.
    cfg_ancla = cfg.datos.get("ancla") or {}
    if cfg_ancla:
        bloque = cfg_ancla.get("bloque_dxf")
        capa = cfg_ancla.get("capa_dxf")
        for disp in contenido.dispositivos:
            if disp.nombre == bloque and (not capa or disp.capa == capa):
                resultado.ancla = {
                    "bloque_dxf": disp.nombre,
                    "capa_dxf": disp.capa,
                    "handle_dxf": disp.handle,
                    "x_dxf": round(disp.x, 4),
                    "y_dxf": round(disp.y, 4),
                    "nombre_en_revit": cfg_ancla.get("nombre_en_revit", bloque),
                }
                break
        if not resultado.ancla:
            resultado.avisos.append(
                "No se encontro el ancla '%s' (capa '%s') en el DXF" % (bloque, capa)
            )

    # La banda declarada debe contener todas las cotas por servicio.
    banda = cfg.datos.get("banda") or {}
    if banda:
        cmin = float(banda.get("cota_min_m", 0.0))
        cmax = float(banda.get("cota_max_m", 0.0))
        for servicio in cfg.datos["servicios_permitidos"]:
            c = cfg.cota_banda(servicio)
            if c < cmin - 1e-9 or c > cmax + 1e-9:
                resultado.avisos.append(
                    "Cota %.3f m de %s fuera de la banda [%.2f, %.2f]" % (c, servicio, cmin, cmax)
                )

    ordenadas = sorted(contenido.polilineas, key=lambda p: (p.capa, -p.largo()))
    resueltos: list[tuple[tuple[Punto2D, ...], int]] = []

    for i, pl in enumerate(ordenadas, start=1):
        if pl.largo() < largo_min:
            resultado.avisos.append(
                "Tramo %s en '%s' omitido: largo %.3f m < minimo %.3f m"
                % (pl.handle, pl.capa, pl.largo(), largo_min)
            )
            continue

        extremos = [
            _extremo_mas_cercano(cfg, pl.inicio, contenido, tol_extremo),
            _extremo_mas_cercano(cfg, pl.fin, contenido, tol_extremo),
        ]

        servicio, avisos = resolver_servicio(cfg, pl.capa, extremos)

        marcador, d_marc = _marcador_mas_cercano(pl.puntos, contenido, tol_marcador)
        if marcador is not None:
            cables = marcador.cables
            origen = "marcador"
            marcadores_txt = ["%s (%d cables, d=%.3f m)" % (marcador.nombre, marcador.cables, d_marc)]
        else:
            heredado = _heredar_cables(pl.puntos, resueltos, radio_herencia)
            if heredado is not None:
                cables = heredado
                origen = "heredado"
                avisos.append(
                    "Sin marcador propio; hereda %d cables de tramo vecino" % heredado
                )
            else:
                cables = cables_default
                origen = "default"
                avisos.append(
                    "Sin marcador ni vecino resoluble; se asume %d cables (revisar)" % cables_default
                )
            marcadores_txt = []

        dim, origen_dim, motivo_dim = dimensionar_servicio(cfg, servicio, cables)
        if origen_dim == "fijo_servicio":
            avisos.append(
                "Diametro fijo por servicio: %s (%s)" % (dim.pulgadas, motivo_dim)
            )
        cota = cfg.cota_banda(servicio)

        # Cajas de conexion en extremos que no tocan un aparato
        for extremo in extremos:
            caja = _resolver_caja(cfg, "RT-%04d" % i, servicio, extremo, contenido,
                                  len(resultado.cajas) + 1)
            if caja is not None:
                resultado.cajas.append(caja)
                avisos.append(
                    "Extremo resuelto como caja de conexion (%s a %.2f m) -> %s"
                    % (caja.aparato_nombre, caja.distancia_m, caja.id)
                )

        puntos_3d, largo_total = _puntos_3d(cfg, pl.puntos, cota, extremos, modo)

        if dim.holgura == 0:
            avisos.append(
                "Tubo al limite: %d cables = capacidad exacta de %s" % (cables, dim.pulgadas)
            )

        for e in extremos:
            if e.tipo == "libre":
                avisos.append(
                    "Extremo sin dispositivo ni caja a <= %.2f m (el mas cercano esta a %.2f m)"
                    % (tol_extremo, e.distancia_m)
                )

        tramo = Tramo(
            id="RT-%04d" % i,
            handle_dxf=pl.handle,
            capa=pl.capa,
            servicio=servicio,
            cables=cables,
            cables_origen=origen,
            material=dim.material,
            calibre=dim.calibre,
            diametro_pulgadas=dim.pulgadas,
            diametro_mm=dim.mm,
            diametro_origen=origen_dim,
            largo_m=largo_total,
            cota_m=cota,
            puntos_2d=list(pl.puntos),
            puntos_3d=puntos_3d,
            extremos=extremos,
            marcadores=marcadores_txt,
            avisos=avisos,
        )
        resultado.tramos.append(tramo)
        resueltos.append((pl.puntos, cables))

    resultado.estadisticas = {
        "dispositivos": len(contenido.dispositivos),
        "marcadores": len(contenido.marcadores),
        "polilineas": len(contenido.polilineas),
        "avisos_lectura": contenido.avisos[:50],
    }

    # Asociar textos de circuito/red (capa Elec-Power-Iden) a los tramos.
    tolerancia_circuito = float(cfg.datos.get('tolerancias', {}).get('asociacion_texto_circuito_m', 1.0))
    _asociar_circuitos(resultado.tramos, contenido.textos_circuito, tolerancia_circuito)

    umbral = float(cfg.datos["reglas_geometria"].get("avisar_cruce_misma_cota_m", 0.02))
    resultado.cruces = detectar_cruces(resultado.tramos, umbral)
    for cruce in resultado.cruces:
        if cruce.separacion_m < umbral:
            resultado.avisos.append(
                "Cruce a la misma cota (%.2f m) entre %s y %s en (%.2f, %.2f)"
                % (cruce.cota_a, cruce.servicio_a, cruce.servicio_b, cruce.x, cruce.y)
            )

    # Marcado de revision: permite localizar en Revit los tramos sin resolver.
    if marcar_revision:
        marcados = 0
        for tramo in resultado.tramos_en_revision():
            tramo.avisos.append(
                "Marcado para revision: Servicio_Conduit forzado a %s (era %s)"
                % (marcar_revision, tramo.servicio)
            )
            tramo.servicio = marcar_revision
            marcados += 1
        resultado.avisos.append(
            "%d tramos sin resolver marcados como %s para revision visual"
            % (marcados, marcar_revision)
        )

    return resultado
