# -*- coding: utf-8 -*-
"""
RE7_PREFLIGHT_PYREVIT_v01.py  (RETIRADO)
Este script no se ejecutaba al lanzarse con exec(open(...).read()) porque su
cuerpo estaba protegido por un guard __main__, y el shell de pyRevit no
lo garantiza. Ademas no dejaba rastro en archivo: si fallaba, la consola
quedaba muda.

Ahora solo delega en RE7_PREFLIGHT_PYREVIT_v02.py, que:
  - se ejecuta de forma incondicional,
  - escribe log en data/f7_preflight_pyrevit.log,
  - escribe reporte JSON en data/f7_preflight_v02.json,
  - sigue siendo de SOLO LECTURA (sin transaccion).
"""
import os

_DEFAULT_ROOT = r"D:\Work\PROJECTS\RevitElectrico"


def _candidatos_directorio():
    out = []
    try:
        out.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    raiz = os.environ.get("REVITELECTRICO_ROOT", "").strip()
    if raiz:
        out.append(os.path.join(raiz, "scripts", "pyrevit"))
    out.append(os.path.join(_DEFAULT_ROOT, "scripts", "pyrevit"))
    return out


def _buscar_v02():
    for d in _candidatos_directorio():
        try:
            p = os.path.join(d, "RE7_PREFLIGHT_PYREVIT_v02.py")
            if os.path.exists(p):
                return p
        except Exception:
            continue
    return None


_src_path = _buscar_v02()
print("[RE7_PREFLIGHT v01 RETIRADO] delegando a v02 ...")
if _src_path is None:
    print("ERROR: no se encontro RE7_PREFLIGHT_PYREVIT_v02.py")
    print("       Defina REVITELECTRICO_ROOT o revise: {}".format(_DEFAULT_ROOT))
else:
    print("[RE7_PREFLIGHT v01] ejecutando: {}".format(_src_path))
    _f = open(_src_path, "r")
    _src = _f.read()
    _f.close()
    exec(compile(_src, _src_path, "exec"), globals())
