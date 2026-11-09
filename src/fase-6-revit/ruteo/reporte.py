# -*- coding: utf-8 -*-
"""Reporte legible del ruteo (consola + HTML opcional)."""
from __future__ import annotations

import datetime
import html
import os

from modelos import ResultadoRuteo


def imprimir_resumen(res: ResultadoRuteo, max_avisos: int = 25) -> None:
    s = res.resumen()
    print("=" * 78)
    print("RUTEO DE CONDUIT — %s" % res.zona)
    print("=" * 78)
    print("DXF           : %s" % os.path.basename(res.dxf))
    print("Material      : %s   Calibre: %s" % (res.material, res.calibre))
    print("Nivel         : %s   Elevacion: %.4f m" % (res.nivel or "(sin nivel)", res.elevacion_nivel_m))
    print("Tramos        : %d   (con marcador: %d | sin marcador: %d)"
          % (s["tramos"], s["tramos_con_marcador"], s["tramos_sin_marcador"]))
    print("Cajas conexion: %d   Cruces en planta: %d (a la misma cota: %d)"
          % (s["cajas_conexion"], s["cruces_planta"], s["cruces_a_la_misma_cota"]))
    print("Longitud total: %.2f m" % s["longitud_total_m"])
    print()
    print("Por servicio:")
    for servicio, n in sorted(s["por_servicio"].items(), key=lambda kv: -kv[1]):
        print("   %-16s %3d tramos   %8.2f m" % (servicio, n, s["largo_por_servicio_m"][servicio]))
    print()
    print("Por diametro:")
    for diam, n in sorted(s["por_diametro"].items(), key=lambda kv: -kv[1]):
        print("   %-10s %3d tramos" % (diam, n))
    print()

    if res.cajas:
        print("Cajas de conexion: %d" % len(res.cajas))
        destinos = {}
        for c in res.cajas:
            destinos[c.aparato_capa] = destinos.get(c.aparato_capa, 0) + 1
        for capa, n in sorted(destinos.items(), key=lambda kv: -kv[1]):
            print("   %-28s %d" % (capa, n))
        print()

    if res.cruces:
        print("Cruces en planta: %d" % len(res.cruces))
        misma = [c for c in res.cruces if c.separacion_m < 0.02]
        print("   a la misma cota: %d | con separacion: %d"
              % (len(misma), len(res.cruces) - len(misma)))
        print()

    con_aviso = [t for t in res.tramos if t.avisos]
    print("Tramos con avisos: %d" % len(con_aviso))
    mostrados = 0
    for t in con_aviso:
        if mostrados >= max_avisos:
            print("   ... (%d tramos mas con avisos)" % (len(con_aviso) - mostrados))
            break
        print("   %s [%s %s] %s" % (t.id, t.servicio, t.diametro_pulgadas, "; ".join(t.avisos)))
        mostrados += 1

    if res.avisos:
        print()
        print("Avisos globales: %d" % len(res.avisos))
        for a in res.avisos[:max_avisos]:
            print("   - %s" % a)
    print("=" * 78)


def escribir_html(res: ResultadoRuteo, ruta_html: str) -> str:
    s = res.resumen()
    filas = []
    for t in res.tramos:
        avisos = " ".join(html.escape(a) for a in t.avisos)
        filas.append(
            "<tr class='%s'>"
            "<td>%s</td><td>%s</td><td>%s</td><td class='num'>%d</td>"
            "<td>%s</td><td class='num'>%.2f</td><td class='num'>%.2f</td>"
            "<td>%s</td><td class='aviso'>%s</td></tr>"
            % ("con-aviso" if t.avisos else "",
               t.id, t.servicio, html.escape(t.capa), t.cables, t.diametro_pulgadas,
               t.largo_m, t.cota_m,
               t.cables_origen, avisos)
        )

    resumen_servicio = "".join(
        "<li><b>%s</b>: %d tramos · %.2f m</li>" % (k, v, s["largo_por_servicio_m"][k])
        for k, v in sorted(s["por_servicio"].items(), key=lambda kv: -kv[1])
    )
    resumen_diametro = "".join(
        "<li><b>%s</b>: %d tramos</li>" % (k, v)
        for k, v in sorted(s["por_diametro"].items(), key=lambda kv: -kv[1])
    )

    contenido = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ruteo de conduit — {zona}</title>
