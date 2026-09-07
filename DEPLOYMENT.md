# Развёртывание MytraTS в локальной сети (Apache2 + GitHub)

## Итоговая схема
```
Браузер ──:80──▶ Apache2
                   ├── /        → статика фронтенда (frontend/dist)
                   └── /api/*   → uvicorn 127.0.0.1:8000 (бэкенд Litestar)
```
- Бэкенд слушает только `127.0.0.1:8000`; наружу смотрит только Apache.
- Фронтенд ходит в API по относительному пути `/api` → один origin, без CORS/cookie-проблем.

## Требования
- Debian/Ubuntu + Apache2, доступ в интернет.
- **Системный Python 3.11** — обязателен (проект закреплён на `>=3.11`).
  В Ubuntu 24.04 «из коробки» только 3.12, поэтому 3.11 ставится из PPA deadsnakes (см. §1).
  Нельзя позволять `uv` скачивать собственный Python в `/home/<юзер>`: сервис `mytra`
  туда доступа не имеет и падает с `status=203/EXEC`.
- `bun` — сборка фронтенда.
- СУБД не нужна: SQLite-файл `mytra.db` (передаётся отдельно, в git его нет).
- pandas/numpy удалены — привязки к CPU x86-64-v2 больше нет.

## 1. Подготовка сервера
```bash
sudo apt update && sudo apt install -y git apache2 sqlite3
# Системный Python 3.11 (в Ubuntu 24.04 по умолчанию только 3.12)
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt update
sudo apt install -y python3.11 python3.11-venv
curl -LsSf https://astral.sh/uv/install.sh | sh      # uv
curl -fsSL https://bun.sh/install | bash             # bun
# после установки перезайти в сессию (или source ~/.local/bin/env / ~/.bashrc)
```

## 2. Клонирование из GitHub
```bash
sudo mkdir -p /opt/mytra && sudo chown "$USER:" /opt/mytra
git clone https://github.com/Rozenwaard/MytraTS.git /opt/mytra
```

## 3. Бэкенд
```bash
cd /opt/mytra
# only-system — использовать системный Python 3.11, а не скачивать свой в /home/<юзер>
uv sync --python-preference only-system            # создаст .venv (в т.ч. uvicorn)
cp .env.example .env
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env
```
База: положите полученный от разработчика файл `mytra.db` в `/opt/mytra/mytra.db`.
(Если база старой версии без колонки `errors` — выполните `uv run python _migrate_errors.py`.)

Первый вход: логин = табельный номер, пароль = табельный номер (система попросит сменить).

## 4. Фронтенд (сборка)
```bash
cd /opt/mytra/frontend
bun install
bun run build     # → frontend/dist
```

## 4а. Фронтенд Svelte («Руны», `frontend-svelte/`)

Новый фронтенд на SvelteKit 2 + Svelte 5 (Runes), менеджер `bun`, порт **5174** (dev),
прокси `/api` → `:8000`. Живёт рядом со старым React-фронтом (`frontend/`, порт 5173).

### Ключевые решения (зафиксированы, не менять без причины)

- **Tailwind CSS v4 — только v4, НЕ v3.** Стили подключаются плагином `@tailwindcss/vite`
  (`vite.config.ts` → `tailwindcss()`), тема описана в `src/routes/layout.css` через
  `@import 'tailwindcss'` + `@theme inline` + `@custom-variant dark`. Отдельных
  `tailwind.config.js` / `postcss.config.js` **нет и не должно быть**. Даунгрейд до v3 (или
  классические `@tailwind base/components/utilities`) ломает генерацию стилей — страница
  рендерится «голой», без CSS.
- **Node `^20.19.0 || >=22.12.0`** — требование Vite 8. Node 18 не подходит.
- **Сборка — только свежим `bun`** (не yarn/npm). Свежий bun несёт собственный lightningcss,
  который понимает синтаксис Tailwind v4 (`--spacing()` и т.д.). На старом bun/Node сборка
  падает с `lightningcss … --spacing()` / «unsupported syntax».
- **Прод-режим — это Node-сервер SvelteKit, а не статика.** `@sveltejs/adapter-auto` в
  Node-окружении резолвится в `adapter-node`: сборка даёт `build/index.js`, который сам
  отдаёт статику и роутинг (SSR). Apache должен проксировать `/` на этот сервер, а НЕ
  указывать `DocumentRoot /opt/mytra/frontend/dist` (это старый React-фронт).

### Требования

- Node ≥ 20.19 (проверка `node -v`).
- Свежий `bun` (проверка `bun -v`), ставится как в §1.
- В `package.json` прописан `engines: { "node": ">=20.19.0" }`, а в `.npmrc` —
  `engine-strict=true`: на старом Node установка/сборка упадёт сразу с понятной ошибкой,
  а не с загадочным `--spacing()`.

### Запуск (dev)

