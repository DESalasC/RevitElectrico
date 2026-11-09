# -*- coding: utf-8 -*-
"""
CARGAR_FAMILIAS_v01.py — Carga familias .rfa al documento RVT activo
antes de ejecutar Tarea F (modelado de FamilyInstance).

Lee una lista de familias desde un JSON de configuración (o usa una lista
por defecto) y las carga al documento activo mediante
Document.LoadFamily(path). Retorna un JSON de resultado con las familias
cargadas correctamente y las que fallaron.

USO (dentro de Revit con pyRevit):
  pyrevit agent run "src/fase-6-revit/CARGAR_FAMILIAS_v01.py" --revit=<PID> --mode=modify --title="Cargar familias electricas" --timeout=300

Opciones CLI:
  --config  Ruta al JSON de configuracion con la lista de familias.
            Si se omite, se usa una lista por defecto integrada.
  --lib-dir Directorio base de la libreria de familias.
            Si se omite se usa la variable de entorno
            REVIT_ELECTRICO_LIB (fallback: D:/Work/LIBRARIES/bim/RevitElectrico).

El JSON de configuracion tiene este formato:
{
  "familias": [
    {"nombre": "M_Toma doble", "ruta_relativa": "04_Tomas_e_Interruptores/M_Toma doble.rfa"},
    ...
  ]
}


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


def _import_revit_db():
    import sys
    mock_db = sys.modules.get("Autodesk.Revit.DB")
    if mock_db is not None:
        return {
            "FilteredElementCollector": getattr(mock_db, "FilteredElementCollector", None),
            "Family": getattr(mock_db, "Family", None),
        }
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit.DB import (
        FilteredElementCollector,
        Family,
    )
    return {
        "FilteredElementCollector": FilteredElementCollector,
        "Family": Family,
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


def _buscar_familia_por_nombre(doc, nombre_familia, revit_db):
    """Busca una familia cargada en el documento por su nombre."""
    FilteredElementCollector = revit_db.get("FilteredElementCollector")
    Family = revit_db.get("Family")
    if FilteredElementCollector is None or Family is None:
        return None
    colector = FilteredElementCollector(doc).OfClass(Family)
    for fam in colector.ToElements():
        try:
            nombre_fam = _obtener_nombre_elemento(fam, revit_db)
            if nombre_fam and nombre_fam.strip().lower() == nombre_familia.strip().lower():
                return fam
        except Exception:
            continue
    return None


def familias_cargadas(doc, revit_db):
    """Retorna un set con los nombres de las familias ya cargadas en el doc."""
    FilteredElementCollector = revit_db["FilteredElementCollector"]
    Family = revit_db["Family"]
    nombres = set()
    colector = FilteredElementCollector(doc).OfClass(Family)
    for fam in colector.ToElements():
        try:
            nombre = _obtener_nombre_elemento(fam, revit_db)
            if nombre:
                nombres.add(nombre)
        except Exception:
            continue
    return nombres


def cargar_familia(doc, ruta_rfa, nombre_familia, revit_db):
    """Carga un archivo .rfa al documento.

    doc.LoadFamily(ruta) en Revit 2026 devuelve bool, no el objeto Family.
    Requiere una Transaccion activa, de lo contrario retorna False.
    Tras un True, se re-busca la familia por nombre en el documento.

    Retorna (ok, mensaje, familia_obj) donde familia_obj es el Family
    cargado/localizado o None si no se pudo localizar por nombre.
    """
    if not os.path.exists(ruta_rfa):
        return False, "Archivo no encontrado: {}".format(ruta_rfa), None
    try:
        Transaction = revit_db.get("Transaction")
        if Transaction is None:
            import Autodesk.Revit.DB as _db
            Transaction = _db.Transaction
        trans = Transaction(doc, "CARGAR_FAMILIAS_v01 — Cargar {}".format(nombre_familia))
        trans.Start()
        try:
            exito = doc.LoadFamily(ruta_rfa)
            trans.Commit()
        except Exception:
            trans.RollBack()
            raise
        if exito:
            familia = _buscar_familia_por_nombre(doc, nombre_familia, revit_db)
            if familia is not None:
                return True, "Cargada correctamente", familia
            return True, "Cargada correctamente", None
        return False, "LoadFamily retorno falso", None
    except Exception as exc:
        return False, "Error: {}".format(exc), None


# Lista por defecto de familias necesarias para Tarea F (Apartamento F 02)
FAMILIAS_POR_DEFECTO = [
    {"nombre": "M_Toma doble", "ruta_relativa": "04_Tomas_e_Interruptores/M_Toma doble.rfa"},
    {"nombre": "M_Toma simple", "ruta_relativa": "04_Tomas_e_Interruptores/M_Toma simple.rfa"},
    {"nombre": "M_Toma resistente a la intemperie", "ruta_relativa": "04_Tomas_e_Interruptores/M_Toma resistente a la intemperie.rfa"},
    {"nombre": "M_Interruptor bipolar", "ruta_relativa": "04_Tomas_e_Interruptores/M_Interruptor bipolar.rfa"},
    {"nombre": "M_Interruptor", "ruta_relativa": "04_Tomas_e_Interruptores/M_Interruptor.rfa"},
    {"nombre": "M_Ventilador", "ruta_relativa": "06_Ventilacion_Extractores/M_Ventilador.rfa"},
    {"nombre": "E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN", "ruta_relativa": "01_Tableros_y_Protecciones/E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN.rfa"},
    {"nombre": "COMBO MOUNTING RING", "ruta_relativa": "02_Iluminacion_Interior/COMBO trim.rfa"},
]


def main():
    print("=" * 60)
    print("CARGAR_FAMILIAS_v01 — Cargar familias .rfa al RVT activo")
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
        description="Carga familias .rfa al documento RVT activo"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="",
        help="Ruta al JSON de configuracion con la lista de familias (opcional).",
    )
    parser.add_argument(
        "--lib-dir",
        type=str,
        default="",
        help="Directorio base de la libreria de familias (opcional).",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Ruta del JSON de resultado de salida (opcional).",
    )
    args = parser.parse_args()

    # Determinar directorio base de la libreria
    lib_dir = args.lib_dir
    if not lib_dir:
        lib_dir = os.environ.get("REVIT_ELECTRICO_LIB", "")
    if not lib_dir or not os.path.exists(lib_dir):
        lib_dir = "D:/Work/LIBRARIES/bim/RevitElectrico"
    print("Directorio de libreria: {}".format(lib_dir))

    # Cargar lista de familias
    if args.config and os.path.exists(args.config):
        with open(args.config, "r") as f:
            config = json.load(f)
        familias = config.get("familias", FAMILIAS_POR_DEFECTO)
    else:
        familias = FAMILIAS_POR_DEFECTO

    # Familias ya cargadas
    ya_cargadas = familias_cargadas(doc, revit_db)
    print("Familias ya cargadas en el documento: {}".format(len(ya_cargadas)))

    exitos = []
    fallos = []
    omitidas = []

    for fam in familias:
        nombre = fam.get("nombre", "")
        ruta_relativa = fam.get("ruta_relativa", "")
        ruta_completa = os.path.join(lib_dir, ruta_relativa)

        print("  Procesando: {}".format(nombre))

        if nombre in ya_cargadas:
            print("    OMITIDA: ya cargada en el documento")
            omitidas.append({
                "nombre": nombre,
                "ruta_relativa": ruta_relativa,
                "motivo": "Ya cargada",
            })
            continue

        ok, mensaje, familia_obj = cargar_familia(doc, ruta_completa, nombre, revit_db)
        if ok:
            print("    OK: cargada")
            exitos.append({
                "nombre": nombre,
                "ruta_relativa": ruta_relativa,
                "ruta_completa": ruta_completa,
                "motivo": mensaje,
            })
            if familia_obj is not None:
                try:
                    ya_cargadas.add(_obtener_nombre_elemento(familia_obj, revit_db) or nombre)
                except Exception:
                    ya_cargadas.add(nombre)
        else:
            print("    FALLO: {}".format(mensaje))
            fallos.append({
                "nombre": nombre,
                "ruta_relativa": ruta_relativa,
                "ruta_completa": ruta_completa,
                "motivo": mensaje,
            })

    print("\n=== Resultado ===")
    print("Exitosas: {}".format(len(exitos)))
    print("Fallidas: {}".format(len(fallos)))
    print("Omitidas (ya cargadas): {}".format(len(omitidas)))

    resultado = {
        "version": "v01",
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "documento": doc.Title,
        "lib_dir": lib_dir,
        "total_familias": len(familias),
        "exitosas": len(exitos),
        "fallidas": len(fallos),
        "omitidas": len(omitidas),
        "exitos": exitos,
        "fallos": fallos,
        "omitidas": omitidas,
    }

    if args.json_out:
        json_out = args.json_out
    else:
        root = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())
        json_out = os.path.join(root, "data", "cargar_familias_resultado.json")
    _guardar_json(json_out, resultado)
    print("JSON guardado en: {}".format(json_out))
    return resultado


if __name__ == "__main__":
    main()
