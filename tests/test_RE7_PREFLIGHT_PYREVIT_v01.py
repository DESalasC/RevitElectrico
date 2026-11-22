"""Guardia estatica: los scripts pyRevit de F7 solo leen el modelo Revit."""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_PYREVIT = os.path.join(RAIZ, "scripts", "pyrevit")

# Scripts completos de solo lectura (Etapa 0 del ruteo F7).
SOLO_LECTURA = [
    "RE7_PREFLIGHT_PYREVIT_v02.py",
    "RE7_DIAGNOSTICO_PYREVIT_v01.py",
]

# v01 quedo retirado: solo delega en v02 (nunca se ejecutaba con exec()).
DELEGADOS = [
    "RE7_PREFLIGHT_PYREVIT_v01.py",
]

# Tokens que nunca deben aparecer en un script de solo lectura.
PROHIBIDOS = [
    "Transaction",
    "NewFamilyInstance",
    ".Delete(",
    "doc.Save",
    "Regenerate",
    "ElbowFitting",
]


def _fuente(nombre):
    with open(os.path.join(DIR_PYREVIT, nombre), "r") as f:
        return f.read()


def test_scripts_pyrevit_son_solo_lectura():
    for nombre in SOLO_LECTURA + DELEGADOS:
        fuente = _fuente(nombre)
        for token in PROHIBIDOS:
            assert token not in fuente, f"{nombre} escribe en el modelo: {token!r}"


def test_scripts_pyrevit_dejan_evidencia_en_archivo():
    """La consola de pyRevit puede quedar muda: todo script debe loguear a archivo."""
    for nombre in SOLO_LECTURA:
        fuente = _fuente(nombre)
        assert 'clr.AddReference("RevitAPI")' in fuente, nombre
        assert "FilteredElementCollector" in fuente, nombre
        assert "traceback" in fuente, nombre
        assert ".log" in fuente, f"{nombre} no escribe log a archivo"


def test_scripts_pyrevit_se_ejecutan_sin_depender_de__name__():
    """exec(open(...).read()) no garantiza __name__ == '__main__'."""
    for nombre in SOLO_LECTURA + DELEGADOS:
        fuente = _fuente(nombre)
        assert '__name__ == "__main__"' not in fuente, (
            f"{nombre} usa el guard __main__: con exec() el cuerpo no se ejecuta"
        )


def test_v01_delega_en_v02():
    fuente = _fuente("RE7_PREFLIGHT_PYREVIT_v01.py")
    assert "RE7_PREFLIGHT_PYREVIT_v02.py" in fuente
    assert "exec(compile(" in fuente
