from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    """Fixed set of accounts (two, for now). No self-signup endpoint exists."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="added_by")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    emoji: Mapped[str | None] = mapped_column(String(8))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    keywords: Mapped[list["CategoryKeyword"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class CategoryKeyword(Base):
    """keyword -> category. Drives the auto-suggest on the entry form."""

    __tablename__ = "category_keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    # stored lowercase; matching is a case-insensitive substring test
    keyword: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    # ties are broken by priority first, then by longer keyword
    priority: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped["Category"] = relationship(back_populates="keywords")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Always stored as UTC-aware; rendered in settings.app_timezone.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    description: Mapped[str] = mapped_column(String(255))
    # Numeric, never float. Positive = money out; negative allowed for refunds.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    added_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text)

    # --- slip ---
    # Object path inside the private Supabase bucket, never a public URL.
    # Signed URLs are minted per request and are not persisted.
    slip_path: Mapped[str | None] = mapped_column(String(400))
    # Transaction reference decoded from the slip's QR code. Unique so that
    # two people photographing the same slip cannot both log it.
    # Postgres allows unlimited NULLs in a UNIQUE column, so manual entries
    # without a slip are unaffected.
    slip_ref: Mapped[str | None] = mapped_column(String(120), unique=True)

    # --- provenance (kept even while OCR is disabled) ---
    # "manual" | "ocr" | "qr" — lets us measure real extraction accuracy later
    source: Mapped[str] = mapped_column(String(16), default="manual")
    ocr_raw_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[str | None] = mapped_column(String(16))

    # --- optimistic locking ---
    # Bumped on every update. A client PUTting a stale version gets a 409
    # instead of silently clobbering the other person's edit.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    added_by: Mapped["User"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship()


# Dashboard queries are almost always "this month, newest first".
Index("ix_transactions_occurred_at_desc", Transaction.occurred_at.desc())
