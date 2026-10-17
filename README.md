# Caja de Doña Rosa: MVP (FastAPI + web propia, Gemini/Groq/Grok)

Agente web que convierte notas de voz y mensajes de una bodeguera en ventas, gastos y fiados, calcula su flujo de caja y estima una cuota mensual sostenible. Reto Mibanco "De la libreta a la caja".

```
Navegador (mic / texto) → Voz→texto (Gemini) → LLM extractor (Gemini, JSON) → Validador (código) → Libro de caja → Flujo y cuota (código)
                                                                           └─ si falta el monto: repregunta
```

El LLM solo interpreta el texto. Lo que se guarda y todo cálculo de plata lo hace código:
- **Validador:** un monto que no sale de lo que dijo la usuaria (o de un fiado ya registrado) se deja vacío con `requiere_confirmacion = SI`.
- **Fiados:** el libro los recuerda, así "me pagó lo del aceite" se completa con los S/ 11 anotados antes.
- **Flujo y cuota:** se calculan en `core/calc.py`.

## Instalación y uso

```bash
pip install -r requirements.txt
cp .env.example .env          # pega tu GEMINI_API_KEY (y opcionalmente GROQ_API_KEY / XAI_API_KEY)
python3 -m uvicorn server:app --port 8501    # abre http://localhost:8501
```

Basta una clave. Se usan en el orden Gemini → Groq → xAI Grok y, si un modelo se satura, se pasa al siguiente. Nunca subas `.env` a git.

La interfaz es HTML/CSS/JS propio (`web/`), responsive, sin dependencias de frontend. Cada navegador tiene su propio libro de caja. La nota de voz se puede **cancelar** (botón o Esc) antes de enviarla.

## Despliegue gratis desde GitHub

GitHub Pages solo sirve páginas estáticas y la clave de IA quedaría expuesta en el navegador, por eso el servidor corre aparte. Con el repo en GitHub:
- **Render** (gratis): *New → Blueprint* con este repo (usa `render.yaml`) y pega `GEMINI_API_KEY` en las variables de entorno. Da una URL `https`, necesaria para el micrófono.
- **Hugging Face Spaces** (gratis): Space tipo Docker con este repo (usa `Dockerfile`) y la clave en *Secrets*.

Los libros se guardan en `data/sesiones/` (temporal en el plano gratis).

| Qué | Comando |
|---|---|
| Medir exactitud con el kit | `python3 eval.py` |
| Procesar el set oculto sin la web | `python3 batch.py set_oculto.csv resultados_miequipo.csv` |
| Pruebas offline | `python3 tests/test_core.py` |

## Límites de Groq a tener en cuenta (plan gratis)

- `gpt-oss-120b` y `gpt-oss-20b`: unos 30 peticiones/min y 8,000 tokens/min por organización.
- `whisper-large-v3`: unos 20 peticiones/min y 7,200 s de audio por hora.
- Por eso el prompt es compacto (~12 ejemplos, ~1,300 tokens) y el lote se procesa en trozos de 10 mensajes. Si un modelo da 429, el código reintenta y usa el modelo de respaldo.
- Confirma tus límites reales en la sección de límites de https://console.groq.com.

## Antes de la demo

- **Libro vacío:** cada navegador guarda su libro en `data/sesiones/`. Usa **Borrar todo y empezar de cero** (Mi caja → Más opciones) antes de la prueba en vivo para no arrastrar datos de ensayos.
- **Micrófono:** el navegador solo deja grabar en `localhost` o en una página `https`. Una URL `http` en la red local no funcionará.
- **Nueva clave en caliente:** si cambias `.env`, reinicia uvicorn.

## Estructura

```
server.py       API (FastAPI) que sirve la web
web/            interfaz: index.html, app.css, app.js
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
