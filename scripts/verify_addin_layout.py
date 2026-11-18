"""
verify_addin_layout.py
======================
Inspecciona la carpeta de add-ins de Revit y reporta si la instalacion
de mcp-servers-for-revit cumple con la estructura esperada.

Disenaado para correr en Windows (Python 3.8+, sin dependencias externas).
Solo usa la biblioteca estandar.

USO
---
    # Detectar version automaticamente (prefiere la mas alta numerada)
    python verify_addin_layout.py

    # Forzar una version especifica
    python verify_addin_layout.py --year 2026

    # Carpeta de addins personalizada
    python verify_addin_layout.py --addins-root "C:\\Users\\Dario Salas\\AppData\\Roaming\\Autodesk\\Revit\\Addins\\2026"

    # Guardar reporte en JSON
    python verify_addin_layout.py --json-out reporte_addin.json

EXIT CODES
----------
    0 = Instalacion correcta
    1 = Hay warnings pero no errores criticos
    2 = Hay errores criticos (no abrir Revit hasta arreglarlos)
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


# Estructura esperada del fork mcp-servers-for-revit
EXPECTED_STRUCTURE = {
    "manifest": "mcp-servers-for-revit.addin",
    "plugin_dir": "revit_mcp_plugin",
    "plugin_dll": "revit_mcp_plugin/RevitMCPPlugin.dll",
    "commandset_dir": "revit_mcp_plugin/Commands/RevitMCPCommandSet",
    "commandset_manifest": "revit_mcp_plugin/Commands/RevitMCPCommandSet/command.json",
    "commandset_year_dir": "revit_mcp_plugin/Commands/RevitMCPCommandSet/{year}",
    "commandset_dll": "revit_mcp_plugin/Commands/RevitMCPCommandSet/{year}/RevitMCPCommandSet.dll",
}

# DLLs que NO deben estar en la carpeta del plugin porque Revit
# ya los carga en su propio AppDomain. Si los encuentras, son la
# causa directa del "dependency hell".
PROHIBITED_IN_PLUGIN = {
    "RevitAPI.dll",
    "RevitAPIUI.dll",
    "Newtonsoft.Json.dll",
    "Microsoft.Windows.SDK.NET.dll",
}


def find_all_addins_roots():
    """Devuelve lista de (year_int, Path) para todas las carpetas Addins de Revit.

    Ordenadas de menor a mayor anio. Solo carpetas cuyo nombre es un entero
    (ej: 2024, 2025, 2026, 2027). Ignora carpetas como 'PyRevIT' u otras no numericas.
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit(
            "APPDATA no esta definida. Este script debe correr en Windows. "
            "Si lo estas corriendo en otro lado, usa --addins-root con la ruta completa."
        )

    base = Path(appdata) / "Autodesk" / "Revit" / "Addins"
    if not base.exists():
        raise SystemExit(
            "No se encontro la carpeta base: {}. "
            "Revisa que Revit este instalado o usa --addins-root.".format(base)
        )

    candidates = sorted(
        [p for p in base.iterdir() if p.is_dir() and p.name.isdigit()],
        key=lambda p: int(p.name),
    )
    return [(int(p.name), p) for p in candidates]


def find_addins_root(year=None):
    """Localiza una carpeta Addins especifica para un anio dado."""
    if not year:
        raise ValueError("find_addins_root requiere year. Usa find_all_addins_roots() para auto-detectar.")
    all_roots = find_all_addins_roots()
    for y, p in all_roots:
        if y == year:
            return p
    raise SystemExit(
        "No existe carpeta de add-ins para Revit {}. Versiones encontradas: {}".format(
            year, [y for y, _ in all_roots]
        )
    )


def has_mcp_installation(year_dir):
    """Detecta si una carpeta de add-ins tiene alguna senal de mcp-servers-for-revit.

    Retorna True si existe:
      - Carpeta revit_mcp_plugin/, O
      - Cualquier .addin que mencione RevitMCPPlugin / RevitMCPCommandSet / mcp-servers-for-revit
    """
    plugin_dir = year_dir / EXPECTED_STRUCTURE["plugin_dir"]
    if plugin_dir.exists():
        return True
    for addin_path in year_dir.glob("*.addin"):
        try:
            content = addin_path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if "revitmcp" in content or "mcp-servers-for-revit" in content:
            return True
    return False


