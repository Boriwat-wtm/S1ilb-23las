import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import settings
from .models import DIRECTIONS, LEDGER_KINDS, ROLE_EDITOR, ROLE_VIEWER, ROLES

LOCAL_TZ = ZoneInfo(settings.app_timezone)

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MIN_PASSWORD_LEN = 8


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    display_name: str = Field(min_length=1, max_length=80)
    password: str

    @field_validator("username")
    @classmethod
    def valid_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError(
                "ชื่อผู้ใช้ต้องยาว 3–32 ตัว ใช้ได้เฉพาะ a-z 0-9 . _ - และขึ้นต้นด้วยตัวอักษรหรือตัวเลข"
            )
        return v

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LEN:
            raise ValueError(f"รหัสผ่านต้องยาวอย่างน้อย {MIN_PASSWORD_LEN} ตัว")
        return v

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ต้องกรอกชื่อที่แสดง")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ต้องกรอกชื่อที่แสดง")
        return v


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LEN:
            raise ValueError(f"รหัสผ่านใหม่ต้องยาวอย่างน้อย {MIN_PASSWORD_LEN} ตัว")
        return v


# --------------------------------------------------------------------------
# ledgers
# --------------------------------------------------------------------------
class LedgerTotals(BaseModel):
    total_in: Decimal = Decimal(0)
    total_out: Decimal = Decimal(0)
    balance: Decimal = Decimal(0)
    count: int = 0


class LedgerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = "cashflow"
    emoji: str | None = None
    note: str | None = None

    @field_validator("kind")
    @classmethod
    def known_kind(cls, v: str) -> str:
        if v not in LEDGER_KINDS:
            raise ValueError(f"ประเภทสมุดต้องเป็น {' หรือ '.join(LEDGER_KINDS)}")
        return v

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ต้องตั้งชื่อสมุด")
        return v


class LedgerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    emoji: str | None = None
    note: str | None = None
    archived: bool | None = None


class LedgerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    emoji: str | None
    note: str | None
    archived: bool
    owner: UserOut
    created_at: datetime
    # filled in by the router, not by the ORM
    my_role: str
    member_count: int = 1
    totals: LedgerTotals = LedgerTotals()


# --------------------------------------------------------------------------
# members
# --------------------------------------------------------------------------
class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user: UserOut
    role: str
    created_at: datetime


class MemberInvite(BaseModel):
    username: str
    role: str = ROLE_VIEWER

    @field_validator("username")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def invitable_role(cls, v: str) -> str:
        # Ownership transfer is not an invite; it is a separate, deliberate act.
        if v not in (ROLE_EDITOR, ROLE_VIEWER):
            raise ValueError("สิทธิ์ที่เชิญได้คือ editor หรือ viewer เท่านั้น")
        return v


class MemberRoleUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def assignable_role(cls, v: str) -> str:
        if v not in (ROLE_EDITOR, ROLE_VIEWER):
            raise ValueError("เปลี่ยนได้เป็น editor หรือ viewer เท่านั้น")
        return v


# --------------------------------------------------------------------------
# categories
# --------------------------------------------------------------------------
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    emoji: str | None = None
    sort_order: int = 100


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    emoji: str | None = None
    sort_order: int = 100
    keywords: list[str] = []


class CategorySuggestion(BaseModel):
    category: CategoryOut | None = None
    matched_keyword: str | None = None


# --------------------------------------------------------------------------
# entries
# --------------------------------------------------------------------------
def _localize(value: datetime) -> datetime:
    """A naive timestamp from the client means Bangkok wall-clock time."""
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ)
    return value


class EntryBase(BaseModel):
    occurred_at: datetime
    description: str = Field(min_length=1, max_length=255)
    # Always positive; the sign is carried by `direction`.
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    direction: str = "out"
    category_id: int | None = None
    note: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def ensure_tz(cls, v: datetime) -> datetime:
        return _localize(v)

    @field_validator("direction")
    @classmethod
    def known_direction(cls, v: str) -> str:
        if v not in DIRECTIONS:
            raise ValueError("direction ต้องเป็น in หรือ out")
        return v

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ต้องกรอกรายการ")
        return v


class EntryCreate(EntryBase):
    slip_path: str | None = None
    slip_ref: str | None = None
    source: str = "manual"
    ocr_raw_text: str | None = None
    ocr_confidence: str | None = None

    @field_validator("source")
    @classmethod
    def known_source(cls, v: str) -> str:
        if v not in {"manual", "ocr", "qr"}:
            raise ValueError("source ต้องเป็น manual, ocr หรือ qr")
        return v


class EntryUpdate(EntryBase):
    version: int
    slip_path: str | None = None


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ledger_id: int
    occurred_at: datetime
    description: str
    amount: Decimal
    direction: str
    note: str | None
    source: str
    version: int
    created_at: datetime
    updated_at: datetime
    category: CategoryOut | None
    created_by: UserOut
    slip_path: str | None


class EntryPage(BaseModel):
    items: list[EntryOut]
    total: int
    totals: LedgerTotals
    limit: int
    offset: int


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------
class CategoryTotal(BaseModel):
    category: CategoryOut | None
    total_in: Decimal
    total_out: Decimal
    count: int


class UserTotal(BaseModel):
    user: UserOut
    total_in: Decimal
    total_out: Decimal
    count: int


class LedgerSummary(BaseModel):
    """Serves both ledger kinds without branching.

    A cashflow book reads `period`; a debt book reads `lifetime.balance` as the
    amount still outstanding and `period` as this month's movement.
    """

    month: str  # "YYYY-MM" in Asia/Bangkok
    kind: str
    period: LedgerTotals
    lifetime: LedgerTotals
    by_category: list[CategoryTotal]
    by_user: list[UserTotal]


# --------------------------------------------------------------------------
# slips
# --------------------------------------------------------------------------
class SlipUploadResult(BaseModel):
    slip_path: str | None = None
    signed_url: str | None = None
    extraction_ok: bool = False
    provider: str = "none"
    source: str = "manual"
    confidence: str = "low"
    amount: Decimal | None = None
    occurred_at: datetime | None = None
    description: str | None = None
    slip_ref: str | None = None
    duplicate_of_id: int | None = None
    raw_text: str | None = None
    message: str | None = None
    suggestion: CategorySuggestion | None = None


class SignedUrlResponse(BaseModel):
    signed_url: str
    expires_in: int
