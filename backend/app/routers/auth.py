from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..deps import CurrentUser, DbSession
from ..models import User
from ..ratelimit import client_key, login_limiter, register_limiter
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue(user: User) -> TokenResponse:
    token, expires_at = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token, expires_at=expires_at, user=UserOut.model_validate(user)
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: DbSession) -> TokenResponse:
    """Public signup. Rate limited per IP — see app/ratelimit.py for why that
    brake is the cheapest thing that works and where it stops working."""
    register_limiter.check(client_key(request))

    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # UNIQUE(username) — the check and the insert are one step on purpose,
        # so two simultaneous signups cannot both pass a pre-check.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="ชื่อผู้ใช้นี้มีคนใช้แล้ว"
        ) from None

    db.refresh(user)
    return _issue(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    login_limiter.check(client_key(request))

    user = db.execute(
        select(User).where(User.username == payload.username.strip().lower())
    ).scalar_one_or_none()

    # Same message either way — no hints about which half was wrong.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
        )

    return _issue(user)


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)
