"""
brief_diario.py — Brief macro de cada mañana.

Tres capas:
  1. NÚMEROS (determinista)  — tasas, acciones, divisas. Sin IA, sin margen de error.
  2. NOTICIAS (IA)           — titulares macro explicados en clave educativa.
  3. CONCEPTO (determinista) — un término rotativo del glosario.

Deliberadamente NO menciona tu cartera. Su trabajo es que entiendas el contexto,
no que reacciones a él. La perspectiva de cartera va el viernes.

Uso:
    python -m src.brief_diario           # envía a Telegram
    python -m src.brief_diario --local   # imprime en pantalla, no envía
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import datos
import llm
import noticias
import telegram

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ZONA = ZoneInfo("America/Santo_Domingo")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha() -> str:
    h = datetime.now(ZONA)
    return f"{DIAS[h.weekday()]} {h.day} de {MESES[h.month - 1]}"


# --- Capa 3: concepto educativo rotativo -------------------------------------

CONCEPTOS = [
    ("Curva de rendimientos", "La forma de la curva resume qué espera el mercado de la economía. Cuando el plazo corto paga más que el largo está 'invertida' — históricamente ha anticipado recesiones."),
    ("Prima por plazo", "La compensación extra por prestar a 30 años en vez de a 2. Explica por qué las tasas largas suben aunque la Fed recorte: si hay mucho déficit, el mercado exige más."),
    ("Duración", "Sensibilidad de un bono a las tasas. Duración 15 significa que si las tasas bajan 1%, el bono sube ~15%. Es la palanca de riesgo de la renta fija."),
    ("Beta", "Cuánto se mueve un activo respecto al mercado. Beta 2.0 amplifica el doble — al subir y al bajar. No es 'más rentable', es más volátil."),
    ("VIX", "La volatilidad que el mercado espera a 30 días. Bajo 15 es calma, sobre 30 es pánico. Contra-intuitivo: los niveles altos suelen ser buenos puntos de entrada."),
    ("Correlación", "Si dos activos se mueven juntos. Es la base real de la diversificación: tener 10 acciones tecnológicas no es diversificar, todas se mueven igual."),
    ("Drawdown", "La caída desde el máximo al mínimo posterior. Si pierdes 30% necesitas +43% para recuperarte; si pierdes 50%, necesitas +100%."),
    ("Empinamiento", "Cuando la brecha entre tasas largas y cortas se amplía. Si esperas empinamiento, los bonos largos rinden peor que los medios."),
    ("Estanflación", "Inflación alta con crecimiento estancado. Rompe la diversificación clásica: acciones y bonos caen juntos."),
    ("Dollar Cost Averaging", "Invertir cantidades fijas a intervalos regulares. Reduce el riesgo de entrar en el peor momento y el arrepentimiento, que causa las malas decisiones."),
    ("Prima de riesgo", "El retorno extra que exiges por invertir en algo riesgoso en vez del bono del Tesoro. Con tasas altas, las acciones compiten cuesta arriba."),
    ("Punto base", "Una centésima de un 1%. Cuando dicen que el bono subió 25pb, subió 0.25%. Se usa para evitar confusiones entre porcentajes de porcentajes."),
]


def _concepto_del_dia() -> str:
    nombre, texto = CONCEPTOS[datetime.now(ZONA).timetuple().tm_yday % len(CONCEPTOS)]
    return f"*{nombre}* — {texto}"


# --- Capa 1: números ---------------------------------------------------------

def _bloque_numeros(c: dict, m: dict, loc: dict) -> tuple[list[str], str]:
    """Devuelve (líneas para Telegram, resumen plano para el modelo)."""
    lineas: list[str] = []
    plano: list[str] = []

    if c:
        lineas.append("*Tasas del Tesoro*")
        for plazo in ("3M", "5Y", "10Y", "30Y"):
            if plazo in c:
                lineas.append(f"  {plazo}: {c[plazo].texto()}")
                plano.append(f"Tesoro {plazo}: {c[plazo].valor:.2f}% ({c[plazo].cambio_dia:+.2f}% dia)")
        if (p := datos.pendiente(c)):
            spread, lectura = p
            lineas.append(f"  _10a−3m: {spread:+.0f}pb — {lectura}_")
            plano.append(f"Diferencial 10a-3m: {spread:+.0f}pb ({lectura})")
        lineas.append("")

    acciones = [n for n in ("S&P 500", "Nasdaq 100", "VIX") if n in m]
    if acciones:
        lineas.append("*Acciones*")
        for n in acciones:
            lineas.append(f"  {n}: {m[n].texto()}")
            plano.append(f"{n}: {m[n].valor:,.2f} ({m[n].cambio_dia:+.2f}% dia)")
        if "VIX" in m:
            lineas.append(f"  _{datos.leer_vix(m['VIX'].valor)}_")
        lineas.append("")

    otros = [n for n in ("Dólar (DXY)", "Brent", "Oro") if n in m]
    if otros:
        lineas.append("*Divisas y materias primas*")
        for n in otros:
            lineas.append(f"  {n}: {m[n].texto()}")
            plano.append(f"{n}: {m[n].valor:,.2f} ({m[n].cambio_dia:+.2f}% dia)")
        lineas.append("")

    if "USD/DOP" in loc:
        d = loc["USD/DOP"]
        lineas.append("*Contexto local*")
        lineas.append(f"  {datos.leer_dop(d.valor)}")
        if d.cambio_semana is not None:
            lineas.append(f"  _Variación semanal: {d.cambio_semana:+.2f}%_")
            plano.append(f"USD/DOP: {d.valor:.2f} ({d.cambio_semana:+.2f}% sem)")
        lineas.append("")

    return lineas, "\n".join(plano) if plano else "Datos de mercado no disponibles."


# --- Capa 2: noticias explicadas ---------------------------------------------

PROMPT = """Eres un analista macro escribiendo para una persona que está \
empezando a invertir y quiere ENTENDER cómo funcionan los mercados. Escribe en \
español, directo y sin jerga innecesaria. Cuando uses un término técnico, \
explícalo en la misma frase.

