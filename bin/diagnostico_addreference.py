# -*- coding: utf-8 -*-
"""
diagnostico_addreference.py
===========================
Diagnostica por que clr.AddReference("MiAddin") falla en tu entorno.

Causas tipicas del error:
    IOError: System.IO.IOException: Could not add reference to assembly MiAddin

1. DLL no encontrada en el path esperado (no esta en GAC ni en probing path).
2. Bitness mismatch: Revit es x64 pero la DLL es x86 (o viceversa).
3. Microsoft.CSharp.dll no esta disponible (de la que MiAddin depende).
4. .NET Framework 4.8 no instalado (IronPython 2.7 no carga DLLs .NET 8).
5. Path con caracteres especiales o espacios mal escapados.
6. La DLL esta bloqueada por Windows (Mark of the Web / SmartScreen).

Uso:
    exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\diagnostico_addreference.py").read())
    diagnosticar()
"""

import os
import sys
import clr


def _check(path):
    """Devuelve (existe, size_bytes, mensaje) para una ruta."""
    if not path:
        return False, 0, "ruta vacia"
    if os.path.exists(path):
        return True, os.path.getsize(path), "OK"
    return False, 0, "no existe"


def _es_x64(dll_path):
    """Lee el PE header para saber si la DLL es x64 (True) o x86 (False)."""
    try:
        with open(dll_path, "rb") as f:
            # DOS header: 'MZ' en offset 0
            if f.read(2) != b"MZ":
                return None, "no es PE (sin MZ)"
            # PE offset en offset 0x3C
            f.seek(0x3C)
            pe_offset = int.from_bytes(f.read(4), "little")
            f.seek(pe_offset)
            if f.read(4) != b"PE\x00\x00":
                return None, "no es PE (sin PE header)"
            # Machine type en offset pe_offset + 4 (2 bytes)
            machine = int.from_bytes(f.read(2), "little")
            if machine == 0x8664:  # IMAGE_FILE_MACHINE_AMD64
                return True, "x64 (AMD64)"
            elif machine == 0x14C:  # IMAGE_FILE_MACHINE_I386
                return False, "x86 (I386)"
            else:
                return None, "machine=0x{0:x}".format(machine)
    except Exception as ex:
        return None, "error leyendo PE: " + str(ex)


def _buscar_en_gac():
    """Intenta buscar MiAddin en el GAC."""
    try:
        import System
        # El GAC de .NET Framework 4.x esta en C:\Windows\Microsoft.NET\assembly
        gac_dirs = [
            r"C:\Windows\Microsoft.NET\assembly\GAC_MSIL",
            r"C:\Windows\Microsoft.NET\assembly\GAC_64",
            r"C:\Windows\Microsoft.NET\assembly\GAC_32",
            r"C:\Windows\assembly\GAC_MSIL",  # legacy .NET 2.0
        ]
        found = []
        for gac in gac_dirs:
            if os.path.exists(gac):
                for entry in os.listdir(gac):
                    if "MiAddin" in entry:
                        found.append(os.path.join(gac, entry))
        return found
    except Exception:
        return []


def _buscar_microsoft_csharp():
    """Verifica que Microsoft.CSharp.dll este disponible."""
    try:
        import System
        # Cargar via reflexion
        try:
            asm = System.Reflection.Assembly.Load("Microsoft.CSharp, Version=4.0.0.0, "
                                                  "Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a")
            return True, "cargada desde GAC: " + asm.Location
        except Exception:
            pass
        # Buscar en disco
        candidates = [
            r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\Microsoft.CSharp.dll",
            r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\Microsoft.CSharp.dll",
        ]
        for c in candidates:
            if os.path.exists(c):
                return True, c
        return False, "no encontrada en GAC ni en disco"
    except Exception as ex:
        return False, "error: " + str(ex)


def _intentar_addreference_por_nombre():
    """Replica el intento del script que fallo y captura el error exacto."""
    try:
        clr.AddReference("MiAddin")
        return True, "OK - AddReference por nombre funciono"
    except Exception as ex:
        return False, str(ex)


def _intentar_addreferencebypath(dll_path):
    """Prueba el metodo correcto: AddReferenceByPath."""
    try:
        clr.AddReferenceByPath(dll_path)
        return True, "OK - AddReferenceByPath funciono"
    except Exception as ex:
        return False, str(ex)


