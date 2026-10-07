"""
cartera.py — Carga de la cartera, desde secreto o desde archivo.

Por qué existe: con el repositorio público, cartera.json quedaría visible para
cualquiera. Este módulo permite guardar su contenido como un secreto de GitHub
(CARTERA_JSON) en lugar de como archivo, de modo que el repo pueda ser público
sin exponer las posiciones.

Orden de búsqueda:
  1. Variable de entorno CARTERA_JSON  (el secreto, en produccion)
  2. Archivo cartera.json en la raiz    (respaldo, para probar en local)

Si ninguna existe, devuelve un diccionario vacio y el bot sigue funcionando
en lo que no dependa de la cartera.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent
ARCHIVO = RAIZ / "cartera.json"


def cargar() -> dict:
    """Devuelve la cartera como diccionario. Nunca lanza."""
    crudo = os.getenv("CARTERA_JSON")

    # Distinguimos tres casos, porque fallan de formas distintas y una cadena
    # vacia es "falsa" en Python: sin este diagnostico, un secreto vacio cae
    # al archivo en silencio y parece que el secreto no existe.
    if crudo is None:
        log.warning(
            "CARTERA_JSON no llega al script. O el secreto no existe, o al "
            "workflow le falta la linea CARTERA_JSON en su bloque env."
        )
    elif not crudo.strip():
        log.error(
            "CARTERA_JSON existe pero esta VACIO (%d caracteres). "
            "Vuelve a crear el secreto y verifica que el valor se haya pegado.",
            len(crudo),
        )
        crudo = None
    else:
        log.info("CARTERA_JSON recibido: %d caracteres.", len(crudo))

    if crudo:
        try:
            datos = json.loads(crudo)
            n = len(datos.get("posiciones", []))
            log.info("Cartera leida del secreto CARTERA_JSON (%d posiciones).", n)
            return datos
        except json.JSONDecodeError as exc:
            # Fallo tipico: se pego el JSON con comillas raras o incompleto.
            log.error("CARTERA_JSON existe pero no es JSON valido: %s", exc)
            log.error("Reviso si hay archivo de respaldo.")

    if ARCHIVO.exists():
        try:
            with ARCHIVO.open(encoding="utf-8") as f:
                datos = json.load(f)
            n = len(datos.get("posiciones", []))
            log.info("Cartera leida del archivo cartera.json (%d posiciones).", n)
            return datos
        except Exception as exc:  # noqa: BLE001
            log.error("No pude leer cartera.json: %s", exc)

    log.error(
        "Sin cartera. Falta el secreto CARTERA_JSON o el archivo cartera.json. "
        "Las secciones que dependen de la cartera saldran vacias."
    )
    return {}
