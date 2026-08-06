from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import settings

LOCAL_TZ = ZoneInfo(settings.app_timezone)


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


# --------------------------------------------------------------------------
# categories
# --------------------------------------------------------------------------
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    emoji: str | None = None
    sort_order: int = 100


class CategorySuggestion(BaseModel):
    category: CategoryOut | None = None
    matched_keyword: str | None = None


# --------------------------------------------------------------------------
# transactions
# --------------------------------------------------------------------------
def _localize(value: datetime) -> datetime:
    """A naive timestamp from the client means Bangkok wall-clock time."""
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ)
    return value


class TransactionBase(BaseModel):
    occurred_at: datetime
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    category_id: int | None = None
    note: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def ensure_tz(cls, v: datetime) -> datetime:
        return _localize(v)

    @field_validator("amount")
    @classmethod
    def non_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("จำนวนเงินต้องไม่เป็น 0")
        return v

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ต้องกรอกรายการ")
        return v


class TransactionCreate(TransactionBase):
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


class TransactionUpdate(TransactionBase):
    # The version the client last read. Mismatch => 409, so a concurrent edit
    # by the other person is surfaced instead of silently overwritten.
    version: int
    slip_path: str | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    description: str
    amount: Decimal
    note: str | None
    source: str
    version: int
    created_at: datetime
    updated_at: datetime
    category: CategoryOut | None
    added_by: UserOut
    slip_path: str | None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    total_amount: Decimal
    limit: int
    offset: int


class CategoryTotal(BaseModel):
    category: CategoryOut | None
    total: Decimal
    count: int


class UserTotal(BaseModel):
    user: UserOut
    total: Decimal
    count: int


class MonthlySummary(BaseModel):
    month: str  # "YYYY-MM" in Asia/Bangkok
    total: Decimal
    count: int
    by_category: list[CategoryTotal]
    by_user: list[UserTotal]


# --------------------------------------------------------------------------
# slips
# --------------------------------------------------------------------------
class SlipUploadResult(BaseModel):
    """Everything the entry form needs to prefill itself.

    `extraction_ok` false is a normal outcome, not an error: the form simply
    opens blank and the user types it in. The upload itself still succeeded.
    """

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
