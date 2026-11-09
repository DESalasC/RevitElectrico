# -*- coding: utf-8 -*-
"""
RE_ACTIVAR_SYMBOLOS_v01.py — Asegura que los símbolos (tipos) de familia
solicitados por Tarea F existan y estén activos en el documento RVT activo.

Lee el JSON de entrada de Tarea F (data/apto_F_02_aplicar_mapa_v3.json) y,
para cada acción con familia + símbolo, verifica que el símbolo exista dentro
de la familia cargada. Estrategia:
  1. Si el símbolo ya existe y está activo -> lo usa tal cual.
  2. Si el símbolo existe pero está inactivo -> lo activa.
  3. Si el símbolo no existe -> duplica el primer símbolo disponible de la
     familia con el nombre solicitado y lo activa.

USO (dentro de Revit con pyRevit):
  pyrevit agent run "src/fase-6-revit/RE_ACTIVAR_SYMBOLOS_v01.py" --revit=<PID> --mode=modify --title="Activar simbolos Tarea F" --timeout=300

Opciones CLI:
  --json-in  Ruta al JSON de entrada de Tarea F (default: data/apto_F_02_aplicar_mapa_v3.json)
  --json-out Ruta del JSON de resultado (default: data/activar_symbolos_resultado.json)

IronPython 2.7 (dentro de Revit / pyRevit) — SIN type hints, SIN f-strings, SIN requests/bs4.
Usar .format() y concatenación de strings.


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import json
import os
from datetime import datetime


def _ascii_safe(valor):
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor
    try:
        return str(valor).encode("ascii", "replace").decode("ascii")
    except Exception:
        return "?"


def _sanitizar_dict(d):
    if isinstance(d, dict):
        return {_ascii_safe(k): _sanitizar_dict(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [_sanitizar_dict(v) for v in d]
    elif isinstance(d, tuple):
        return tuple(_sanitizar_dict(v) for v in d)
    else:
        return _ascii_safe(d)


def _guardar_json(ruta, datos):
    dirpath = os.path.dirname(ruta)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath)
    with open(ruta, "w") as f:
        datos_limpios = _sanitizar_dict(datos)
        contenido = json.dumps(datos_limpios, indent=2, ensure_ascii=True)
        f.write(contenido)


def _cargar_json(ruta):
    with open(ruta, "r") as f:
        return json.load(f)


def _import_revit_db():
    import sys
    mock_db = sys.modules.get("Autodesk.Revit.DB")
    if mock_db is not None:
        return {
            "FilteredElementCollector": getattr(mock_db, "FilteredElementCollector", None),
            "Family": getattr(mock_db, "Family", None),
            "FamilySymbol": getattr(mock_db, "FamilySymbol", None),
        }
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector,
        Family,
        FamilySymbol,
    )
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "Family": Family,
        "FamilySymbol": FamilySymbol,
    }


def _obtener_nombre_elemento(elemento, revit_db):
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass
    try:
        import Autodesk.Revit.DB as _db
        p = elemento.get_Parameter(_db.BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            valor = p.AsString()
            if valor:
                return valor
    except Exception:
        pass
    return None


def _obtener_nombre_simbolo(simbolo, revit_db):
    try:
        nombre = getattr(simbolo, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass
    try:
        import Autodesk.Revit.DB as _db
        p = simbolo.get_Parameter(_db.BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            valor = p.AsString()
            if valor:
                return valor
    except Exception:
        pass
    try:
        for parametro in simbolo.Parameters:
            try:
                valor = parametro.AsString()
                if valor and valor.strip():
                    return valor
            except Exception:
                continue
    except Exception:
        pass
    return None


def _nombre_coincide(nombre_obtenido, nombre_esperado):
    if not nombre_obtenido or not nombre_esperado:
        return False
    return nombre_obtenido.strip().lower() == nombre_esperado.strip().lower()


def _buscar_familia_por_nombre(doc, nombre_familia, revit_db):
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    Family = revit_db.get("Family")
    if Family is None:
        return None
    colector = FilteredElementCollector(doc).OfClass(Family)
    for fam in colector.ToElements():
        try:
            nombre_fam = _obtener_nombre_elemento(fam, revit_db)
            if _nombre_coincide(nombre_fam, nombre_familia):
                return fam
        except Exception:
            continue
    return None


def _listar_simbolos_familia(familia, doc, revit_db):
    simbolos = []
    for id_elem in familia.GetFamilySymbolIds():
        simbolo = doc.GetElement(id_elem)
        if simbolo is None:
            continue
        nombre_sim = _obtener_nombre_simbolo(simbolo, revit_db)
        simbolos.append((simbolo, nombre_sim))
    return simbolos


def _activar_simbolo(simbolo, doc):
    try:
        if not simbolo.IsActive:
            simbolo.Activate()
            doc.Regenerate()
            return True
    except Exception:
        pass
    return False


def _duplicar_simbolo(simbolo, nuevo_nombre):
    try:
        return simbolo.Duplicate(nuevo_nombre)
    except Exception:
        return None


def asegurar_simbolo(doc, nombre_familia, nombre_simbolo, revit_db):
    """
    Asegura que exista y esté activo el símbolo solicitado.
    Retorna (simbolo, nombre_usado, accion) donde accion es:
      'ya_existia_activo', 'se_activo', 'se_duplico', 'no_disponible',
      'familia_no_encontrada'.
    """
    familia = _buscar_familia_por_nombre(doc, nombre_familia, revit_db)
    if familia is None:
        return None, None, "familia_no_encontrada"

    simbolos = _listar_simbolos_familia(familia, doc, revit_db)

    # 1. Coincidencia exacta
    for simbolo, nombre_sim in simbolos:
        if _nombre_coincide(nombre_sim, nombre_simbolo):
            if simbolo.IsActive:
                return simbolo, nombre_sim, "ya_existia_activo"
            else:
                _activar_simbolo(simbolo, doc)
                return simbolo, nombre_sim, "se_activo"

    # 2. No existe: duplicar el primero disponible
    if simbolos:
        simbolo_base, nombre_base = simbolos[0]
        nuevo = _duplicar_simbolo(simbolo_base, nombre_simbolo)
        if nuevo is not None:
            _activar_simbolo(nuevo, doc)
            return nuevo, nombre_simbolo, "se_duplico"

    return None, None, "no_disponible"


def main():
    print("=" * 60)
    print("RE_ACTIVAR_SYMBOLOS_v01 — Activar símbolos de familia para Tarea F")
    print("=" * 60)

    revit_db = _import_revit_db()

    app = __revit__.Application
    uidoc = __revit__.ActiveUIDocument

    doc = None
    if uidoc is not None:
        doc = uidoc.Document
    else:
        try:
            docs = app.Documents
            if docs is not None and docs.Size > 0:
                doc = docs.get_Item(0)
        except Exception:
            doc = None

    if doc is None:
        print("ERROR: No hay un documento de Revit activo abierto.")
        return {"conectado": False}

    print("Documento: {}".format(doc.Title))

    import argparse
    parser = argparse.ArgumentParser(
        description="Asegura que los símbolos de familia de Tarea F existan y estén activos"
    )
    parser.add_argument(
        "--json-in",
        type=str,
        default="",
        help="Ruta al JSON de entrada de Tarea F (opcional).",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de resultado de salida (opcional).",
    )
    args = parser.parse_args()

    root = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())

    json_in = args.json_in
    if not json_in:
        json_in = os.path.join(root, "data", "apto_F_02_aplicar_mapa_v3.json")
    print("JSON de entrada: {}".format(json_in))

    reporte = _cargar_json(json_in)
    acciones = reporte.get("acciones_modelar", [])
    print("Acciones de modelado a procesar: {}".format(len(acciones)))

    ya_vistos = set()
    resultados = []
    resumen = {
        "ya_existia_activo": 0,
        "se_activo": 0,
        "se_duplico": 0,
        "no_disponible": 0,
        "familia_no_encontrada": 0,
    }

    for accion in acciones:
        familia_nombre = accion.get("familia")
        simbolo_nombre = accion.get("simbolo")
        clave = (familia_nombre, simbolo_nombre)

        if clave in ya_vistos:
            continue
        ya_vistos.add(clave)

        if not familia_nombre or not simbolo_nombre:
            continue

        print("  {} / {}".format(familia_nombre, simbolo_nombre))
        simbolo, nombre_usado, accion_tomada = asegurar_simbolo(
            doc, familia_nombre, simbolo_nombre, revit_db
        )
        resumen[accion_tomada] = resumen.get(accion_tomada, 0) + 1

        resultados.append({
            "familia": familia_nombre,
            "simbolo_solicitado": simbolo_nombre,
            "simbolo_usado": nombre_usado,
            "accion": accion_tomada,
        })
        print("    -> {} (usando '{}')".format(accion_tomada, nombre_usado or "—"))

    print("\n=== Resumen ===")
    for k, v in resumen.items():
        print("  {}: {}".format(k, v))

    resultado = {
        "version": "v01",
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "json_entrada": json_in,
        "total_simbolos_procesados": len(resultados),
        "resumen": resumen,
        "resultados": resultados,
    }

    if args.json_out:
        json_out = args.json_out
    else:
        json_out = os.path.join(root, "data", "activar_symbolos_resultado.json")
    _guardar_json(json_out, resultado)
    print("JSON guardado en: {}".format(json_out))
    return resultado


if __name__ == "__main__":
    main()
