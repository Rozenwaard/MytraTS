# STATE — MYTRA (MytraTS)

## Что это
Приложение управления реестрами заданий энергосбыта. Бэкенд — Litestar (JSON API) + SQLAlchemy 2, фронтенд — React SPA + TanStack.
Бизнес-логика и правила — `docs/БИЗНЕС-ЛОГИКА.md`.

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
├── app.py                 # точка входа: сборка Litestar-приложения из роутеров
├── deps.py                # get_current_user, require_auth (общие зависимости)
├── sql.py                 # build_in_clause (общий SQL-хелпер для IN)
├── data/
│   ├── config.py          # engine, SECRET_KEY из .env
│   └── models.py          # RawAfl, MainAfl (+errors), StoryAfl, Calendar, User (+ ROLES, FIELD_ROLES, ADMIN_ROLES)
├── services/
│   ├── uploader.py        # xlsx → raw_afl (async engine, run_sync)
│   ├── processor.py       # 30+ SQL-шагов классификации
│   ├── merger.py          # raw → main (INSERT новых + UPDATE существующих, возвращает inserted/updated/affected)
│   ├── reestr.py          # генерация xlsx реестра/отчёта, DEPT_PREFIXES, LOCALE_SUFFIXES
│   ├── report_check.py    # правила проверки «Алькор» (check_row), recompute_errors, BALANCE_ERRORS, STOP_FACTOR_*
│   └── dashboard.py       # build_scope (виды работ+территории+видимость+отделение), генераторы xlsx отчётов дашборда
├── routers/
│   ├── auth.py             # логин/логаут, смена пароля, настройки, поиск пользователей
│   ├── upload.py           # загрузка xlsx + прогресс загрузки
│   ├── main_afl.py         # таблица реестров, статистика, смена вида работ
│   ├── reestr.py           # формирование/сброс реестров, список, выгрузка
│   ├── report.py           # формирование отчётного периода + выгрузка xlsx
│   ├── story.py            # архив (перенос строк) + отклонение
│   ├── dashboard.py        # сводка ошибок и отчёты дашборда
│   └── lookups.py          # справочники (отделения, исполнители, виды работ)
├── frontend/
│   └── src/
│       ├── api/           # client.ts (fetch+cookie), main-afl.ts, dashboard.ts
│       ├── store/auth.tsx # AuthContext (user, login, logout)
│       ├── hooks/         # use-main-afl.ts, use-dashboard.ts
│       ├── routes/        # __root (navbar+тема), login, _authenticated/{main-afl, change-password, dashboard}
│       ├── components/    # data-table.tsx (клик-выбор строк), logo.tsx
│       └── lib/use-theme.ts
└── _migrate_errors.py     # миграция: ALTER main_afl ADD errors + бэкфилл
```

## Роли (5)
Хранятся в `users.role` (явное поле). `User.effective_role` = role или derived (fallback из dept+position). Константы в models.py:
- `ROLES = (администратор, специалист, менеджер, оператор, работник)`
- `FIELD_ROLES = (оператор, работник)` — видимость по locale
- `ADMIN_ROLES = (администратор, специалист)` — полные права

Матрица (страница «Реестры» `/main-afl`):
- **администратор**: вкладки Загрузка/Обзор/Настройка (без Список). Кнопка «Поменять работу» + выпадающий список видов работ (меняет task_report у ОДНОЙ выбранной строки, PATCH /api/main-afl/task-report). Видит колонку «Отделения» и скролл исполнителей.

## Что сделано (вкладка «Обзор»)
- Таблица main_afl: поиск (адрес/№/лс), сортировка (серверная), пагинация, выбор строк кликом (подсветка).
- Статистика-фильтры (4 колонки для админ/спец, 3 для менеджер/оператор):
  1. Статистика: ПСК, РЛЭ, План, Внеплан (по task_type), Выполнено, Не выполнено (включает Дубли+Ручная проверка), С реестром, Без реестра.
  2. Вид работ (по task_report, «Не выполнено» = NULL/'').
  3. Отделения (по executor_organization, прилагательное без «отделение») — только админ/спец.
  4. Исполнители (алфавит, с locale) — скролл по 12 строк для админ/спец, простой список для менеджер/оператор.
- Поиск по дате — выпадающий список доступных done_day.
- Фильтры суммируются (AND). «Сброс фильтров» очищает.
- Вкладка Загрузка: файл .xlsx + прогресс (polling /api/upload/progress/{id}), статусы loading→loaded→processing→merging→complete. Сообщение «Загружено: N | Новых: M | Обновлено: K» (update возвращён).
- Вкладка Список (менеджер/оператор): плашки реестров (номер + (П) для пустых), кнопки Печать/Пустой/Удалить из реестра, метаданные Вид работ/Заказчик. Фильтр таблицы по выбранному реестру.
- Вкладка Настройка: порядок + видимость колонок (drag&drop, autosave в users.settings).
- Тема light/dark (autumn/dracula), кнопка в навбаре.

## Дашборд (стартовая страница `/dashboard`)
После логина открывается Дашборд, вкладка «Обзор»:
- Карточки-счётчики: заданий в зоне, с ошибками, отправлено в биллинг (из числа ошибок), на исправлении (не отправлено), всего ошибок (в строках «на исправлении»).
- Сетка частоты ошибок — расклад по видам ошибок из строк «на исправлении».
- Фильтр по отделениям (выпадающий список) — только для администратора/специалиста.
- Кнопки выгрузки xlsx (4): «Отчёт об ошибках» (№ задания + ошибки) — видна всем; «Балансовая принадлежность» (№ задания + тип ПУ: группа 3 → 2 → 1), «Дата работ» (только № задания), «Отметка о проверке» (только № задания, verified='Нет') — только администратор/специалист. В имя файла добавляется дата-время.
- Зона (карточки): территории стоп-фактора (region='СПб' или municipal_district='ЛО Гатчинский муниципальный район') + зона видимости пользователя + customer='ПСК' + только 10 видов работ (task_report). Выгрузки — дополнительно только не отправленные в биллинг (sent_to_billing='Нет').

## Проверка отчёта «Алькор» (ошибки и стоп-фактор)
- `main_afl.errors` — колонка с найденными ошибками (через `; `). Пересчитывается при загрузке (`recompute_errors`) и миграцией `_migrate_errors.py`.
- Всего 25 типов ошибок = 23 стоп-фактора + 2 балансовых («Балансовая принадлежность», «Балансовая принадлежность нового ПУ»).
- Стоп-фактор (23 ошибки) блокирует присвоение номера реестра; активен для region='СПб' или municipal_district='ЛО Гатчинский муниципальный район' (кроме строк, где только балансовые ошибки). В `api_reestr` такие строки исключаются и возвращаются в `blocked`.
- 2 балансовые ошибки обрабатываются особо (не стоп-фактор).
- Виды работ для дашборда/отчётов — `DASHBOARD_WORK_TYPES` в services/dashboard.py (10 типов).

## Эндпоинты (routers/)
Auth: `/api/login`, `/api/me`, `/api/logout`, `/api/change-password`, `/api/user/settings` (GET/POST)
Данные: `/api/main-afl` (GET, параметры: page, per_page, sort, order, search, customer, task_report, task_type, executor_org, executor_filter, only_completed, only_without_reestr, reestr, done_day), `/api/main-afl/stats` (GET), `/api/users/search`
Реестры: `/api/reestr` (POST, + возвращает blocked), `/api/reestr/reset` (POST), `/api/download-reestr/{reestr_number}`, `/api/reestr-list`, `/api/task-reports`, `/api/executor-organizations`, `/api/executors`, `/api/main-afl/task-report` (PATCH)
Дашборд: `/api/dashboard/summary` (GET, ?dept=), `/api/dashboard/errors-report` (GET xlsx, ?dept=), `/api/dashboard/balance-report` (GET xlsx, ?dept=), `/api/dashboard/date-report` (GET xlsx, ?dept=), `/api/dashboard/verified-report` (GET xlsx, ?dept=)
Загрузка: `/api/upload` (POST multipart), `/api/upload/progress/{upload_id}`
Готово на бэке, нет UI: `/api/report` (POST), `/api/download-report/{period}`, `/api/story-afl` (GET), `/api/story-afl/reject` (POST)

## НЕ ДОДЕЛАНО (заглушки / TODO)
1. **Архив (Story)** — страница `/story` в навбаре ведёт на `/main-afl` (заглушка). Бэкенд-эндпоинты готовы: `/api/story-afl` (GET с фильтрами), `/api/story-afl/reject` (POST). Нужно: страница архива + таблица с фильтрами.
2. **Формирование отчёта** — `/api/report` (POST) + `/api/download-report/{period}` готовы на бэке. Нужен UI (выбор месяца/года, кнопка «Сформировать», скачивание). Логика: строки с reestr_date → report=period, «Отклонён» → report=«Отклонён», перенос в story_afl, удаление из main_afl.
3. **README.md** — пустой.
4. `.env` — не в git (в .gitignore), есть `.env.example`.

## Конвенции
- SQL: только bindparams (`:name`), без f-string-инъекций. Для IN — `build_in_clause(prefix, values)` в sql.py.
- Роли проверяются через `user.effective_role`.
- Фильтры на бэке строятся из `clauses` + `params` dict.
- Фронт: типы в `api/main-afl.ts`, запросы через `api<T>()` (client.ts, credentials:include).
- Коммиты атомарные, ветка master, пушится на GitHub.

- **специалист**: как админ, но БЕЗ кнопки/списка смены вида работ. Тоже видит Отделения + скролл исполнителей.
- **менеджер**: видимость по dept. Вкладки Загрузка/Обзор/Список/Настройка. Кнопка «В реестр». Нет колонки Отделений, нет скролла исполнителей (простой список).
- **оператор**: как менеджер, но видимость по locale.
- **работник**: пока = оператор (выделен на будущее).
