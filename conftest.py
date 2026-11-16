# -*- coding: utf-8 -*-
"""conftest.py de RevitElectrico.

Fija ``basetemp`` a una carpeta por corrida dentro del proyecto para evitar el
``PermissionError [WinError 5]`` en el teardown de carpetas temporales de pytest.

Notas de la correccion 2026-11-15 (F0):

* ``basetemp`` **no** es una clave valida de ``pytest.ini`` en pytest 9: emite
  ``PytestConfigWarning: Unknown config option: basetemp`` y se ignora. Por eso la
  unica via efectiva es este hook.
* La carpeta fija ``.pytest_temps`` quedo con una ACL rota en la estacion de trabajo
  (no se puede ni leer con ``Get-Acl``) y su borrado falla. Para no depender de ella,
  cada corrida usa ``.pytest_tmp/run-<pid>``; el teardown afecta solo a esa subcarpeta.
* La limpieza de corridas anteriores es best-effort: nunca hace fallar la sesion.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

BASE_NOMBRE = ".pytest_tmp"
EDAD_MINIMA_LIMPIEZA_S = 24 * 60 * 60


def _limpiar_corridas_viejas(base_raiz: Path) -> None:
    """Elimina subcarpetas ``run-*`` con mas de un dia de antiguedad. Nunca lanza."""
    ahora = time.time()
    try:
        candidatos = list(base_raiz.glob("run-*"))
    except OSError:
        return
    for candidato in candidatos:
        try:
            if not candidato.is_dir():
                continue
            if ahora - candidato.stat().st_mtime < EDAD_MINIMA_LIMPIEZA_S:
                continue
            shutil.rmtree(str(candidato), ignore_errors=True)
        except OSError:
            continue


def pytest_configure(config):
    """Redefine basetemp antes de que pytest cree las carpetas temporales de sesion."""
    base_raiz = Path(config.rootdir) / BASE_NOMBRE
    try:
        base_raiz.mkdir(parents=True, exist_ok=True)
    except OSError:
        config.option.basetemp = None
        return

    _limpiar_corridas_viejas(base_raiz)

    corrida = base_raiz / ("run-{pid}".format(pid=os.getpid()))
    try:
        corrida.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(corrida)
    except OSError:
        # Si no se puede crear la subcarpeta, se deja que pytest use su valor por defecto.
        config.option.basetemp = None
