# Bot Macro — Telegram

Brief macro diario + perspectiva de cartera los viernes. Corre en GitHub Actions: **sin servidor, sin costo de hosting, sin dejar nada encendido.**

---

## Qué hace

| Cuándo | Qué envía |
|---|---|
| Lun–Vie 7:00am (RD) | Brief macro: números + noticias explicadas + concepto educativo |
| Cada 2h en horario de mercado | Radar por evento — **solo si algo cruza umbral Y es estructural** |
| Cada 2h en horario de mercado | Alertas de umbral sobre tus posiciones |
| Viernes 5:30pm | Perspectiva de tu cartera, con el mercado ya cerrado |

### El brief diario tiene tres capas

**1. Números (sin IA).** Tasas, acciones, dólar, petróleo, oro, VIX. Código determinista: o funciona o falla ruidosamente. Cero riesgo de que un modelo invente una cifra que suene plausible.

**2. Noticias explicadas (con IA).** Lee titulares de cinco fuentes RSS públicas, los filtra por relevancia macro, y el modelo escribe 2-3 explicaciones educativas: qué pasó y qué mecanismo económico hay detrás. Incluye perspectiva de alguien que gana en pesos e invierte en dólares.

**El brief diario excluye noticias de empresas individuales.** Si un titular habla solo de Micron o Nvidia, se descarta — eso es tu cartera, no macro, y verlo a diario invita a reaccionar. Las noticias de empresa entran solo en el brief del viernes.

**3. Concepto del día (sin IA).** Un término del glosario, rotando entre 12 según el día del año.

**Regla clave de diseño:** el modelo recibe las cifras ya calculadas y tiene prohibido inventar números. Su trabajo es explicar, no reportar. Y el prompt le instruye explícitamente a decir "hoy no hubo nada relevante" cuando sea el caso, en vez de fabricar importancia.

**El brief diario nunca menciona tu cartera** — su trabajo es que entiendas el contexto, no que reacciones a él.

**El viernes sí la analiza**, porque interpretar una semana frente a posiciones concretas requiere juicio.

### Las alertas de umbral

**Sin IA, a propósito.** Su trabajo no es interpretar sino constatar un hecho y devolverte a la regla que tú definiste en frío. Un modelo generando análisis justo cuando tu posición cae 8% agregaría ruido en el peor momento. La alerta buena es aburrida.

Cada alerta tiene tres partes: qué pasó, cuánto afectó tu cartera, y **tu regla citada textualmente**.

Qué dispara:

| Condición | Umbral por defecto |
|---|---|
| Una posición cae en un día | −6% |
| Una posición sube en un día | +8% |
| La cartera completa cae | −3% |
| Precio cruza un nivel tuyo | TLT < $78, MU < $190 |
| Precio se acerca a un nivel | dentro del 5% |

Tres controles para que no te saturen:

- **48 horas de silencio** por posición — la misma alerta no se repite
- **Máximo 2 alertas al día**, pase lo que pase
- Si cinco posiciones caen a la vez, llega **un mensaje con las más relevantes**, no cinco mensajes

Los niveles se configuran en `cartera.json`, sección `reglas` → `niveles`. Cada uno lleva una `nota` que es lo que el bot te va a citar cuando se active — escríbela ahora, mientras estás tranquilo. Ese texto es el que vas a leer en un mal día.

### El radar por evento

Revisa cada 2 horas durante horario de mercado, pero **filtra en dos etapas**:

**Etapa 1 — determinista, sin IA, sin costo.** ¿Cruzó algo un umbral objetivo?

| Disparador | Umbral |
|---|---|
| VIX | ±15% en un día |
| S&P 500 | ±1.8% |
| Nasdaq 100 | ±2.2% |
| Brent | ±4% |
| Oro | ±2.5% |
| Dólar (DXY) | ±1% |
| Cualquier tasa del Tesoro | ±12 puntos base |
| Titular no visto | puntaje ≥ 9 |

Si nada cruza, el proceso termina ahí y nunca se llama al modelo. La mayoría de las corridas mueren aquí.

**Excepción importante:** si el disparo vino del mercado o de las tasas, el bot recoge los titulares recientes **sin aplicar el filtro de palabras clave**. La razón: las listas de keywords solo cubren categorías previsibles. Una pandemia, una guerra, una quiebra bancaria o un desastre natural usan vocabulario que nadie escribió de antemano — y son exactamente los eventos que más mueven los mercados. Cuando el mercado ya se movió de forma inusual, ese movimiento es la evidencia de que pasó algo, y una lista de palabras no debería poder vetar la explicación.

