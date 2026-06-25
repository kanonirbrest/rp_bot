"""HTTP API погашения промокодов NR-* (POST /api/promo/redeem)."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import date, datetime
from zoneinfo import ZoneInfo

import tornado.web

import config
import database as db

logger = logging.getLogger(__name__)

_PROMO_TIMEZONE = ZoneInfo("Europe/Minsk")
_REDEEM_ERRORS = {
    "invalid_format": 400,
    "not_found": 404,
    "already_used": 409,
    "expired": 410,
}


def is_promo_campaign_active() -> bool:
    d, m, y = config.PROMO_CAMPAIGN_VALID_UNTIL.strip().split(".")
    last_day = date(int(y), int(m), int(d))
    return datetime.now(_PROMO_TIMEZONE).date() <= last_day


def _check_auth(handler: tornado.web.RequestHandler) -> bool:
    if not config.PROMO_API_SECRET:
        return False
    auth = handler.request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth[7:].strip()
    return secrets.compare_digest(token, config.PROMO_API_SECRET)


class PromoRedeemHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ("POST",)

    def set_default_headers(self) -> None:
        self.set_header("Content-Type", "application/json; charset=utf-8")

    async def post(self) -> None:
        if not _check_auth(self):
            self.set_status(401)
            self.write(json.dumps({"ok": False, "error": "unauthorized"}))
            return

        try:
            body = json.loads(self.request.body.decode() or "{}")
        except json.JSONDecodeError:
            self.set_status(400)
            self.write(json.dumps({"ok": False, "error": "invalid_json"}))
            return

        code = body.get("code", "")
        try:
            result = await db.redeem_promo_code(
                code,
                discount_percent=config.PROMO_DISCOUNT_PERCENT,
            )
        except db.PromoRedeemError as exc:
            self.set_status(_REDEEM_ERRORS.get(exc.code, 400))
            self.write(json.dumps({"ok": False, "error": exc.code}))
            return
        except Exception:
            logger.exception("promo redeem failed for code=%r", code)
            self.set_status(500)
            self.write(json.dumps({"ok": False, "error": "internal_error"}))
            return

        logger.info("promo redeemed: code=%s user_id=%s", result["code"], result["user_id"])
        self.set_status(200)
        self.write(json.dumps({"ok": True, **result}))


def patch_webhook_app() -> None:
    """Добавляет /api/promo/redeem к Tornado-приложению webhook PTB."""
    from telegram.ext import _updater as updater_module
    from telegram.ext._utils import webhookhandler as wh

    if getattr(wh.WebhookAppClass, "_promo_api_patched", False):
        return

    class PatchedWebhookApp(tornado.web.Application):
        def __init__(
            self,
            webhook_path: str,
            bot,
            update_queue,
            secret_token: str | None = None,
        ):
            shared = {
                "bot": bot,
                "update_queue": update_queue,
                "secret_token": secret_token,
            }
            handlers = [
                (r"/api/promo/redeem/?", PromoRedeemHandler),
                (rf"{webhook_path}/?", wh.TelegramHandler, shared),
            ]
            super().__init__(handlers)

        def log_request(self, handler: tornado.web.RequestHandler) -> None:
            pass

    # PTB импортирует WebhookAppClass в _updater при загрузке модуля — патчим оба.
    wh.WebhookAppClass = PatchedWebhookApp  # type: ignore[misc, assignment]
    updater_module.WebhookAppClass = PatchedWebhookApp  # type: ignore[misc, assignment]
    wh.WebhookAppClass._promo_api_patched = True
    logger.info("Promo API route registered: POST /api/promo/redeem")
