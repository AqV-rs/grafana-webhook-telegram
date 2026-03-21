# Grafana → Telegram relay

Python-сервис для приема webhook от Grafana и отправки сообщений в Telegram.

## Что делает

- принимает webhook от Grafana
- **не шаблонизирует сообщение внутри Python**
- берет уже готовый текст из payload от Grafana
- маршрутизирует уведомление в один или несколько Telegram-чатов по URL
- умеет проверять `X-Webhook-Secret`

## Логика извлечения текста

Сервис ищет `message`, то есть шаблонами управляем в Grafana, а сервис только пересылает.

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

Рекомендуемая схема:

- для каждой логической группы сделать свой webhook URL
- в Grafana использовать Notification templates для формирования `title` / `message`

Например:

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

- в Contact point указывать URL этого сервиса

Например:

- `https://alerts.example.com/grafana/prod`
- `https://alerts.example.com/grafana/dev`
- `https://alerts.example.com/grafana/db`

## Важные замечания

### HTML parse mode

По умолчанию включен `HTML`, значит в шаблонах Grafana можно использовать:

- `<b>жирный</b>`
- `<i>курсив</i>`
- `<code>код</code>`
- `<a href="https://example.com">ссылка</a>`
- `<pre>formatted text</pre>`

Важно экранировать спецсимволы, если Grafana может подставлять сырой текст с `<` или `&`.

### Ограничение Telegram

У Telegram есть ограничение на длину текста сообщения. Если payload fallback-режима слишком длинный, JSON будет обрезан.

## Подключение в Grafana