def check_zone_identifier(path):
    """Detecta si un archivo viene de descarga de internet (Zone.Identifier ADS)."""
    if os.name != "nt":
        return False
    try:
        # NTFS Alternate Data Stream: <filename>:Zone.Identifier
        ads_path = "{}:Zone.Identifier".format(str(path))
        return os.path.exists(ads_path)
    except (OSError, ValueError):
        return False


def parse_addin_manifest(addin_path):
    """Parsea un .addin XML y devuelve lista de add-ins declarados."""
    results = []
    try:
        tree = ET.parse(addin_path)
        root = tree.getroot()
    except ET.ParseError as e:
        return [{"parse_error": str(e)}]

    for addin_node in root.findall("AddIn"):
        info = {
            "type": addin_node.get("Type", ""),
            "name": (addin_node.findtext("Name") or "").strip(),
            "assembly": (addin_node.findtext("Assembly") or "").strip(),
            "full_class_name": (addin_node.findtext("FullClassName") or "").strip(),
            "client_id": (addin_node.findtext("ClientId") or "").strip(),
        }
        results.append(info)
    return results


def classify_manifests(year_dir):
    """Clasifica los .addin por si registran el plugin, el command set, o ambos."""
    found = {
        "mcp_plugin": [],       # Registran RevitMCPPlugin correctamente
        "mcp_commandset": [],   # Registran RevitMCPCommandSet como app top-level (BUG)
        "ambiguous": [],        # Mencionan ambos (tambien problematico)
        "others": [],           # Otros add-ins sin relacion con MCP
    }

    for addin_path in sorted(year_dir.glob("*.addin")):
        addins = parse_addin_manifest(addin_path)
        if not addins:
            found["others"].append({"path": str(addin_path), "note": "vacio o no parseable"})
            continue

        has_plugin = False
        has_commandset = False
        for info in addins:
            if "parse_error" in info:
                continue
            assembly = info.get("assembly", "").lower()
            class_name = info.get("full_class_name", "").lower()
            name = info.get("name", "").lower()
            if "revitmcpplugin" in assembly or "revitmcpplugin" in class_name or "mcp-servers-for-revit" in name:
                has_plugin = True
            if "revitmcpcommandset" in assembly or "revitmcpcommandset" in class_name:
                has_commandset = True

        if has_plugin and has_commandset:
            found["ambiguous"].append({"path": str(addin_path), "addins": addins})
        elif has_plugin:
            found["mcp_plugin"].append({"path": str(addin_path), "addins": addins})
        elif has_commandset:
            found["mcp_commandset"].append({"path": str(addin_path), "addins": addins})
        else:
            found["others"].append({"path": str(addin_path), "addins": addins})

    return found


def scan_dlls_in_plugin(year_dir):
    """Recorre el arbol del plugin en busca de DLLs bloqueados o prohibidos."""
    plugin_dir = year_dir / EXPECTED_STRUCTURE["plugin_dir"]
    blocked = []
    prohibited = []

    if not plugin_dir.exists():
        return blocked, prohibited

    for dll in plugin_dir.rglob("*.dll"):
        if check_zone_identifier(dll):
            blocked.append(str(dll))
        if dll.name in PROHIBITED_IN_PLUGIN:
            prohibited.append(str(dll))

    return blocked, prohibited


