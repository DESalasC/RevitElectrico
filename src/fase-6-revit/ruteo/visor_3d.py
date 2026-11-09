# -*- coding: utf-8 -*-
"""Visor HTML interactivo del ruteo en 3D (proyeccion isométrica).

Dibuja los tramos elevados a su cota real (banda 2.65-2.74 m), con bajantes
verticales en los extremos que cambian de cota. Los circuitos se distinguen por
color y por etiqueta (red/TF-01, TF-03...). Los tramos en revision se resaltan
en magenta con trazo animado.

La proyeccion isometrica es autocontenida (SVG, sin dependencias de red) para
que el visor funcione sin conexion a internet.
"""
from __future__ import annotations

import html
import json
import math
import os

from dxf_lector import ContenidoDXF
from modelos import ResultadoRuteo

COLORES = {
    "TOMAS": "#f0a33c",
    "ILUMINACION": "#3fb6a8",
    "COMUNICACIONES": "#6b8ff0",
    "FUERZA": "#d95f6a",
}
COLOR_REVISION = "#ff2d95"
COLOR_CAJA = "#ffd166"
COLOR_APARATO = "#e6edf3"


def _color(servicio: str) -> str:
    return COLORES.get(servicio, "#9aa7b4")


def _iso_project(x: float, y: float, z: float, scale: float) -> tuple[float, float]:
    """Proyeccion isometrica: x_screen = (x - y) * cos(30), y_screen = (x+y)/2 - z."""
    u = (x - y) * 0.8660254
    v = (x + y) * 0.5 - z * 0.8660254
    return u * scale, v * scale


