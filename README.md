# approval-service

Backend-сервис согласования контента перед публикацией.

## Стек

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- SQLite локально, PostgreSQL через `DATABASE_URL`
- pytest

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Если `DATABASE_URL` не задан, используется SQLite: `sqlite:///./approval_service.db`.

## Docker

```bash
docker compose up --build
```

Compose поднимает `app` и `postgres`. Миграции применяются при старте контейнера приложения.

## Тесты

```bash
pytest
```

## Auth-заглушка

Каждый защищенный запрос должен передавать:

- `X-User-Id`: идентификатор текущего пользователя;
- `X-User-Actions`: права через запятую.

Права:

- `approval:read` — чтение заявок;
- `approval:create` — создание заявки;
- `approval:decide` — approve/reject;
- `approval:cancel` — cancel.

Если `X-User-Id` отсутствует, сервис вернет `401`. Если не хватает права — `403`.

## Идемпотентность создания

Для `POST /api/v1/workspaces/{workspace_id}/approval-requests` можно передать
`Idempotency-Key`. Повтор запроса с тем же `workspace_id` и ключом вернет уже созданную
заявку и не создаст дубль. Без заголовка каждый запрос создает новую заявку.

## Примеры

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests \
  -H "Content-Type: application/json" \
  -H "X-User-Id: usr_1" \
  -H "X-User-Actions: approval:create" \
  -H "Idempotency-Key: create-pub-123" \
  -d '{
    "sourceType": "publication",
    "sourceId": "pub_123",
    "title": "Instagram reel draft",
    "description": "Needs final approval",
    "reviewerUserIds": ["usr_2", "usr_3"]
  }'
```

```bash
curl http://localhost:8000/api/v1/workspaces/ws_1/approval-requests \
  -H "X-User-Id: usr_1" \
  -H "X-User-Actions: approval:read"
```

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/approve \
  -H "Content-Type: application/json" \
  -H "X-User-Id: usr_2" \
  -H "X-User-Actions: approval:decide" \
  -d '{"comment": "Approved"}'
```

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/reject \
  -H "Content-Type: application/json" \
  -H "X-User-Id: usr_2" \
  -H "X-User-Actions: approval:decide" \
  -d '{"reason": "Brand tone is wrong"}'
```

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/ws_1/approval-requests/{request_id}/cancel \
  -H "Content-Type: application/json" \
  -H "X-User-Id: usr_1" \
  -H "X-User-Actions: approval:cancel" \
  -d '{"reason": "Draft was removed"}'
```

