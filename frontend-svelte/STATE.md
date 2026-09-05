# STATE — Руны (новый фронтенд)

SvelteKit-переезд текущего React-фронтенда. Бэкенд не трогаем, перетаскиваем функционал по частям.

Бизнес-логика, роли, эндпоинты и общий стейт проекта — [`../STATE.md`](../STATE.md) и [`../docs/БИЗНЕС-ЛОГИКА.md`](../docs/БИЗНЕС-ЛОГИКА.md).

## Стек
- SvelteKit 2 + Svelte 5 (Runes) + TypeScript strict, менеджер `bun`.
- Tailwind CSS v4 (`@tailwindcss/vite`).
- shadcn-svelte v1.6 — preset **`vega`** («classic shadcn/ui look», Lucide/Inter, base `neutral`).
- TanStack Table v8 — фреймворк-агностичный **`@tanstack/table-core`**.
- TanStack Query v5 (`@tanstack/svelte-query`) — кэш/дедуп; в перспективе `mutate`+`invalidateQueries` для таблицы с вводом данных.
- Тема light/dark — `mode-watcher`.

## Запуск
```powershell
cd C:\Users\ASUS\MaterialThought\MytraTS\frontend-svelte
bun install
bun run dev      # порт 5174, прокси /api → :8000
bun run check    # svelte-check (типы)
```
Браузер: http://localhost:5174. Логин — табельный номер + пароль.

## Технологические нюансы (грабли, найденные при сборке)
- **shadcn-svelte v1.6** перешёл на «пресеты» (`nova/vega/maia/lyra/mira/luma/sera/rhea`). Флаг `init --preset` принимает **не имя, а base62-код**: `vega` = `bIkeymG`, `nova` = `b0`, `rhea` = `b27GcrRo`, `mira` = `b1D0dv72`, `luma` = `b1VlIttI`. `--preset vega` (именем) падает с `not a valid preset`.
  Неинтерактивный init: `bun x shadcn-svelte@latest init --preset bIkeymG --css src/routes/layout.css --lib-alias '$lib' --components-alias '$lib/components' --utils-alias '$lib/utils' --hooks-alias '$lib/hooks' --ui-alias '$lib/components/ui' -y`.
- init **не дописывает тему CSS** (обрывается на подтверждении «перезаписать layout.css») — `src/routes/layout.css` писали вручную (`:root`/`.dark`/`@theme inline`).
- **TanStack Table**: `@tanstack/svelte-table` v8.21 — это Svelte 4 (store + `flexRender` через `svelte:component`, peerDep `^4||^3`), в Runes не тянем. Используем `@tanstack/table-core` напрямую (`createTable` + `getCoreRowModel`/`getSortedRowModel`). Тип `createTable` требует `onStateChange` и `renderFallbackValue` — передаём заглушки (`onStateChange: () => {}`, `renderFallbackValue: null`). **Без включённого pinning не звать `row.getVisibleCells()`** — внутри он читает `columnPinning.left` и падает (`Cannot read properties of undefined (reading 'left')`); если колонки не скрываются/не пинятся — бери `row.getAllCells()`.
- **TanStack Query v5** — store-based: `StoreOrVal = T | Readable<T>`, результат `Readable<QueryObserverResult>`. Для Runes: опции через `toStore(() => ({...}))`, результат через `fromStore(query)` → доступ `result.current.data` (а НЕ `.data`).
- **lucide-svelte**: иконки kebab-case из `@lucide/svelte/icons/<name>`; есть `chart-bar`, `circle-question-mark`, а `bar-chart-3`/`help-circle` — нет (проверять имя перед импортом).
- components.json: `style: "vega"`, `registry` автодеривится (`.../registry/{style}`).

## Решения по дизайну
- Стиль shadcn-svelte `vega` (современный, Lucide/Inter), base neutral. «Ищем новый стиль» — эксперименты отдельно.
- Логотип «три молнии» (Mitra) перенесён 1:1 из React (`logo.svelte`, path `M13 2L3 14h9l-1 8 10-12h-9l1-8z`).
- Шелл: сайдбар слева + верхняя панель (ФИО, тема, выход). Дропдаун-меню юзера пока не делаем — простые кнопки.
- Таблица «Обзор»: **11 колонок** (захардкожены из настроек `staff_id=660`) + **чекбокс-колонка слева** (эксперимент — «приживётся или нет»); **левый клик по строке раскрывает** оставшиеся 14 колонок (сетка «лейбл — значение»).
- Серверные сортировка/пагинация (50 строк/стр), скелетоны загрузки.

## Структура
```
src/
├── lib/
│   ├── api/          # client.ts (api<T>), main-afl.ts (типы + buildMainAflQuery)
│   ├── store/        # auth.svelte.ts (Runes-хранилище)
│   ├── components/
│   │   ├── ui/       # shadcn-svelte компоненты
│   │   └── logo.svelte
│   ├── columns.ts    # 11 видимых + 14 «на раскрытие»
│   ├── query.ts      # QueryClient
│   └── utils.ts      # cn()
└── routes/
    ├── +layout.ts / +layout.svelte   # ssr=false, QueryClientProvider, ModeWatcher
    ├── +page.svelte                  # редирект / → /main-afl
    ├── login/+page.svelte
    └── (app)/                        # защищённая зона
        ├── +layout.ts                # auth-гвард (loadAuth → redirect /login)
        ├── +layout.svelte            # сайдбар + топбар
        ├── main-afl/+page.svelte     # «Реестры → Обзор»
        └── dashboard|reports|help    # заглушки
```

## Что сделано / не сделано
- ✅ auth (логин/логаут/гвард), шелл, тема, «Обзор» (таблица: 11+чекбокс, раскрытие, sort/pagination).
- ⬜ Фильтры/поиск/статистика над таблицей; Загрузка/Список/Настройка; действия «В реестр»/«Поменять работу»; динамика колонок из `/api/user/settings`; Дашборд/Отчёты/Помощь.

## Конвенции
- Svelte 5 Runes: `$state`/`$derived`/`$effect` (не legacy-сторы).
- Runes-хранилища — файлы `.svelte.ts`.
- Компоненты shadcn — из `$lib/components/ui/*`, кастомизация через `class` + `cn()`.
- API — только через `api<T>()` (client.ts), типы в `$lib/api/*`.
