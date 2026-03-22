# Grafana → Telegram relay

Небольшой Python-сервис, который принимает webhook от Grafana и пересылает сообщения в Telegram.

Сервис создан для обхода ограничений доступа к Telegram API.

Обычно разворачивается на внешнем сервере (VPS) и работает как relay между Grafana и Telegram.

## TL;DR

Grafana → webhook → relay service → Telegram

## Что делает

- принимает webhook от Grafana
- использует готовый текст из payload (`message`)
- не изменяет и не шаблонизирует сообщение
- маршрутизирует уведомления по URL в один или несколько Telegram-чатов
- поддерживает проверку `X-Webhook-Secret`

## Как это работает

1. Grafana отправляет webhook на endpoint сервиса
2. Сервис проверяет `X-Webhook-Secret` (если задан)
3. Из payload извлекается поле `message`
4. Сообщение отправляется в соответствующие Telegram-чаты

## Requirements

- Docker + Docker Compose
- Telegram Bot Token
   
## Конфиг

Основные переменные в `.env`:

- `TELEGRAM_BOT_TOKEN` — токен бота
- `WEBHOOK_SECRET` — общий секрет для проверки заголовка `X-Webhook-Secret`
- `DEFAULT_PARSE_MODE` — обычно `HTML`
- `ROUTES_JSON` — маршруты и Telegram-цели
- `HOST` — хост прослушивания сервисом
- `PORT` — порт прослушивания сервисом

### Пример `ROUTES_JSON`

В `.env` json важно указывать в строку из-за особенностей Docker

```
{"/grafana/prod":["-1006666666"],"/grafana/dev":["-1005555555555"],"/grafana/db":["-1001111111111","-1002222222222"]}
```

## Запуск

```bash
cp .env.example .env
# отредактировать .env

docker compose up -d --build
```

Проверка:

```bash
curl http://localhost:8000/health
```

## Пример webhook вызова

```bash
curl -X POST http://localhost:8000/grafana/prod \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Secret: secret' \
  -d '{
    "message": "Instance <code>app-01</code> is down"
  }'
```

## Настройка в Grafana

### 1. Создать webhook endpoint

Для каждой логической группы создайте отдельный URL:

- `https://alerts.example.com/grafana/prod`
- `https://alerts.example.com/grafana/dev`
- `https://alerts.example.com/grafana/db`

---

### 2. Настроить Contact point

В Contact point укажите:

- URL сервиса
- метод: `POST`

При необходимости добавьте заголовок в Extra Headers:
`X-Webhook-Secret: <your_secret>`

---

### 3. Настроить шаблон сообщения

Рекомендуется использовать Notification templates и формировать поле `message`.

Пример шаблона:

```
{{ define "telegram.message" }}
{{- $a := index .Alerts 0 -}}

Status: [{{ $.Status }}]
Alert: {{ $.CommonLabels.alertname }}

{{- if $a.Annotations.summary }}
{{ $a.Annotations.summary }}
{{- else }}
(no summary)
{{- end }}

Метрики:
{{- range .Alerts }}
- {{ .Annotations.description }}
{{- end }}

{{- if $a.PanelURL }}
Panel: {{ $a.PanelURL }}
{{- end }}
{{ end }}
```

---

### 4. Привязать шаблон к Contact point

Укажите созданный template в настройках Contact point.
  
## Ограничения и особенности

### Форматирование сообщений

По умолчанию используется `HTML` parse mode, поэтому в шаблонах Grafana можно использовать:

- `<b>жирный</b>`
- `<i>курсив</i>`
- `<code>код</code>`
- `<a href="https://example.com">ссылка</a>`
- `<pre>formatted text</pre>`

Важно: экранируйте спецсимволы (`<`, `&`), если Grafana подставляет сырой текст.

---

### Ограничения Telegram

Telegram ограничивает длину сообщения.

Если текст слишком длинный, сообщение может быть обрезано.

---

### Безопасность

- Сервис не поддерживает `https` из коробки
- Используйте reverse proxy (например, Nginx)
- Обязательно включайте `X-Webhook-Secret`

Алерты могут содержать чувствительные данные — не оставляйте сервис публично доступным без защиты.

## License

MIT License © 2026 Nikita Liskov