def verify_year(year_dir, year):
    """Ejecuta todas las verificaciones y devuelve un reporte estructurado."""
    report = {
        "year_dir": str(year_dir),
        "year": year,
        "errors": [],
        "warnings": [],
        "ok": [],
        "structure": {},
        "addins": {},
        "blocked_dlls": [],
        "prohibited_dlls_in_plugin": [],
    }

    # 1. Estructura de archivos esperada
    plugin_dir = year_dir / EXPECTED_STRUCTURE["plugin_dir"]
    report["structure"]["plugin_dir_exists"] = plugin_dir.exists()
    if not plugin_dir.exists():
        report["errors"].append("Falta la carpeta del plugin: {}".format(plugin_dir))
        # Sin plugin no podemos verificar mas; seguimos con manifiestos
    else:
        plugin_dll = year_dir / EXPECTED_STRUCTURE["plugin_dll"]
        report["structure"]["plugin_dll_exists"] = plugin_dll.exists()
        if not plugin_dll.exists():
            report["errors"].append("Falta RevitMCPPlugin.dll: {}".format(plugin_dll))

        cs_dir = year_dir / EXPECTED_STRUCTURE["commandset_dir"]
        report["structure"]["commandset_dir_exists"] = cs_dir.exists()
        if not cs_dir.exists():
            report["errors"].append("Falta carpeta del CommandSet: {}".format(cs_dir))

        cs_json = year_dir / EXPECTED_STRUCTURE["commandset_manifest"]
        report["structure"]["commandset_json_exists"] = cs_json.exists()
        if not cs_json.exists():
            report["errors"].append("Falta command.json: {}".format(cs_json))

        cs_year_dir = year_dir / EXPECTED_STRUCTURE["commandset_year_dir"].format(year=year)
        report["structure"]["commandset_year_dir_exists"] = cs_year_dir.exists()
        if not cs_year_dir.exists():
            report["errors"].append(
                "Falta carpeta del anio del CommandSet para Revit {}: {}".format(year, cs_year_dir)
            )

        cs_dll = year_dir / EXPECTED_STRUCTURE["commandset_dll"].format(year=year)
        report["structure"]["commandset_dll_exists"] = cs_dll.exists()
        if not cs_dll.exists():
            report["errors"].append(
                "Falta RevitMCPCommandSet.dll para Revit {}: {}".format(year, cs_dll)
            )

    # 2. Manifiestos .addin
    addin_map = classify_manifests(year_dir)
    report["addins"] = {
        "mcp_plugin_manifests": addin_map["mcp_plugin"],
        "mcp_commandset_manifests": addin_map["mcp_commandset"],
        "ambiguous_manifests": addin_map["ambiguous"],
        "others": addin_map["others"],
    }

    if len(addin_map["mcp_plugin"]) == 0:
        report["errors"].append(
            "No se encontro ningun .addin que registre RevitMCPPlugin como ExternalApplication. "
            "Falta el manifiesto principal mcp-servers-for-revit.addin."
        )
    elif len(addin_map["mcp_plugin"]) > 1:
        report["errors"].append(
            "Hay {} manifiestos que registran el plugin (debe ser 1): {}".format(
                len(addin_map["mcp_plugin"]),
                [Path(m["path"]).name for m in addin_map["mcp_plugin"]],
            )
        )
    else:
        report["ok"].append("Hay exactamente 1 manifiesto para el plugin.")

    # ESTE es el bug que tuviste:
    n_cs = len(addin_map["mcp_commandset"])
    if n_cs > 0:
        names = [Path(m["path"]).name for m in addin_map["mcp_commandset"]]
        report["errors"].append(
            "ENCONTRADO {} manifiesto(s) que registran RevitMCPCommandSet como "
            "ExternalApplication de Revit: {}. ELIMINALO/S. El CommandSet debe ser "
            "cargado dinamicamente por el plugin leyendo command.json, no por Revit "
            "como add-in de nivel superior.".format(n_cs, names)
        )

    n_amb = len(addin_map["ambiguous"])
    if n_amb > 0:
        names = [Path(m["path"]).name for m in addin_map["ambiguous"]]
        report["errors"].append(
            "{} manifiesto(s) declaran a la vez el plugin y el command set en el mismo "
            "archivo XML: {}. Separa la declaracion del command set y eliminala.".format(
                n_amb, names
            )
        )

    # 3. DLLs bloqueados y prohibidos en el arbol del plugin
    blocked, prohibited = scan_dlls_in_plugin(year_dir)
    report["blocked_dlls"] = blocked
    report["prohibited_dlls_in_plugin"] = prohibited

    if blocked:
        report["warnings"].append(
            "{} DLL(s) marcados como descargados de internet (Zone.Identifier ADS). "
            "Revit los puede rechazar silenciosamente. Desbloquealos con PowerShell:\n"
            "    Get-ChildItem -Recurse -Filter '*.dll' '{}' | Unblock-File".format(
                len(blocked),
                year_dir / EXPECTED_STRUCTURE["plugin_dir"],
            )
        )

    if prohibited:
        report["errors"].append(
            "Se encontraron DLLs que NO deben estar en la carpeta del plugin porque "
            "Revit ya los carga en su AppDomain (son los que causan el dependency hell): "
            "{}. Borralos de la carpeta del plugin y deja que Revit use sus propias "
            "versiones.".format(prohibited)
        )

    # 4. Resumen OK final
    if not report["errors"]:
        report["ok"].append(
            "Estructura de mcp-servers-for-revit correcta para Revit {}.".format(year)
        )

    return report


