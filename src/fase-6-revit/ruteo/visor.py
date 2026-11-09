# -*- coding: utf-8 -*-
"""Visor HTML interactivo del ruteo.

Dibuja el plano (tuberias, aparatos, marcadores de cables y cajas) en un SVG
autocontenido y resalta los tramos con extremos sin resolver, para que el
operador pueda localizarlos visualmente sin abrir Revit.
"""
from __future__ import annotations

import html
import json
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


def _color(servicio: str) -> str:
    return COLORES.get(servicio, "#9aa7b4")


def _hexagono(cx: float, cy: float, r: float) -> str:
    import math
    puntos = []
    for i in range(6):
        ang = math.radians(60 * i - 30)
        puntos.append("%.3f,%.3f" % (cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return " ".join(puntos)


def escribir_visor(res: ResultadoRuteo, contenido: ContenidoDXF, ruta_html: str) -> str:
    # --- bbox y transformacion (Y invertida para SVG) ---
    xs: list[float] = []
    ys: list[float] = []
    for t in res.tramos:
        for x, y in t.puntos_2d:
            xs.append(x)
            ys.append(y)
    for d in contenido.dispositivos:
        xs.append(d.x)
        ys.append(d.y)
    if not xs:
        xs, ys = [0.0, 1.0], [0.0, 1.0]

    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    margen = 1.0
    ancho = (maxx - minx) + 2 * margen
    alto = (maxy - miny) + 2 * margen

    def tx(x: float) -> float:
        return (x - minx) + margen

    def ty(y: float) -> float:
        return (maxy - y) + margen

    trazo = max(ancho, alto) / 420.0

    # --- capas del SVG ---
    svg_lineas: list[str] = []
    for t in res.tramos:
        if len(t.puntos_2d) < 2:
            continue
        d = "M " + " L ".join("%.3f %.3f" % (tx(x), ty(y)) for x, y in t.puntos_2d)
        en_revision = any(e.tipo == "libre" for e in t.extremos)
        clase = "tramo revision" if en_revision else "tramo"
        color = COLOR_REVISION if en_revision else _color(t.servicio)
        titulo = "%s · %s · %s · %d cables · %.2f m%s" % (
            t.id, t.servicio, t.diametro_pulgadas, t.cables, t.largo_m,
            " · EN REVISION" if en_revision else "")
        svg_lineas.append(
            '<path class="%s" d="%s" stroke="%s" stroke-width="%.4f" '
            'data-servicio="%s" data-revision="%s" data-id="%s">'
            '<title>%s</title></path>'
            % (clase, d, color, trazo * (2.4 if en_revision else 1.4),
               html.escape(t.servicio), "1" if en_revision else "0",
               t.id, html.escape(titulo))
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
        svg_aparatos.append(
            '<circle class="aparato" cx="%.3f" cy="%.3f" r="%.3f" fill="%s" '
            'data-servicio="%s"><title>%s · %s</title></circle>'
            % (tx(disp.x), ty(disp.y), trazo * 1.5, _color(serv),
               html.escape(serv), html.escape(disp.nombre), html.escape(disp.capa))
        )

    svg_marcadores: list[str] = []
    for marc in contenido.marcadores:
        svg_marcadores.append(
            '<g class="marcador" data-servicio=""><title>%s · %d cables</title>'
            '<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" fill="#0f1720" '
            'stroke="#8fa6bb" stroke-width="%.4f"/>'
            '<text x="%.3f" y="%.3f" font-size="%.3f" fill="#e6edf3" '
            'text-anchor="middle" dominant-baseline="central">%d</text></g>'
            % (html.escape(marc.nombre), marc.cables,
               tx(marc.x) - trazo * 2.2, ty(marc.y) - trazo * 2.2, trazo * 4.4, trazo * 4.4,
               trazo * 0.5, tx(marc.x), ty(marc.y), trazo * 3.0, marc.cables)
        )

    svg_cajas: list[str] = []
    for caja in res.cajas:
        svg_cajas.append(
            '<polygon class="caja" points="%s" fill="none" stroke="#ffd166" '
            'stroke-width="%.4f" data-servicio="%s"><title>Caja %s · %s · %s</title></polygon>'
            % (_hexagono(tx(caja.x), ty(caja.y), trazo * 3.0), trazo, html.escape(caja.servicio),
               caja.id, html.escape(caja.aparato_nombre), html.escape(caja.servicio))
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
            '<div class="rev-meta">capa %s · largo %.2f m</div>'
            '<div class="rev-ext">Extremos libres: %s</div></li>'
            % (t.id, html.escape(t.servicio), t.id, t.diametro_pulgadas, t.cables,
               html.escape(t.capa), t.largo_m, html.escape(detalle))
        )

    servicios_presentes = sorted({t.servicio for t in res.tramos})
    filtros = "".join(
        '<label class="chip" style="--c:%s"><input type="checkbox" checked '
        'data-filtro="%s"><span></span>%s</label>'
        % (_color(s), html.escape(s), html.escape(s))
        for s in servicios_presentes
    )

    s = res.resumen()

    documento = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Visor de ruteo — {zona}</title>
<style>
  :root {{ --bg:#0b1219; --panel:#121c26; --line:#233544; --txt:#e6edf3;
           --muted:#8fa6bb; --rev:{rev}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
          font:14px/1.5 "Segoe UI",system-ui,sans-serif; }}
  header {{ padding:18px 22px 10px; border-bottom:1px solid var(--line); }}
  h1 {{ margin:0 0 2px; font-size:19px; }}
  .sub {{ color:var(--muted); font-size:12.5px; }}
  .kpis {{ display:flex; gap:10px; flex-wrap:wrap; margin:14px 0 4px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:9px;
          padding:8px 14px; min-width:96px; }}
  .kpi b {{ display:block; font-size:19px; color:#7fd8cd; }}
  .kpi span {{ font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
  .kpi.alerta b {{ color:var(--rev); }}
  .chips {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:12px; }}
  .chip {{ display:inline-flex; align-items:center; gap:6px; font-size:12px;
           background:var(--panel); border:1px solid var(--line); border-radius:999px;
           padding:4px 11px 4px 8px; cursor:pointer; user-select:none; }}
  .chip input {{ display:none; }}
  .chip span {{ width:10px; height:10px; border-radius:3px; background:var(--c); opacity:.35; }}
  .chip input:checked + span {{ opacity:1; }}
  .chip input:checked ~ * {{ color:var(--txt); }}
  .toggle {{ display:inline-flex; align-items:center; gap:7px; font-size:12px; cursor:pointer;
             background:var(--panel); border:1px solid var(--line); border-radius:999px;
             padding:4px 12px; }}
  main {{ display:grid; grid-template-columns:1fr 340px; gap:14px; padding:14px 22px 26px; }}
  .plano {{ background:#0e1720; border:1px solid var(--line); border-radius:12px;
            overflow:hidden; position:relative; }}
  svg {{ display:block; width:100%; height:min(72vh,760px); }}
  .tramo {{ fill:none; stroke-linecap:round; stroke-linejoin:round; transition:opacity .15s; }}
  .tramo.revision {{ stroke-dasharray:0.5 0.3; animation:pulso 1.6s linear infinite; }}
  @keyframes pulso {{ to {{ stroke-dashoffset:-1.6; }} }}
  .tramo.apagado, .aparato.apagado, .marcador.apagado, .caja.apagado {{ opacity:.10; }}
  .resaltado {{ stroke-width:0.35 !important; filter:drop-shadow(0 0 4px var(--rev)); }}
  aside {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
           padding:14px; overflow:auto; max-height:min(72vh,760px); }}
  aside h2 {{ font-size:12px; margin:0 0 10px; color:var(--muted); text-transform:uppercase;
              letter-spacing:.05em; }}
  ul {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:8px; }}
  .rev-item {{ border:1px solid var(--line); border-left:3px solid var(--rev); border-radius:8px;
               padding:9px 11px; cursor:pointer; transition:background .15s; }}
  .rev-item:hover {{ background:#1a2836; }}
  .rev-item.activo {{ background:#1f2f3f; box-shadow:0 0 0 1px var(--rev) inset; }}
  .rev-head {{ display:flex; align-items:center; gap:7px; flex-wrap:wrap; }}
  .pill {{ font-size:10.5px; text-transform:uppercase; letter-spacing:.04em;
           background:#22323f; border-radius:5px; padding:1px 6px; color:#a8c0d4; }}
  .dim {{ font-size:11.5px; color:var(--muted); }}
  .rev-meta, .rev-ext {{ font-size:11.5px; color:var(--muted); margin-top:3px; word-break:break-word; }}
  .vacio {{ color:var(--muted); font-size:13px; }}
  @media (max-width:900px) {{
    main {{ grid-template-columns:1fr; padding:12px; }}
    aside {{ max-height:none; }}
    svg {{ height:56vh; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Visor de ruteo — {zona}</h1>
  <div class="sub">{dxf} · {material} / {calibre} · {nivel}</div>
  <div class="kpis">
    <div class="kpi"><b>{tramos}</b><span>Tramos</span></div>
    <div class="kpi"><b>{largo:.1f} m</b><span>Longitud</span></div>
    <div class="kpi"><b>{cajas}</b><span>Cajas</span></div>
    <div class="kpi"><b>{cruces}</b><span>Cruces</span></div>
    <div class="kpi alerta"><b>{revision_n}</b><span>En revision</span></div>
  </div>
  <div class="chips">
    {filtros}
    <label class="toggle"><input type="checkbox" id="solo-revision"> Solo revision</label>
  </div>
</header>
<main>
  <div class="plano">
    <svg id="svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho:.3f} {alto:.3f}" preserveAspectRatio="xMidYMid meet">
      {svg_lineas}
      {svg_aparatos}
      {svg_marcadores}
      {svg_cajas}
    </svg>
  </div>
  <aside>
    <h2>Tramos en revision ({revision_n})</h2>
    {lista}
  </aside>
</main>
<script>
(function () {{
  var svg = document.getElementById("svg");
  var items = Array.prototype.slice.call(document.querySelectorAll(".rev-item"));
  var capas = Array.prototype.slice.call(document.querySelectorAll(".tramo, .aparato, .marcador, .caja"));
  var checks = Array.prototype.slice.call(document.querySelectorAll("[data-filtro]"));
  var soloRev = document.getElementById("solo-revision");

  function aplicar() {{
    var activos = {{}};
    checks.forEach(function (c) {{ activos[c.getAttribute("data-filtro")] = c.checked; }});
    var solo = soloRev.checked;
    capas.forEach(function (el) {{
      var serv = el.getAttribute("data-servicio") || "";
      var rev = el.getAttribute("data-revision") === "1";
      var visible = solo ? rev : (serv === "" || activos[serv] !== false);
      el.classList.toggle("apagado", !visible);
    }});
  }}
  checks.forEach(function (c) {{ c.addEventListener("change", aplicar); }});
  soloRev.addEventListener("change", aplicar);

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
    svg.setAttribute("viewBox", "0 0 {ancho:.3f} {alto:.3f}");
    items.forEach(function (i) {{ i.classList.remove("activo"); }});
  }});
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
        filtros=filtros,
        ancho=ancho,
        alto=alto,
        svg_lineas="\n".join(svg_lineas),
        svg_aparatos="\n".join(svg_aparatos),
        svg_marcadores="\n".join(svg_marcadores),
        svg_cajas="\n".join(svg_cajas),
        lista=("<ul>" + "".join(items) + "</ul>") if items else
              '<p class="vacio">Sin tramos en revision.</p>',
    )

    os.makedirs(os.path.dirname(os.path.abspath(ruta_html)), exist_ok=True)
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(documento)
    return ruta_html