def diagnosticar():
    """Diagnostico completo."""
    print "=" * 70
    print "DIAGNOSTICO clr.AddReference('MiAddin')"
    print "=" * 70

    # --- 1. Resolver ruta de la DLL ---
    print "\n[1/6] Resolviendo ruta de MiAddin.dll..."
    root = os.environ.get("REVITELECTRICO_ROOT", r"D:\Work\PROJECTS\RevitElectrico")
    print "      REVITELECTRICO_ROOT =", root
    print "      MIADDIN_DLL =", os.environ.get("MIADDIN_DLL", "(no set)")

    candidates = [
        os.environ.get("MIADDIN_DLL"),
        os.path.join(root, "bin", "MiAddin.dll"),
        os.path.join(root, "MiAddin", "build", "MiAddin.dll"),
        os.path.join(root, "MiAddin", "MiAddin.dll"),
        os.path.join(root, "MiAddin.dll"),
    ]
    found_path = None
    for c in candidates:
        if not c:
            continue
        existe, size, msg = _check(c)
        print "      [{0}] {1} ({2})".format(
            "OK" if existe else "  ", c, "{0} bytes".format(size) if existe else msg
        )
        if existe and not found_path:
            found_path = c

    if not found_path:
        print "\n>>> ACCION: Copia MiAddin.dll a una de las rutas listadas,"
        print "    o setea la variable MIADDIN_DLL con la ruta absoluta."
        return False

    print "\n      DLL encontrada:", found_path

    # --- 2. Verificar bitness ---
    print "\n[2/6] Verificando arquitectura de la DLL..."
    es64, msg = _es_x64(found_path)
    print "      Arquitectura DLL:", msg
    try:
        import System
        proc_bits = System.IntPtr.Size * 8  # 4 bytes en x86, 8 en x64
        print "      Arquitectura proceso Revit:", proc_bits, "bits"
        if es64 is not None:
            if (es64 and proc_bits == 64) or (not es64 and proc_bits == 32):
                print "      [OK] Arquitecturas coinciden"
            else:
                print "      [FAIL] Mismatch! DLL es {0} pero Revit es {1}".format(
                    "x64" if es64 else "x86", proc_bits
                )
                print "      >>> ACCION: Recompila la DLL con el Platform correcto."
                print "          - Si Revit es x64 (lo normal): -p:Platform=x64"
                print "          - Si Revit es x86: -p:Platform=x86"
                return False
    except Exception as ex:
        print "      (no se pudo verificar proceso:", str(ex), ")"

    # --- 3. Verificar Microsoft.CSharp.dll ---
    print "\n[3/6] Verificando Microsoft.CSharp.dll (dependencia de MiAddin)..."
    ok, msg = _buscar_microsoft_csharp()
    print "      [{0}] {1}".format("OK" if ok else "FAIL", msg)
    if not ok:
        print "      >>> ACCION: Instala .NET Framework 4.8 Developer Pack."
        print "          https://dotnet.microsoft.com/download/dotnet-framework/net48"
        return False

    # --- 4. .NET Framework runtime version ---
    print "\n[4/6] Version de .NET Framework..."
    try:
        import System
        ver = System.Environment.Version
        print "      Runtime Version:", ver.ToString()
        print "      OS:", System.Environment.OSVersion.ToString(),
        print " (", System.IntPtr.Size * 8, "bits )"
    except Exception as ex:
        print "      (no se pudo leer):", str(ex)

    # --- 5. GAC ---
    print "\n[5/6] Buscando MiAddin en el GAC..."
    gac_hits = _buscar_en_gac()
    if gac_hits:
        print "      Encontrada en GAC:", gac_hits
    else:
        print "      (no esta en el GAC - esto es NORMAL para DLLs externas)"

    # --- 6. Reproducir error original + probar fix ---
    print "\n[6/6] Probando metodos de carga..."
    ok1, msg1 = _intentar_addreference_por_nombre()
    print "      clr.AddReference('MiAddin'):",
    print "[OK]" if ok1 else "[FAIL]"
    print "        ->", msg1

    ok2, msg2 = _intentar_addreferencebypath(found_path)
    print "      clr.AddReferenceByPath(path):",
    print "[OK]" if ok2 else "[FAIL]"
    print "        ->", msg2

    if ok2:
        print "\n>>> SOLUCION: usa MiAddinLoader.py o directamente:"
        print "    import clr"
        print '    clr.AddReferenceByPath(r"' + found_path + '")'
        print "    from MiAddin import Placer"
        print "    print Placer.Version()"
        return True
    elif ok1:
        print "\n>>> OK: AddReference por nombre SI funciono. Usealo directamente."
        return True
    else:
        print "\n>>> NINGUN metodo funciono. Causas posibles:"
        print "    - DLL bloqueada por Windows (clic derecho > Propiedades > Unblock)"
        print "    - DLL corrupta (re-descarga/copiala)"
        print "    - Antivirus bloqueando la carga"
        print "    - Permisos de lectura en la ruta"
        return False


if __name__ == "__main__":
    diagnosticar()
