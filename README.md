# Mu Trading Bot

Mu Trading Bot es un asistente de analisis de oportunidades de trading. Escanea activos, detecta posibles setups, envia alertas informativas a Discord y confirma decisiones pre-cierre. No ejecuta compras ni ventas automaticamente.

## Advertencia importante

- Este proyecto es educativo y experimental.
- No es asesoramiento financiero.
- No ejecuta compras ni ventas automaticamente.
- Las decisiones finales deben ser revisadas manualmente por el usuario.
- Antes de operar, revisar grafico, precio real, liquidez, CEDEAR si aplica, comisiones y riesgo propio.

## Features actuales

- Backend FastAPI con documentacion interactiva en `/docs`.
- Scanner automatico con `yfinance`.
- Indicadores tecnicos: SMA30, ASL21, EMA150, EMA200, RSI y PPO.
- Watchlist persistente en base de datos.
- Alertas iniciales a Discord.
- Webhook compatible con TradingView y Postman.
- Filtro de mercado abierto/cerrado para evitar alertas operativas fuera de horario.
- Estado `WATCHLIST` para oportunidades detectadas fuera de horario.
- Archivado de alertas.
- Confirmacion pre-cierre manual y automatizable.
- Scheduler opcional para scanner y confirmacion pre-cierre.
- Tests automatizados con pytest.

## Stack tecnico

- Python 3.11+
- FastAPI
- Pydantic / Pydantic Settings
- SQLAlchemy
- SQLite para desarrollo
- yfinance
- pandas
- numpy
- HTTPX
- pytest
- Discord Webhooks

## Estructura del proyecto

```text
app/
  core/            Logica de scoring, riesgo, decision, indicadores y horarios de mercado
  database/        Engine, sesiones y base SQLAlchemy
  integrations/    Discord y validacion TradingView
  models/          Modelos SQLAlchemy
  schemas/         Schemas Pydantic
  services/        Servicios de alertas, scanner, scheduler, watchlist y confirmaciones
  main.py          App FastAPI y endpoints
docs/              Documentacion adicional
examples/          Payloads de ejemplo
tests/             Suite de tests
.env.example       Variables de entorno de ejemplo
requirements.txt   Dependencias Python
Taskfile.yml       Comandos repetitivos
```

## Requisitos

- Python 3.11+.
- Entorno virtual Python.
- Cuenta o servidor de Discord.
- Webhook de Discord.
- Opcional: ngrok para exponer FastAPI localmente.
- Opcional: TradingView para enviar webhooks reales.
- Opcional: Taskfile para usar comandos `task`.

## Instalacion local

Desde WSL/Linux:

