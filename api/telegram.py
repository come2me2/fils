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

# PTB application will be built lazily to avoid failing health when env is missing
ptb_app = None
_initialized = False

fastapi_app = FastAPI(title="FILS Design Telegram Webhook")
# Vercel expects a module-level variable named `app` for ASGI.
app = fastapi_app


@fastapi_app.on_event("startup")
async def on_startup():
    # Do not initialize PTB here; wait for first webhook call
    return


@fastapi_app.on_event("shutdown")
async def on_shutdown():
    global _initialized, ptb_app
    if _initialized and ptb_app is not None:
        await ptb_app.stop()
        await ptb_app.shutdown()
        _initialized = False


@fastapi_app.get("/api/health")
async def health():
    return {"status": "ok", "bot_initialized": _initialized}


@fastapi_app.post("/api/telegram")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(default=None)):
    # Optional secret verification
    if WEBHOOK_SECRET:
        if not x_telegram_bot_api_secret_token or x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()

    # Ensure PTB initialized (cold start safety)
    global _initialized, ptb_app, BOT_TOKEN
    if not _initialized:
        if not BOT_TOKEN:
            # Re-read in case env is present at runtime
            BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not BOT_TOKEN:
            raise HTTPException(status_code=500, detail="BOT token is not configured")
        if ptb_app is None:
            ptb_app = build_application()
        await ptb_app.initialize()
        await ptb_app.start()
        _initialized = True

    # Parse update and process (await) to avoid serverless task cancellation
    update = Update.de_json(data=data, bot=ptb_app.bot)
    await ptb_app.process_update(update)

    return JSONResponse({"ok": True})
