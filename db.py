import os
import json
import threading
from datetime import datetime
from typing import Any, Dict, List, Tuple

import psycopg

_DB_LOCK = threading.Lock()

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set (Neon Postgres)")
    # psycopg will parse the URL (sslmode is typically required on Neon)
    return psycopg.connect(DATABASE_URL, autocommit=True)


def init_db() -> None:
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                      telegram_id BIGINT PRIMARY KEY,
                      username TEXT,
                      first_name TEXT,
                      last_name TEXT,
                      language_code TEXT,
                      is_bot BOOLEAN DEFAULT FALSE,
                      phone TEXT,
                      created_at TIMESTAMPTZ,
                      updated_at TIMESTAMPTZ,
                      last_active_at TIMESTAMPTZ
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS submissions (
                      id BIGSERIAL PRIMARY KEY,
                      telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
                      model TEXT,
                      answers_json TEXT,
                      created_at TIMESTAMPTZ
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS promo_codes (
                      id BIGSERIAL PRIMARY KEY,
                      code TEXT UNIQUE NOT NULL,
                      telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
                      amount INTEGER DEFAULT 5000,
                      is_used BOOLEAN DEFAULT FALSE,
                      used_at TIMESTAMPTZ,
                      created_at TIMESTAMPTZ,
                      expires_at TIMESTAMPTZ
                    );
                    """
                )


def upsert_user(user: Dict[str, Any]) -> None:
    now = datetime.utcnow().isoformat()
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (telegram_id, username, first_name, last_name, language_code, is_bot, created_at, updated_at, last_active_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (telegram_id) DO UPDATE SET
                      username=EXCLUDED.username,
                      first_name=EXCLUDED.first_name,
                      last_name=EXCLUDED.last_name,
                      language_code=EXCLUDED.language_code,
                      is_bot=EXCLUDED.is_bot,
                      updated_at=EXCLUDED.updated_at,
                      last_active_at=EXCLUDED.last_active_at
                    ;
                    """,
                    (
                        user.get("telegram_id"),
                        user.get("username"),
                        user.get("first_name"),
                        user.get("last_name"),
                        user.get("language_code"),
                        bool(user.get("is_bot")),
                        now,
                        now,
                        now,
                    ),
                )


def update_user_phone(telegram_id: int, phone: str) -> None:
    now = datetime.utcnow().isoformat()
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET phone=%s, updated_at=%s, last_active_at=%s WHERE telegram_id=%s",
                    (phone, now, now, telegram_id),
                )


def touch_user_active(telegram_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET last_active_at=%s WHERE telegram_id=%s",
                    (now, telegram_id),
                )


def add_submission(telegram_id: int, model: str, answers: List[Tuple[str, int]]) -> None:
    now = datetime.utcnow().isoformat()
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO submissions (telegram_id, model, answers_json, created_at) VALUES (%s, %s, %s, %s)",
                    (telegram_id, model, json.dumps(answers, ensure_ascii=False), now),
                )


def list_users(limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      u.telegram_id,
                      u.username,
                      u.first_name,
                      u.last_name,
                      u.phone,
                      u.language_code,
                      u.is_bot,
                      u.created_at,
                      u.updated_at,
                      u.last_active_at,
                      (
                        SELECT s.model
                        FROM submissions s
                        WHERE s.telegram_id = u.telegram_id
                        ORDER BY s.created_at DESC
                        LIMIT 1
                      ) AS last_model
                    FROM users u
                    ORDER BY u.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                cols = [d[0] for d in cur.description]
                rows_raw = cur.fetchall()
    return [dict(zip(cols, r)) for r in rows_raw]


def stats_summary() -> Dict[str, Any]:
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                users_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM submissions")
                subs_count = cur.fetchone()[0]
                cur.execute("SELECT model, COUNT(*) FROM submissions GROUP BY model ORDER BY COUNT(*) DESC")
                pairs = cur.fetchall()
    by_model = {k: v for k, v in pairs}
    return {"users": users_count, "submissions": subs_count, "by_model": by_model}


def generate_promo_code(telegram_id: int, amount: int = 5000) -> str:
    """Generate a unique promo code for user"""
    import random
    import string
    
    now = datetime.utcnow()
    expires_at = now.replace(year=now.year + 1)  # Valid for 1 year
    
    # Generate code: FILS + 6 random chars
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    code = f"FILS{random_part}"
    
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                # Ensure uniqueness
                while True:
                    cur.execute("SELECT id FROM promo_codes WHERE code = %s", (code,))
                    if not cur.fetchone():
                        break
                    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                    code = f"FILS{random_part}"
                
                cur.execute(
                    """
                    INSERT INTO promo_codes (code, telegram_id, amount, created_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (code, telegram_id, amount, now.isoformat(), expires_at.isoformat())
                )
    
    return code


def get_user_promo_codes(telegram_id: int) -> List[Dict[str, Any]]:
    """Get all promo codes for a user"""
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT code, amount, is_used, used_at, created_at, expires_at
                    FROM promo_codes 
                    WHERE telegram_id = %s 
                    ORDER BY created_at DESC
                    """,
                    (telegram_id,)
                )
                cols = [d[0] for d in cur.description]
                rows_raw = cur.fetchall()
    return [dict(zip(cols, r)) for r in rows_raw]


def get_promo_stats() -> Dict[str, Any]:
    """Get promo codes statistics"""
    with _DB_LOCK:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM promo_codes")
                total_codes = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM promo_codes WHERE is_used = TRUE")
                used_codes = cur.fetchone()[0]
                cur.execute("SELECT SUM(amount) FROM promo_codes WHERE is_used = TRUE")
                total_used_amount = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM promo_codes WHERE expires_at > NOW() AND is_used = FALSE")
                active_codes = cur.fetchone()[0]
    return {
        "total_codes": total_codes,
        "used_codes": used_codes,
        "active_codes": active_codes,
        "total_used_amount": total_used_amount
    }
