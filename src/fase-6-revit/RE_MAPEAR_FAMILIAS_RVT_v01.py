# -*- coding: utf-8 -*-
"""
RE_MAPEAR_FAMILIAS_RVT_v01.py — Mapea nombres de familia y simbolo del JSON
de Tarea F a los nombres REALES de familias y simbolos cargados en el RVT.

Lee el JSON de entrada de Tarea F (data/apto_F_02_aplicar_mapa_v3.json) y,
para cada combinacion unica de familia + simbolo:
  1. Asegura que la familia este cargada en el documento (si no, carga el
     archivo .rfa de la libreria local).
  2. Asegura que el simbolo exista y este activo dentro de la familia:
     - Si existe y esta activo -> lo usa.
     - Si existe pero esta inactivo -> lo activa.
     - Si no existe -> duplica el primer simbolo disponible con el nombre
       solicitado y lo activa.
  3. Reporta familia_no_encontrada si la familia no esta cargada ni se puede
     cargar, y no_disponible si la familia no tiene simbolos.

Genera un JSON de salida con las acciones de Tarea F enriquecidas con
familia_real y simbolo_real (los nombres que realmente se usaron en el RVT),
listo para ser consumido por RE_APLICAR_MAPA_V3_REVIT_v02.py con --json-in.

USO (dentro de Revit con pyRevit):
  pyrevit agent run "src/fase-6-revit/RE_MAPEAR_FAMILIAS_RVT_v01.py" --revit=<PID> --mode=modify --title="Mapear familias RVT Tarea F" --timeout=300

Opciones CLI:
  --json-in  Ruta al JSON de entrada de Tarea F (default: data/apto_F_02_aplicar_mapa_v3.json)
  --json-out Ruta del JSON de resultado (default: data/mapear_familias_rvt_resultado.json)
  --lib-dir  Directorio base de la libreria de familias (default: $REVIT_ELECTRICO_LIB o D:/Work/LIBRARIES/bim/RevitElectrico)

IronPython 2.7 (dentro de Revit / pyRevit) — SIN type hints, SIN f-strings, SIN requests/bs4.
Usar .format() y concatenacion de strings.


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


def _ruta_rfa_para_familia(nombre_familia, lib_dir):
    """
    Retorna la ruta completa al archivo .rfa de la libreria local para un
    nombre de familia dado, o None si no se encuentra un archivo candidato.

    Convencion: la ruta relativa sigue el mapeo de CARGAR_FAMILIAS_v01.py:
      - M_Toma doble -> 04_Tomas_e_Interruptores/M_Toma doble.rfa
      - M_Toma simple -> 04_Tomas_e_Interruptores/M_Toma simple.rfa
      - M_Toma resistente a la intemperie -> 04_Tomas_e_Interruptores/M_Toma resistente a la intemperie.rfa
      - M_Interruptor bipolar -> 04_Tomas_e_Interruptores/M_Interruptor bipolar.rfa
      - M_Interruptor -> 04_Tomas_e_Interruptores/M_Interruptor.rfa
      - M_Ventilador -> 06_Ventilacion_Extractores/M_Ventilador.rfa
      - E_Distribution Panel_... -> 01_Tableros_y_Protecciones/...
      - COMBO MOUNTING RING -> 02_Iluminacion_Interior/COMBO trim.rfa

    Si el nombre coincide exactamente con una entrada del mapeo por defecto,
    se usa esa ruta. Si no, se intenta buscar un archivo .rfa cuyo nombre de
    archivo (sin extension) coincida con el nombre de la familia en cualquier
    subdirectorio de lib_dir.
    """
    MAPEO_RUTAS_POR_DEFECTO = {
        "M_Toma doble": "04_Tomas_e_Interruptores/M_Toma doble.rfa",
        "M_Toma simple": "04_Tomas_e_Interruptores/M_Toma simple.rfa",
        "M_Toma resistente a la intemperie": "04_Tomas_e_Interruptores/M_Toma resistente a la intemperie.rfa",
        "M_Interruptor bipolar": "04_Tomas_e_Interruptores/M_Interruptor bipolar.rfa",
        "M_Interruptor": "04_Tomas_e_Interruptores/M_Interruptor.rfa",
        "M_Ventilador": "06_Ventilacion_Extractores/M_Ventilador.rfa",
        "E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN": "01_Tableros_y_Protecciones/E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN.rfa",
        "COMBO MOUNTING RING": "02_Iluminacion_Interior/COMBO trim.rfa",
    }

    if nombre_familia in MAPEO_RUTAS_POR_DEFECTO:
        ruta_relativa = MAPEO_RUTAS_POR_DEFECTO[nombre_familia]
        ruta_completa = os.path.join(lib_dir, ruta_relativa)
        if os.path.exists(ruta_completa):
            return ruta_completa

    # Busqueda de fallback: cualquier .rfa cuyo nombre de archivo coincida
    for dirpath, dirnames, filenames in os.walk(lib_dir):
        for filename in filenames:
            if not filename.lower().endswith(".rfa"):
                continue
            nombre_archivo = os.path.splitext(filename)[0]
            if _nombre_coincide(nombre_archivo, nombre_familia):
                return os.path.join(dirpath, filename)

    return None


def _cargar_familia_si_falta(doc, nombre_familia, lib_dir, revit_db):
    """
    Asegura que la familia este cargada en el documento. Si no esta, intenta
    cargar el archivo .rfa correspondiente de la libreria local.
    Retorna (familia, mensaje) donde familia es el objeto Family o None.
    """
    familia = _buscar_familia_por_nombre(doc, nombre_familia, revit_db)
    if familia is not None:
        return familia, "ya_cargada"

    ruta_rfa = _ruta_rfa_para_familia(nombre_familia, lib_dir)
    if ruta_rfa is None:
        return None, "archivo_rfa_no_encontrado"

    if not os.path.exists(ruta_rfa):
        return None, "archivo_rfa_no_existe: {}".format(ruta_rfa)

    try:
        Transaction = revit_db.get("Transaction")
        if Transaction is None:
            import Autodesk.Revit.DB as _db
            Transaction = _db.Transaction
        trans = Transaction(doc, "RE_MAPEAR_FAMILIAS_RVT_v01 — Cargar {}".format(nombre_familia))
        trans.Start()
        try:
            exito = doc.LoadFamily(ruta_rfa)
            trans.Commit()
        except Exception:
            trans.RollBack()
            raise
        if exito:
            # doc.LoadFamily retorna bool en Revit API, no el objeto Family.
            # Hay que buscar la familia recien cargada en el documento.
            # Primero intenta coincidencia exacta por nombre.
            familia = _buscar_familia_por_nombre(doc, nombre_familia, revit_db)
            if familia is not None:
                return familia, "cargada_desde_rfa"

            # Fallback: buscar coincidencia parcial (el nombre de la familia
            # cargada puede diferir del nombre del archivo .rfa).
            FilteredElementCollector = revit_db["FilteredElementCollector"]
            Family = revit_db.get("Family")
            if Family is not None:
                for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
                    try:
                        nombre_fam = _obtener_nombre_elemento(fam, revit_db) or ""
                        if nombre_fam and (
                            nombre_familia.lower() in nombre_fam.lower()
                            or nombre_fam.lower() in nombre_familia.lower()
                        ):
                            return fam, "cargada_desde_rfa_partial"
                    except Exception:
                        continue

            return None, "load_family_ok_pero_no_encontrada"
        return None, "load_family_retorno_falso"
    except Exception as exc:
        return None, "error_cargando_rfa: {}".format(exc)


def asegurar_simbolo(doc, nombre_familia, nombre_simbolo, lib_dir, revit_db):
    """
    Asegura que exista y este activo el simbolo solicitado.
    Retorna (simbolo, nombre_usado, accion, mensaje) donde accion es:
      'ya_existia_activo', 'se_activo', 'se_duplico', 'no_disponible',
      'familia_no_encontrada', 'archivo_rfa_no_encontrado'.
    """
    familia, mensaje_fam = _cargar_familia_si_falta(doc, nombre_familia, lib_dir, revit_db)
    if familia is None:
        return None, None, "familia_no_encontrada", mensaje_fam

    simbolos = _listar_simbolos_familia(familia, doc, revit_db)

    # 1. Coincidencia exacta
    for simbolo, nombre_sim in simbolos:
        if _nombre_coincide(nombre_sim, nombre_simbolo):
            if simbolo.IsActive:
                return simbolo, nombre_sim, "ya_existia_activo", "simbolo ya activo"
            else:
                _activar_simbolo(simbolo, doc)
                return simbolo, nombre_sim, "se_activo", "simbolo activado"

    # 2. No existe: duplicar el primero disponible
    if simbolos:
        simbolo_base, nombre_base = simbolos[0]
        nuevo = _duplicar_simbolo(simbolo_base, nombre_simbolo)
        if nuevo is not None:
            _activar_simbolo(nuevo, doc)
            return nuevo, nombre_simbolo, "se_duplico", "simbolo duplicado desde '{}'".format(nombre_base)

    return None, None, "no_disponible", "familia sin simbolos disponibles"


def main():
    print("=" * 60)
    print("RE_MAPEAR_FAMILIAS_RVT_v01 — Mapear familias RVT para Tarea F")
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
        description="Mapea nombres de familia y simbolo de Tarea F a nombres reales del RVT"
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
    parser.add_argument(
        "--lib-dir",
        type=str,
        default="",
        help="Directorio base de la libreria de familias (opcional).",
    )
    args = parser.parse_args()

    root = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())

    json_in = args.json_in
    if not json_in:
        json_in = os.path.join(root, "data", "apto_F_02_aplicar_mapa_v3.json")
    print("JSON de entrada: {}".format(json_in))

    lib_dir = args.lib_dir
    if not lib_dir:
        lib_dir = os.environ.get("REVIT_ELECTRICO_LIB", "")
    if not lib_dir or not os.path.exists(lib_dir):
        lib_dir = "D:/Work/LIBRARIES/bim/RevitElectrico"
    print("Directorio de libreria: {}".format(lib_dir))

    reporte = _cargar_json(json_in)
    acciones = reporte.get("acciones_modelar", [])
    print("Acciones de modelado a procesar: {}".format(len(acciones)))

    # Procesar combinaciones unicas de familia + simbolo
    ya_vistos = set()
    mapeo_simbolos = {}  # (familia, simbolo) -> (familia_real, simbolo_real, accion, mensaje)
    resumen = {
        "ya_existia_activo": 0,
        "se_activo": 0,
        "se_duplico": 0,
        "no_disponible": 0,
        "familia_no_encontrada": 0,
        "archivo_rfa_no_encontrado": 0,
    }

    for accion in acciones:
        familia_nombre = accion.get("familia")
        simbolo_nombre = accion.get("simbolo")
        if not familia_nombre or not simbolo_nombre:
            continue
        clave = (familia_nombre, simbolo_nombre)
        if clave in ya_vistos:
            continue
        ya_vistos.add(clave)

        print("  {} / {}".format(familia_nombre, simbolo_nombre))
        simbolo, nombre_usado, accion_tomada, mensaje = asegurar_simbolo(
            doc, familia_nombre, simbolo_nombre, lib_dir, revit_db
        )
        resumen[accion_tomada] = resumen.get(accion_tomada, 0) + 1
        mapeo_simbolos[clave] = {
            "familia_solicitada": familia_nombre,
            "simbolo_solicitado": simbolo_nombre,
            "familia_real": familia_nombre,
            "simbolo_real": nombre_usado,
            "accion": accion_tomada,
            "mensaje": mensaje,
        }
        print("    -> {} (simbolo: '{}')".format(accion_tomada, nombre_usado or "—"))

    print("\n=== Resumen ===")
    for k, v in resumen.items():
        print("  {}: {}".format(k, v))

    # Enriquecer las acciones de entrada con los nombres reales
    acciones_enriquecidas = []
    for accion in acciones:
        familia_nombre = accion.get("familia")
        simbolo_nombre = accion.get("simbolo")
        clave = (familia_nombre, simbolo_nombre)
        info = mapeo_simbolos.get(clave, {
            "familia_real": familia_nombre,
            "simbolo_real": simbolo_nombre,
            "accion": "sin_procesar",
            "mensaje": "familia o simbolo no especificado",
        })
        accion_enriquecida = dict(accion)
        accion_enriquecida["familia_real"] = info["familia_real"]
        accion_enriquecida["simbolo_real"] = info["simbolo_real"]
        accion_enriquecida["accion_simbolo"] = info["accion"]
        accion_enriquecida["mensaje_simbolo"] = info["mensaje"]
        acciones_enriquecidas.append(accion_enriquecida)

    resultado = {
        "version": "v01",
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "json_entrada": json_in,
        "lib_dir": lib_dir,
        "total_acciones": len(acciones),
        "total_simbolos_procesados": len(mapeo_simbolos),
        "resumen": resumen,
        "mapeo_simbolos": mapeo_simbolos,
        "acciones_enriquecidas": acciones_enriquecidas,
    }

    if args.json_out:
        json_out = args.json_out
    else:
        json_out = os.path.join(root, "data", "mapear_familias_rvt_resultado.json")
    _guardar_json(json_out, resultado)
    print("JSON guardado en: {}".format(json_out))
    return resultado


if __name__ == "__main__":
    main()
