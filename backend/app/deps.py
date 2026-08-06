"""Auth and the ledger authorization layer.

Every ledger-scoped route depends on `LedgerRead`, `LedgerWrite`, or
`LedgerAdmin`. There is no other way in — resolving the ledger and resolving
permission to touch it are the same query, so a route physically cannot read a
ledger it forgot to check.

Non-membership answers **404, never 403**. A 403 would confirm that a ledger id
exists, which is enough to enumerate other people's private books.
"""

from dataclasses import dataclass
from datetime import timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import CAN_ADMIN, CAN_EDIT, Ledger, LedgerMember, User
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบสมุดนี้"
)


def get_current_user(
    db: DbSession,
    creds: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ต้องเข้าสู่ระบบก่อน",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized

    payload = decode_access_token(creds.credentials)
    if not payload or "sub" not in payload:
        raise unauthorized

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise unauthorized

    # Tokens issued before the last password change are dead.
    #
    # The tzinfo guard is not defensive padding. A naive datetime's
    # .timestamp() is interpreted as *local* time, so on a UTC+7 machine the
    # cutoff would land seven hours in the past and every stale token would
    # sail through — a security check failing open, silently. Postgres hands
    # back an aware value and this is a no-op; the guard means correctness does
    # not depend on that.
    #
    # Both sides floor to whole seconds because PyJWT truncates `iat`; without
    # it the token minted by a password change would fail its own check.
    changed_at = user.password_changed_at
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    if int(payload.get("iat", 0)) < int(changed_at.timestamp()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="รหัสผ่านถูกเปลี่ยนแล้ว กรุณาเข้าสู่ระบบใหม่",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass
class LedgerContext:
    ledger: Ledger
    membership: LedgerMember
    user: User

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def can_edit(self) -> bool:
        return self.role in CAN_EDIT

    @property
    def can_admin(self) -> bool:
        return self.role in CAN_ADMIN


def get_ledger_ctx(
    ledger_id: int, db: DbSession, current_user: CurrentUser
) -> LedgerContext:
    row = db.execute(
        select(Ledger, LedgerMember)
        .join(LedgerMember, LedgerMember.ledger_id == Ledger.id)
        .where(Ledger.id == ledger_id, LedgerMember.user_id == current_user.id)
    ).one_or_none()

    if row is None:
        raise _NOT_FOUND

    ledger, membership = row
    return LedgerContext(ledger=ledger, membership=membership, user=current_user)


def get_ledger_ctx_write(
    ctx: Annotated[LedgerContext, Depends(get_ledger_ctx)],
) -> LedgerContext:
    if not ctx.can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="คุณดูสมุดนี้ได้อย่างเดียว ลงรายการไม่ได้",
        )
    return ctx


def get_ledger_ctx_admin(
    ctx: Annotated[LedgerContext, Depends(get_ledger_ctx)],
) -> LedgerContext:
    if not ctx.can_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="เฉพาะเจ้าของสมุดเท่านั้นที่ทำได้",
        )
    return ctx


# Read = any member. Write = owner or editor. Admin = owner only.
# 403 here is safe: reaching these means membership is already proven.
LedgerRead = Annotated[LedgerContext, Depends(get_ledger_ctx)]
LedgerWrite = Annotated[LedgerContext, Depends(get_ledger_ctx_write)]
LedgerAdmin = Annotated[LedgerContext, Depends(get_ledger_ctx_admin)]
