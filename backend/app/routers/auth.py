from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..deps import CurrentUser, DbSession
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserOut
from ..security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.execute(
        select(User).where(User.username == payload.username.strip().lower())
    ).scalar_one_or_none()

    # Same message either way — no hints about which half was wrong.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
        )

    token, expires_at = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/users", response_model=list[UserOut])
def list_users(db: DbSession, current_user: CurrentUser) -> list[UserOut]:
    """Both accounts — the dashboard needs them for the 'added by' filter."""
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [UserOut.model_validate(u) for u in users]
