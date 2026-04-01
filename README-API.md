# Upwork Scraper REST API

REST-сервис для домена `https://api.scriptium.com`.

## Base URL

- `https://api.scriptium.com`

## Аутентификация

- Для рабочих endpoint обязателен заголовок `x-api-key`.
- Ключи задаются через env: `API_KEYS=key1,key2,key3`.

## Endpoints

- `GET /v1/health`
- `POST /v1/auth/login`
- `POST /v1/search`
- `POST /v1/collect-urls`
- `POST /v1/collect-bestmatch-urls`
- `POST /v1/parse-job-urls`
- `POST /v1/parse-bestmatch-urls`
- `POST /v1/pull-jobs`
- `POST /v1/pull-bestmatch-jobs`

## Формат ошибок

Все ошибки возвращаются в едином формате:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "search.limit must be in range 1..100.",
    "details": {}
  },
  "request_id": "9df15ac3-9f1e-46db-bc1e-44de6c9f2aab",
  "timestamp": "2026-04-01T12:00:00+00:00"
}
```

## HTTP статус-коды

- `200` успех
- `400` ошибки валидации
- `401` отсутствует/невалидный `x-api-key`, auth/cookies ошибки
- `503` upstream/captcha/proxy ошибки
- `500` системные ошибки

## Примеры curl

```bash
curl -X POST "https://api.scriptium.com/v1/search" \
  -H "Content-Type: application/json" \
  -H "x-api-key: <YOUR_KEY>" \
  -H "X-Request-ID: req-001" \
  -d '{"search":{"query":"n8n","limit":10}}'
```

```bash
curl -X POST "https://api.scriptium.com/v1/pull-jobs" \
  -H "Content-Type: application/json" \
  -H "x-api-key: <YOUR_KEY>" \
  -d '{"limit":20}'
```