```bash
cd /home/elias/Projects/mu_trading_bot

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

Si usas Taskfile:

```bash
task setup
```

## Variables de entorno

Crear un archivo `.env` en la raiz del proyecto. Puedes partir desde `.env.example`:

```bash
cp .env.example .env
```

Ejemplo:

```env
APP_NAME=Mu Trading Bot
ENVIRONMENT=local
DATABASE_URL=sqlite:///./mu_trading_bot.db
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TRADINGVIEW_WEBHOOK_SECRET=test-secret
ENABLE_SCHEDULER=false
SCHEDULER_INTERVAL_SECONDS=300
```

Notas:

- `DISCORD_WEBHOOK_URL` es privado. No debe subirse a Git.
- `TRADINGVIEW_WEBHOOK_SECRET` valida requests externas al webhook.
- Para TradingView puede usarse query param: `?secret=test-secret`.
- `ENABLE_SCHEDULER` controla si el scheduler arranca junto con FastAPI.
- Si cambias `.env`, reinicia `uvicorn`.

## Como correr el proyecto

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Luego abrir:

```text
http://127.0.0.1:8000/docs
```

Con Taskfile:

```bash
task dev
```

## Como correr tests

```bash
source .venv/bin/activate
pytest
```

Con Taskfile:

```bash
task test
```

## Flujo principal del bot

1. Se carga una watchlist persistente.
2. El scanner analiza tickers usando datos diarios de yfinance.
3. Si el mercado esta abierto, puede crear alertas `EN_OBSERVACION`.
4. Si el mercado esta cerrado, el scanner operativo bloquea alertas; con `allow_after_hours=true` puede crear `WATCHLIST`.
5. Las alertas se envian a Discord.
6. Cerca del cierre, el bot confirma alertas activas:
   - `COMPRAMOS`
   - `NO_COMPRAMOS`
7. La alerta deja de estar activa y queda guardada para historial.
8. Las alertas de prueba o watchlist pueden archivarse sin borrado fisico.

## Endpoints principales

### Health

- `GET /`

### Discord

- `POST /webhooks/test-discord`

### TradingView / Postman

- `POST /webhooks/tradingview`
- `POST /webhooks/tradingview?secret=test-secret`

El endpoint acepta el secreto por header:

```text
X-Webhook-Secret: test-secret
```

O por query param, util para TradingView:

```text
/webhooks/tradingview?secret=test-secret
```

### Watchlist

- `GET /watchlist`
- `POST /watchlist`
- `PATCH /watchlist/{ticker}`
- `DELETE /watchlist/{ticker}`
- `POST /watchlist/seed-defaults`

### Scanner

- `POST /scanner/run`
- `POST /scanner/run?allow_after_hours=true`
- `POST /scanner/run?force_alert=true`
- `POST /scanner/run-watchlist`
- `POST /scanner/run-watchlist?allow_after_hours=true`

### Alerts

- `GET /alerts/active`
- `GET /alerts/watchlist`
- `GET /alerts/archived`
- `PATCH /alerts/{alert_id}/archive`
- `POST /alerts/archive-watchlist`
- `POST /alerts/archive-test-alerts`

### Confirmations

- `POST /confirmations/pre-close`
- `POST /confirmations/pre-close/{alert_id}`

### Scheduler

- `GET /scheduler/status`
- `POST /scheduler/run-once`

## Ejemplos de uso con Postman

### A. Cargar watchlist inicial

```text
POST http://127.0.0.1:8000/watchlist/seed-defaults
```

### B. Ver watchlist

```text
GET http://127.0.0.1:8000/watchlist
```

### C. Ejecutar scanner manual

```text
POST http://127.0.0.1:8000/scanner/run
Content-Type: application/json
```

Body:

```json
{
  "tickers": ["AAPL", "MSFT", "NVDA"]
}
```

### D. Ejecutar scanner de watchlist

```text
POST http://127.0.0.1:8000/scanner/run-watchlist
```

### E. Ejecutar scanner fuera de horario como watchlist

```text
POST http://127.0.0.1:8000/scanner/run-watchlist?allow_after_hours=true
```

### F. Confirmacion pre-cierre manual

```text
POST http://127.0.0.1:8000/confirmations/pre-close
```

## Ejemplo de webhook manual

Endpoint:

```text
POST http://127.0.0.1:8000/webhooks/tradingview
```

Headers:

```text
Content-Type: application/json
X-Webhook-Secret: test-secret
```

Body:

```json
{
  "ticker": "TEST_CONFIRM",
  "market": "USA",
  "timeframe": "1D",
  "source": "mixed",
  "reason": "Alerta de prueba para validar confirmacion pre-cierre.",
  "close": 100.0,
  "sma30": 99.0,
  "asl21": 98.0,
  "ema150": 90.0,
  "ema200": 85.0,
  "rsi": 60.0,
  "rsi_ma": 55.0,
  "koncorde_azul": 8.2,
  "koncorde_azul_prev": 6.5,
  "koncorde_marron": 14.4,
  "koncorde_marron_prev": 12.8,
  "koncorde_media": 10.1,
  "ppo": 1.25,
  "ppo_signal": 1.1,
  "ppo_hist": 0.15,
  "ppo_hist_prev": 0.07,
  "volume_ok": true,
  "support": 95.0,
  "resistance": 101.0,
  "target": 115.0,
  "stop_loss": 95.0,
  "weekly_context": "alcista",
  "monthly_context": "sano",
  "fundamental_context": "neutral",
  "notes": "Prueba controlada."
}
```

## Discord

El bot envia:

- Alertas iniciales cuando detecta oportunidades.
- Watchlist fuera de horario cuando se permite `allow_after_hours=true`.
- Confirmaciones pre-cierre con decision final.

La integracion usa `allowed_mentions` vacio para evitar pings no deseados. Si `DISCORD_WEBHOOK_URL` no esta configurado, el proyecto imprime el mensaje en consola para desarrollo local.

## Scheduler

Por defecto esta desactivado:

```env
ENABLE_SCHEDULER=false
SCHEDULER_INTERVAL_SECONDS=300
```

Para activarlo:

```env
ENABLE_SCHEDULER=true
SCHEDULER_INTERVAL_SECONDS=300
```

Luego reiniciar FastAPI.

Cuando esta activo:

- Escanea la watchlist durante mercado abierto.
- No crea alertas operativas si el mercado esta cerrado.
- Ejecuta confirmacion pre-cierre alrededor de las 15:30 America/New_York.
- Evita confirmar dos veces el mismo dia.

Se puede revisar el estado con:

```text
GET /scheduler/status
```

Y ejecutar una corrida manual del scanner con:

```text
POST /scheduler/run-once
```

## Estados de alertas

- `EN_OBSERVACION`: alerta activa pendiente de confirmacion.
- `WATCHLIST`: oportunidad detectada fuera de horario. No es alerta operativa.
- `COMPRAMOS`: alerta confirmada como compra por la logica pre-cierre.
- `NO_COMPRAMOS`: alerta rechazada por la logica pre-cierre.
- `ARCHIVED`: alerta archivada manualmente o por limpieza.

Tambien existen estados historicos/internos del modelo, como `SIN_OPORTUNIDAD`, `ALERTA`, `CONFIRMADA`, `INVALIDADA` y `POSIBLE_SENUELO`.

## Troubleshooting

### Discord no recibe mensajes

- Revisar `DISCORD_WEBHOOK_URL`.
- Confirmar que el webhook de Discord no haya sido eliminado.
- Revisar la consola de FastAPI.
- Probar `POST /webhooks/test-discord`.

### 401 Invalid webhook secret

- Revisar `X-Webhook-Secret`.
- Revisar `TRADINGVIEW_WEBHOOK_SECRET` en `.env`.
- Si se usa TradingView, usar `?secret=test-secret` en la URL.

### Scheduler no corre

- Revisar `ENABLE_SCHEDULER=true`.
- Reiniciar `uvicorn` despues de cambiar `.env`.
- Revisar `GET /scheduler/status`.

### `/scanner/run-watchlist` devuelve `scanned=0`

- Revisar `GET /watchlist`.
- Ejecutar `POST /watchlist/seed-defaults`.
- Confirmar que los tickers esten `enabled=true`.

### Not Found en endpoints nuevos

- Reiniciar `uvicorn`.
- Revisar `http://127.0.0.1:8000/docs`.
- Confirmar que se esta apuntando al servidor correcto.

### Mercado cerrado

- El scanner operativo no crea alertas fuera de horario.
- Usar `allow_after_hours=true` solo para crear `WATCHLIST`.

## Roadmap

- Historial de decisiones mas completo.
- Backtesting.
- Mejoras en analisis fundamental.
- Mejor calculo de soportes y resistencias.
- Integracion futura con Telegram.
- Panel web.
- Mejor manejo de feriados USA y half-days.
- Metricas de performance del bot.

## Seguridad

- No subir `.env` a Git.
- No publicar webhooks, tokens ni secretos.
- Rotar el webhook de Discord si fue compartido por error.
- Cambiar `TRADINGVIEW_WEBHOOK_SECRET` en entornos reales.
