"""
disparadores.py — Etapa 1 del radar por evento: filtro determinista.

Sin IA y sin costo. Su único trabajo es responder una pregunta:
¿pasó algo objetivamente inusual desde la última revisión?

Si la respuesta es no, el proceso termina aquí y nunca se llama al modelo.
Esto no es solo ahorro: cada consulta al modelo es una oportunidad de que
responda "sí, esto es importante". Preguntarle 40 veces por semana erosiona
el listón. Preguntarle solo cuando ya hay evidencia objetiva lo mantiene alto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import datos
import estado
import noticias

log = logging.getLogger(__name__)


# Umbrales de movimiento diario. Deliberadamente altos: buscamos rupturas,
# no fluctuaciones. Configurables desde cartera.json.
UMBRALES = {
    "VIX": 15.0,          # el termómetro del miedo salta
    "S&P 500": 1.8,       # movimiento amplio del mercado
    "Nasdaq 100": 2.2,    # tecnología, más volátil por naturaleza
    "Brent": 4.0,         # shock energético
    "Oro": 2.5,           # huida a refugio
    "Dólar (DXY)": 1.0,   # el dólar se mueve poco; 1% ya es mucho
}

# Tasas: en puntos base, no en porcentaje de variación.
UMBRAL_TASA_PB = 12.0

# Puntaje mínimo de un titular para considerarlo disparador por sí solo.
UMBRAL_TITULAR = 9


@dataclass
class Disparo:
    tipo: str        # "mercado", "tasa" o "noticia"
    detalle: str
    magnitud: float

    def __str__(self) -> str:
        return f"[{self.tipo}] {self.detalle}"


def _revisar_mercados(m: dict, umbrales: dict) -> list[Disparo]:
    disparos = []
    for nombre, lectura in m.items():
        limite = umbrales.get(nombre)
        if limite is None or lectura.cambio_dia is None:
            continue
        if abs(lectura.cambio_dia) >= limite:
            disparos.append(Disparo(
                tipo="mercado",
                detalle=f"{nombre} se movió {lectura.cambio_dia:+.2f}% (umbral {limite}%)",
                magnitud=abs(lectura.cambio_dia),
            ))
    return disparos


def _revisar_tasas(c: dict, umbral_pb: float) -> list[Disparo]:
    """
    Un movimiento de tasas se mide en puntos base sobre el nivel, no en
    variación porcentual: que el 10 años pase de 4.60% a 4.75% es 15pb,
    un movimiento grande, aunque en términos porcentuales sea solo 3%.
    """
    disparos = []
    for plazo, lectura in c.items():
        if lectura.cambio_dia is None:
            continue
        # cambio_dia viene en % de variación del nivel; lo convertimos a pb
        nivel_previo = lectura.valor / (1 + lectura.cambio_dia / 100)
        movimiento_pb = abs(lectura.valor - nivel_previo) * 100
        if movimiento_pb >= umbral_pb:
            disparos.append(Disparo(
                tipo="tasa",
                detalle=f"Tesoro {plazo} se movió {movimiento_pb:.0f}pb (umbral {umbral_pb:.0f}pb)",
                magnitud=movimiento_pb,
            ))
    return disparos


def _revisar_noticias(est: dict, umbral: int) -> tuple[list[Disparo], list]:
    """Titulares de peso alto que no hayamos visto antes."""
    titulares = noticias.manuales() + noticias.obtener(
        maximo=15, horas=24, incluir_empresas=True
    )

    disparos, nuevos = [], []
    for t in titulares:
        if estado.ya_visto(est, t.titulo):
            continue
        nuevos.append(t)
        if t.puntaje >= umbral:
            disparos.append(Disparo(
                tipo="noticia",
                detalle=f"Titular de peso {t.puntaje}: {t.titulo[:70]}",
                magnitud=float(t.puntaje),
            ))
    return disparos, nuevos


def evaluar(est: dict, config: dict | None = None) -> tuple[list[Disparo], list, dict]:
    """
    Etapa 1 completa.

    Devuelve (disparos, titulares_nuevos, datos_mercado).
    Si disparos está vacío, no hay que llamar al modelo.
    """
    config = config or {}
    umbrales = {**UMBRALES, **config.get("umbrales_mercado", {})}
    umbral_pb = config.get("umbral_tasa_pb", UMBRAL_TASA_PB)
    umbral_tit = config.get("umbral_titular", UMBRAL_TITULAR)

    c, m = datos.curva(), datos.mercados()

    disparos = _revisar_mercados(m, umbrales) + _revisar_tasas(c, umbral_pb)
    disparos_noticia, nuevos = _revisar_noticias(est, umbral_tit)
    disparos += disparos_noticia

    disparos.sort(key=lambda d: d.magnitud, reverse=True)

    if disparos:
        log.info("Disparos detectados: %d", len(disparos))
        for d in disparos:
            log.info("  %s", d)
    else:
        log.info("Nada cruzó umbral. Sin llamada al modelo.")

    return disparos, nuevos, {"curva": c, "mercados": m}
