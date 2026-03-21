import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("grafana-telegram-webhook")

app = FastAPI(title="Grafana to Telegram Relay", version="2.0.1")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
DEFAULT_PARSE_MODE = os.getenv("DEFAULT_PARSE_MODE", "HTML").strip() or None
DISABLE_WEB_PAGE_PREVIEW = os.getenv("DISABLE_WEB_PAGE_PREVIEW", "true").lower() in {"1", "true", "yes", "on"}
SEND_RAW_JSON_FALLBACK = os.getenv("SEND_RAW_JSON_FALLBACK", "true").lower() in {"1", "true", "yes", "on"}


def mask_token(text: str) -> str:
    if not TELEGRAM_BOT_TOKEN:
        return text
    return text.replace(TELEGRAM_BOT_TOKEN, "***")


def load_routes() -> Dict[str, List[Dict[str, Any]]]:
    raw = os.getenv("ROUTES_JSON", "").strip()
    if not raw:
        raise RuntimeError("ROUTES_JSON is empty")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ROUTES_JSON is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("ROUTES_JSON must be a JSON object")

    normalized: Dict[str, List[Dict[str, Any]]] = {}
    for path, target in parsed.items():
        if not isinstance(path, str) or not path.startswith("/"):
            raise RuntimeError(f"Route key must be a path starting with '/': {path!r}")

        targets: List[Dict[str, Any]] = []
        if isinstance(target, list):
            for item in target:
                if isinstance(item, (str, int)):
                    targets.append({"chat_id": str(item)})
                elif isinstance(item, dict) and "chat_id" in item:
                    entry = {"chat_id": str(item["chat_id"])}
                    if "parse_mode" in item and item["parse_mode"]:
                        entry["parse_mode"] = str(item["parse_mode"])
                    targets.append(entry)
                else:
                    raise RuntimeError(f"Unsupported target in route {path}: {item!r}")
        else:
            raise RuntimeError(f"Route value for {path} must be a list")

        if not targets:
            raise RuntimeError(f"Route {path} has no targets")

        normalized[path] = targets

    return normalized


ROUTES = load_routes()

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is empty")


async def send_telegram_message(target: Dict[str, Any], text: str) -> Dict[str, Any]:
    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": target["chat_id"],
        "text": text,
        "disable_web_page_preview": DISABLE_WEB_PAGE_PREVIEW,
    }

    parse_mode = target.get("parse_mode", DEFAULT_PARSE_MODE)
    if parse_mode:
        payload["parse_mode"] = parse_mode

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload)

    if response.status_code >= 400:
        safe_body = mask_token(response.text)
        logger.error(
            "Telegram send failed: status=%s body=%s",
            response.status_code,
            safe_body,
        )
        raise HTTPException(status_code=502, detail=f"Telegram API error: {safe_body}")

    return response.json()


def _string(value: Any) -> str:
    return str(value).strip()


def extract_message(payload: Dict[str, Any]) -> str:
    title = _string(payload.get("title", ""))
    message = _string(payload.get("message", ""))

    if message:
        return message

    if title:
        return title

    alerts = payload.get("alerts")
    if isinstance(alerts, list):
        parts: List[str] = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            annotations = alert.get("annotations", {}) if isinstance(alert.get("annotations"), dict) else {}
            summary = _string(annotations.get("summary", ""))
            description = _string(annotations.get("description", ""))
            text = summary or description
            if text:
                parts.append(text)
        if parts:
            return "\n\n".join(parts)

    common_annotations = payload.get("commonAnnotations")
    if isinstance(common_annotations, dict):
        summary = _string(common_annotations.get("summary", ""))
        description = _string(common_annotations.get("description", ""))
        text = summary or description
        if text:
            return text

    if SEND_RAW_JSON_FALLBACK:
        raw = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(raw) > 3900:
            raw = raw[:3900] + "\n..."
        return f"<pre>{raw}</pre>"

    raise HTTPException(status_code=400, detail="No text found in payload")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "routes": list(ROUTES.keys())}


@app.post("/{full_path:path}")
async def receive_webhook(
    full_path: str,
    request: Request,
    x_webhook_secret: Optional[str] = Header(default=None),
) -> JSONResponse:
    route_path = "/" + full_path

    if route_path not in ROUTES:
        raise HTTPException(status_code=404, detail="Unknown webhook route")

    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    text = extract_message(payload)
    results = []

    for target in ROUTES[route_path]:
        telegram_result = await send_telegram_message(target, text)
        results.append(
            {
                "chat_id": target["chat_id"],
                "telegram_ok": telegram_result.get("ok", False),
            }
        )

    return JSONResponse(
        {
            "ok": True,
            "route": route_path,
            "sent_to": results,
        }
    )