**Etapa 2 — solo si algo cruzó.** Se consulta al modelo, que aún puede responder que fue volatilidad sin causa de fondo. El prompt le dice explícitamente que esa es la respuesta más frecuente y correcta.

**Silencio de 4 días** entre radares. Sin eso, una semana volátil te llenaría de mensajes y dejarías de leerlos.

Por qué el filtro previo importa más de lo que parece: preguntarle al modelo 40 veces por semana "¿hay algo importante?" erosiona el listón, porque cada consulta es una oportunidad nueva de responder que sí. Preguntándole solo cuando ya hay evidencia objetiva, se consulta 2-3 veces por semana y el listón se mantiene alto. De paso sale más barato.

Cuando se envía, tiene una estructura fija de seis secciones:

| Sección | Qué contiene |
|---|---|
| La noticia | Qué pasó y qué mecanismo económico hay detrás |
| El mapa | Qué activos toca, incluyendo los que no tienes |
| Por qué podría estar equivocado | El contraargumento. **Obligatorio** |
| Dónde estás parado | Tu exposición actual con pesos reales |
| De dónde saldría el dinero | Qué tendrías que vender o cuánta liquidez gastar |
| La pregunta para tus mentores | Una pregunta que te enseñe el principio general |

**Nunca cierra con una recomendación.** El mensaje termina en la pregunta, no en un ticker. Y el prompt obliga: si el modelo no encuentra un contraargumento sólido, la noticia no calificaba y no se envía nada.

El pie del mensaje dice siempre lo mismo: ninguna decisión se toma el día que llega. Consúltalo, duérmelo, y evalúalo en unos días si sigue teniendo sentido.

**Una semana sin radar es un resultado correcto y frecuente.**

El estado se guarda en `estado.json`, que el workflow hace commit de vuelta al repo — GitHub Actions no tiene memoria entre corridas. Ahí se registra qué titulares ya se evaluaron y cuándo fue el último radar.

Para forzar una revisión sin esperar: Actions → Radar por evento → Run workflow → marca `forzar`.

---

## Paso 1 — Crear el bot en Telegram

1. Abre Telegram, busca **@BotFather** (con verificación azul)
2. Envía `/newbot`
3. Nombre visible: cualquiera, ej. `Macro Brief`
4. Username: debe terminar en `bot`, ej. `tunombre_macro_bot`
5. Copia el **token** que te devuelve

⚠️ El token es la contraseña del bot. No lo compartas. Si se filtra, `/revoke` en BotFather lo regenera.

## Paso 2 — Tu chat ID

1. Busca **@userinfobot**
2. Mándale cualquier mensaje
3. Anota el número que te responde

## Paso 3 — Escríbele a tu bot

Búscalo por su username y mándale un "hola".

**Este paso no es opcional:** Telegram bloquea que un bot inicie conversación contigo hasta que tú le escribas primero. Si lo saltas, el bot fallará con "chat not found".

---

## Paso 4 — Probar en tu computadora

```bash
pip install -r requirements.txt

# Ver el brief en pantalla, sin enviar nada
python brief_diario.py --local
```

Si ves el brief con datos reales, la parte de mercado funciona. Ahora prueba el envío:

```bash
# Mac / Linux
export TELEGRAM_TOKEN="tu_token"
export TELEGRAM_CHAT_ID="tu_chat_id"

# Windows PowerShell
$env:TELEGRAM_TOKEN="tu_token"
$env:TELEGRAM_CHAT_ID="tu_chat_id"

python brief_diario.py
```

Debe llegarte el mensaje a Telegram. **No sigas hasta que esto funcione** — es mucho más fácil depurar aquí que dentro de GitHub Actions.

---

## Paso 5 — Subir a GitHub

1. Crea un repositorio **privado** en github.com (importante: privado, porque `cartera.json` tiene tus posiciones)
2. Sube estos archivos:

```
.github/workflows/diario.yml
.github/workflows/radar.yml
.github/workflows/semanal.yml
datos.py
noticias.py
llm.py
telegram.py
brief_diario.py
brief_semanal.py
radar.py
cartera.json
requirements.txt
```

Desde la terminal:

