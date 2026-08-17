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
- Python 3.11 (ставит `uv`), `bun` — сборка фронтенда.
- СУБД не нужна: SQLite-файл `mytra.db` (передаётся отдельно, в git его нет).

## 1. Подготовка сервера
```bash
sudo apt update && sudo apt install -y git apache2 sqlite3
curl -LsSf https://astral.sh/uv/install.sh | sh      # uv (поставит Python 3.11)
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
uv sync                                            # создаст .venv (в т.ч. uvicorn)
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
Файл `/etc/apache2/sites-available/mytra.conf`:
```apache
<VirtualHost *:80>
    # Имя или IP сервера; для доступа по IP — закомментировать
    ServerName mytra.local

    DocumentRoot /opt/mytra/frontend/dist

    <Directory /opt/mytra/frontend/dist>
        Options -Indexes +FollowSymLinks
        AllowOverride None
        Require all granted
        FallbackResource /index.html
    </Directory>

    ProxyPass /api http://127.0.0.1:8000
    ProxyPassReverse /api http://127.0.0.1:8000

    LimitRequestBody 0
</VirtualHost>
```
```bash
sudo a2dissite 000-default
sudo a2ensite mytra
sudo apache2ctl configtest
sudo systemctl reload apache2
```

## 7. Файрвол и проверка
```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw enable
curl http://127.0.0.1:8000/api/login   # JSON (бэкенд жив)
curl http://localhost/api/login        # JSON (прокси работает)
```
Открыть в браузере `http://<ip-сервера>/`.

## Обновление
```bash
cd /opt/mytra && git pull && uv sync
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
- **`/api` 404 / Connection refused** — не запущен uvicorn или не включены модули `proxy proxy_http`.
- **«no such table: users»** — не положен `mytra.db` или он пустой.
- **Логин не проходит** — при первом входе пароль = табельному номеру; пользователь должен быть в базе.
- **Права на БД** — `mytra.db` должен принадлежать пользователю `mytra`.