def _hexagono(cx: float, cy: float, r: float) -> str:
    puntos = []
    for i in range(6):
        ang = math.radians(60 * i - 30)
        puntos.append("%.3f,%.3f" % (cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return " ".join(puntos)


def _bajo_cota(servicio: str) -> str:
    return _color(servicio)


def escribir_visor_3d(res: ResultadoRuteo, contenido: ContenidoDXF, ruta_html: str) -> str:
    # --- recoger todos los puntos 3D para el bbox ---
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []

    def _agregar(p):
        xs.append(p[0])
        ys.append(p[1])
        zs.append(p[2])

    for t in res.tramos:
        for p in t.puntos_3d:
            _agregar(p)
    for c in res.cajas:
        _agregar((c.x, c.y, c.x and c.y and 0.0))  # z se fija abajo
    for disp in contenido.dispositivos:
        _agregar((disp.x, disp.y, 0.0))

    if not xs:
        xs, ys = [0.0, 1.0], [0.0, 1.0]
    zs = zs or [0.0, 2.75]

    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    minz, maxz = min(zs), max(zs)
    margen = 1.0
    ancho = (maxx - minx) + 2 * margen
    alto = (maxy - miny) + 2 * margen
    profundidad = (maxz - minz) + 2 * margen

    # escala para que quepa en el panel
    max_dim = max(ancho, alto, profundidad * 1.5)
    scale = 420.0 / max_dim if max_dim > 0 else 1.0

    # --- capas del SVG ---
    svg_lineas: list[str] = []
    for t in res.tramos:
        if len(t.puntos_3d) < 2:
            continue
        en_revision = any(e.tipo == "libre" for e in t.extremos)
        clase = "tramo revision" if en_revision else "tramo"
        color = COLOR_REVISION if en_revision else _color(t.servicio)

        # segmentos consecutivos en 3D proyectados a isometrica
        segmentos = []
        for i in range(len(t.puntos_3d) - 1):
            ax, ay, az = t.puntos_3d[i]
            bx, by, bz = t.puntos_3d[i + 1]
            ua, va = _iso_project(ax, ay, az, scale)
            ub, vb = _iso_project(bx, by, bz, scale)
            segmentos.append("M %.2f %.2f L %.2f %.2f" % (ua, va, ub, vb))
        d = " ".join(segmentos)

        titulo_plano = (
            "%s · %s · %s · %d cables · %.2f m"
            % (t.id, t.servicio, t.diametro_pulgadas, t.cables, t.largo_m)
        )
        if t.red:
            titulo_plano += " · RED %s" % html.escape(t.red)
        if en_revision:
            titulo_plano += " · EN REVISION"
        svg_lineas.append(
            '<path class="%s" d="%s" stroke="%s" stroke-width="%.4f" fill="none" '
            'stroke-linecap="round" stroke-linejoin="round" '
            'data-servicio="%s" data-red="%s" data-revision="%s" data-id="%s">'
            '<title>%s</title></path>'
            % (
                clase, d, color, scale * 0.0012 * (2.4 if en_revision else 1.4),
                html.escape(t.servicio), html.escape(t.red or ""),
                "1" if en_revision else "0", t.id,
                html.escape(titulo_plano),
            )
        )

    svg_aparatos: list[str] = []
    for disp in contenido.dispositivos:
        serv = ""
        for t in res.tramos:
            for e in t.extremos:
                if e.handle == disp.handle and e.tipo == "dispositivo":
                    serv = e.servicio or t.servicio
                    break
            if serv:
                break
        if not serv:
            continue
        # elevar al dispositivo a su altura de montaje
        z = 0.0
        for t in res.tramos:
            for e in t.extremos:
                if e.handle == disp.handle and e.tipo == "dispositivo" and e.altura_m is not None:
                    z = e.altura_m
        u, v = _iso_project(disp.x, disp.y, z, scale)
        svg_aparatos.append(
            '<circle class="aparato" cx="%.2f" cy="%.2f" r="%.3f" fill="%s" '
            'data-servicio="%s"><title>%s · %s · cota %.2f m</title></circle>'
            % (u, v, scale * 0.005, _color(serv),
               html.escape(serv), html.escape(disp.nombre), html.escape(disp.capa), z)
        )

    svg_cajas: list[str] = []
    for caja in res.cajas:
        u, v = _iso_project(caja.x, caja.y, caja.cota_m, scale)
        svg_cajas.append(
            '<polygon class="caja" points="%s" fill="none" stroke="%s" '
            'stroke-width="%.4f" data-servicio="%s"><title>Caja %s · %s · %s · cota %.2f m</title></polygon>'
            % (
                _hexagono(u, v, scale * 0.008), COLOR_CAJA, scale * 0.0012,
                html.escape(caja.servicio), caja.id,
                html.escape(caja.aparato_nombre), html.escape(caja.servicio), caja.cota_m,
            )
        )

    # --- lista de revision ---
    revision = res.tramos_en_revision()
    items = []
    for t in revision:
        libres = [e for e in t.extremos if e.tipo == "libre"]
        detalle = " · ".join("(%.2f, %.2f) a %.2f m" % (e.x, e.y, e.distancia_m) for e in libres)
        items.append(
            '<li class="rev-item" data-id="%s">'
            '<div class="rev-head"><span class="pill">%s</span>'
            '<strong>%s</strong><span class="dim">%s · %d cables</span></div>'
            '<div class="rev-meta">capa %s · largo %.2f m · red %s</div>'
            '<div class="rev-ext">Extremos libres: %s</div></li>'
            % (
                t.id, html.escape(t.servicio), t.id, t.diametro_pulgadas, t.cables,
                html.escape(t.capa), t.largo_m, html.escape(t.red or "-"),
                html.escape(detalle),
            )
        )

    servicios_presentes = sorted({t.servicio for t in res.tramos})
    redes_presentes = sorted({t.red for t in res.tramos if t.red})
    filtros_serv = "".join(
        '<label class="chip" style="--c:%s"><input type="checkbox" checked '
        'data-filtro="serv:%s"><span></span>%s</label>'
        % (_color(s), s, s)
        for s in servicios_presentes
    )
    filtros_red = "".join(
        '<label class="chip" style="--c:#b388ff"><input type="checkbox" checked '
        'data-filtro="red:%s"><span></span>%s</label>'
        % (r, r)
        for r in redes_presentes
    )

    s = res.resumen()
    vista_def = "iso"

    documento = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Visor 3D de ruteo — {zona}</title>
<style>
  :root {{ --bg:#0a0f18; --panel:#141f2b; --line:#263748; --txt:#e6edf3;
           --muted:#8fa6bb; --rev:{rev}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
          font:14px/1.5 "Segoe UI",system-ui,sans-serif; }}
  header {{ padding:16px 22px 8px; border-bottom:1px solid var(--line); }}
  h1 {{ margin:0 0 2px; font-size:18px; }}
  .sub {{ color:var(--muted); font-size:12px; }}
  .kpis {{ display:flex; gap:8px; flex-wrap:wrap; margin:12px 0 4px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:8px;
          padding:7px 12px; min-width:84px; }}
  .kpi b {{ display:block; font-size:17px; color:#7fd8cd; }}
  .kpi span {{ font-size:10.5px; color:var(--muted); text-transform:uppercase;
               letter-spacing:.04em; }}
  .kpi.alerta b {{ color:var(--rev); }}
  .vistas {{ display:flex; gap:6px; margin:10px 0 4px; flex-wrap:wrap; }}
  .btn-vista {{ background:var(--panel); border:1px solid var(--line); border-radius:8px;
                font-size:11px; padding:4px 10px; cursor:pointer; color:var(--txt); }}
  .btn-vista.activa {{ border-color:#7fd8cd; color:#7fd8cd; }}
  .chips {{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; margin-top:8px; }}
  .chip {{ display:inline-flex; align-items:center; gap:5px; font-size:11px;
           background:var(--panel); border:1px solid var(--line); border-radius:999px;
           padding:3px 9px 3px 7px; cursor:pointer; user-select:none; }}
  .chip input {{ display:none; }}
  .chip span {{ width:9px; height:9px; border-radius:3px; background:var(--c); opacity:.35; }}
  .chip input:checked + span {{ opacity:1; }}
  .chip input:checked ~ * {{ color:var(--txt); }}
  .toggle {{ display:inline-flex; align-items:center; gap:6px; font-size:11px; cursor:pointer;
             background:var(--panel); border:1px solid var(--line); border-radius:999px;
             padding:3px 10px; }}
  main {{ display:grid; grid-template-columns:1fr 330px; gap:12px; padding:12px 22px 22px; }}
  .plano {{ background:#0d151f; border:1px solid var(--line); border-radius:10px;
            overflow:hidden; position:relative; }}
  svg {{ display:block; width:100%; height:min(70vh,720px); }}
  .tramo {{ fill:none; stroke-linecap:round; stroke-linejoin:round; transition:opacity .15s; }}
  .tramo.revision {{ stroke-dasharray:0.5 0.3; animation:pulso 1.6s linear infinite; }}
  @keyframes pulso {{ to {{ stroke-dashoffset:-1.6; }} }}
  .tramo.apagado, .aparato.apagado, .caja.apagado {{ opacity:.10; }}
  .resaltado {{ stroke-width:0.35 !important; filter:drop-shadow(0 0 5px var(--rev)); }}
  aside {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
           padding:12px; overflow:auto; max-height:min(70vh,720px); }}
  aside h2 {{ font-size:11px; margin:0 0 8px; color:var(--muted); text-transform:uppercase;
              letter-spacing:.05em; }}
  ul {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:7px; }}
  .rev-item {{ border:1px solid var(--line); border-left:3px solid var(--rev); border-radius:7px;
               padding:8px 10px; cursor:pointer; transition:background .15s; }}
  .rev-item:hover {{ background:#1a2836; }}
  .rev-item.activo {{ background:#1f2f3f; box-shadow:0 0 0 1px var(--rev) inset; }}
  .rev-head {{ display:flex; align-items:center; gap:6px; flex-wrap:wrap; }}
  .pill {{ font-size:10px; text-transform:uppercase; letter-spacing:.04em;
           background:#22323f; border-radius:5px; padding:1px 6px; color:#a8c0d4; }}
  .dim {{ font-size:11px; color:var(--muted); }}
  .rev-meta, .rev-ext {{ font-size:10.5px; color:var(--muted); margin-top:2px; word-break:break-word; }}
  .vacio {{ color:var(--muted); font-size:12.5px; }}
  .pista {{ font-size:11px; color:var(--muted); margin-top:8px; font-style:italic; }}
  @media (max-width:900px) {{
    main {{ grid-template-columns:1fr; padding:10px; }}
    aside {{ max-height:none; }}
    svg {{ height:54vh; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Visor 3D de ruteo — {zona}</h1>
  <div class="sub">{dxf} · {material} / {calibre} · {nivel} · proyeccion isometrica</div>
  <div class="kpis">
    <div class="kpi"><b>{tramos}</b><span>Tramos</span></div>
    <div class="kpi"><b>{largo:.1f} m</b><span>Longitud</span></div>
    <div class="kpi"><b>{cajas}</b><span>Cajas</span></div>
    <div class="kpi alerta"><b>{revision_n}</b><span>En revision</span></div>
  </div>
  <div class="vistas">
    <button class="btn-vista activa" data-vista="iso">Isometrica</button>
    <button class="btn-vista" data-vista="planta">Planta (Z=0)</button>
    <button class="btn-vista" data-vista="elev-norte">Elevacion Norte</button>
    <button class="btn-vista" data-vista="elev-este">Elevacion Este</button>
  </div>
  <div class="chips">
    {filtros_serv}
    {filtros_red}
    <label class="toggle"><input type="checkbox" id="solo-revision"> Solo revision</label>
  </div>
</header>
<main>
  <div class="plano">
    <svg id="svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho:.3f} {alto:.3f}" preserveAspectRatio="xMidYMid meet">
      {svg_lineas}
      {svg_aparatos}
      {svg_cajas}
    </svg>
  </div>
  <aside>
    <h2>Tramos en revision ({revision_n})</h2>
    {lista}
    <div class="pista">Proyeccion isometrica: el eje Z (altura) se inclina hacia abajo.
    Los tramos de distinto servicio cruzan a distinta cota dentro de la banda 2.65-2.74 m.</div>
  </aside>
</main>
<script>
(function () {{
  var svg = document.getElementById("svg");
  var items = Array.prototype.slice.call(document.querySelectorAll(".rev-item"));
  var capas = Array.prototype.slice.call(document.querySelectorAll(".tramo, .aparato, .caja"));
  var checks = Array.prototype.slice.call(document.querySelectorAll("[data-filtro]"));
  var soloRev = document.getElementById("solo-revision");
  var btns = Array.prototype.slice.call(document.querySelectorAll(".btn-vista"));

  var viewBoxBase = "0 0 {ancho:.3f} {alto:.3f}";
  var vistas = {{
    "planta": "0 0 {ancho:.3f} {alto:.3f}",
    "elev-norte": "0 0 {ancho:.3f} {prof:.3f}",
    "elev-este": "0 0 {ancho:.3f} {prof:.3f}",
    "iso": viewBoxBase,
  }};

  function aplicar() {{
    var activos = {{}};
    checks.forEach(function (c) {{ activos[c.getAttribute("data-filtro")] = c.checked; }});
    var solo = soloRev.checked;
    capas.forEach(function (el) {{
      var serv = el.getAttribute("data-servicio") || "";
      var red = el.getAttribute("data-red") || "";
      var rev = el.getAttribute("data-revision") === "1";
      var okServ = serv === "" || activos["serv:" + serv] !== false;
      var okRed = red === "" || activos["red:" + red] !== false;
      var visible = solo ? rev : (okServ && okRed);
      el.classList.toggle("apagado", !visible);
    }});
  }}
  checks.forEach(function (c) {{ c.addEventListener("change", aplicar); }});
  soloRev.addEventListener("change", aplicar);

  btns.forEach(function (b) {{
    b.addEventListener("click", function () {{
      btns.forEach(function (bb) {{ bb.classList.toggle("activa", bb === b); }});
      var vista = b.getAttribute("data-vista");
      svg.setAttribute("viewBox", vistas[vista] || viewBoxBase);
      items.forEach(function (i) {{ i.classList.remove("activo"); }});
    }});
  }});

  function enfocar(id) {{
    var path = svg.querySelector('[data-id="' + id + '"]');
    items.forEach(function (i) {{ i.classList.toggle("activo", i.getAttribute("data-id") === id); }});
    if (!path) return;
    var b = path.getBBox();
    var pad = Math.max(b.width, b.height) * 0.6 + 1.2;
    svg.setAttribute("viewBox", (b.x - pad) + " " + (b.y - pad) + " " +
                                (b.width + 2 * pad) + " " + (b.height + 2 * pad));
    path.classList.add("resaltado");
    setTimeout(function () {{ path.classList.remove("resaltado"); }}, 1600);
  }}
  items.forEach(function (i) {{
    i.addEventListener("click", function () {{ enfocar(i.getAttribute("data-id")); }});
  }});
  svg.addEventListener("dblclick", function () {{
    svg.setAttribute("viewBox", viewBoxBase);
    items.forEach(function (i) {{ i.classList.remove("activo"); }});
  }};
  aplicar();
}})();
</script>
</body></html>
""".format(
        zona=html.escape(res.zona),
        dxf=html.escape(os.path.basename(res.dxf)),
        material=html.escape(res.material),
        calibre=html.escape(res.calibre),
        nivel=html.escape(res.nivel or "(sin nivel)"),
        tramos=s["tramos"],
        largo=s["longitud_total_m"],
        cajas=s["cajas_conexion"],
        cruces=s["cruces_planta"],
        revision_n=len(revision),
        rev=COLOR_REVISION,
        filtros_serv=filtros_serv,
        filtros_red=filtros_red,
        ancho=ancho,
        alto=alto,
        prof=profundidad,
        svg_lineas="\n".join(svg_lineas),
        svg_aparatos="\n".join(svg_aparatos),
        svg_cajas="\n".join(svg_cajas),
        lista=("<ul>" + "".join(items) + "</ul>") if items else
              '<p class="vacio">Sin tramos en revision.</p>',
    )

    os.makedirs(os.path.dirname(os.path.abspath(ruta_html)), exist_ok=True)
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(documento)
    return ruta_html
