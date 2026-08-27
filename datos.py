"""
datos.py — Obtención de datos de mercado.

Usa yfinance, que no requiere API key. Todos los datos vienen con retraso
de ~15 minutos, suficiente para contexto macro.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import yfinance as yf

log = logging.getLogger(__name__)


# --- Universo de seguimiento -------------------------------------------------

CURVA = {
    "3M": ("^IRX", "Letra 3 meses"),
    "5Y": ("^FVX", "Bono 5 años"),
    "10Y": ("^TNX", "Bono 10 años"),
    "30Y": ("^TYX", "Bono 30 años"),
}

MERCADOS = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "VIX": "^VIX",
    "Dólar (DXY)": "DX-Y.NYB",
    "Brent": "BZ=F",
    "Oro": "GC=F",
}

# Contexto local dominicano
LOCAL = {
    "USD/DOP": "DOP=X",
}


@dataclass
class Lectura:
    nombre: str
    valor: float
    cambio_dia: float | None = None
    cambio_semana: float | None = None
    unidad: str = ""

    def texto(self, invertir_color: bool = False) -> str:
        """
        Formatea el valor con su variación: color + flecha.

        La FLECHA siempre indica la dirección real del dato.
        El COLOR indica si eso es bueno o malo PARA TU CARTERA.

        invertir_color=True se usa en las tasas del Tesoro, donde precio y
        rendimiento se mueven en direcciones opuestas: si el rendimiento del
        30 años sube, el precio de TLT baja. Como tienes TLT e IEF, una tasa
        al alza es una mala noticia — de ahí que salga 🔴▲: subió, y te
        perjudica.

        La flecha sobrevive a cualquier dispositivo que renderice los emojis
        distinto. Nunca dependas del color solo para leer la dirección.
        """
        base = f"{self.valor:.2f}%" if self.unidad == "%" else (
            f"{self.valor:,.0f}" if self.valor >= 1000 else f"{self.valor:,.2f}"
        )
        if self.cambio_dia is None:
            return base

        if self.cambio_dia == 0:
            return f"{base} ⚪= {self.cambio_dia:+.2f}%"

        subio = self.cambio_dia > 0
        flecha = "▲" if subio else "▼"
        favorable = (not subio) if invertir_color else subio
        color = "🟢" if favorable else "🔴"

        return f"{base} {color}{flecha} {self.cambio_dia:+.2f}%"


# --- Descarga ----------------------------------------------------------------

def _historial(ticker: str, dias: int = 12):
    """Descarga histórico reciente. Devuelve None si falla (nunca lanza)."""
    try:
        fin = datetime.now()
        inicio = fin - timedelta(days=dias + 8)  # colchón por feriados
        df = yf.Ticker(ticker).history(start=inicio, end=fin, interval="1d")
        if df is None or df.empty:
            log.warning("Sin datos: %s", ticker)
            return None
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("Fallo al descargar %s: %s", ticker, exc)
        return None


def leer(ticker: str, nombre: str, unidad: str = "") -> Lectura | None:
    """Lee último valor con variación diaria y semanal."""
    df = _historial(ticker)
    if df is None:
        return None

    cierres = df["Close"].dropna()
    if cierres.empty:
        return None

    ultimo = float(cierres.iloc[-1])

    def variacion(pasos: int) -> float | None:
        if len(cierres) <= pasos:
            return None
        previo = float(cierres.iloc[-1 - pasos])
        return (ultimo - previo) / previo * 100 if previo else None

    return Lectura(
        nombre=nombre,
        valor=ultimo,
        cambio_dia=variacion(1),
        cambio_semana=variacion(5),
        unidad=unidad,
    )


def curva() -> dict[str, Lectura]:
    salida = {}
    for plazo, (ticker, _) in CURVA.items():
        if (l := leer(ticker, plazo, unidad="%")):
            salida[plazo] = l
    return salida


def local() -> dict[str, Lectura]:
    """Tipo de cambio y otros indicadores locales."""
    salida = {}
    for nombre, ticker in LOCAL.items():
        if (l := leer(ticker, nombre)):
            salida[nombre] = l
    return salida


def mercados() -> dict[str, Lectura]:
    salida = {}
    for nombre, ticker in MERCADOS.items():
        if (l := leer(ticker, nombre)):
            salida[nombre] = l
    return salida


def precios(tickers: list[str]) -> dict[str, Lectura]:
    """Lee una lista arbitraria de tickers (para la cartera)."""
    salida = {}
    for t in tickers:
        if (l := leer(t, t)):
            salida[t] = l
    return salida


# --- Interpretaciones --------------------------------------------------------

def pendiente(c: dict[str, Lectura]) -> tuple[float, str] | None:
    """Diferencial 10a-3m en puntos base, con lectura."""
    if "10Y" not in c or "3M" not in c:
        return None
    spread = (c["10Y"].valor - c["3M"].valor) * 100

    if spread < -50:
        txt = "Curva profundamente invertida — señal histórica de recesión"
    elif spread < 0:
        txt = "Curva invertida — el mercado descuenta desaceleración"
    elif spread < 50:
        txt = "Curva plana — transición, sin señal clara"
    elif spread < 150:
        txt = "Curva con pendiente normal — expansión ordenada"
    else:
        txt = "Curva empinada — expectativa de crecimiento o inflación"
    return spread, txt


def leer_vix(v: float) -> str:
    if v < 15:
        return "Calma. También es cuando la gente baja la guardia."
    if v < 20:
        return "Normal. Mercado funcionando sin estrés."
    if v < 30:
        return "Nerviosismo. Los movimientos diarios se amplifican."
    return "Miedo. Nivel de crisis."


def leer_dop(valor: float, cambio_anual: float | None = None) -> str:
    """
    Contextualiza el USD/DOP.

    El peso dominicano es de flotación administrada: el Banco Central suaviza
    los movimientos, así que la variación diaria casi siempre es ruido. Lo que
    importa es la tendencia acumulada.
    """
    base = f"1 USD = {valor:,.2f} DOP"
    if cambio_anual is None:
        return base
    return f"{base} · {cambio_anual:+.1f}% en 12 meses"