```bash
# 1. бэкенд (порт 8000) — отдельный терминал
cd /opt/mytra && uv run uvicorn app:app --reload --port 8000

# 2. фронт Svelte (порт 5174) — другой терминал
cd /opt/mytra/frontend-svelte && bun install && bun run dev
```
Открыть `http://localhost:5174`. Логин — табельный номер + пароль (первый вход — сменить пароль).

### Сборка (prod)

```bash
cd /opt/mytra/frontend-svelte && bun install && bun run build
# → build/ с build/index.js (Node-сервер SvelteKit)
```

Запуск prod-сервера (порт по умолчанию 3000, переопределяется `PORT`):

```bash
cd /opt/mytra/frontend-svelte && PORT=3000 bun build/index.js
# или: node build/index.js
```

В Apache вместо `DocumentRoot` на `frontend/dist` проксируйте `/` на `127.0.0.1:3000`,
а `/api` — на `127.0.0.1:8000` (готовый конфиг — §6, подраздел «Svelte-фронт»).


## 5. systemd-сервис бэкенда
Файл `/etc/systemd/system/mytra.service`:
```ini
[Unit]
Description=Mytra backend (uvicorn)
After=network.target

[Service]
Type=simple
User=mytra
Group=mytra
WorkingDirectory=/opt/mytra
ExecStart=/opt/mytra/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
sudo useradd --system --home /opt/mytra --shell /usr/sbin/nologin mytra
sudo chown -R mytra:mytra /opt/mytra
sudo chmod -R o+rX /opt/mytra      # Apache должен читать статику фронтенда
sudo systemctl daemon-reload
sudo systemctl enable --now mytra
sudo systemctl status mytra        # active (running)
```

## 6. Apache2
```bash
sudo a2enmod proxy proxy_http
```
Файл `/etc/apache2/sites-available/mytra.conf` (боевой конфиг, работает в локалке):
```apache
<VirtualHost *:80>
    # Раскомментировать, если доступ по DNS-имени; для доступа по IP — оставить закрытым
    # ServerName mytra.company.ru

    DocumentRoot /opt/mytra/frontend/dist

    <Directory /opt/mytra/frontend/dist>
        Options -Indexes +FollowSymLinks
        AllowOverride None
        Require all granted
        FallbackResource /index.html
    </Directory>

    ProxyPreserveHost On
    ProxyRequests Off

    # ВАЖНО: /api обязателен и в цели — см. пояснение ниже
    ProxyPass /api http://127.0.0.1:8000/api
    ProxyPassReverse /api http://127.0.0.1:8000/api
</VirtualHost>
```
```bash
sudo a2dissite 000-default
sudo a2ensite mytra
sudo apache2ctl configtest
sudo systemctl reload apache2
```

### Почему `/api` обязателен в целевом URL
`ProxyPass` не «добавляет» префикс, а **заменяет** его: совпавшая часть пути отбрасывается
и подставляется путь из второго аргумента.
- ❌ `ProxyPass /api http://127.0.0.1:8000` — путь у цели пустой, поэтому `/api/login`
  уедет на бэкенд как `/login`. **Все 9 роутеров приложения зарегистрированы как
  `Router("/api", ...)`**, то есть каждый эндпоинт живёт под `/api/...` → получите 404 на всё API.
- ✅ `ProxyPass /api http://127.0.0.1:8000/api` — `/api/login` → `/api/login`. Верно.

Не путать с dev-режимом: Vite (`frontend/vite.config.ts`, `proxy: { "/api": "http://localhost:8000" }`)
префикс **сохраняет**, поэтому там короткая запись работает. У Apache семантика другая.

### Остальные директивы
- `ProxyPreserveHost On` — передаёт бэкенду исходный `Host` вместо `127.0.0.1:8000`.
- `ProxyRequests Off` — это и так дефолт, но пишем явно: страхует от превращения сервера
  в открытый forward-прокси.
- `LimitRequestBody` не задаём: дефолт Apache — `0` (без лимита), а реальный потолок задаёт
  само приложение — `request_max_body_size=35 МБ` в `app.py`. Если понадобятся xlsx крупнее,
  поднимать нужно **и** там, и (при необходимости) в Apache.
- `ProxyTimeout` тоже не задаём. Он наследует `Timeout` (в Debian/Ubuntu `apache2.conf` — 300 с),
  и этого хватает: `POST /api/upload` только принимает файл и сразу отдаёт `upload_id`, а разбор
  и слияние идут фоновой задачей (`asyncio.create_task`), прогресс фронт опрашивает через
  `GET /api/upload/progress/{id}`. То есть долгая обработка через прокси не висит.
- CORS в прод-режиме не участвует: фронт и API на одном origin. `CORSConfig` в `app.py`
  прописан только под dev-origin `http://localhost:5173`.

### Svelte-фронт («Руны»): Node-сервер вместо статики

Если наружу смотрим новый Svelte-фронт (а не React), конфиг меняется: статику больше не
отдаём через `DocumentRoot`, а проксируем `/` на Node-сервер SvelteKit (`build/index.js`,
порт 3000). Файл `/etc/apache2/sites-available/mytra.conf`:

