# STATE — MYTRA (MytraTS)

## Что это
Приложение управления реестрами заданий энергосбыта. Перенос со старого проекта `C:\Users\ASUS\MaterialThought\Mytra` (Litestar + Jinja2 + vanilla JS) на новый `C:\Users\ASUS\MaterialThought\MytraTS` (Litestar JSON API + React SPA + TanStack).

## Стек
- **Бэкенд**: Python 3.11, Litestar 2.24, SQLAlchemy 2 (async + aiosqlite), `uv` для зависимостей. БД — SQLite `mytra.db`.
- **Фронтенд**: Vite + React 19 + TypeScript (strict), Tailwind v4 + DaisyUI 5, TanStack Router/Query/Table. Менеджер — `bun`.
- **Git**: https://github.com/Rozenwaard/MytraTS

## Запуск (dev)
```powershell
# бэкенд (порт 8000)
cd C:\Users\ASUS\MaterialThought\MytraTS
uv run uvicorn app:app --reload --port 8000

# фронтенд (порт 5173, прокси /api → :8000)
cd C:\Users\ASUS\MaterialThought\MytraTS\frontend
bun run dev
```
Браузер: http://localhost:5173. Логин: табельный номер + пароль (первый вход — пароль = табельный номер, потом смена). Тестовый юзер staff_id=2190.

## Структура
```
MytraTS/
├── app.py                 # все эндпоинты (Litestar), ~670 строк
├── data/
│   ├── config.py          # engine, SECRET_KEY из .env
│   └── models.py          # RawAfl, MainAfl, StoryAfl, Calendar, User (+ ROLES, FIELD_ROLES, ADMIN_ROLES)
├── services/
│   ├── uploader.py        # xlsx → raw_afl (async engine, run_sync)
│   ├── processor.py       # 30+ SQL-шагов классификации (портирован как есть)
│   ├── merger.py          # raw → main (только INSERT новых, без update)
│   └── reestr.py          # генерация xlsx реестра/отчёта, DEPT_PREFIXES, LOCALE_SUFFIXES
├── frontend/
│   └── src/
│       ├── api/           # client.ts (fetch+cookie), main-afl.ts (типы + fetch)
│       ├── store/auth.tsx # AuthContext (user, login, logout)
│       ├── hooks/use-main-afl.ts # useMainAfl, useMainAflStats
│       ├── routes/        # __root (navbar+тема), login, _authenticated/main-afl (вся логика страницы Реестры)
│       ├── components/    # data-table.tsx (клик-выбор строк), logo.tsx
│       └── lib/use-theme.ts
└── _migrate_role.py       # миграция: ALTER users ADD role + бэкфилл
```

## Роли (5)
Хранятся в `users.role` (явное поле). `User.effective_role` = role или derived (fallback из dept+position). Константы в models.py:
- `ROLES = (администратор, специалист, менеджер, оператор, работник)`
- `FIELD_ROLES = (оператор, работник)` — видимость по locale
- `ADMIN_ROLES = (администратор, специалист)` — полные права

Матрица (страница «Реестры» `/main-afl`):
- **администратор**: вкладки Загрузка/Обзор/Настройка (без Список). Кнопка «Поменять работу» + выпадающий список видов работ (меняет task_report у ОДНОЙ выбранной строки, PATCH /api/main-afl/task-report). Видит колонку «Отделения» и скролл исполнителей.

## Что сделано (вкладка «Обзор» = бывшее «Добавление»)
- Таблица main_afl: поиск (адрес/№/лс), сортировка (серверная), пагинация, выбор строк кликом (подсветка).
- Статистика-фильтры (4 колонки для админ/спец, 3 для менеджер/оператор):
  1. Статистика: ПСК, РЛЭ, План, Внеплан (по task_type), Выполнено, Не выполнено (включает Дубли+Ручная проверка), С реестром, Без реестра.
  2. Вид работ (по task_report, «Не выполнено» = NULL/'').
  3. Отделения (по executor_organization, прилагательное без «отделение») — только админ/спец.
  4. Исполнители (алфавит, с locale) — скролл по 12 строк для админ/спец, простой список для менеджер/оператор.
- Поиск по дате — выпадающий список доступных done_day.
- Фильтры суммируются (AND). «Сброс фильтров» очищает.
- Вкладка Загрузка: файл .xlsx + прогресс (polling /api/upload/progress/{id}), статусы loading→loaded→processing→merging→complete. Сообщение «Загружено: N | Новых: M» (без Обновлено).
- Вкладка Список (менеджер/оператор): плашки реестров (номер + (П) для пустых), кнопки Печать/Пустой/Удалить из реестра, метаданные Вид работ/Заказчик. Фильтр таблицы по выбранному реестру.
- Вкладка Настройка: порядок + видимость колонок (drag&drop, autosave в users.settings).
- Тема light/dark (autumn/dracula), кнопка в навбаре.

## Эндпоинты (app.py)
Auth: `/api/login`, `/api/me`, `/api/logout`, `/api/change-password`, `/api/user/settings` (GET/POST)
Данные: `/api/main-afl` (GET, параметры: page, per_page, sort, order, search, customer, task_report, task_type, executor_org, executor_filter, only_completed, only_without_reestr, reestr, done_day), `/api/main-afl/stats` (GET), `/api/users/search`
Реестры: `/api/reestr` (POST), `/api/reestr/reset` (POST), `/api/download-reestr/{reestr_number}`, `/api/reestr-list`, `/api/task-reports`, `/api/executor-organizations`, `/api/executors`, `/api/main-afl/task-report` (PATCH)
Загрузка: `/api/upload` (POST multipart), `/api/upload/progress/{upload_id}`

## НЕ ДОДЕЛАНО (заглушки / не перенесено)
1. **Архив (Story)** — страница `/story` в навбаре ведёт на `/main-afl` (заглушка). Бэкенд-эндпоинты готовы: `/api/story-afl` (GET с фильтрами), `/api/story-afl/reject` (POST). Нужно: страница архива + таблица с фильтрами.
2. **Формирование отчёта** — `/api/report` (POST) + `/api/download-report/{period}` готовы на бэке. Нужен UI (выбор месяца/года, кнопка «Сформировать», скачивание). Логика: строки с reestr_date → report=period, «Отклонён» → report=«Отклонён», перенос в story_afl, удаление из main_afl.
3. **README.md** — пустой.
4. `.env` — не в git (в .gitignore), есть `.env.example`.

## Конвенции
- SQL: только bindparams (`:name`), без f-string-инъекций. Для IN — `_build_in_clause(prefix, values)` в app.py.
- Роли проверяются через `user.effective_role`.
- Фильтры на бэке строятся из `clauses` + `params` dict.
- Фронт: типы в `api/main-afl.ts`, запросы через `api<T>()` (client.ts, credentials:include).
- Коммиты атомарные (сейчас всё в master).

- **специалист**: как админ, но БЕЗ кнопки/списка смены вида работ. Тоже видит Отделения + скролл исполнителей.
- **менеджер**: видимость по dept. Вкладки Загрузка/Обзор/Список/Настройка. Кнопка «В реестр». Нет колонки Отделений, нет скролла исполнителей (простой список).
- **оператор**: как менеджер, но видимость по locale.
- **работник**: пока = оператор (выделен на будущее).
