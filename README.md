# Mi Caja: MVP (FastAPI + HTML/CSS/JS + Groq)

Agente web que convierte notas de voz y mensajes de una bodeguera en ventas, gastos y fiados, calcula su flujo de caja y estima una cuota mensual sostenible. Reto Mibanco "De la libreta a la caja".

```
Navegador (mic / texto) → Whisper (Groq) → LLM extractor (Groq, JSON) → Validador (código) → Libro de caja → Flujo y cuota (código)
                                                                           └─ si falta el monto: repregunta
```

El LLM solo interpreta el texto. Lo que se guarda y todo cálculo de plata lo hace código:
- **Validador:** un monto que no sale de lo que dijo la usuaria (o de un fiado ya registrado) se deja vacío con `requiere_confirmacion = SI`.
- **Fiados:** el libro los recuerda, así "me pagó lo del aceite" se completa con los S/ 11 anotados antes.
- **Flujo y cuota:** se calculan en `core/calc.py`.

## Instalación

```bash
cd mvp
pip install -r requirements.txt
cp .env.example .env     # en Windows PowerShell: copy .env.example .env
```

Edita `.env` y pega tu clave en `GROQ_API_KEY` (se crea en https://console.groq.com/keys). Nunca la subas a git ni la pongas en el navegador.

## Uso

| Qué | Comando |
|---|---|
| App web | `python -m uvicorn server:app --port 8000` y abre http://localhost:8000 |
| Medir exactitud con el kit (necesita clave) | `python eval.py` (`--desde E16` evalúa solo desde ese mensaje) |
| Procesar el set oculto sin la web | `python batch.py set_oculto.csv resultados_miequipo.csv` |
| Pruebas offline (sin clave) | `python tests/test_core.py` |

La app tiene dos ventanas:
1. **💬 Chat:** un celular con WhatsApp abierto. Se escribe o se graba una nota de voz con el botón del micrófono; Mi Caja responde en burbujas como una persona ("escribiendo…", doble check azul). Si falta un monto, pregunta; se le contesta y lo completa. También responde "¿cuánto puedo pagar de cuota al mes?" y "¿cuánto me queda?".
2. **📊 Dashboard:** lo que te queda en la semana, ventas, gastos, cobros y fiados; gráfico por día, gastos por concepto, la cuota con su cálculo paso a paso y el registro con buscador, filtros y botón para eliminar (con Deshacer).

El botón ⚙️ abre las **herramientas del equipo**: día de hoy, **Cargar semana de ejemplo (sin IA)**, **Borrar todo**, y **Procesar lote** para subir `set_oculto.csv` y descargar `resultados_<equipo>.csv` con las columnas exactas de la plantilla.

**Foto del bot:** pon un archivo cuadrado `assets/bot.png` (o `.jpg` / `.webp`, mínimo 256 × 256). Si no hay, se usa `assets/bot.svg`.

## Límites de Groq a tener en cuenta (plan gratis)

- `gpt-oss-120b` y `gpt-oss-20b`: unos 30 peticiones/min y 8,000 tokens/min por organización.
- `whisper-large-v3`: unos 20 peticiones/min y 7,200 s de audio por hora.
- Por eso el prompt es compacto (~12 ejemplos, ~1,300 tokens) y el lote se procesa en trozos de 10 mensajes. Si un modelo da 429, el código reintenta y usa el modelo de respaldo.
- Confirma tus límites reales en la sección de límites de https://console.groq.com.

## Antes de la demo

- **Libro vacío:** el libro se guarda en `data/ledger.json` y sobrevive a reinicios. Usa **Borrar todo y empezar de cero** antes de la prueba en vivo para no arrastrar datos de ensayos.
- **Micrófono:** el navegador solo deja grabar en `localhost` o en una página `https`. Una URL `http` en la red local no funcionará.
- **Nueva clave en caliente:** si cambias `.env`, reinicia el servidor (`uvicorn`).

## Estructura

```
server.py       servidor web (API sobre core/)
web/            interfaz: index.html, styles.css, app.js
assets/         foto del bot
eval.py         exactitud contra la clave del kit
batch.py        procesa un CSV de mensajes a CSV de entrega
core/
  llm.py        Groq: Whisper y JSON, con reintentos y modelo de respaldo
  extractor.py  prompt + ejemplos del kit + orquestación por mensaje o lote
  validator.py  anula montos no justificables, completa repreguntas
  ledger.py     libro de caja y memoria de fiados abiertos
  calc.py       flujo de caja y estimación de cuota
  export.py     CSV en el formato de la plantilla
  format.py     respuestas en lenguaje simple
  intents.py    detecta preguntas de cuota y resumen sin usar el LLM
data/           CSV del kit
tests/          pruebas offline
```
