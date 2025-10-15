import os
import asyncio
from typing import Optional, Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Header, HTTPException, Depends, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, PlainTextResponse
from telegram import Update

from bot import build_application
from db import init_db, list_users, stats_summary

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

# PTB application will be built lazily to avoid failing health when env is missing
ptb_app = None
_initialized = False

fastapi_app = FastAPI(title="FILS Design Telegram Webhook")
# Vercel expects a module-level variable named `app` for ASGI.
app = fastapi_app


@fastapi_app.on_event("startup")
async def on_startup():
    # Initialize DB; PTB will be initialized lazily on first webhook call
    try:
        init_db()
    except Exception:
        pass
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
    # Try DB connectivity
    db_ok = True
    db_err = None
    try:
        # light-touch: stats_summary() runs SELECTs
        _ = stats_summary()
    except Exception as e:
        db_ok = False
        db_err = str(e)
    return {"status": "ok", "bot_initialized": _initialized, "db_ok": db_ok, "db_error": db_err}


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


# ---------------------- Admin area ----------------------

def _is_admin(request: Request) -> bool:
    cookie = request.cookies.get("admin_secret")
    return bool(ADMIN_SECRET) and cookie == ADMIN_SECRET


async def require_admin(request: Request):
    if not _is_admin(request):
        raise HTTPException(status_code=302, detail="redirect", headers={"Location": "/admin/login"})


@fastapi_app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page():
    html = """
    <html><head><title>FILS Admin — Login</title></head>
    <body style="font-family: system-ui; max-width: 640px; margin: 40px auto;">
      <h2>Вход в админку</h2>
      <form method="post" action="/admin/login" style="display:flex; gap:8px;">
        <input type="password" name="secret" placeholder="ADMIN_SECRET" style="flex:1; padding:8px;" />
        <button type="submit" style="padding:8px 16px;">Войти</button>
      </form>
    </body></html>
    """
    return HTMLResponse(html)


@fastapi_app.post("/admin/login")
async def admin_login(secret: str = Form(...)):
    if not ADMIN_SECRET:
        return PlainTextResponse("ADMIN_SECRET не задан", status_code=500)
    if secret != ADMIN_SECRET:
        return PlainTextResponse("Неверный секрет", status_code=403)
    resp = RedirectResponse(url="/admin", status_code=302)
    resp.set_cookie("admin_secret", ADMIN_SECRET, httponly=True, max_age=60*60*12)
    return resp


@fastapi_app.get("/admin/logout")
async def admin_logout():
    resp = RedirectResponse(url="/admin/login", status_code=302)
    resp.delete_cookie("admin_secret")
    return resp


@fastapi_app.get("/admin", response_class=HTMLResponse)
async def admin_home(_: Any = Depends(require_admin)):
    html = """
    <html><head><title>FILS Admin</title></head>
    <body style=\"font-family: system-ui; max-width: 1000px; margin: 24px auto; display:flex; gap:24px;\">\n
      <aside style=\"min-width:220px;\">\n
        <h3>Меню</h3>\n
        <ul style=\"list-style:none; padding-left:0; line-height: 1.9;\">\n
          <li><a href=\"/admin/users\">Пользователи</a></li>\n
          <li><a href=\"/admin/stats\">Статистика</a></li>\n
          <li><a href=\"/admin/broadcasts\">Рассылки</a></li>\n
          <li><a href=\"/admin/logout\">Выйти</a></li>\n
        </ul>\n
      </aside>\n
      <main style=\"flex:1;\">\n
        <h2>FILS Admin</h2>\n
        <p>Выберите раздел слева.</p>\n
      </main>\n
    </body></html>
    """
    return HTMLResponse(html)


@fastapi_app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(_: Any = Depends(require_admin)):
    # Ensure schema
    try:
        init_db()
    except Exception:
        pass
    error_html = ""
    try:
        users = list_users(limit=500)
    except Exception as e:
        # If tables are missing, try to initialize and retry once
        msg = str(e)
        try:
            if "relation \"users\" does not exist" in msg.lower():
                init_db()
                users = list_users(limit=500)
            else:
                raise
        except Exception:
            users = []
            error_html = f"<div style='color:#b00; margin:8px 0;'>DB error: {msg}</div>"
    rows = "".join(
        f"<tr><td>{u.get('telegram_id')}</td><td>@{u.get('username') or ''}</td><td>{u.get('first_name') or ''} {u.get('last_name') or ''}</td><td>{u.get('phone') or ''}</td><td>{u.get('created_at')}</td><td>{u.get('last_active_at') or ''}</td></tr>"
        for u in users
    )
    html = f"""
    <html><head><title>Пользователи — FILS Admin</title></head>
    <body style=\"font-family: system-ui; max-width: 1200px; margin: 24px auto; display:flex; gap:24px;\">\n
      <aside style=\"min-width:220px;\">\n
        <h3>Меню</h3>\n
        <ul style=\"list-style:none; padding-left:0; line-height: 1.9;\">\n
          <li><a href=\"/admin/users\"><b>Пользователи</b></a></li>\n
          <li><a href=\"/admin/stats\">Статистика</a></li>\n
          <li><a href=\"/admin/broadcasts\">Рассылки</a></li>\n
          <li><a href=\"/admin/logout\">Выйти</a></li>\n
        </ul>\n
      </aside>\n
      <main style=\"flex:1;\">\n
        <h2>Пользователи</h2>\n
        {error_html}\n
        <table border=1 cellpadding=6 cellspacing=0>\n
          <tr><th>ID</th><th>Username</th><th>Имя</th><th>Телефон</th><th>Создан</th><th>Активность</th></tr>\n
          {rows}\n
        </table>\n
      </main>\n
    </body></html>
    """
    return HTMLResponse(html)


