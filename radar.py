"""
radar.py — Radar de oportunidad/amenaza, una vez por semana.

Estructura fija de cada mensaje:
  1. LA NOTICIA        — qué pasó, en lenguaje llano
  2. EL MAPA           — qué activos toca, a favor y en contra
  3. EL ATERRIZAJE     — contraargumento, tu exposición actual, de dónde saldría
                         el dinero, y una pregunta para tus mentores

Nunca cierra con una recomendación. El objetivo es darte el mapa completo y
devolverte a una decisión fría, no empujarte a una caliente.

Modo por evento (por defecto): se ejecuta cada 2 horas durante horario de
mercado, pero en dos etapas. Primero un filtro determinista sin IA revisa si
algo cruzó un umbral objetivo; solo si algo cruzó se consulta al modelo. Así
el modelo se consulta 2-3 veces por semana en vez de 40, y el listón se
mantiene alto.

Uso:
    python -m src.radar              # modo evento (revisa umbrales primero)
    python -m src.radar --forzar     # salta el filtro, consulta directo
    python -m src.radar --local      # imprime en pantalla, no envía
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import datos
import disparadores
import estado
import llm
import noticias
import telegram

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ZONA = ZoneInfo("America/Santo_Domingo")
RAIZ = Path(__file__).resolve().parent
CARTERA = RAIZ / "cartera.json"

# Si el modelo responde exactamente esto, no se envía nada.
SIN_NOVEDAD = "SIN_RADAR"

# Días mínimos de silencio entre radares. Sin esto, una semana volátil te
# llenaría de mensajes y dejarías de leerlos.
SILENCIO_DIAS = 4.0


PROMPT = """Eres un analista macro escribiendo para una persona que está \
aprendiendo a invertir y trabaja con mentores. Vive en República Dominicana e \
invierte en activos denominados en dólares. Escribe en español, directo y sin \
jerga innecesaria.

CIFRAS DE MERCADO (ya verificadas, úsalas tal cual):
{numeros}

QUÉ DISPARÓ ESTA REVISIÓN:
{disparos}

TITULARES RECIENTES:
{titulares}

SU CARTERA ACTUAL:
{cartera}

SU CONTEXTO:
{contexto}

TAREA
Un filtro automático detectó que algo cruzó un umbral y por eso te consulto. \
Pero que algo se haya movido NO significa que sea estructural.

Identifica UNA sola noticia que sea estructural — que cambie algo de fondo, no \
un movimiento de precio ni un titular ruidoso. Si lo que disparó la revisión es \
solo volatilidad sin causa de fondo, responde ÚNICAMENTE con la palabra \
{sin_novedad} y nada más. Eso es lo más frecuente y es correcto.

Si la hay, escribe el mensaje con EXACTAMENTE esta estructura:

*La noticia*
Qué pasó, en 2 o 3 líneas, con tus propias palabras. Explica el mecanismo \
económico, no solo el hecho.

*El mapa*
Qué activos toca esto y en qué dirección. Incluye activos que la persona NO \
tiene, si aplican. Sé concreto con los nombres, pero NO los presentes como \
recomendación — es un mapa de qué se conecta con qué.

*Por qué podría estar equivocado*
El contraargumento. Qué tendría que pasar para que esta lectura falle, o por \
qué el efecto podría ser menor de lo que parece. Esta sección es OBLIGATORIA: \
si no encuentras un contraargumento sólido, entonces la noticia no calificaba \
y debes responder {sin_novedad}.

*Dónde estás parado*
Su exposición actual a lo que toca esta noticia, usando los pesos reales de su \
cartera. Si ya está posicionado, DILO claramente — es un resultado valioso.

*De dónde saldría el dinero*
Si quisiera actuar, qué tendría que vender o cuánta liquidez gastar. Ninguna \
compra existe sin una venta.

*La pregunta para tus mentores*
Una sola pregunta concreta que le ayude a entender el principio general detrás \
de esta situación. No "¿debo comprar X?", sino algo que le enseñe a pensar.

