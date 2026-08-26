"""
telegram.py — Envío de mensajes a Telegram.

Usa la API HTTP directa: no requiere librería de bot, solo requests.
Telegram limita los mensajes a 4096 caracteres, así que dividimos si hace falta.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

LIMITE = 4000  # margen bajo el límite real de 4096


def _partir(texto: str) -> list[str]:
    """Divide un texto largo por párrafos, sin cortar a media línea."""
    if len(texto) <= LIMITE:
        return [texto]

    partes, actual = [], ""
    for linea in texto.split("\n"):
        if len(actual) + len(linea) + 1 > LIMITE:
            if actual:
                partes.append(actual.rstrip())
            actual = linea + "\n"
        else:
            actual += linea + "\n"
    if actual.strip():
        partes.append(actual.rstrip())
    return partes


def enviar(texto: str, token: str | None = None, chat_id: str | None = None) -> bool:
    """
    Envía un mensaje. Devuelve True si todas las partes se entregaron.

    Lee TELEGRAM_TOKEN y TELEGRAM_CHAT_ID del entorno si no se pasan.
    """
    token = token or os.getenv("TELEGRAM_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log.error("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = True

    for parte in _partir(texto):
        try:
            r = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": parte,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
            if r.status_code != 200:
                log.error("Telegram respondió %s: %s", r.status_code, r.text[:300])
                ok = False
        except Exception as exc:  # noqa: BLE001
            log.error("Error al enviar a Telegram: %s", exc)
            ok = False

    return ok
