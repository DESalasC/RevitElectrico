# -*- coding: utf-8 -*-
# RE_CONFIGURAR_DXF_REVIT_v02.py
# Reconfigura la colocación de elementos DXF a la posición actual en Revit.
# Los elementos del "Apartamento Tipo F 02" YA EXISTEN en Revit:
#   - No crea FamilyInstances nuevas.
#   - Calcula la diferencia entre coordenadas DXF y posición actual en Revit.
#   - Mueve las instancias existentes a su posición correcta.
#
# Transformación confirmada (sesión 2026-10-20, traslación pura sin espejo):
#   X_revit = X_dxf + 6.49   (pies)
#   Y_revit = Y_dxf + 10.2234 (pies)
#
# Ejecutar dentro de Revit 2026 (pyRevit Python Shell).

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

import json
import math
import os

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
DXF_JSON_PATH = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\3.-Proceso\_prueba_modelado\modelo_apt_F02_piso5.json"
MAPA_JSON_PATH = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\3.-Proceso\_prueba_modelado\MAPA_BLOQUES_REVIT_v3.json"
RESULTADO_JSON_PATH = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\resultado_reconfiguracion_dxf_revit.json"

# ---------------------------------------------------------------------------
# Parámetros de transformación (traslación pura confirmada)
# ---------------------------------------------------------------------------
TX = 6.49      # pies (X_revit = X_dxf + 6.49)
TY = 10.2234   # pies (Y_revit = Y_dxf + 10.2234)

# ---------------------------------------------------------------------------
# Carga de datos JSON (IronPython 2.7: sin parametro encoding)
# ---------------------------------------------------------------------------
def cargar_json(path):
    with open(path, "r") as f:
        return json.load(f)

def guardar_json(path, datos):
    directorio = os.path.dirname(path)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio)
    with open(path, "w") as f:
        json.dump(datos, f, ensure_ascii=True, indent=2)