def print_report(report):
    """Imprime el reporte en consola."""
    year = report["year"]
    bar = "=" * 70
    line = "-" * 70

    print()
    print(bar)
    print("  Verificacion de add-ins - Revit {}".format(year))
    print("  Carpeta: {}".format(report["year_dir"]))
    print(bar)
    print()

    # Estructura
    print("[ESTRUCTURA]")
    for k, v in sorted(report["structure"].items()):
        icon = "[OK]" if v else "[--]"
        print("  {} {}: {}".format(icon, k, v))
    print()

    # Manifiestos
    a = report["addins"]
    print("[MANIFIESTOS .addin]")
    print("  Plugin manifests (esperado: 1): {}".format(len(a["mcp_plugin_manifests"])))
    for m in a["mcp_plugin_manifests"]:
        print("      - {}".format(Path(m["path"]).name))
    print("  CommandSet como ExternalApp (esperado: 0): {}".format(
        len(a["mcp_commandset_manifests"])
    ))
    for m in a["mcp_commandset_manifests"]:
        print("      - {}".format(Path(m["path"]).name))
    print("  Ambiguos (declar ambos): {}".format(len(a["ambiguous_manifests"])))
    for m in a["ambiguous_manifests"]:
        print("      - {}".format(Path(m["path"]).name))
    print("  Otros add-ins en la carpeta: {}".format(len(a["others"])))
    print()

    # DLLs bloqueados
    if report["blocked_dlls"]:
        print("[DLLs BLOQUEADOS (Zone.Identifier)]: {}".format(len(report["blocked_dlls"])))
        for d in report["blocked_dlls"][:10]:
            print("      - {}".format(d))
        if len(report["blocked_dlls"]) > 10:
            print("      ... y {} mas".format(len(report["blocked_dlls"]) - 10))
        print()

    # DLLs prohibidos
    if report["prohibited_dlls_in_plugin"]:
        print("[DLLs PROHIBIDOS en carpeta del plugin]: {}".format(
            len(report["prohibited_dlls_in_plugin"])
        ))
        for d in report["prohibited_dlls_in_plugin"]:
            print("      - {}".format(d))
        print()

    # Errores
    if report["errors"]:
        print("[ERRORES - bloquean arranque] ({})".format(len(report["errors"])))
        for e in report["errors"]:
            print("  [X] {}".format(e))
        print()

    # Warnings
    if report["warnings"]:
        print("[WARNINGS] ({})".format(len(report["warnings"])))
        for w in report["warnings"]:
            print("  [!] {}".format(w))
        print()

    # OK
    if report["ok"]:
        print("[OK]")
        for o in report["ok"]:
            print("  [+] {}".format(o))
        print()

    # Veredicto
    print(line)
    if report["errors"]:
        print("  VEREDICTO: INSTALACION ROTA. {} error(es) critico(s).".format(len(report["errors"])))
        print("  Arregla los ERRORES antes de abrir Revit.")
    elif report["warnings"]:
        print("  VEREDICTO: INSTALACION DUDOSA. {} warning(s).".format(len(report["warnings"])))
        print("  Recomendado arreglar los warnings, pero puede funcionar.")
    else:
        print("  VEREDICTO: INSTALACION CORRECTA. Listo para abrir Revit.")
    print(line)
    print()


