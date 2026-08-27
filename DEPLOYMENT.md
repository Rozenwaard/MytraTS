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
- **Системный Python 3.11** — обязателен (проект закреплён на `>=3.11,<3.13`).
  В Ubuntu 24.04 «из коробки» только 3.12, поэтому 3.11 ставится из PPA deadsnakes (см. §1).
  Нельзя позволять `uv` скачивать собственный Python в `/home/<юзер>`: сервис `mytra`
  туда доступа не имеет и падает с `status=203/EXEC`.
- `bun` — сборка фронтенда.
- СУБД не нужна: SQLite-файл `mytra.db` (передаётся отдельно, в git его нет).
- **Проверить CPU сервера** — на гипервизоре без x86-64-v2 критично, чтобы NumPy остался
  версии 1.26.x. Подробно — раздел «Особенности окружения (прод-сервер)».

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

## 7. Файрвол и проверка
```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw enable
curl http://127.0.0.1:8000/api/login   # JSON (бэкенд жив)
curl http://localhost/api/login        # JSON (прокси работает)
```
Открыть в браузере `http://<ip-сервера>/`.

## Особенности окружения (прод-сервер)

### NumPy: baseline x86-64-v2 и старый гипервизор
Прод-сервер работает на CPU/гипервизоре без набора инструкций **x86-64-v2**
(SSSE3 / SSE4.1 / SSE4.2 / POPCNT). Начиная с версии 2.0 колёса NumPy собираются
именно с этим baseline, поэтому на импорте бэкенд падает:
```
RuntimeError: NumPy was built with baseline optimizations:
(X86_V2) but your machine doesn't support: (X86_V2).
```
- Baseline **нельзя отключить в рантайме**: `NPY_DISABLE_CPU_FEATURES` управляет только
  опциональными (dispatchable) наборами вроде AVX-512, а baseline вкомпилен в колесо.
- Поэтому в `pyproject.toml` жёстко зафиксировано **`numpy>=1.26.0,<2`** (у 1.26.x baseline — SSE3).
  **Не поднимать до 2.x**, пока сервер не переедет на CPU с поддержкой x86-64-v2.
- Из-за пина NumPy обязателен потолок `requires-python = ">=3.11,<3.13"`: без него `uv`
  резолвит зависимости и для Python ≥3.14, где pandas требует `numpy>=2.3.3`, и выдаёт
  `No solution found ... your project's requirements are unsatisfiable`.
  Плюс колёса numpy 1.26.4 существуют только для cp39–cp312.

### Чего НЕ делать
- **Не «лечить» это руками на сервере.** `uv sync` приводит `.venv` в точное соответствие
  с `uv.lock`, поэтому любой ручной `uv pip install "numpy<2"` будет снесён при первом же
  обновлении. Пин обязан жить в `pyproject.toml` + закоммиченном `uv.lock`.
- **Не использовать `uv add --frozen`** для обхода ошибки резолвинга: `--frozen` пропускает
  пересчёт lock-файла, и `pyproject.toml` с `uv.lock` расходятся.
- В venv, созданном `uv`, **нет `pip`** (`.venv/bin/pip: command not found` — это норма).
  Если всё же нужна разовая установка: `uv pip install <pkg> --python /opt/mytra/.venv/bin/python`.

### Если добавляете новые бинарные зависимости
`pydantic-core`, `cryptography`, `python-calamine`, `uvloop`, `httptools` собраны под базовый
x86-64 и работают. Но научные пакеты (`pyarrow`, `scipy`, новый `numpy`) собираются под
x86-64-v2 и упадут так же — проверяйте перед добавлением.

## Обновление
```bash
cd /opt/mytra && git pull && uv sync --python-preference only-system
cd frontend && bun install && bun run build && cd ..
sudo systemctl restart mytra
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
- **`RuntimeError: NumPy was built with baseline optimizations: (X86_V2)`** — на сервер попал
  NumPy 2.x. См. «Особенности окружения (прод-сервер)»: должен быть `numpy 1.26.x`.
- **`No solution found when resolving dependencies` при `uv sync`/`uv add`** — снят потолок
  `requires-python` в `pyproject.toml`; он обязан оставаться `">=3.11,<3.13"`.
