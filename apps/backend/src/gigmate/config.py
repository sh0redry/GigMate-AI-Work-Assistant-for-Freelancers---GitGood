import os
from pathlib import Path

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[4]))
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./local-data/gigmate.db")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo-only-change-me")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
TRUSTED_ORIGINS = set(
    os.environ.get(
        "TRUSTED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:18080,http://127.0.0.1:18080",
    ).split(",")
)
if os.environ.get("APP_MODE", "replay") != "replay":
    raise RuntimeError("This development skeleton only supports APP_MODE=replay")
