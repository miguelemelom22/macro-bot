"""
estado.py — Memoria entre ejecuciones.

GitHub Actions no tiene estado: cada corrida arranca de cero. Para que el radar
por evento no repita la misma noticia ni te sature, guardamos un archivo JSON
que el workflow hace commit de vuelta al repositorio.

Qué recordamos:
  - Cuándo se envió el último radar (para respetar el silencio mínimo)
  - Qué titulares ya se reportaron (para no repetirlos)
  - Los últimos valores de mercado (para detectar movimientos entre corridas)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent
ARCHIVO = RAIZ / "estado.json"

VACIO = {
    "ultimo_radar": None,
    "titulares_vistos": [],
    "ultimos_valores": {},
    "envios": {},  # {"brief_diario": "2026-08-28", ...}
}


def cargar() -> dict:
    if not ARCHIVO.exists():
        return dict(VACIO)
    try:
        with ARCHIVO.open(encoding="utf-8") as f:
            datos = json.load(f)
        return {**VACIO, **datos}
    except Exception as exc:  # noqa: BLE001
        log.warning("Estado ilegible, arranco de cero: %s", exc)
        return dict(VACIO)


def guardar(estado: dict) -> None:
    # Conservamos solo los últimos 200 hashes: suficiente para no repetir,
    # y evita que el archivo crezca sin control.
    estado["titulares_vistos"] = estado.get("titulares_vistos", [])[-200:]
    try:
        with ARCHIVO.open("w", encoding="utf-8") as f:
            json.dump(estado, f, indent=2, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        log.error("No pude guardar el estado: %s", exc)


def huella(texto: str) -> str:
    """Hash corto de un titular, para identificarlo sin guardar el texto."""
    normalizado = " ".join(texto.lower().split()[:10])
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:16]


def ya_visto(estado: dict, titulo: str) -> bool:
    return huella(titulo) in estado.get("titulares_vistos", [])


def marcar_visto(estado: dict, titulo: str) -> None:
    h = huella(titulo)
    if h not in estado["titulares_vistos"]:
        estado["titulares_vistos"].append(h)


def silencio_activo(estado: dict, dias_minimos: float) -> bool:
    """
    True si aún estamos dentro del período de silencio tras el último radar.

    Sin esto, una semana volátil te llenaría de mensajes y dejarías de leerlos.
    """
    ultimo = estado.get("ultimo_radar")
    if not ultimo:
        return False
    try:
        fecha = datetime.fromisoformat(ultimo)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - fecha < timedelta(days=dias_minimos)


def marcar_radar_enviado(estado: dict) -> None:
    estado["ultimo_radar"] = datetime.now(timezone.utc).isoformat()


# --- Control de envío diario -------------------------------------------------

def ya_enviado_hoy(tarea: str, zona: str = "America/Santo_Domingo") -> bool:
    """
    True si `tarea` ya se envió hoy.

    Existe porque los cron de GitHub Actions no garantizan ejecución: si se
    programan varios disparos como red de seguridad, hay que evitar que llegue
    el mismo mensaje tres veces.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    est = cargar()
    hoy = datetime.now(ZoneInfo(zona)).date().isoformat()
    return est.get("envios", {}).get(tarea) == hoy


def marcar_enviado_hoy(tarea: str, zona: str = "America/Santo_Domingo") -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    est = cargar()
    est.setdefault("envios", {})[tarea] = datetime.now(ZoneInfo(zona)).date().isoformat()
    guardar(est)
