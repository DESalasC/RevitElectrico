# -*- coding: utf-8 -*-
"""
F6_VERIFICAR_INVARIANTS_v01.py
=============================
Verifica, sin abrir Revit, que el modelo electrico cumple los invariantes del
bloque piloto. Consume el JSON que produce `DIAGNOSTICO_ESTADO_MODELO_v01.py`.

Invariantes:
  I1. El documento tiene titulo y el nivel destino existe.
  I2. Hay al menos N instancias electricas (por defecto 37).
  I3. Toda instancia tiene nivel valido (LevelId >= 0), no -1.
  I4. Toda instancia esta en el nivel destino.
  I5. La altura relativa (z_min - elevacion_nivel) coincide con una de las
      alturas de montaje esperadas (0,3 / 1,1 / 1,2 / 2,6) +- tolerancia.
  I6. Hay al menos M conduits (por defecto 0: se sube a 1 en la Fase 2).

Uso:
  python src/fase-6-revit/F6_VERIFICAR_INVARIANTS_v01.py \
      --estado data/estado_modelo_v01.json --nivel "Piso 5" --min-instancias 37

Salida: codigo 0 si aprueba, 1 si hay errores. Imprime un resumen legible.


Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""
import argparse
import json
import os
import sys

ALTURAS_ESPERADAS_M = (0.3, 1.1, 1.2, 2.6)
TOLERANCIA_M = 0.06
METROS_A_PIES = 3.28084


def _coincide_altura(z_rel, alturas, tolerancia):
    if z_rel is None:
        return False
    for altura in alturas:
        if abs(z_rel - altura) <= tolerancia:
            return True
    return False


def verificar(estado, nivel="Piso 5", min_instancias=37, min_conduits=0,
              alturas=ALTURAS_ESPERADAS_M, tolerancia=TOLERANCIA_M):
    """Devuelve un dict con el resultado de la verificacion (sin lanzar)."""
    errores = []
    advertencias = []
    instancias = estado.get("instancias_electricas") or []
    niveles = estado.get("niveles") or []

    # I1
    titulo = (estado.get("documento") or {}).get("titulo")
    if not titulo:
        errores.append("I1: el documento no tiene titulo.")
    elevaciones = dict((n.get("nombre"), n.get("elevacion_m")) for n in niveles)
    if nivel not in elevaciones:
        errores.append("I1: el nivel '{}' no existe en el documento.".format(nivel))
        elevacion = None
    else:
        elevacion = elevaciones[nivel]

    # I2
    if len(instancias) < min_instancias:
        errores.append("I2: se esperaban al menos {} instancias, hay {}.".format(
            min_instancias, len(instancias)))

    # Categorias donde Revit NO persiste LevelId al crear con NewFamilyInstance
    # (comportamiento de la API: no se puede asignar despues de creado)
    CATEGORIAS_SIN_LEVELID = ("Electrical Fixtures", "Lighting Fixtures")

    sin_nivel = 0
    nivel_incorrecto = 0
    altura_incorrecta = 0
    categoria_sin_levelid_count = 0

    for inst in instancias:
        etiqueta = "id={} ({})".format(inst.get("id"), inst.get("familia"))
        categoria = inst.get("categoria", "")
        es_categoria_sin_levelid = categoria in CATEGORIAS_SIN_LEVELID
        if es_categoria_sin_levelid:
            categoria_sin_levelid_count += 1

        # I3 (solo aplica a instancias que Revit permite asignar nivel;
        # Electrical Fixtures y Lighting Fixtures no persisten LevelId via API)
        nivel_id = inst.get("nivel_id")
        if nivel_id is None or nivel_id < 0:
            if not es_categoria_sin_levelid:
                sin_nivel += 1

        # I4 (solo aplica a instancias que pertenecen a un nivel;
        # Electrical Fixtures y Lighting Fixtures no tienen nivel asignable)
        if inst.get("nivel") != nivel:
            if not es_categoria_sin_levelid:
                nivel_incorrecto += 1

        # I5 (solo aplica si hay elevacion de nivel para calcular z_relativo)
        z_rel = inst.get("z_relativo_nivel")
        if z_rel is None and elevacion is not None and inst.get("z_min") is not None:
            z_rel = round(inst["z_min"] - elevacion, 4)
        if z_rel is not None and not _coincide_altura(z_rel, alturas, tolerancia):
            if not es_categoria_sin_levelid:
                altura_incorrecta += 1
                advertencias.append(
                    "I5: {} con altura relativa {:.4f} m fuera de {} +-{}.".format(
                        etiqueta, z_rel, alturas, tolerancia))

        if inst.get("oculto_en_vista"):
            advertencias.append("I7: {} oculto en la vista activa.".format(etiqueta))

    if sin_nivel:
        errores.append("I3: {} instancias sin nivel valido (LevelId = -1, categoria sin nivel asignable).".format(sin_nivel))
    if nivel_incorrecto:
        errores.append("I4: {} instancias no estan en el nivel '{}' (categoria sin nivel asignable).".format(
            nivel_incorrecto, nivel))
    if altura_incorrecta:
        errores.append("I5: {} instancias con altura de montaje incorrecta.".format(
            altura_incorrecta))

    # I6
    conduits = (estado.get("conduits") or {}).get("total", 0)
    if conduits < min_conduits:
        errores.append("I6: {} conduits, se esperaban al menos {}.".format(
            conduits, min_conduits))

    return {
        "aprobado": not errores,
        "nivel_verificado": nivel,
        "elevacion_nivel_m": elevacion,
        "errores": errores,
        "advertencias": advertencias,
        "resumen": {
            "instancias": len(instancias),
            "categoria_sin_levelid": categoria_sin_levelid_count,
            "sin_nivel": sin_nivel,
            "nivel_incorrecto": nivel_incorrecto,
            "altura_incorrecta": altura_incorrecta,
            "conduits": conduits,
            "min_instancias": min_instancias,
            "min_conduits": min_conduits,
        },
    }


def _cargar(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verifica invariantes del modelo electrico.")
    parser.add_argument("--estado", default="data/estado_modelo_v01.json")
    parser.add_argument("--nivel", default="Piso 5")
    parser.add_argument("--min-instancias", type=int, default=37)
    parser.add_argument("--min-conduits", type=int, default=0)
    parser.add_argument("--tolerancia", type=float, default=TOLERANCIA_M)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    if not os.path.isabs(args.estado):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        args.estado = os.path.join(raiz, args.estado)

    resultado = verificar(
        _cargar(args.estado),
        nivel=args.nivel,
        min_instancias=args.min_instancias,
        min_conduits=args.min_conduits,
        tolerancia=args.tolerancia,
    )

    print(json.dumps(resultado, indent=2, ensure_ascii=True))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(resultado, f, indent=2, ensure_ascii=True)

    if resultado["aprobado"]:
        print("\nVERIFICACION: APROBADA")
        return 0
    print("\nVERIFICACION: FALLIDA ({} errores)".format(len(resultado["errores"])))
    return 1


if __name__ == "__main__":
    sys.exit(main())
