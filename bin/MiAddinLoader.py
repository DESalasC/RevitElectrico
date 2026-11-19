# -*- coding: utf-8 -*-
"""
MiAddinLoader.py
================
Loader robusto para MiAddin.dll desde IronPython 2.7 (pyRevit en Revit 2026).

PROBLEMA que resuelve
--------------------
El error clasico:

    IOError: System.IO.IOException: Could not add reference to assembly MiAddin
       at IronPython.Runtime.ClrModule.AddReference(...)

Ocurre porque `clr.AddReference("name")` NO busca en `sys.path`. Busca en:
  1. El GAC (Global Assembly Cache).
  2. El PrivateBinPath del host (carpeta de Revit + probing paths del AppDomain).
  3. No encuentra "MiAddin" en ninguno de esos dos lugares => IOException.

SOLUCION
--------
Usar `clr.AddReferenceByPath(ruta_absoluta_a_MiAddin.dll)`, que SI toma
una ruta del sistema de archivos y carga la DLL directamente.

Si AddReferenceByPath falla, hay 3 fallbacks:
  - clr.AddReferenceToFileAndPath (API legacy de IronPython)
  - System.Reflection.Assembly.LoadFrom + clr.AddReference(asm)
  - System.Reflection.Assembly.LoadFrom + import directo

USO
---
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\MiAddinLoader.py").read())
    from MiAddin import Placer
    print Placer.Version()

Si quieres customizar la ruta:
    import os
    os.environ["MIADDIN_DLL"] = r"C:\\ruta\\custom\\MiAddin.dll"
    exec(open(r"...\\MiAddinLoader.py").read())
"""

import os
import sys
import clr


def _resolver_ruta_dll():
    """Devuelve la ruta absoluta a MiAddin.dll en orden de prioridad."""
    # 1. Variable de entorno explicita (maximo control)
    env_path = os.environ.get("MIADDIN_DLL")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. Carpeta bin del proyecto RevitElectrico (convencion)
    root = os.environ.get("REVITELECTRICO_ROOT",
                          r"D:\Work\PROJECTS\RevitElectrico")
    candidates = [
        os.path.join(root, "bin", "MiAddin.dll"),
        os.path.join(root, "MiAddin", "build", "MiAddin.dll"),
        os.path.join(root, "MiAddin", "MiAddin.dll"),
        os.path.join(root, "MiAddin.dll"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    # 3. Mismo directorio del script
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else None
    if here:
        c = os.path.join(here, "MiAddin.dll")
        if os.path.exists(c):
            return c

    return None


def _cargar_por_ruta(dll_path):
    """Intenta cargar la DLL con AddReferenceByPath y fallbacks."""
    # Metodo 1: AddReferenceByPath (preferido en IronPython 2.7+)
    try:
        clr.AddReferenceByPath(dll_path)
        return "AddReferenceByPath"
    except Exception as ex1:
        msg1 = str(ex1)

    # Metodo 2: AddReferenceToFileAndPath (API legacy, a veces funciona)
    try:
        # Solo el nombre del archivo, no la ruta completa
        # Requiere que la carpeta este en sys.path o en el PrivateBinPath
        folder = os.path.dirname(dll_path)
        if folder not in sys.path:
            sys.path.append(folder)
        clr.AddReferenceToFileAndPath(dll_path)
        return "AddReferenceToFileAndPath"
    except Exception as ex2:
        msg2 = str(ex2)

    # Metodo 3: Reflection Assembly.LoadFrom + clr.AddReference(Assembly)
    try:
        import System
        asm = System.Reflection.Assembly.LoadFrom(dll_path)
        clr.AddReference(asm)
        return "Assembly.LoadFrom + AddReference(asm)"
    except Exception as ex3:
        msg3 = str(ex3)

    # Ningun metodo funciono - reportar
    raise IOError(
        "No se pudo cargar MiAddin.dll desde: {0}\n\n"
        "Causas intentadas:\n"
        "  1. AddReferenceByPath: {1}\n"
        "  2. AddReferenceToFileAndPath: {2}\n"
        "  3. Assembly.LoadFrom + AddReference(asm): {3}\n\n"
        "Verifica:\n"
        "  - Que la DLL exista en la ruta.\n"
        "  - Que Microsoft.CSharp.dll este disponible (.NET Framework 4.x).\n"
        "  - Que la arquitectura coincida (Revit x64, DLL x64).\n"
        .format(dll_path, msg1, msg2, msg3)
    )


def cargar_miaddin():
    """Punto de entrada: carga MiAddin.dll y devuelve el modulo Placer."""
    dll_path = _resolver_ruta_dll()
    if not dll_path:
        raise IOError(
            "MiAddin.dll no encontrada. Setea una de estas opciones:\n"
            "  - Variable de entorno MIADDIN_DLL=ruta\\a\\MiAddin.dll\n"
            "  - Variable de entorno REVITELECTRICO_ROOT con la carpeta del proyecto\n"
            "  - Copia MiAddin.dll a <REVITELECTRICO_ROOT>\\bin\\\n"
            "O edita _resolver_ruta_dll() en este script."
        )

    metodo = _cargar_por_ruta(dll_path)
    print "[MiAddinLoader] DLL cargada: " + dll_path
    print "[MiAddinLoader] Metodo usado: " + metodo

    from MiAddin import Placer
    print "[MiAddinLoader] Placer.Version(): " + Placer.Version()
    return Placer


# --- Ejecucion al importar -------------------------------------------------
# Cuando haces `exec(open("MiAddinLoader.py").read())`, esto corre y deja
# `Placer` disponible en el scope global del llamador.
Placer = cargar_miaddin()
