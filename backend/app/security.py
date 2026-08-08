from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from .config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # malformed hash in the DB — treat as a failed login, not a 500
        return False


def password_stamp(changed_at: datetime) -> int:
    """Microsecond stamp identifying one particular password.

    Tokens carry this and it is compared for *equality*, not for order. The
    obvious design — compare the token's `iat` against password_changed_at —
    has a one-second hole in it, because PyJWT floors `iat` to whole seconds:
    a token minted in the same second as a password change compares equal and
    survives the change. Equality on a microsecond stamp has no such window.
    """
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    return int(changed_at.timestamp() * 1_000_000)


def create_access_token(
    user_id: int, username: str, changed_at: datetime
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.jwt_expire_days)
    payload = {
        "sub": str(user_id),
        "username": username,
        "pwc": password_stamp(changed_at),
        "exp": expires_at,
        "iat": now,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
