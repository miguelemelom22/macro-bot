"""
brief_semanal.py — Perspectiva de cartera, viernes después del cierre.

Se envía cuando el mercado ya cerró: recibes el análisis cuando NO puedes
actuar. Ese enfriamiento obligatorio de 62 horas es una funcionalidad, no
una limitación.

A diferencia del brief diario (determinista), este usa un modelo de lenguaje
porque interpretar una semana completa frente a una cartera sí requiere juicio.

Si no hay ANTHROPIC_API_KEY configurada, cae a un resumen puramente numérico.

Uso:
    python -m src.brief_semanal
    python -m src.brief_semanal --local
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import datos
import llm
import noticias
import telegram

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ZONA = ZoneInfo("America/Santo_Domingo")
RAIZ = Path(__file__).resolve().parent
CARTERA = RAIZ / "cartera.json"

# --- Cartera -----------------------------------------------------------------

def cargar_cartera() -> dict:
    if not CARTERA.exists():
        log.warning("No existe cartera.json")
        return {}
    with CARTERA.open(encoding="utf-8") as f:
        return json.load(f)


def evaluar_cartera(cartera: dict) -> tuple[list[dict], float]:
    """Lee precios y calcula el movimiento semanal ponderado."""
    posiciones = cartera.get("posiciones", [])
    tickers = [p["ticker"] for p in posiciones if p.get("ticker") != "USDT"]
    lecturas = datos.precios(tickers)

    filas, movimiento = [], 0.0
    for p in posiciones:
        t, peso = p["ticker"], p["peso"]
        if t == "USDT":
            filas.append({"ticker": t, "peso": peso, "semana": 0.0, "bloque": p.get("bloque", "")})
            continue
        l = lecturas.get(t)
        if l is None or l.cambio_semana is None:
            continue
        filas.append({
            "ticker": t, "peso": peso, "semana": l.cambio_semana,
            "bloque": p.get("bloque", ""), "precio": l.valor,
        })
        movimiento += (peso / 100) * l.cambio_semana

    return filas, movimiento


# --- Capa de razonamiento ----------------------------------------------------

PROMPT = """Eres un analista macro escribiendo para una persona que está \
aprendiendo a invertir y trabaja con mentores. Escribe en español, tono directo \
y educativo, sin jerga innecesaria.

DATOS DE MERCADO DE LA SEMANA:
{mercado}

SU CARTERA (peso % y movimiento semanal %):
{cartera}

MOVIMIENTO PONDERADO DE LA CARTERA ESTA SEMANA: {movimiento:+.2f}%

TITULARES DE LA SEMANA:
{titulares}

SU CONTEXTO:
{contexto}

Escribe un análisis breve (máximo 350 palabras) con esta estructura:

1. *Lo que movió la semana* — 2 o 3 puntos macro relevantes
2. *Qué significa para tu cartera* — conecta lo macro con SUS posiciones concretas
3. *Qué vigilar* — 1 o 2 cosas específicas

REGLAS IMPORTANTES:
- Si la semana no tuvo nada materialmente relevante para sus posiciones, DILO \
claramente. No inventes significado donde no lo hay. Un "esta semana no pasó \
nada que cambie tu tesis" es una respuesta válida y valiosa.
- No recomiendes comprar ni vender. Explica, no dirijas.
- Recuérdale que el análisis es para entender, no para actuar el lunes en la \
apertura.
- Usa *asteriscos* para negritas (formato Telegram), nunca ** dobles.
"""


def analizar_con_llm(mercado: str, cartera_txt: str, movimiento: float,
                     contexto: str, titulares: str) -> str | None:
    return llm.preguntar(
        PROMPT.format(
            mercado=mercado, cartera=cartera_txt, movimiento=movimiento,
            contexto=contexto, titulares=titulares,
        ),
        max_tokens=1400,
    )


# --- Construcción ------------------------------------------------------------

def construir() -> str:
    cartera = cargar_cartera()
    filas, movimiento = evaluar_cartera(cartera)

    c, m = datos.curva(), datos.mercados()

    # Contexto de mercado para el prompt
    partes = []
    if c:
        partes.append("Tasas: " + ", ".join(
            f"{p} {c[p].valor:.2f}% ({c[p].cambio_semana:+.2f}% sem)"
            for p in ("3M", "5Y", "10Y", "30Y")
            if p in c and c[p].cambio_semana is not None
        ))
    for n in ("S&P 500", "Nasdaq 100", "VIX", "Dólar (DXY)", "Brent", "Oro"):
        if n in m and m[n].cambio_semana is not None:
            partes.append(f"{n}: {m[n].valor:,.2f} ({m[n].cambio_semana:+.2f}% sem)")
    mercado_txt = "\n".join(partes) if partes else "Datos no disponibles."

    cartera_txt = "\n".join(
        f"{f['ticker']} ({f['bloque']}): peso {f['peso']}%, semana {f['semana']:+.2f}%"
        for f in filas
    ) or "Sin datos de cartera."

    hoy = datetime.now(ZONA)
    encabezado = f"📊 *Perspectiva Semanal* · viernes {hoy.day}\n_Mercado cerrado. Esto es para entender, no para actuar._\n"

    # Tabla numérica (siempre)
    tabla = [f"\n*Tu cartera esta semana: {movimiento:+.2f}%*\n"]
    por_bloque: dict[str, float] = {}
    for f in filas:
        por_bloque[f["bloque"]] = por_bloque.get(f["bloque"], 0.0) + (f["peso"] / 100) * f["semana"]
    for bloque, aporte in por_bloque.items():
        if bloque:
            tabla.append(f"  {bloque}: {aporte:+.2f}pp")

    titulares = noticias.como_bloque(noticias.obtener(maximo=8, horas=170, incluir_empresas=True))

    analisis = analizar_con_llm(
        mercado_txt, cartera_txt, movimiento,
        cartera.get("contexto", "Inversionista principiante, horizonte de 8 meses."),
        titulares,
    )

    cuerpo = analisis if analisis else (
        "\n_Resumen numérico (sin capa de análisis configurada)._\n\n"
        + "\n".join(f"  {f['ticker']}: {f['semana']:+.2f}%" for f in filas if f["ticker"] != "USDT")
    )

    pie = "\n\n_Regla acordada: si algo amerita acción, se decide el lunes por la tarde — nunca en la apertura._\n_No es asesoría financiera._"

    return encabezado + "\n".join(tabla) + "\n\n" + cuerpo + pie


def main() -> int:
    texto = construir()

    if "--local" in sys.argv:
        print(texto)
        return 0

    if telegram.enviar(texto):
        log.info("Brief semanal enviado.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