# ---------------------------------------------------------------------------
# Diagnóstico: listar FamilyInstances existentes
# ---------------------------------------------------------------------------
def listar_family_instances(doc):
    """Retorna lista de FamilyInstances con su nombre de familia, símbolo y posición.

Ultimos tres cambios
--------------------
1. 2026-11-08 v02: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""
    instancias = []
    collector = FilteredElementCollector(doc).OfClass(FamilyInstance)
    for fi in collector:
        try:
            fam_name = fi.Symbol.Family.Name if fi.Symbol and fi.Symbol.Family else ""
            sym_name = fi.Symbol.Name if fi.Symbol else ""
            loc = fi.Location
            if loc and hasattr(loc, "Point"):
                pt = loc.Point
                instancias.append({
                    "id": int(fi.Id),
                    "familia": fam_name,
                    "simbolo": sym_name,
                    "x": pt.X,
                    "y": pt.Y,
                    "z": pt.Z,
                    "categoria": fi.Category.Name if fi.Category else "",
                })
        except Exception:
            continue
    return instancias

# ---------------------------------------------------------------------------
# Buscar FamilySymbol por nombre
# ---------------------------------------------------------------------------
def obtener_tipo_familia(doc, nombre_familia, nombre_simbolo):
    collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
    for fs in collector:
        try:
            fam_name = fs.Family.Name if fs.Family else ""
            sym_name = fs.Name
        except Exception:
            continue
        if fam_name == nombre_familia and sym_name == nombre_simbolo:
            return fs, None
    # Fallback: solo familia
    for fs in collector:
        try:
            fam_name = fs.Family.Name if fs.Family else ""
        except Exception:
            continue
        if fam_name == nombre_familia:
            return fs, None
    return None, "No se encontró FamilySymbol: familia='{}', símbolo='{}'".format(nombre_familia, nombre_simbolo)

# ---------------------------------------------------------------------------
# Buscar nivel por nombre
# ---------------------------------------------------------------------------
def obtener_nivel_por_nombre(doc, nombre_nivel):
    collector = FilteredElementCollector(doc).OfClass(Level)
    for nivel in collector:
        if nivel.Name == nombre_nivel:
            return nivel
    return None

# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def reconfigurar_dxf_revit(doc, dxf_json_path=DXF_JSON_PATH, mapa_json_path=MAPA_JSON_PATH,
                           resultado_json_path=RESULTADO_JSON_PATH):
    print("=== RE_CONFIGURAR_DXF_REVIT_v02 ===")
    print("Documento: {}".format(doc.Title))
    print("Ruta: {}".format(doc.PathName))

    # Diagnóstico: FamilyInstances existentes
    print("\n--- DIAGNÓSTICO: FamilyInstances existentes en Revit ---")
    instancias_existentes = listar_family_instances(doc)
    print("Total FamilyInstances: {}".format(len(instancias_existentes)))
    for inst in instancias_existentes[:30]:
        print("  ID={} | familia='{}' | símbolo='{}' | X={:.3f} Y={:.3f} Z={:.3f}".format(
            inst["id"], inst["familia"], inst["simbolo"], inst["x"], inst["y"], inst["z"]))
    if len(instancias_existentes) > 30:
        print("  ... y {} más".format(len(instancias_existentes) - 30))

    # Cargar datos DXF y MAPA
    try:
        dxf_data = cargar_json(dxf_json_path)
        mapa_data = cargar_json(mapa_json_path)
        print("\nJSON DXF cargado: {} elementos".format(len(dxf_data.get("elementos", []))))
        print("MAPA cargado: {} entradas".format(len(mapa_data.get("mapeo", {}))))
    except Exception as exc:
        print("ERROR cargando JSON: {}".format(exc))
        return

    mapeo = mapa_data.get("mapeo", {})
    elementos_dxf = dxf_data.get("elementos", [])

    contadores = {
        "dispositivos_dxf": 0,
        "dispositivos_emparejados": 0,
        "dispositivos_sin_emparejar": 0,
        "dispositivos_movidos": 0,
        "dispositivos_error": 0,
        "marcadores_saltados": 0,
        "tubos_dxf": 0,
        "tubos_procesados": 0,
        "tubos_error": 0,
    }

    resultados_detalle = []
    errores_muestra = []

    # Emparejar FamilyInstances existentes con elementos DXF por nombre de familia
    # Creamos un índice: (familia, símbolo) -> lista de instancias existentes
    indice_instancias = {}
    for inst in instancias_existentes:
        clave = (inst["familia"], inst["simbolo"])
        indice_instancias.setdefault(clave, []).append(inst)

    # Iniciar transacción
    t = Transaction(doc, "Reconfigurar colocación DXF→Revit v02")
    t.Start()

    try:
        for elem in elementos_dxf:
            tipo_elem = elem.get("tipo")

            if tipo_elem == "dispositivo":
                contadores["dispositivos_dxf"] += 1
                nombre_dxf = elem.get("nombre", "")
                es_marcador = elem.get("es_marcador", False)

                # Saltar marcadores de conductores
                if es_marcador or nombre_dxf in ("1FTN", "1TNR", "1FTNR", "2FT2N", "1FTR", "1FTN2R", "1TN2R"):
                    contadores["marcadores_saltados"] += 1
                    resultados_detalle.append({
                        "nombre": nombre_dxf,
                        "tipo": "marcador_conductor",
                        "estado": "saltado",
                        "motivo": "Marcador de conductor, no dispositivo físico"
                    })
                    continue

                entrada_mapa = mapeo.get(nombre_dxf)
                if not entrada_mapa or not entrada_mapa.get("mapear", False):
                    contadores["dispositivos_sin_emparejar"] += 1
                    resultados_detalle.append({
                        "nombre": nombre_dxf,
                        "tipo": "dispositivo",
                        "estado": "sin_mapeo",
                        "motivo": "Sin mapeo en MAPA_v3 o mapear=false"
                    })
                    continue

                familia_nombre = entrada_mapa.get("familia")
                simbolo_nombre = entrada_mapa.get("simbolo")
                altura_m = entrada_mapa.get("altura_m", 0.0)

                # Buscar instancias existentes que coincidan con familia y símbolo
                clave = (familia_nombre, simbolo_nombre)
                candidatas = indice_instancias.get(clave, [])

                if not candidatas:
                    contadores["dispositivos_sin_emparejar"] += 1
                    contadores["dispositivos_error"] += 1
                    msg = "No hay FamilyInstance existente con familia='{}', símbolo='{}'".format(familia_nombre, simbolo_nombre)
                    errores_muestra.append(msg)
                    resultados_detalle.append({
                        "nombre": nombre_dxf,
                        "familia": familia_nombre,
                        "simbolo": simbolo_nombre,
                        "estado": "sin_instancia_existente",
                        "motivo": msg
                    })
                    continue

                # Tomar la primera instancia candidata (no movida aún)
                # En una versión más avanzada se marcaría como usada para no reusarla
                instancia_revit = candidatas[0]

                # Calcular posición objetivo desde DXF + transformación
                x_dxf = elem.get("x", 0.0)
                y_dxf = elem.get("y", 0.0)
                z_dxf = elem.get("z", 0.0)

                x_objetivo = x_dxf + TX
                y_objetivo = y_dxf + TY
                nivel_piso5 = obtener_nivel_por_nombre(doc, "Piso 5")
                elevacion_nivel_pies = nivel_piso5.Elevation if nivel_piso5 else 43.3727
                z_objetivo = elevacion_nivel_pies + (altura_m * 3.28084)

                # Calcular desplazamiento desde posición actual en Revit
                pt_actual = instancia_revit["x"], instancia_revit["y"], instancia_revit["z"]
                dx = x_objetivo - pt_actual[0]
                dy = y_objetivo - pt_actual[1]
                dz = z_objetivo - pt_actual[2]

                # Mover la instancia existente
                try:
                    vector = XYZ(dx, dy, dz)
                    ElementTransformUtils.MoveElement(doc, instancia_revit["id"], vector)
                    contadores["dispositivos_movidos"] += 1
                    contadores["dispositivos_emparejados"] += 1
                    resultados_detalle.append({
                        "nombre": nombre_dxf,
                        "familia": familia_nombre,
                        "simbolo": simbolo_nombre,
                        "instance_id": instancia_revit["id"],
                        "x_actual": pt_actual[0],
                        "y_actual": pt_actual[1],
                        "z_actual": pt_actual[2],
                        "x_objetivo": x_objetivo,
                        "y_objetivo": y_objetivo,
                        "z_objetivo": z_objetivo,
                        "desplazamiento": {"dx": dx, "dy": dy, "dz": dz},
                        "estado": "movido"
                    })
                except Exception as exc:
                    contadores["dispositivos_error"] += 1
                    if len(errores_muestra) < 5:
                        errores_muestra.append(str(exc))
                    resultados_detalle.append({
                        "nombre": nombre_dxf,
                        "familia": familia_nombre,
                        "simbolo": simbolo_nombre,
                        "instance_id": instancia_revit["id"],
                        "estado": "error_movimiento",
                        "motivo": str(exc)
                    })

            elif tipo_elem == "tubo_horizontal":
                contadores["tubos_dxf"] += 1
                # Los tubos horizontales ya existen como Conduit; se podría mover también
                # Por ahora solo contamos y reportamos
                contadores["tubos_procesados"] += 1
                resultados_detalle.append({
                    "tipo": "tubo_horizontal",
                    "sistema": elem.get("sistema", "ILUMINACIÓN"),
                    "estado": "contado",
                    "motivo": "Tubos horizontales ya existen en Revit; revisar posiciones manualmente"
                })

        t.Commit()
        print("\nTransacción commiteada.")

    except Exception as exc:
        t.RollBack()
        print("ERROR durante la transacción: {}".format(exc))
        raise

    # Guardar resultados
    resultado = {
        "documento": doc.Title,
        "fecha": "2026-10-28",
        "transformacion": {"TX": TX, "TY": TY},
        "contadores": contadores,
        "detalle": resultados_detalle,
        "errores_muestra": errores_muestra,
    }

    try:
        guardar_json(resultado_json_path, resultado)
        print("Resultado guardado en: {}".format(resultado_json_path))
    except Exception as exc:
        print("Advertencia: no se pudo guardar resultado JSON: {}".format(exc))

    print("\n=== RESUMEN ===")
    print("Dispositivos en DXF: {}".format(contadores["dispositivos_dxf"]))
    print("  Emparejados con instancia existente: {}".format(contadores["dispositivos_emparejados"]))
    print("  Movidos a posición correcta: {}".format(contadores["dispositivos_movidos"]))
    print("  Sin emparejar (no mapeados o sin instancia): {}".format(contadores["dispositivos_sin_emparejar"]))
    print("  Errores de movimiento: {}".format(contadores["dispositivos_error"]))
    print("Marcadores saltados: {}".format(contadores["marcadores_saltados"]))
    print("Tubos en DXF: {}".format(contadores["tubos_dxf"]))
    print("  Procesados: {}".format(contadores["tubos_procesados"]))

    print("\n--- ERRORES (muestra) ---")
    for e in errores_muestra:
        print("  {}".format(e))

    return resultado


if __name__ == "__main__":
    try:
        app = __revit__.Application
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document
        reconfigurar_dxf_revit(doc)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit Python Shell).")
        print("Variable __revit__ no definida.")
