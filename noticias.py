"""
noticias.py — Titulares macro desde RSS público.

Sin API key ni costo. Lee varios feeds, descarta lo viejo, filtra por
relevancia macro y devuelve los titulares más pertinentes.

Nota sobre uso: solo pasamos titular + resumen breve al modelo, que escribe
su propia explicación. No reproducimos artículos.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser

log = logging.getLogger(__name__)


# --- Fuentes -----------------------------------------------------------------

FEEDS = {
    "CNBC Economía": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "CNBC Mercados": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "Yahoo Finanzas": "https://finance.yahoo.com/news/rssindex",
    "Reserva Federal": "https://www.federalreserve.gov/feeds/press_all.xml",
}


# --- Relevancia --------------------------------------------------------------

# Peso alto: mueve el mercado completo
MACRO_FUERTE = [
    "federal reserve", "fed ", "fomc", "powell", "warsh", "rate cut", "rate hike",
    "interest rate", "treasury", "yield", "inflation", "cpi", "ppi", "jobs report",
    "payroll", "unemployment", "gdp", "recession", "tariff", "deficit", "debt ceiling",
    "ecb", "bank of japan", "dollar", "oil price", "crude", "opec",
]

# Peso medio: sectorial amplio, sigue siendo macro
MACRO_MEDIO = [
    "bond market", "credit market", "consumer spending", "retail sales",
    "housing", "mortgage", "manufacturing", "services pmi", "trade deficit",
    "emerging markets", "dominican", "caribbean", "latin america",
    "ai spending", "data center", "semiconductor demand",
]

# Nombres de empresa: NO van en el brief diario (eso es cartera, no macro).
# Se reservan para el brief del viernes.
EMPRESAS = [
    "nvidia", "micron", "meta ", "alphabet", "google", "mastercard",
    "broadcom", "amd", "intel", "apple", "amazon", "tesla", "microsoft",
]

# Descartar: ruido que no aporta
RUIDO = [
    "how to", "best deals", "cyber monday", "gift guide", "horoscope",
    "celebrity", "recipe", "sponsored", "advertisement",
]


@dataclass
class Titular:
    titulo: str
    fuente: str
    resumen: str
    puntaje: int

    def como_texto(self) -> str:
        base = f"[{self.fuente}] {self.titulo}"
        if self.resumen:
            base += f"\n   {self.resumen}"
        return base


def _limpiar(texto: str) -> str:
    """Quita HTML y espacios sobrantes de los resúmenes RSS."""
    sin_html = re.sub(r"<[^>]+>", "", texto or "")
    return re.sub(r"\s+", " ", sin_html).strip()


def _puntuar(titulo: str, resumen: str, incluir_empresas: bool = False) -> int:
    """
    Puntúa relevancia. 0 = descartar.

    Por defecto excluye noticias de empresas individuales: el brief diario es
    macro, y hablar de tus posiciones a diario invita a reaccionar. Las
    noticias de empresa entran solo en el brief semanal.
    """
    texto = f"{titulo} {resumen}".lower()

    if any(r in texto for r in RUIDO):
        return 0

    puntaje = 0
    puntaje += 3 * sum(1 for k in MACRO_FUERTE if k in texto)
    puntaje += 1 * sum(1 for k in MACRO_MEDIO if k in texto)

    if incluir_empresas:
        puntaje += 2 * sum(1 for k in EMPRESAS if k in texto)
    elif puntaje == 0 and any(k in texto for k in EMPRESAS):
        return 0  # solo habla de una empresa: fuera del brief diario

    return puntaje


def _es_reciente(entrada, horas: int) -> bool:
    """True si la entrada es de las últimas N horas (o si no trae fecha)."""
    marca = getattr(entrada, "published_parsed", None) or getattr(entrada, "updated_parsed", None)
    if marca is None:
        return True  # sin fecha: no la descartamos
    publicado = datetime(*marca[:6], tzinfo=timezone.utc)
    return publicado >= datetime.now(timezone.utc) - timedelta(hours=horas)


def obtener(maximo: int = 6, horas: int = 30,
            incluir_empresas: bool = False,
            sin_filtro: bool = False) -> list[Titular]:
    """
    Devuelve los titulares más relevantes de las últimas `horas`.

    incluir_empresas=False (brief diario): solo macro.
    incluir_empresas=True  (brief semanal): también noticias de tus posiciones.

    sin_filtro=True: DESACTIVA el filtro de palabras clave y devuelve los
    titulares más recientes tal cual. Se usa cuando el mercado ya se movió de
    forma inusual: en ese caso el movimiento mismo es la evidencia de que algo
    pasó, y la lista de palabras clave no debería poder vetar la explicación.

    Por qué importa: las listas de MACRO_FUERTE y MACRO_MEDIO solo cubren
    categorías previsibles. Una pandemia, una guerra, una quiebra bancaria o un
    desastre natural usan vocabulario que nadie puso en la lista de antemano —
    y son exactamente los eventos que más mueven los mercados. Filtrar por
    palabras clave garantiza perderse lo imprevisible.

    Nunca lanza: si un feed falla, se omite y seguimos con los demás.
    """
    encontrados: list[Titular] = []
    vistos: set[str] = set()

    for fuente, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("Feed falló (%s): %s", fuente, exc)
            continue

        if not getattr(feed, "entries", None):
            log.warning("Feed vacío: %s", fuente)
            continue

        for entrada in feed.entries[:25]:
            titulo = _limpiar(getattr(entrada, "title", ""))
            if not titulo:
                continue

            if not _es_reciente(entrada, horas):
                continue

            # Deduplicar por las primeras palabras del titular
            clave = " ".join(titulo.lower().split()[:7])
            if clave in vistos:
                continue

            resumen = _limpiar(getattr(entrada, "summary", ""))[:280]

            if sin_filtro:
                # Solo descartamos ruido evidente; todo lo demás pasa.
                if any(r in f"{titulo} {resumen}".lower() for r in RUIDO):
                    continue
                puntaje = 1
            else:
                puntaje = _puntuar(titulo, resumen, incluir_empresas)
                if puntaje == 0:
                    continue

            vistos.add(clave)
            encontrados.append(Titular(titulo, fuente, resumen, puntaje))

    encontrados.sort(key=lambda t: t.puntaje, reverse=True)
    log.info("Titulares relevantes: %d", len(encontrados))
    return encontrados[:maximo]


def como_bloque(titulares: list[Titular]) -> str:
    """Formatea los titulares para pasarlos al modelo."""
    if not titulares:
        return "Sin titulares macro relevantes en las últimas horas."
    return "\n\n".join(t.como_texto() for t in titulares)


# --- Titulares manuales ------------------------------------------------------

def manuales(ruta: str = "titulares_manuales.txt") -> list[Titular]:
    """
    Lee titulares que hayas pegado tú en un archivo de texto.

    Útil si tienes acceso a una fuente sin RSS público (Bloomberg Terminal,
    un boletín por correo, notas de tus mentores). Un titular por línea;
    las líneas que empiezan con # se ignoran.

    Estos titulares entran con prioridad máxima: si te tomaste el trabajo de
    pegarlos, es porque importan.
    """
    from pathlib import Path

    archivo = Path(ruta)
    if not archivo.exists():
        return []

    salida = []
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        salida.append(Titular(titulo=linea, fuente="Manual", resumen="", puntaje=99))

    if salida:
        log.info("Titulares manuales: %d", len(salida))
    return salida
