# Upwork Scraper CLI

Отдельный CLI-сервис для запуска scraping-пайплайнов и работы с БД.

## Запуск

- Новый формат:
  - `python -m src.cli.app auth.login --json-input '{"credentials":{"username":"...","password":"..."}}'`
  - `python -m src.cli.app search.run --json-input '{"search":{"query":"n8n","limit":10}}'`
- Legacy-совместимость:
  - `python main.py --command search --jsonInput '{"search":{"query":"n8n","limit":10}}'`
  - `python -m src.cli.app --command search --jsonInput '{"search":{"query":"n8n","limit":10}}'`

## Команды CLI (новый формат)

- `auth.login` — логин в Upwork, валидация сессии, сохранение cookies.
- `search.run` — поиск вакансий по `search.query`.
- `search.bestmatch` — best-match поиск без `search.query`.
- `urls.collect` — сбор URL в `job_urls`.
- `urls.collect --bestmatch` — сбор URL в `job_urls_bestmatch`.
- `jobs.parse` — парсинг `job_urls` -> `jobs`.
- `jobs.parse --bestmatch` — парсинг `job_urls_bestmatch` -> `job_bestmach`.
- `jobs.pull` — выдача unchecked из `jobs`.
- `jobs.pull --bestmatch` — выдача unchecked из `job_bestmach`.

## Форматы входа

- `--json-input '<json-string>'`
- `--input-file /absolute/path/input.json`
- env `jsonInput` (совместимый формат)

## Выход и коды завершения

- Успех: JSON в stdout + exit code `0`.
- Ошибка домена: JSON с `error.code` + exit code `3`.
- Непредвиденная ошибка: JSON с `UNEXPECTED_ERROR` + exit code `1`.
- Некорректный вызов (help): exit code `2`.

## Примеры

```bash
python -m src.cli.app search.run --json-input '{"credentials":{"username":"user@example.com"},"search":{"query":"python","limit":20}}'
```

```bash
python -m src.cli.app jobs.pull --json-input '{"limit":50}'
```
