"""
diagnostico.py — Revisa por qué falta alguna sección del brief.

Ejecutar desde Actions: workflow "Diagnostico" -> Run workflow.
El resultado sale en el log, no se envía a Telegram.
"""

import os
import sys

print("=" * 60)
print("1. SECRETOS CONFIGURADOS")
print("=" * 60)
for nombre in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "ANTHROPIC_API_KEY"):
    valor = os.getenv(nombre)
    if valor:
        print(f"  OK  {nombre}: presente ({len(valor)} caracteres)")
    else:
        print(f"  NO  {nombre}: FALTA")

print()
print("=" * 60)
print("2. FEEDS RSS")
print("=" * 60)
import noticias

total_bruto = 0
for fuente, url in noticias.FEEDS.items():
    try:
        import feedparser
        feed = feedparser.parse(url)
        n = len(getattr(feed, "entries", []))
        total_bruto += n
        estado = "OK " if n else "NO "
        print(f"  {estado} {fuente}: {n} entradas")
    except Exception as exc:
        print(f"  NO  {fuente}: ERROR {exc}")

print(f"\n  Total de entradas descargadas: {total_bruto}")

print()
print("=" * 60)
print("3. FILTRO DE RELEVANCIA")
print("=" * 60)
titulares = noticias.obtener(maximo=10)
print(f"  Titulares que pasaron el filtro: {len(titulares)}")
for t in titulares:
    print(f"    [{t.puntaje}] {t.fuente}: {t.titulo[:65]}")

if not titulares and total_bruto > 0:
    print()
    print("  DIAGNOSTICO: los feeds funcionan pero nada pasó el filtro.")
    print("  Baja el listón agregando palabras clave en MACRO_MEDIO,")
    print("  o amplía la ventana de horas en la llamada a obtener().")

print()
print("=" * 60)
print("4. LLAMADA A LA API DE ANTHROPIC")
print("=" * 60)
import llm

if not llm.disponible():
    print("  NO  Sin ANTHROPIC_API_KEY.")
else:
    r = llm.preguntar("Responde solamente con la palabra OK.", max_tokens=20)
    if r:
        print(f"  OK  La API respondió: {r[:60]}")
    else:
        print("  NO  La API no respondió. Revisa saldo y validez de la clave.")

print()
print("=" * 60)
print("5. DATOS DE MERCADO")
print("=" * 60)
import datos

c = datos.curva()
m = datos.mercados()
print(f"  Tasas obtenidas: {len(c)} de 4")
print(f"  Mercados obtenidos: {len(m)} de 6")
if c:
    for k, v in c.items():
        print(f"    {k}: {v.valor:.2f}%")
