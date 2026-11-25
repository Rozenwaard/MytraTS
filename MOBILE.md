# Мобильный контур РКС (MytraGo)

## Цель
Полевой рабочий на дешёвом Android (BV6300) «включил и работает»:
сканирует QR для привязки, получает задания, заполняет отчёт, делает фото, отправляет.
Без настроек и ввода URL.

## Архитектура — одно приложение, две обёртки
Один SvelteKit-фронт (SPA, `adapter-static`) собирается в статику и работает в двух контекстах:

| Контекст | Запуск | Офлайн | Нативные возможности |
|---|---|---|---|
| Web-PWA (браузер) | HTTPS-туннель (тест) / прод-домен | service worker | нет (getUserMedia — ненадёжно) |
| **Capacitor APK (основной)** | нативный WebView, ассеты из APK | локальная статика + офлайн-очередь | ML Kit (QR), Camera, Geolocation, Preferences |

**Основная цель — Capacitor APK.** Web-PWA оставлен как запасной/отладочный путь.

## Ключевые решения и почему
1. **QR-сканер — нативный `@capacitor-mlkit/barcode-scanning`** (не html5-qrcode):
   html5-qrcode (getUserMedia) давал чёрный экран на BV6300.
   ML Kit рисует камеру ПОД WebView: WebView делаем прозрачным, контент скрываем
   (`visibility: hidden`), оставляем только слой сканера `.barcode-scanner-modal`.
2. **QR содержит URL** `/m/enroll?code=XXXX` → при сканировании извлекаем `code`
   из URL (функция `extractCode`), а не шлём весь URL в бэк.
3. **Фото — планируется `@capacitor/camera`** (живое превью + чёткий снимок),
   а не системная камера (`input capture`). При необходимости — свой Kotlin-плагин на CameraX.
4. **Service worker — только web-PWA.** В Capacitor не регистрируется
   (`Capacitor.isNativePlatform()`). В самом SW API не кэшируется и не перехватывается:
   только `GET`, только same-origin, `/api/*` — мимо.
5. **Адрес бэка** — `VITE_API_URL` при сборке (тест: URL Cloudflare quick tunnel;
   прод: домен). URL туннеля меняется при перезапуске cloudflared → пересобираем APK.
   (`PUBLIC_API_URL` не инлайнится в rolldown-vite без `svelte.config.js` → используем `VITE_*`.)
6. **API-запросы — нативный `CapacitorHttp`** (OkHttp), а не `fetch`:
   `fetch` из WebView давал «Failed to fetch» (CORS/сетка WebView). Нативный HTTP
   идёт мимо WebView/CORS напрямую через нативный стек.
7. **Старые service worker'ы сносятся** при старте в Capacitor (`unregister` всех
   регистраций): SW от прошлых установок APK остаётся в WebView и мешает.

## Что сделано
- [x] Бэк: enroll-code / enroll / sync / reports / photos / return, справочники, нормы, цепочка task_type, форма реестра.
- [x] Мобильный фронт `/m/*`: вход, задания, мастер задания, фото (WebP), гео+h3, офлайн-очередь.
- [x] QR→URL привязка `/m/enroll`, брендинг MytraGo.
- [x] Capacitor: adapter-static, android-проект, permissions (CAMERA/LOCATION), JDK 21, первый APK.
- [x] Нативный ML Kit QR-сканер в `/m/login` (камера видна, прозрачность WebView).
- [x] Извлечение `code` из URL QR + подробная ошибка привязки.
- [x] Нативный HTTP (`CapacitorHttp`) для API + снос старых SW в Capacitor.
- [x] Привязка QR проверена на телефоне (BV6300) — работает.

## В работе / осталось
- [ ] Фото на `@capacitor/camera` (превью + снимок).
- [ ] Иконка приложения — логотип Mytra (из `favicon.svg`).
- [ ] Пересборка APK под прод-домен.
- [ ] Тест полного цикла на телефоне: задания → отчёт → фото → отправка.

## Технические заметки
- Сборка APK: задать `VITE_API_URL` в `.env` → `bun run build` → `bunx cap sync android` →
  `gradlew assembleDebug` (JAVA_HOME = jdk21).
- APK называем с числовым префиксом: `00-…`, `01-…`, … (debug-сборки в Downloads).
- Эмулятор `Medium_Phone_API_37.0` — для проверки превью камеры
  (виртуальная камера, реальный QR на нём не проверить).
- Чёрный экран камеры на дешёвых устройствах = проблема getUserMedia; используем ML Kit.
