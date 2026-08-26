"""
llm.py — Cliente compartido para la API de Anthropic.

Regla de diseño: el modelo NUNCA reporta números. Recibe las cifras ya
calculadas por el código y su trabajo es explicarlas. Así eliminamos la
posibilidad de que invente un dato que suene plausible.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

URL = "https://api.anthropic.com/v1/messages"
MODELO = os.getenv("MODELO_LLM", "claude-sonnet-5")


def disponible() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def preguntar(prompt: str, max_tokens: int = 1200) -> str | None:
    """
    Envía un prompt y devuelve el texto. None si falla o no hay clave.

    Nunca lanza: si la API falla, el brief sale igual sin la capa de análisis.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.info("Sin ANTHROPIC_API_KEY; omito la capa de análisis.")
        return None

    try:
        r = requests.post(
            URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODELO,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=90,
        )
        if r.status_code != 200:
            log.error("API respondió %s: %s", r.status_code, r.text[:300])
            return None

        bloques = r.json().get("content", [])
        texto = "\n".join(
            b.get("text", "") for b in bloques if b.get("type") == "text"
        ).strip()
        return texto or None

    except Exception as exc:  # noqa: BLE001
        log.error("Error al llamar la API: %s", exc)
        return None
