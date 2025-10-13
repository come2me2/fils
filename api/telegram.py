import os
import asyncio
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from telegram import Update

from bot import build_application

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

# Build PTB application (no polling)
ptb_app = build_application()
_initialized = False

fastapi_app = FastAPI(title="FILS Design Telegram Webhook")
# Vercel expects a module-level variable named `app` for ASGI.
app = fastapi_app


@fastapi_app.on_event("startup")
async def on_startup():
    global _initialized
    if not _initialized:
        # Initialize & start PTB application (without polling/server)
        await ptb_app.initialize()
        await ptb_app.start()
        _initialized = True


@fastapi_app.on_event("shutdown")
async def on_shutdown():
    global _initialized
    if _initialized:
        await ptb_app.stop()
        await ptb_app.shutdown()
        _initialized = False


@fastapi_app.get("/api/health")
async def health():
    return {"status": "ok"}


@fastapi_app.post("/api/telegram")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(default=None)):
    # Optional secret verification
    if WEBHOOK_SECRET:
        if not x_telegram_bot_api_secret_token or x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()

    # Ensure PTB initialized (cold start safety)
    global _initialized
    if not _initialized:
        await ptb_app.initialize()
        await ptb_app.start()
        _initialized = True

    # Parse update and process
    update = Update.de_json(data=data, bot=ptb_app.bot)
    await ptb_app.process_update(update)

    return JSONResponse({"ok": True})