```bash
git init
git add .
git commit -m "Bot macro v1"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

## Paso 6 — Guardar los secretos

En tu repo: **Settings → Secrets and variables → Actions → New repository secret**

| Nombre | Valor |
|---|---|
| `TELEGRAM_TOKEN` | El token de BotFather |
| `TELEGRAM_CHAT_ID` | Tu chat ID |
| `ANTHROPIC_API_KEY` | Para las noticias explicadas y el análisis del viernes |

Sin `ANTHROPIC_API_KEY` el bot sigue funcionando: el brief diario muestra los titulares crudos sin explicación, y el viernes envía solo el resumen numérico.

Los secretos nunca aparecen en los logs ni en el código. Es la forma correcta de manejarlos.

## Paso 7 — Probar el workflow

Ve a la pestaña **Actions** → **Brief diario** → **Run workflow**.

Eso lo ejecuta de inmediato sin esperar al horario. Si llega el mensaje, ya está funcionando.

---

## Personalizar

**Cambiar la hora**

Los cron en GitHub Actions van en UTC. República Dominicana es UTC−4 todo el año (no cambia horario), así que:

| Hora RD | UTC | Cron |
|---|---|---|
| 6:00am | 10:00 | `0 10 * * 1-5` |
| 7:00am | 11:00 | `0 11 * * 1-5` |
| 8:00am | 12:00 | `0 12 * * 1-5` |

**Cambiar tu cartera** — edita `cartera.json`. El campo `contexto` es texto libre y es lo que hace que el análisis del viernes sea sobre *ti* y no genérico. Mientras más específico, mejor.

**Cambiar los conceptos educativos** — la lista `CONCEPTOS` en `brief_diario.py`. Rota automáticamente según el día del año. Agrega los términos que aprendas de tus mentores.

**Ajustar las alertas** — la sección `reglas` en `cartera.json`. Los `niveles` son tus líneas de precio; la `nota` de cada uno es lo que leerás cuando se active.

**Ajustar los umbrales del radar** — la sección `radar` en `cartera.json`. Si te llegan demasiados radares, súbelos; si sospechas que se pierden cosas, bájalos. El `silencio_dias` controla el mínimo entre mensajes.

**Ajustar qué noticias entran** — en `noticias.py` hay cuatro listas:

| Lista | Peso | Efecto |
|---|---|---|
| `MACRO_FUERTE` | 3 | Mueve todo el mercado (Fed, tasas, inflación, petróleo) |
| `MACRO_MEDIO` | 1 | Sectorial amplio, sigue siendo macro |
| `EMPRESAS` | 2 | **Solo cuenta en el brief del viernes** |
| `RUIDO` | — | Descarta (ofertas, recetas, farándula) |

Para añadir fuentes RSS, el diccionario `FEEDS`.

**Pegar tus propios titulares** — edita `titulares_manuales.txt`, un titular por línea. Útil si tienes acceso a una fuente sin RSS público (Bloomberg Terminal, un boletín por correo, notas de tus mentores). Entran con prioridad máxima sobre los automáticos.

⚠️ Bloomberg no ofrece feeds RSS públicos. Los "generadores de RSS de Bloomberg" que aparecen en buscadores son scrapers de terceros que violan sus términos de uso — no los uses.

---

## Dos advertencias sobre GitHub Actions

**1. Los cron pueden retrasarse.** En momentos de alta carga, GitHub puede ejecutar el workflow con 5–20 minutos de retraso. Para un brief macro es irrelevante.

**2. Se desactivan tras 60 días sin actividad.** Si no tocas el repo por dos meses, GitHub pausa los workflows programados y te avisa por correo. Un commit cualquiera reactiva el contador.

---

## Costo

| Pieza | Costo |
|---|---|
| Telegram | Gratis |
| yfinance | Gratis |
| Feeds RSS | Gratis |
| GitHub Actions | Gratis (~30 min/mes de los 2,000 disponibles) |
| API de Anthropic | ~$0.01 diario + radar 2-3/semana + viernes → **~$0.60/mes** |

---

## Estructura

```
datos.py           Descarga e interpretación de datos de mercado
noticias.py        Lectura y filtrado de titulares RSS
titulares_manuales.txt Titulares que pegues tú (opcional)
llm.py             Cliente compartido de la API de Anthropic
telegram.py        Envío de mensajes
brief_diario.py    Brief matutino (números + noticias + concepto)
radar.py           Radar por evento (dos etapas)
alertas.py         Alertas de umbral sobre tus posiciones (sin IA)
disparadores.py    Etapa 1: filtro determinista de umbrales
estado.py          Memoria entre corridas
estado.json            Estado persistido (lo crea el bot)
brief_semanal.py   Análisis de cartera del viernes
cartera.json           Tus posiciones y tu contexto
```

Todo el código maneja fallos sin lanzar excepciones: si un ticker no responde, se omite y el brief sale igual con el resto.

---

## Siguiente paso (v2)

Cuando lo hayas usado un mes y sepas qué te sirve y qué te sobra, las extensiones naturales son:

- **Conexión a Binance** — con clave API de **solo lectura**, nunca con permisos de trading ni retiro
- **Multiusuario** — para compartirlo con amigos; requiere servidor 24/7 (~$5/mes) y base de datos

---

_Este bot es informativo y educativo. No es asesoría financiera._
