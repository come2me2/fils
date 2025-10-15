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

# Pre-build PTB application; initialize on startup to avoid per-request cold init
ptb_app = build_application()
_initialized = False

fastapi_app = FastAPI(title="FILS Design Telegram Webhook")
# Vercel expects a module-level variable named `app` for ASGI.
app = fastapi_app


def admin_layout(*, title: str, active: str, body: str) -> HTMLResponse:
    # active in {"users","stats","broadcasts","home"}
    def a(href: str, text: str, key: str) -> str:
        on = " class=\"active\"" if key == active else ""
        return f"<a href=\"{href}\"{on}>{text}</a>"

    html = f"""
    <!doctype html>
    <html lang="ru">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>{title} — FILS Admin</title>
      <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
      <style>
        :root {{
          --bg: #0f1113;
          --panel: #15181b;
          --muted: #7c8a99;
          --text: #e7edf2;
          --brand: #a4b1bc; /* спокойный серо-голубой */
          --accent: #c9d4dc; /* светлый для границ */
          --ok: #3ecf8e;
          --danger: #ff5a5f;
        }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; background: var(--bg); color: var(--text); font-family: 'Roboto', system-ui, -apple-system, Segoe UI, Arial, sans-serif; }}
        .wrap {{ display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }}
        aside {{ background: var(--panel); border-right: 1px solid #1d2226; padding: 24px 16px; position: sticky; top: 0; height: 100vh; }}
        .brand {{ font-weight: 700; letter-spacing: .5px; color: var(--brand); margin: 0 0 16px; }}
        nav a {{ display: block; padding: 10px 12px; color: var(--text); text-decoration: none; border-radius: 8px; margin-bottom: 6px; border: 1px solid transparent; }}
        nav a:hover {{ background: #1a1f24; border-color: #20262b; }}
        nav a.active {{ background: #1b2026; border-color: var(--accent); color: #fff; }}
        .content {{ padding: 28px 28px 48px; }}
        h1, h2 {{ margin: 0 0 14px; font-weight: 600; }}
        .panel {{ background: var(--panel); border: 1px solid #1d2226; border-radius: 12px; padding: 18px; }}
        .muted {{ color: var(--muted); }}
        .error {{ color: var(--danger); margin: 8px 0 16px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #22272b; }}
        th {{ color: var(--muted); font-weight: 500; letter-spacing: .3px; }}
        tr:hover td {{ background: #171b1f; }}
        .btn {{ display: inline-block; padding: 10px 14px; border-radius: 10px; border: 1px solid #2a3137; background: #1a1f24; color: #e7edf2; text-decoration: none; cursor: pointer; }}
        .btn:hover {{ background: #20262b; }}
        textarea, input[type="password"] {{ width: 100%; background: #0f1317; color: #e7edf2; border: 1px solid #20262b; border-radius: 10px; padding: 10px 12px; }}
        form .row {{ display: flex; gap: 12px; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <aside>
          <h3 class="brand">FILS Admin</h3>
          <nav>
            {a('/admin', 'Главная', 'home')}
            {a('/admin/users', 'Пользователи', 'users')}
            {a('/admin/stats', 'Статистика', 'stats')}
            {a('/admin/broadcasts', 'Рассылки', 'broadcasts')}
            <a href="/admin/logout" class="muted">Выйти</a>
          </nav>
        </aside>
        <main class="content">
          {body}
        </main>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


@fastapi_app.on_event("startup")
async def on_startup():
    # Initialize DB
    try:
        init_db()
    except Exception:
        pass
    # Initialize and start PTB app once per instance
    global _initialized
    if not _initialized:
        await ptb_app.initialize()
        await ptb_app.start()
        _initialized = True
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

    # Ensure PTB app is initialized (fallback if startup wasn't triggered)
    global _initialized
    if not _initialized:
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
    return admin_layout(
        title="Вход",
        active="home",
        body=(
            "<h2>Вход в админку</h2>"
            '<div class="panel">'
            '<form method="post" action="/admin/login" class="row">'
            '<input type="password" name="secret" placeholder="ADMIN_SECRET" />'
            '<button class="btn" type="submit">Войти</button>'
            "</form>"
            "</div>"
        ),
    )


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
    return admin_layout(
        title="Главная",
        active="home",
        body=(
            "<h2>FILS Admin</h2>"
            '<div class="panel"><p class="muted">Выберите раздел слева.</p></div>'
        ),
    )


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
        f"<tr><td>{u.get('telegram_id')}</td><td>@{u.get('username') or ''}</td><td>{u.get('first_name') or ''} {u.get('last_name') or ''}</td><td>{u.get('phone') or ''}</td><td>{u.get('last_model') or '-'}</td><td>{u.get('created_at')}</td><td>{u.get('last_active_at') or ''}</td></tr>"
        for u in users
    )
    return admin_layout(
        title="Пользователи",
        active="users",
        body=(
            "<h2>Пользователи</h2>"
            f"{error_html}"
            '<div class="panel">'
            '<div style="overflow:auto">'
            '<table>'
            '<tr><th>ID</th><th>Username</th><th>Имя</th><th>Телефон</th><th>Результат</th><th>Создан</th><th>Активность</th></tr>'
            f"{rows}"
            '</table>'
            '</div>'
            '</div>'
        ),
    )


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

    # Fallback text when no model data
    if not by_model_html:
        by_model_html = "<li class='muted'>Пока нет данных</li>"

    return admin_layout(
        title="Статистика",
        active="stats",
        body=(
            "<h2>Статистика</h2>"
            f"{error_html}"
            '<div class="panel">'
            f"<p>Пользователи: <b>{s.get('users', 0)}</b></p>"
            f"<p>Квизов пройдено: <b>{s.get('submissions', 0)}</b></p>"
            "<h3 class='muted' style='margin-top:12px;'>По моделям</h3>"
            f"<ul>{by_model_html}</ul>"
            "</div>"
        ),
    )

@fastapi_app.get("/admin/migrate")
async def admin_migrate(_: Any = Depends(require_admin)):
    try:
        init_db()
        return PlainTextResponse("OK: schema ensured")
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)


@fastapi_app.get("/admin/broadcasts", response_class=HTMLResponse)
async def admin_broadcasts_page(_: Any = Depends(require_admin)):
    return admin_layout(
        title="Рассылки",
        active="broadcasts",
        body=(
            "<h2>Рассылка</h2>"
            '<div class="panel">'
            '<form method="post" action="/admin/broadcasts" style="display:flex; flex-direction:column; gap:12px;">'
            '<textarea name="text" rows="6" placeholder="Текст сообщения"></textarea>'
            '<div><button class="btn" type="submit">Отправить всем</button></div>'
            "</form>"
            "</div>"
        ),
    )


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