@fastapi_app.get("/admin/stats", response_class=HTMLResponse)
async def admin_stats(_: Any = Depends(require_admin)):
    # Ensure schema
    try:
        init_db()
    except Exception:
        pass
    try:
        s = stats_summary()
        by_model_html = "".join(f"<li>{k}: {v}</li>" for k, v in s.get("by_model", {}).items())
        error_html = ""
    except Exception as e:
        msg = str(e)
        try:
            if "relation \"users\" does not exist" in msg.lower() or "relation \"submissions\" does not exist" in msg.lower():
                init_db()
                s = stats_summary()
                by_model_html = "".join(f"<li>{k}: {v}</li>" for k, v in s.get("by_model", {}).items())
                error_html = ""
            else:
                raise
        except Exception:
            s = {"users": 0, "submissions": 0, "by_model": {}}
            by_model_html = ""
            error_html = f"<div style='color:#b00; margin:8px 0;'>DB error: {msg}</div>"

@fastapi_app.get("/admin/migrate")
async def admin_migrate(_: Any = Depends(require_admin)):
    try:
        init_db()
        return PlainTextResponse("OK: schema ensured")
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)
    html = f"""
    <html><head><title>Статистика — FILS Admin</title></head>
    <body style=\"font-family: system-ui; max-width: 1000px; margin: 24px auto; display:flex; gap:24px;\">\n
      <aside style=\"min-width:220px;\">\n
        <h3>Меню</h3>\n
        <ul style=\"list-style:none; padding-left:0; line-height: 1.9;\">\n
          <li><a href=\"/admin/users\">Пользователи</a></li>\n
          <li><a href=\"/admin/stats\"><b>Статистика</b></a></li>\n
          <li><a href=\"/admin/broadcasts\">Рассылки</a></li>\n
          <li><a href=\"/admin/logout\">Выйти</a></li>\n
        </ul>\n
      </aside>\n
      <main style=\"flex:1;\">\n
        <h2>Статистика</h2>\n
        {error_html}\n
        <p>Пользователи: <b>{s.get('users', 0)}</b></p>\n
        <p>Квизов пройдено: <b>{s.get('submissions', 0)}</b></p>\n
        <h3>По моделям</h3>\n
        <ul>{by_model_html}</ul>\n
      </main>\n
    </body></html>
    """
    return HTMLResponse(html)


@fastapi_app.get("/admin/broadcasts", response_class=HTMLResponse)
async def admin_broadcasts_page(_: Any = Depends(require_admin)):
    html = """
    <html><head><title>Рассылки — FILS Admin</title></head>
    <body style="font-family: system-ui; max-width: 1000px; margin: 24px auto; display:flex; gap:24px;">
      <aside style="min-width:220px;">
        <h3>Меню</h3>
        <ul style="list-style:none; padding-left:0; line-height: 1.9;">
          <li><a href="/admin/users">Пользователи</a></li>
          <li><a href="/admin/stats">Статистика</a></li>
          <li><a href="/admin/broadcasts"><b>Рассылки</b></a></li>
          <li><a href="/admin/logout">Выйти</a></li>
        </ul>
      </aside>
      <main style="flex:1;">
        <h2>Рассылка</h2>
        <form method="post" action="/admin/broadcasts" style="display:flex; flex-direction:column; gap:8px;">
          <textarea name="text" rows="6" placeholder="Текст сообщения" style="padding:8px;"></textarea>
          <button type="submit" style="width:200px; padding:8px 16px;">Отправить всем</button>
        </form>
      </main>
    </body></html>
    """
    return HTMLResponse(html)


@fastapi_app.post("/admin/broadcasts")
async def admin_broadcasts_send(request: Request, text: str = Form(...), _: Any = Depends(require_admin)):
    if not text.strip():
        return PlainTextResponse("Пустое сообщение", status_code=400)

    # Collect recipients
    users = list_users(limit=100000)
    ids = [u.get("telegram_id") for u in users if u.get("telegram_id")]

    if not ids:
        return PlainTextResponse("Нет пользователей", status_code=200)

    # Ensure bot initialized
    global _initialized, ptb_app, BOT_TOKEN
    if not _initialized:
        if not BOT_TOKEN:
            BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not BOT_TOKEN:
            return PlainTextResponse("BOT token не настроен", status_code=500)
        if ptb_app is None:
            ptb_app = build_application()
        await ptb_app.initialize()
        await ptb_app.start()
        _initialized = True

    sent = 0
    for tid in ids:
        try:
            await ptb_app.bot.send_message(chat_id=tid, text=text)
            sent += 1
        except Exception:
            continue

    return PlainTextResponse(f"Отправлено: {sent} из {len(ids)}")
