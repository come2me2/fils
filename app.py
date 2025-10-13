# Root FastAPI entrypoint for Vercel detection
# Delegates to the webhook app defined in api/telegram.py
from api.telegram import app  # noqa: F401
