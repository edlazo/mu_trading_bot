# TradingView Webhook - Mu Trading Bot

Esta guía explica cómo enviar señales reales desde TradingView hacia Mu Trading Bot. El sistema solo genera alertas informativas y confirmaciones; nunca ejecuta compras automáticamente.

## 1. Correr FastAPI local

Desde la raíz del proyecto:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

La API queda disponible en:

```text
http://127.0.0.1:8000
```

Health check:

```bash
curl http://127.0.0.1:8000/
```

## 2. Exponer local con ngrok

En otra terminal:

```bash
ngrok http 8000
```

Ngrok va a mostrar una URL pública similar a:

```text
https://abc123.ngrok-free.app
```

## 3. URL para TradingView

En el campo webhook URL de TradingView usar:

```text
https://URL_NGROK/webhooks/tradingview?secret=test-secret
```

Ejemplo:

```text
https://abc123.ngrok-free.app/webhooks/tradingview?secret=test-secret
```

## 4. Secret requerido

TradingView puede enviar el secret por query param, que es la opción recomendada para alertas reales:

```text
https://URL_NGROK/webhooks/tradingview?secret=test-secret
```

El backend también mantiene compatibilidad con este header para Postman/curl:

```text
X-Webhook-Secret: change-me
```

El valor debe coincidir con la variable de entorno:

```env
TRADINGVIEW_WEBHOOK_SECRET=change-me
```

## 5. Body JSON esperado

TradingView debe enviar JSON válido. Ejemplo mínimo útil:

```json
{
  "ticker": "AAPL",
  "market": "USA",
  "timeframe": "1D",
  "source": "mixed",
  "reason": "Precio recupera zona técnica y los indicadores acompañan parcialmente.",
  "close": 195.2,
  "sma30": 192.8,
  "asl21": 191.4,
  "ema150": 181.6,
  "ema200": 178.9,
  "rsi": 61.5,
  "rsi_ma": 55.2,
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
  "support": 188.4,
  "resistance": 198.5,
  "target": 205.0,
  "stop_loss": 188.4,
  "weekly_context": "alcista",
  "monthly_context": "sano",
  "fundamental_context": "neutral",
  "notes": "Alerta preliminar para seguimiento."
}
```

Campos importantes:

- `ticker`: requerido, no vacío.
- `close`: requerido, mayor a `0`.
- `source`: debe ser `chart`, `indicators`, `fundamentals` o `mixed`.
- `target`, `stop_loss`, `support`, `resistance`, medias e indicadores son opcionales, pero pueden afectar score, riesgo y relación riesgo/beneficio.

## 6. Probar con curl

Con query param:

```bash
curl -X POST "http://127.0.0.1:8000/webhooks/tradingview?secret=change-me" \
  -H "Content-Type: application/json" \
  --data @examples/tradingview_alert_payload.json
```

Con header:

```bash
curl -X POST http://127.0.0.1:8000/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: change-me" \
  --data @examples/tradingview_alert_payload.json
```

## 7. Probar Discord

Para verificar `DISCORD_WEBHOOK_URL` sin crear alertas ni tocar la base:

```bash
curl -X POST http://127.0.0.1:8000/webhooks/test-discord
```

Respuesta esperada:

```json
{
  "status": "discord_test_sent"
}
```