```apache
<VirtualHost *:80>
    # ServerName mytra.company.ru

    ProxyPreserveHost On
    ProxyRequests Off

    # Svelte-приложение (adapter-node) на 127.0.0.1:3000.
    # Слеш на конце цели обязателен — иначе Apache срежет ведущий "/" пути.
    ProxyPass / http://127.0.0.1:3000/
    ProxyPassReverse / http://127.0.0.1:3000/

    # API — на бэкенд (правило длиннее "/", поэтому обрабатывается первым).
    ProxyPass /api http://127.0.0.1:8000/api
    ProxyPassReverse /api http://127.0.0.1:8000/api
</VirtualHost>
```

```bash
sudo apache2ctl configtest && sudo systemctl reload apache2
```

Сам Node-сервер запускается отдельно (dev — `bun run dev`, prod — `bun build/index.js`).
Для прода удобно оформить его как systemd-сервис по аналогии с `mytra.service` (§5):
`WorkingDirectory=/opt/mytra/frontend-svelte`, `ExecStart=$(which bun) build/index.js`,
`Environment=PORT=3000`.

## 7. Файрвол и проверка
```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw enable
curl http://127.0.0.1:8000/api/login   # JSON (бэкенд жив)
curl http://localhost/api/login        # JSON (прокси работает)
```
Открыть в браузере `http://<ip-сервера>/`.

## Особенности окружения (прод-сервер)

### pandas / numpy удалены
Раньше из-за pandas/numpy держали пин `numpy<2` и потолок `requires-python <3.13`
(краш на импорте `RuntimeError: NumPy was built with baseline optimizations: (X86_V2)`
на старом гипервизоре). Сейчас pandas/numpy в зависимостях нет — см. `STATE.md`.

### Чего НЕ делать
- **Не «лечить» зависимости руками на сервере.** `uv sync` приводит `.venv` в точное
  соответствие с `uv.lock`, поэтому любой ручной `uv pip install ...` будет снесён
  при первом же обновлении.
- **Не использовать `uv add --frozen`** для обхода ошибки резолвинга: `--frozen` пропускает
  пересчёт lock-файла, и `pyproject.toml` с `uv.lock` расходятся.
- В venv, созданном `uv`, **нет `pip`** (`.venv/bin/pip: command not found` — это норма).
  Если всё же нужна разовая установка: `uv pip install <pkg> --python /opt/mytra/.venv/bin/python`.

### Если добавляете новые бинарные зависимости
`pydantic-core`, `cryptography`, `python-calamine`, `uvloop`, `httptools` собраны под базовый
x86-64 и работают. Научные пакеты (`pyarrow`, `scipy`, `numpy`) собираются под x86-64-v2
и могут упасть на старом гипервизоре — проверяйте перед добавлением.

## Обновление
```bash
cd /opt/mytra && git pull && uv sync --python-preference only-system
cd frontend && bun install && bun run build && cd ..
sudo systemctl restart mytra
```
Svelte-фронт («Руны», `frontend-svelte/`):
```bash
cd /opt/mytra/frontend-svelte && git pull && bun install && bun run build
# затем перезапустить Node-сервер SvelteKit (systemd-сервис или вручную)
```

## Бэкап БД
```bash
sudo systemctl stop mytra
sudo -u mytra cp /opt/mytra/mytra.db /backup/mytra-$(date +%F).db
sudo systemctl start mytra
```

## Частые проблемы
- **404 на `/dashboard`, `/main-afl`** — не включён `FallbackResource /index.html` или не перезагружен Apache.
- **`/api` 404 / Connection refused** — не запущен uvicorn, не включены модули `proxy proxy_http`,
  либо в `ProxyPass`/`ProxyPassReverse` пропущен `/api` в целевом URL (тогда Apache срезает
  префикс и бэкенд не находит маршрут — см. §6).
- **413 / «файл слишком большой» при загрузке xlsx** — упёрлись в `request_max_body_size=35 МБ`
  в `app.py`, а не в Apache.
- **«no such table: users»** — не положен `mytra.db` или он пустой.
- **Логин не проходит** — при первом входе пароль = табельному номеру; пользователь должен быть в базе.
- **Права на БД** — `mytra.db` должен принадлежать пользователю `mytra`.
- **`status=203/EXEC`** — `uv` создал venv на своём Python внутри `/home/<юзер>`, куда сервису
  `mytra` нет доступа. Лечится системным Python 3.11 (§1) и `uv sync --python-preference only-system`.
- **Сборка Svelte падает: `lightningcss` / `--spacing()` / «unsupported syntax»** — старый
  Node или старый bun. Проверь `node -v` (нужно ≥20.19) и обнови `bun` (§1). Не «лечи»
  даунгрейдом до Tailwind v3 — проект заточен под v4, после v3 стили не генерируются и
  страница рендерится без CSS.
