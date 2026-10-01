import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from gigmate.db import Account, LoginSession
from gigmate.errors import BusinessError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return f"{salt}:{key.hex()}"


def login(db, username: str, password: str):
    account = db.scalar(select(Account).where(Account.username == username))
    if not account or not hmac.compare_digest(
        account.password_hash, password_hash(password, account.password_hash.split(":")[0])
    ):
        raise BusinessError(401, "UNAUTHENTICATED", "Invalid development credentials")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=digest(token),
            account_id=account.id,
            csrf_hash=digest(csrf),
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        )
    )
    return account, token, csrf


def authenticate(db, token: str | None, csrf: str | None = None, mutation=False):
    session = db.get(LoginSession, digest(token or ""))
    if not session or session.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
        raise BusinessError(401, "UNAUTHENTICATED", "Sign in first")
    if mutation and (not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf))):
        raise BusinessError(403, "CSRF_REJECTED", "Invalid CSRF token")
    account = db.scalar(select(Account).where(Account.id == session.account_id).with_for_update())
    if not account or not account.active:
        raise BusinessError(403, "CONSENT_REVOKED", "Account processing is paused")
    return account
