# -*- coding: utf-8 -*-
"""conftest.py de RevitElectrico.

Fuerza basetemp a una carpeta dentro del proyecto (.pytest_temps) para evitar el
PermissionError [WinError 5] en el teardown de carpetas temporales de pytest en
Windows (ruta con espacios en el nombre de usuario y symlinks/junctions temporales).

Esto hace permanente la solución sin depender de pasar --basetemp en cada invocacion.
"""
from __future__ import annotations

from pathlib import Path


def pytest_configure(config):
    """Se ejecuta al iniciar pytest: redefine basetemp antes de crear carpetas temporales de sesion."""
    base = Path(config.rootdir) / ".pytest_temps"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    config.option.basetemp = str(base)