CIFRAS DE MERCADO DE HOY (ya verificadas, úsalas tal cual):
{numeros}

TITULARES DE LAS ÚLTIMAS HORAS:
{titulares}

Escribe una sección breve (máximo 220 palabras) con las 2 o 3 noticias más \
relevantes. Para cada una:
- Una línea de qué pasó, con TUS PROPIAS PALABRAS (nunca copies el titular textual)
- Una o dos líneas de por qué importa y qué mecanismo económico hay detrás

El objetivo es que la persona aprenda a leer el mercado, no que se entere de \
noticias.

La persona vive en República Dominicana e invierte en activos en dólares. \
Cuando sea relevante, menciona brevemente cómo lo que pasa afecta a alguien \
que gana en pesos e invierte en dólares — pero solo si aplica de verdad, no \
lo fuerces.

REGLAS ESTRICTAS:
- NO inventes cifras. Solo puedes citar números de la sección CIFRAS DE MERCADO. \
Si un titular menciona un dato que no está ahí, descríbelo cualitativamente.
- NO reproduzcas titulares ni textos textualmente. Parafrasea siempre.
- NO recomiendes comprar ni vender nada. Explica, no dirijas.
- Si los titulares son irrelevantes o repetitivos, DILO en una línea: es una \
respuesta válida y valiosa. No fabriques importancia.
- Este es un brief MACRO. Si un titular habla solo de una empresa concreta, \
ignóralo — eso se revisa el viernes.
- Formato Telegram: usa *un asterisco* para negritas, nunca ** dobles. Sin encabezados \
con almohadilla.
"""


def _bloque_noticias(numeros_plano: str) -> str | None:
    # Los titulares que pegaste tú van primero, luego los de RSS
    titulares = noticias.manuales() + noticias.obtener(maximo=6)

    if not titulares:
        log.info("Sin titulares relevantes.")
        return None

    if not llm.disponible():
        # Sin IA: mostramos los titulares crudos, sin interpretación
        return "\n".join(f"  • {t.titulo}  _({t.fuente})_" for t in titulares[:4])

    return llm.preguntar(
        PROMPT.format(numeros=numeros_plano, titulares=noticias.como_bloque(titulares)),
        max_tokens=900,
    )


# --- Ensamblado --------------------------------------------------------------

def construir() -> str:
    c, m, loc = datos.curva(), datos.mercados(), datos.local()
    lineas_num, numeros_plano = _bloque_numeros(c, m, loc)

    partes = [f"☕ *Brief Macro* · {_fecha()}", ""]
    partes += lineas_num

    if not c and not m:
        partes += ["⚠️ No pude obtener datos de mercado hoy.", ""]

    if (analisis := _bloque_noticias(numeros_plano)):
        partes += ["📰 *Lo que está moviendo el mercado*", analisis, ""]

    partes += ["📚 *Concepto del día*", _concepto_del_dia(), ""]
    partes += ["_Datos con retraso. Informativo, no asesoría financiera._"]

    return "\n".join(partes)


def main() -> int:
    texto = construir()

    if "--local" in sys.argv:
        print(texto)
        return 0

    if telegram.enviar(texto):
        log.info("Brief diario enviado.")
        return 0

    log.error("No se pudo enviar el brief.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