def print_summary(reports):
    """Imprime una tabla compacta cuando se escanean varias carpetas de add-ins."""
    print()
    print("=" * 70)
    print("  RESUMEN MULTI-VERSION")
    print("=" * 70)
    print("  {:<6} {:<10} {:<10} {:<10} {:<10}  {}".format(
        "Year", "Errores", "Warnings", "OK", "Plugin?", "Veredicto"
    ))
    print("-" * 70)
    for r in reports:
        has_plugin = r["structure"].get("plugin_dir_exists", False)
        plugin_marker = "si" if has_plugin else "--"
        verdict = "ROTA" if r["errors"] else ("dudosa" if r["warnings"] else "OK")
        print("  {:<6} {:<10} {:<10} {:<10} {:<10}  {}".format(
            r["year"],
            len(r["errors"]),
            len(r["warnings"]),
            len(r["ok"]),
            plugin_marker,
            verdict,
        ))
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Verifica la instalacion del add-in mcp-servers-for-revit para Revit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--year", type=int, default=None,
                        help="Anio de Revit (ej: 2026). Si se omite, escanea TODAS "
                             "las carpetas de add-ins encontradas y muestra un resumen.")
    parser.add_argument("--addins-root", type=str, default=None,
                        help="Carpeta Addins personalizada "
                             "(default: %%APPDATA%%\\Autodesk\\Revit\\Addins\\<year>).")
    parser.add_argument("--json-out", type=str, default=None,
                        help="Ruta donde guardar el reporte como JSON.")
    args = parser.parse_args()

    # Estado compartido entre los 3 casos
    reports = []
    sin_mcp = []  # lista de (year, Path) sin MCP instalado (solo para el resumen)

    # Caso 1: ruta explicita via --addins-root
    if args.addins_root:
        year_dir = Path(args.addins_root)
        if not year_dir.exists():
            raise SystemExit("No existe: {}".format(year_dir))
        year = args.year or (int(year_dir.name) if year_dir.name.isdigit() else 0)
        print("[INFO] Inspeccionando carpeta explicita: {}".format(year_dir))
        reports = [verify_year(year_dir, year)]
    # Caso 2: anio explicito via --year
    elif args.year:
        year_dir = find_addins_root(year=args.year)
        print("[INFO] Inspeccionando carpeta Revit {}: {}".format(args.year, year_dir))
        reports = [verify_year(year_dir, args.year)]
    # Caso 3: auto-deteccion - escanear TODAS las carpetas numeradas
    else:
        all_roots = find_all_addins_roots()
        if not all_roots:
            raise SystemExit(
                "No se encontraron carpetas numeradas. Usa --addins-root con la ruta completa."
            )
        con_mcp = []
        for y, p in all_roots:
            if has_mcp_installation(p):
                con_mcp.append((y, p))
            else:
                sin_mcp.append((y, p))
        print("[INFO] Detectadas {} carpetas: {}.".format(len(all_roots), [y for y, _ in all_roots]))
        print("[INFO] Con MCP instalado: {}. Sin MCP: {}.".format(
            [y for y, _ in con_mcp], [y for y, _ in sin_mcp]
        ))
        if not con_mcp:
            print("[WARN] Ninguna carpeta tiene mcp-servers-for-revit instalado.")
        reports = [verify_year(p, y) for y, p in con_mcp]

    # Imprimir reportes individuales (solo carpetas con MCP o explicitas)
    for i, report in enumerate(reports):
        if i > 0:
            print()
        print_report(report)

    # Resumen si hay multiples carpetas en juego (con o sin MCP)
    if len(reports) + len(sin_mcp) > 1:
        all_for_summary = list(reports)
        for y, p in sin_mcp:
            all_for_summary.append({
                "year": y,
                "year_dir": str(p),
                "errors": [],
                "warnings": [],
                "ok": ["Sin MCP instalado (no es error si no usas esta version)."],
                "structure": {"plugin_dir_exists": False},
                "addins": {},
                "blocked_dlls": [],
                "prohibited_dlls_in_plugin": [],
                "mcp_present": False,
            })
        print_summary(all_for_summary)

    # Guardar JSON
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = reports[0] if len(reports) == 1 else {"reports": reports}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("[INFO] Reporte JSON guardado: {}".format(out_path))

    # Exit code = peor estado encontrado entre todas las carpetas
    if any(r["errors"] for r in reports):
        sys.exit(2)
    elif any(r["warnings"] for r in reports):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
