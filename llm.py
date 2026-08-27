"""
llm.py — Cliente para la API de Anthropic.

Regla de diseño: el modelo NUNCA reporta números. Recibe las cifras ya
calculadas por el código y su trabajo es explicarlas. Así eliminamos la
posibilidad de que invente un dato que suene plausible.

Esta versión reporta con detalle por qué falla una llamada. Un fallo silencioso
es peor que un error ruidoso: te deja sin saber si el problema es la clave, el
saldo, el modelo o la red.
"""

from __future__ import annotations

import json
import logging
import os

import requests

log = logging.getLogger(__name__)

URL = "https://api.anthropic.com/v1/messages"

# Modelo principal y alternativas. Si el primero devuelve 404 (nombre no
# reconocido por tu cuenta), se prueba el siguiente automáticamente.
MODELOS = [
    os.getenv("MODELO_LLM", "claude-sonnet-4-5-20250929"),
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
]


def disponible() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _intentar(modelo: str, prompt: str, max_tokens: int, api_key: str):
    """
    Un intento con un modelo concreto.

    Devuelve (texto, reintentar_con_otro_modelo).
    """
    try:
        r = requests.post(
            URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": modelo,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=90,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("EXCEPCION de red al llamar la API: %s: %s", type(exc).__name__, exc)
        return None, False

    if r.status_code == 200:
        try:
            cuerpo = r.json()
        except Exception as exc:  # noqa: BLE001
            log.error("La API devolvio 200 pero el JSON es ilegible: %s", exc)
            log.error("Cuerpo crudo: %s", r.text[:500])
            return None, False

        bloques = cuerpo.get("content", [])
        texto = "\n".join(
            b.get("text", "") for b in bloques if b.get("type") == "text"
        ).strip()

        if texto:
            log.info("Modelo %s respondio OK (%d caracteres).", modelo, len(texto))
            return texto, False

        # 200 pero sin texto: caso raro que antes fallaba en silencio
        log.error("La API devolvio 200 pero SIN texto. Modelo: %s", modelo)
        log.error("stop_reason: %s", cuerpo.get("stop_reason"))
        log.error("Cuerpo: %s", json.dumps(cuerpo)[:500])
        return None, False

    # --- Errores con codigo de estado ---
    detalle = r.text[:400]
    log.error("La API respondio %s con el modelo %s", r.status_code, modelo)
    log.error("Detalle: %s", detalle)

    if r.status_code == 401:
        log.error("DIAGNOSTICO: la clave es invalida. Genera otra en "
                  "console.anthropic.com y actualiza el secreto ANTHROPIC_API_KEY.")
    elif r.status_code == 400 and "credit" in detalle.lower():
        log.error("DIAGNOSTICO: sin saldo. Recarga en console.anthropic.com > Billing.")
    elif r.status_code == 404:
        log.error("DIAGNOSTICO: tu cuenta no reconoce ese nombre de modelo. "
                  "Pruebo con el siguiente de la lista.")
        return None, True  # merece la pena reintentar con otro modelo
    elif r.status_code == 429:
        log.error("DIAGNOSTICO: limite de peticiones alcanzado. Reintenta mas tarde.")
    elif r.status_code >= 500:
        log.error("DIAGNOSTICO: fallo del lado de Anthropic. Reintenta mas tarde.")

    return None, False


def preguntar(prompt: str, max_tokens: int = 1200) -> str | None:
    """
    Envia un prompt y devuelve el texto. None si falla.

    Nunca lanza: si la API falla, el brief sale igual sin la capa de analisis.
    Pero siempre deja constancia en el log de POR QUE fallo.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        log.error("FALTA ANTHROPIC_API_KEY. Revisa que el secreto exista en "
                  "Settings > Secrets and variables > Actions, escrito exactamente asi, "
                  "y que el workflow lo pase en la seccion env.")
        return None

    # Diagnostico de la clave sin exponerla
    limpia = api_key.strip()
    if limpia != api_key:
        log.warning("La clave tenia espacios o saltos de linea alrededor. Los quito.")
        api_key = limpia

    log.info("Clave presente: %d caracteres, empieza con '%s'.",
             len(api_key), api_key[:7])

    if not api_key.startswith("sk-ant-"):
        log.error("La clave NO empieza con 'sk-ant-'. Probablemente copiaste algo "
                  "incompleto o el valor equivocado.")

    for modelo in MODELOS:
        texto, reintentar = _intentar(modelo, prompt, max_tokens, api_key)
        if texto:
            return texto
        if not reintentar:
            break

    log.error("Ningun modelo respondio. El brief sale sin la capa de analisis.")
    return None
