# MYTRA (MytraTS)

Приложение управления реестрами заданий энергосбыта. Бэкенд — **Litestar** (JSON API)
+ **SQLAlchemy 2** (async + aiosqlite), фронтенд — **SvelteKit + Svelte 5 (Runes)**.

## Стек

- **Бэкенд**: Python 3.11+, Litestar, SQLAlchemy 2 (async + aiosqlite), зависимости через `uv`. БД — SQLite (`mytra.db` операционная + `story.db` архив/потребители, `tickets.db`, `sand.db`).
- **Фронтенд**: SvelteKit + Svelte 5 + Tailwind v4 + shadcn-svelte + TanStack Query/Table. Менеджер — `bun`.

## Быстрый старт (dev)

```bash
# бэкенд (порт 8000)
uv run uvicorn app:app --reload --port 8000

# фронтенд (порт 5174, прокси /api → :8000)
cd frontend-svelte
bun install
bun run dev
```

Браузер: http://localhost:5174

Вход: табельный номер + пароль (при первом входе пароль = табельный номер, затем смена).

Запуск без окон терминала (фоном) — см. раздел «Запуск (dev)» в `STATE.md`.

## Документация

| Файл | Что внутри |
|---|---|
| `STATE.md` | структура, эндпоинты, роли, фичи, конвенции, TODO — «где и как» |
| `docs/БИЗНЕС-ЛОГИКА.md` | бизнес-логика и правила обработки данных |
| `DEPLOYMENT.md` | развёртывание в локальной сети (Apache + GitHub) |
| `TODO.md` | отложенные/недоделанные задачи |

Смок-тест после коммитов/замены базы: `cd _scratch; uv run python _smoke_test.py`.

## Репозиторий

https://github.com/Rozenwaard/MytraTS