REGLAS ESTRICTAS
- NO inventes cifras. Solo las de la sección CIFRAS DE MERCADO.
- NO recomiendes comprar ni vender. Ni siquiera de forma indirecta o sugerida.
- NO cierres con una conclusión de acción. El mensaje termina en la pregunta.
- NO reproduzcas titulares textualmente. Parafrasea siempre.
- Prefiere responder {sin_novedad} antes que forzar una noticia mediocre. Una \
semana sin radar es un resultado correcto y frecuente.
- Máximo 400 palabras en total.
- Formato Telegram: *un asterisco* para negritas, nunca ** dobles.
"""


def cargar_cartera() -> dict:
    if not CARTERA.exists():
        return {}
    with CARTERA.open(encoding="utf-8") as f:
        return json.load(f)


def _contexto_mercado() -> str:
    c, m, loc = datos.curva(), datos.mercados(), datos.local()
    partes = []

    for plazo in ("3M", "5Y", "10Y", "30Y"):
        if plazo in c and c[plazo].cambio_semana is not None:
            partes.append(f"Tesoro {plazo}: {c[plazo].valor:.2f}% ({c[plazo].cambio_semana:+.2f}% sem)")

    if (p := datos.pendiente(c)):
        partes.append(f"Diferencial 10a-3m: {p[0]:+.0f}pb ({p[1]})")

    for n in ("S&P 500", "Nasdaq 100", "VIX", "Dólar (DXY)", "Brent", "Oro"):
        if n in m and m[n].cambio_semana is not None:
            partes.append(f"{n}: {m[n].valor:,.2f} ({m[n].cambio_semana:+.2f}% sem)")

    if "USD/DOP" in loc:
        partes.append(f"USD/DOP: {loc['USD/DOP'].valor:.2f}")

    return "\n".join(partes) if partes else "Datos de mercado no disponibles."


def _cartera_texto(cartera: dict) -> str:
    posiciones = cartera.get("posiciones", [])
    if not posiciones:
        return "Sin cartera configurada."
    return "\n".join(
        f"{p['ticker']} ({p.get('bloque', '')}): {p['peso']}%" for p in posiciones
    )


def construir(forzar: bool = False) -> str | None:
    """
    Devuelve el mensaje, o None si no hay nada que reportar.

    Dos etapas:
      1. Filtro determinista (sin IA). Si nada cruzó umbral, termina aquí.
      2. Solo si algo cruzó, se consulta al modelo — que puede decir que no.
    """
    if not llm.disponible():
        log.info("El radar requiere ANTHROPIC_API_KEY. Omitido.")
        return None

    cartera = cargar_cartera()
    est = estado.cargar()

    # Silencio entre radares: se revisa antes que nada
    if not forzar and estado.silencio_activo(est, SILENCIO_DIAS):
        log.info("Dentro del período de silencio (%.0f días). Sin envío.", SILENCIO_DIAS)
        return None

    # --- Etapa 1: filtro determinista, sin costo ---
    if forzar:
        disparos = []
        titulares = noticias.manuales() + noticias.obtener(
            maximo=10, horas=170, incluir_empresas=True
        )
        nuevos = titulares
    else:
        disparos, nuevos, _ = disparadores.evaluar(est, cartera.get("radar", {}))

        # Si el mercado se movió de forma inusual, el filtro de palabras clave
        # no debe poder vetar la explicación: recogemos titulares sin filtrar.
        # Un evento imprevisible (pandemia, guerra, quiebra) nunca va a estar
        # en una lista de keywords escrita de antemano.
        if any(d.tipo in ("mercado", "tasa") for d in disparos):
            log.info("Disparo de mercado: recojo titulares sin filtro de keywords.")
            sin_filtrar = noticias.obtener(maximo=12, horas=24, sin_filtro=True)
            vistos = {n.titulo for n in nuevos}
            nuevos += [t for t in sin_filtrar
                       if t.titulo not in vistos and not estado.ya_visto(est, t.titulo)]

        if not disparos:
            # Marcamos los titulares vistos aunque no disparen, para no
            # reevaluarlos en la próxima corrida.
            for t in nuevos:
                estado.marcar_visto(est, t.titulo)
            estado.guardar(est)
            return None

        titulares = nuevos

    # Un shock de mercado merece análisis aunque el RSS no haya traído nada:
    # el modelo puede interpretar el movimiento en sí. Solo abortamos si no
    # hay NI disparos de mercado NI titulares.
    solo_noticia = all(d.tipo == "noticia" for d in disparos) if disparos else True
    if not titulares and solo_noticia:
        log.info("Sin titulares nuevos y sin disparo de mercado.")
        estado.guardar(est)
        return None

    # --- Etapa 2: consulta al modelo ---
    respuesta = llm.preguntar(
        PROMPT.format(
            numeros=_contexto_mercado(),
            disparos="\n".join(f"- {d}" for d in disparos) if disparos
                     else "Revisión manual forzada, sin disparador automático.",
            titulares=noticias.como_bloque(titulares),
            cartera=_cartera_texto(cartera),
            contexto=cartera.get("contexto", "Inversionista principiante, horizonte de 8 meses."),
            sin_novedad=SIN_NOVEDAD,
        ),
        max_tokens=1600,
    )

    # Pase lo que pase, estos titulares ya fueron evaluados
    for t in titulares:
        estado.marcar_visto(est, t.titulo)

    if not respuesta or SIN_NOVEDAD in respuesta.upper():
        log.info("El modelo no lo consideró estructural. Sin envío.")
        estado.guardar(est)
        return None

    estado.marcar_radar_enviado(est)
    estado.guardar(est)

    hoy = datetime.now(ZONA)
    encabezado = (
        f"🔭 *Radar* · {hoy.day}/{hoy.month} {hoy.strftime('%H:%M')}\n"
        "_Esto NO es una señal de compra ni de venta. "
        "Es el mapa completo para que decidas en frío._\n"
    )
    pie = (
        "\n\n_Ninguna decisión se toma el mismo día que llega este mensaje. "
        "Consúltalo, duérmelo, y si sigue teniendo sentido en unos días, "
        "entonces evalúalo en serio._\n"
        "_No es asesoría financiera._"
    )

    return encabezado + "\n" + respuesta + pie


def main() -> int:
    texto = construir(forzar="--forzar" in sys.argv)

    if texto is None:
        log.info("Sin radar. Esto es normal y esperado la mayoría de las veces.")
        return 0

    if "--local" in sys.argv:
        print(texto)
        return 0

    if telegram.enviar(texto):
        log.info("Radar enviado.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
