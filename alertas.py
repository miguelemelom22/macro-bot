"""
alertas.py — Alertas de umbral sobre tus posiciones.

Deliberadamente SIN IA. Estas alertas no interpretan ni opinan: constatan un
hecho y te devuelven a la regla que tú mismo definiste cuando estabas tranquilo.

Esa es toda la lógica. Un modelo generando análisis en el momento exacto en que
tu posición cae 8% agregaría ruido justo cuando menos lo necesitas. La alerta
buena es aburrida: "esto pasó, tu regla decía esto, estás a esta distancia".

Reglas configurables en cartera.json, sección "reglas".

Uso:
    python -m src.alertas
    python -m src.alertas --local
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import datos
import estado
import telegram

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ZONA = ZoneInfo("America/Santo_Domingo")
RAIZ = Path(__file__).resolve().parent
CARTERA = RAIZ / "cartera.json"

# Valores por defecto si cartera.json no define "reglas"
REGLAS_BASE = {
    "caida_posicion_dia": 6.0,      # una posición cae más de X% en un día
    "caida_cartera_dia": 3.0,       # la cartera completa cae más de X%
    "subida_posicion_dia": 8.0,     # una posición sube más de X% (también informa)
    "horas_silencio_posicion": 48,  # no repetir alerta de la misma posición
    "max_alertas_dia": 2,           # techo diario, pase lo que pase
    "niveles": {},                  # ej. {"TLT": {"bajo": 78, "nota": "..."}}
}


@dataclass
class Alerta:
    clave: str          # identificador para el control de repetición
    icono: str
    titulo: str
    cuerpo: list[str]
    regla: str          # la regla del usuario, citada

    def texto(self) -> str:
        lineas = [f"{self.icono} *{self.titulo}*", ""]
        lineas += self.cuerpo
        lineas += ["", f"*Tu regla:* {self.regla}"]
        return "\n".join(lineas)


def cargar_cartera() -> dict:
    if not CARTERA.exists():
        return {}
    with CARTERA.open(encoding="utf-8") as f:
        return json.load(f)


# --- Control de repetición ---------------------------------------------------

def _silenciada(est: dict, clave: str, horas: int) -> bool:
    registro = est.setdefault("alertas_enviadas", {})
    marca = registro.get(clave)
    if not marca:
        return False
    try:
        fecha = datetime.fromisoformat(marca)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - fecha < timedelta(hours=horas)


def _marcar(est: dict, clave: str) -> None:
    est.setdefault("alertas_enviadas", {})[clave] = datetime.now(timezone.utc).isoformat()


def _enviadas_hoy(est: dict) -> int:
    registro = est.get("alertas_enviadas", {})
    hoy = datetime.now(timezone.utc).date()
    total = 0
    for marca in registro.values():
        try:
            if datetime.fromisoformat(marca).date() == hoy:
                total += 1
        except ValueError:
            continue
    return total


# --- Detección ---------------------------------------------------------------

def _revisar_posiciones(posiciones, lecturas, reglas) -> list[Alerta]:
    alertas = []
    caida = reglas["caida_posicion_dia"]
    subida = reglas["subida_posicion_dia"]

    for p in posiciones:
        t, peso = p["ticker"], p["peso"]
        lec = lecturas.get(t)
        if lec is None or lec.cambio_dia is None:
            continue

        mov = lec.cambio_dia
        impacto = (peso / 100) * mov

        if mov <= -caida:
            alertas.append(Alerta(
                clave=f"caida:{t}",
                icono="⚠️",
                titulo=f"Alerta: {t}",
                cuerpo=[
                    f"*{t} cayó {mov:.1f}% hoy* — supera tu umbral de {caida:.0f}%.",
                    "",
                    f"Precio: ${lec.valor:,.2f}",
                    f"Pesa {peso}% de tu cartera, así que el impacto en el total "
                    f"fue de {impacto:.2f}%.",
                ],
                regla="Una caída diaria no cambia una tesis de 8 meses. "
                      "Esto es información, no una señal de venta.",
            ))

        elif mov >= subida:
            alertas.append(Alerta(
                clave=f"subida:{t}",
                icono="🔵",
                titulo=f"Alerta: {t}",
                cuerpo=[
                    f"*{t} subió {mov:.1f}% hoy.*",
                    "",
                    f"Precio: ${lec.valor:,.2f}",
                    f"Aportó {impacto:+.2f}% a tu cartera.",
                ],
                regla="Vender 1/3 de cualquier posición que suba 50%+ antes del "
                      "mes 5. Un día fuerte no es un 50% acumulado.",
            ))

    return alertas


def _revisar_niveles(lecturas, reglas) -> list[Alerta]:
    """Niveles de precio específicos que definiste tú."""
    alertas = []

    for ticker, cfg in reglas.get("niveles", {}).items():
        lec = lecturas.get(ticker)
        if lec is None:
            continue

        bajo = cfg.get("bajo")
        alto = cfg.get("alto")
        nota = cfg.get("nota", "Revisar la tesis de esta posición.")

        if bajo is not None and lec.valor <= bajo:
            alertas.append(Alerta(
                clave=f"nivel_bajo:{ticker}",
                icono="⚠️",
                titulo=f"Nivel alcanzado: {ticker}",
                cuerpo=[
                    f"*{ticker} está en ${lec.valor:,.2f}* — cruzó tu nivel de ${bajo:,.2f}.",
                ],
                regla=nota,
            ))
        elif bajo is not None:
            distancia = (lec.valor - bajo) / lec.valor * 100
            if distancia <= 5:  # aviso de proximidad
                alertas.append(Alerta(
                    clave=f"cerca_bajo:{ticker}",
                    icono="🟡",
                    titulo=f"{ticker} se acerca a tu nivel",
                    cuerpo=[
                        f"*{ticker} en ${lec.valor:,.2f}*, a {distancia:.1f}% "
                        f"de tu nivel de ${bajo:,.2f}.",
                    ],
                    regla=nota,
                ))

        if alto is not None and lec.valor >= alto:
            alertas.append(Alerta(
                clave=f"nivel_alto:{ticker}",
                icono="🔵",
                titulo=f"Nivel alcanzado: {ticker}",
                cuerpo=[
                    f"*{ticker} está en ${lec.valor:,.2f}* — cruzó tu nivel de ${alto:,.2f}.",
                ],
                regla=nota,
            ))

    return alertas


def _revisar_cartera(posiciones, lecturas, reglas) -> list[Alerta]:
    """Movimiento agregado de la cartera completa."""
    movimiento = 0.0
    contadas = 0
    for p in posiciones:
        lec = lecturas.get(p["ticker"])
        if lec is None or lec.cambio_dia is None:
            continue
        movimiento += (p["peso"] / 100) * lec.cambio_dia
        contadas += 1

    if contadas < 3:  # datos insuficientes, no alertamos a ciegas
        return []

    limite = reglas["caida_cartera_dia"]
    if movimiento > -limite:
        return []

    return [Alerta(
        clave="cartera",
        icono="⚠️",
        titulo="Alerta: cartera completa",
        cuerpo=[
            f"*Tu cartera cayó {movimiento:.2f}% hoy* — supera tu umbral de {limite:.0f}%.",
            "",
            "Un día malo no es una tesis rota. Los bloques de calidad, duración "
            "y cobertura existen precisamente para estos días.",
        ],
        regla="Si el portafolio cae 35% acumulado, reducir a las 3 posiciones de "
              "mayor calidad. No promediar a la baja en las de beta más alto.",
    )]


# --- Ensamblado --------------------------------------------------------------

def construir() -> str | None:
    cartera = cargar_cartera()
    posiciones = [p for p in cartera.get("posiciones", []) if p["ticker"] != "USDT"]
    if not posiciones:
        return None

    reglas = {**REGLAS_BASE, **cartera.get("reglas", {})}
    est = estado.cargar()

    if _enviadas_hoy(est) >= reglas["max_alertas_dia"]:
        log.info("Techo diario de alertas alcanzado.")
        return None

    lecturas = datos.precios([p["ticker"] for p in posiciones])
    if not lecturas:
        log.warning("Sin datos de precios.")
        return None

    candidatas = (
        _revisar_cartera(posiciones, lecturas, reglas)
        + _revisar_niveles(lecturas, reglas)
        + _revisar_posiciones(posiciones, lecturas, reglas)
    )

    horas = reglas["horas_silencio_posicion"]
    nuevas = [a for a in candidatas if not _silenciada(est, a.clave, horas)]

    if not nuevas:
        log.info("Nada cruzó umbral, o ya fue notificado.")
        estado.guardar(est)
        return None

    # Techo por corrida: si cinco posiciones caen a la vez, mandamos las
    # más relevantes, no cinco mensajes.
    cupo = reglas["max_alertas_dia"] - _enviadas_hoy(est)
    nuevas = nuevas[:max(1, cupo)]

    for a in nuevas:
        _marcar(est, a.clave)
    estado.guardar(est)

    hoy = datetime.now(ZONA)
    partes = [f"_{hoy.strftime('%d/%m %H:%M')}_", ""]
    partes += ["\n\n".join(a.texto() for a in nuevas)]
    partes += ["", "_Ninguna decisión se toma con el mercado abierto y la alerta "
                   "recién leída. No es asesoría financiera._"]

    return "\n".join(partes)


def main() -> int:
    texto = construir()

    if texto is None:
        return 0

    if "--local" in sys.argv:
        print(texto)
        return 0

    if telegram.enviar(texto):
        log.info("Alerta enviada.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