<style>
  :root {{ --bg:#0f1720; --panel:#16212c; --line:#24384a; --txt:#e6edf3; --muted:#8fa6bb;
           --accent:#3fb6a8; --warn:#e0a13a; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:28px; background:var(--bg); color:var(--txt);
          font:14px/1.5 "Segoe UI",system-ui,sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .sub {{ color:var(--muted); font-size:13px; margin-bottom:20px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:22px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px; }}
  .kpi .v {{ font-size:24px; font-weight:600; color:var(--accent); }}
  .kpi .l {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
  .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:22px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px 18px; }}
  .card h2 {{ font-size:13px; margin:0 0 8px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }}
  .card ul {{ margin:0; padding-left:18px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:13px; }}
  th {{ background:#1d2c3a; text-align:left; padding:9px 10px; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
  td {{ padding:8px 10px; border-top:1px solid var(--line); vertical-align:top; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  tr.con-aviso {{ background:#2a2317; }}
  td.aviso {{ color:var(--warn); font-size:12px; }}
  @media (max-width:820px) {{ .cols {{ grid-template-columns:1fr; }} body {{ padding:16px; }} }}
</style>
</head>
<body>
<h1>Ruteo de conduit — {zona}</h1>
<p class="sub">{dxf} · {material} / {calibre} · {nivel}</p>

<div class="kpis">
  <div class="kpi"><div class="v">{tramos}</div><div class="l">Tramos</div></div>
  <div class="kpi"><div class="v">{largo:.1f} m</div><div class="l">Longitud total</div></div>
  <div class="kpi"><div class="v">{con_marcador}</div><div class="l">Con marcador</div></div>
  <div class="kpi"><div class="v">{sin_marcador}</div><div class="l">Sin marcador</div></div>
  <div class="kpi"><div class="v">{cajas}</div><div class="l">Cajas conexion</div></div>
  <div class="kpi"><div class="v">{cruces}</div><div class="l">Cruces planta</div></div>
  <div class="kpi"><div class="v">{avisos}</div><div class="l">Avisos</div></div>
</div>

<div class="cols">
  <div class="card"><h2>Por servicio</h2><ul>{resumen_servicio}</ul></div>
  <div class="card"><h2>Por diametro</h2><ul>{resumen_diametro}</ul></div>
</div>

<table>
<thead><tr><th>ID</th><th>Servicio</th><th>Capa</th><th>Cables</th><th>Diam.</th>
<th>Largo</th><th>Cota</th><th>Origen</th><th>Avisos</th></tr></thead>
<tbody>{filas}</tbody>
</table>
</body></html>
""".format(
        zona=html.escape(res.zona),
        dxf=html.escape(os.path.basename(res.dxf)),
        material=html.escape(res.material),
        calibre=html.escape(res.calibre),
        nivel=html.escape(res.nivel or "(sin nivel)"),
        tramos=s["tramos"],
        largo=s["longitud_total_m"],
        con_marcador=s["tramos_con_marcador"],
        sin_marcador=s["tramos_sin_marcador"],
        cajas=s["cajas_conexion"],
        cruces=s["cruces_planta"],
        avisos=s["avisos"],
        resumen_servicio=resumen_servicio,
        resumen_diametro=resumen_diametro,
        filas="\n".join(filas),
    )

    os.makedirs(os.path.dirname(os.path.abspath(ruta_html)), exist_ok=True)
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(contenido)
    return ruta_html
