"""Guardia estatica: RE7_SMOKE_3CONDUITS_v01.py escribe en el modelo (smoke test Etapa 1)."""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA = os.path.join(RAIZ, "scripts", "pyrevit", "RE7_SMOKE_3CONDUITS_v01.py")

# Tokens que DEBEN aparecer en un script de creacion de conduits.
REQUERIDOS = [
    "Transaction",
    "Conduit.Create",
    "doc",
    "Commit",
]


def test_smoke_escribe_en_modelo():
    with open(RUTA, "r") as f:
        fuente = f.read()
    for token in REQUERIDOS:
        assert token in fuente, f"smoke test no escribe en el modelo: {token!r}"
    # Debe contener el orden correcto de argumentos de Conduit.Create
    assert 'Conduit.Create(doc,' in fuente or 'Conduit.Create(document,' in fuente
    assert 'Transaccion' in fuente or 'Transaction' in fuente
