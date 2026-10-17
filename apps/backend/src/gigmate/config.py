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


def workspace_timezone() -> str | None:
    """Trusted merchant/workspace timezone for relative-date resolution.

    Read at call time (not import time) so a worker restart is the only thing
    needed to pick up a changed setting. ``None`` means "not configured"; the
    model provider refuses live extraction rather than guessing a basis.
    """
    value = os.environ.get("GIGMATE_WORKSPACE_TIMEZONE", "").strip()
    return value or None
