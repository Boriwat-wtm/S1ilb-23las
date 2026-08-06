"""Data model.

Shape of the thing: a user owns any number of **ledgers**. A ledger is private
until its owner invites someone into it, and membership carries a role. Nothing
is visible across ledger boundaries — that isolation is the security surface of
this app and every query below is scoped through `ledger_members`.

Two ledger kinds share one entry model, because they turn out to be the same
arithmetic:

    cashflow   in = รายรับ      out = รายจ่าย     balance = Σin − Σout
    debt       in = หนี้เพิ่ม    out = จ่ายคืน      balance = Σin − Σout  (คงค้าง)

Only the labels and the way a ledger is summarised differ, so there is one
`entries` table and no special-casing in the write path.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# --- ledger kinds ---
KIND_CASHFLOW = "cashflow"
KIND_DEBT = "debt"
LEDGER_KINDS = (KIND_CASHFLOW, KIND_DEBT)

# --- entry directions ---
DIR_IN = "in"
DIR_OUT = "out"
DIRECTIONS = (DIR_IN, DIR_OUT)

# --- membership roles, most privileged first ---
ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
ROLES = (ROLE_OWNER, ROLE_EDITOR, ROLE_VIEWER)

CAN_EDIT = (ROLE_OWNER, ROLE_EDITOR)
CAN_ADMIN = (ROLE_OWNER,)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    # JWTs are stateless, so there is nothing to revoke when a password
    # changes. Comparing a token's `iat` against this is what makes "changing
    # my password signs out my other devices" actually true.
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # LedgerMember points at users twice (the member, and who invited them),
    # so the join has to be spelled out.
    memberships: Mapped[list["LedgerMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="LedgerMember.user_id",
    )


class Ledger(Base):
    __tablename__ = "ledgers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16), default=KIND_CASHFLOW)
    emoji: Mapped[str | None] = mapped_column(String(8))
    note: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship()
    members: Mapped[list["LedgerMember"]] = relationship(
        back_populates="ledger", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"kind in ('{KIND_CASHFLOW}', '{KIND_DEBT}')", name="ck_ledger_kind"
        ),
    )


class LedgerMember(Base):
    """Who can see a ledger, and what they may do in it.

    Every read and write goes through a row here. The owner always has a row
    too, so there is exactly one way to answer "may this user touch this
    ledger" and no second code path to forget about.
    """

    __tablename__ = "ledger_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(
        ForeignKey("ledgers.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default=ROLE_VIEWER)
    invited_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ledger: Mapped["Ledger"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(
        back_populates="memberships", foreign_keys=[user_id]
    )
    invited_by: Mapped["User | None"] = relationship(foreign_keys=[invited_by_id])

    __table_args__ = (
        UniqueConstraint("ledger_id", "user_id", name="uq_member_once_per_ledger"),
        CheckConstraint(
            f"role in ('{ROLE_OWNER}', '{ROLE_EDITOR}', '{ROLE_VIEWER}')",
            name="ck_member_role",
        ),
    )


class Category(Base):
    """Categories belong to a ledger, not to the installation.

    A debt ledger and a groceries ledger have nothing useful to say to each
    other, and a shared global list would leak one member's custom categories
    into someone else's private book.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(
        ForeignKey("ledgers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    emoji: Mapped[str | None] = mapped_column(String(8))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    keywords: Mapped[list["CategoryKeyword"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("ledger_id", "name", name="uq_category_name_per_ledger"),
    )


class CategoryKeyword(Base):
    __tablename__ = "category_keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(
        ForeignKey("ledgers.id", ondelete="CASCADE"), index=True
    )
    keyword: Mapped[str] = mapped_column(String(80))
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped["Category"] = relationship(back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("ledger_id", "keyword", name="uq_keyword_per_ledger"),
    )


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(
        ForeignKey("ledgers.id", ondelete="CASCADE"), index=True
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str] = mapped_column(String(255))
    # Always positive. Sign lives in `direction` so that a debt ledger and a
    # cashflow ledger can share the same aggregate: Σin − Σout.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    direction: Mapped[str] = mapped_column(String(4), default=DIR_OUT)

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text)

    # --- slip ---
    slip_path: Mapped[str | None] = mapped_column(String(400))
    # Scoped per ledger, not globally unique. A global constraint would let one
    # user discover, via a 409, that a slip they hold was already filed in
    # someone else's private ledger.
    slip_ref: Mapped[str | None] = mapped_column(String(120))

    # --- provenance ---
    source: Mapped[str] = mapped_column(String(16), default="manual")
    ocr_raw_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[str | None] = mapped_column(String(16))

    # --- optimistic locking ---
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_by: Mapped["User"] = relationship()
    category: Mapped["Category | None"] = relationship()
    ledger: Mapped["Ledger"] = relationship()

    __table_args__ = (
        UniqueConstraint("ledger_id", "slip_ref", name="uq_slip_ref_per_ledger"),
        CheckConstraint(
            f"direction in ('{DIR_IN}', '{DIR_OUT}')", name="ck_entry_direction"
        ),
        CheckConstraint("amount > 0", name="ck_entry_amount_positive"),
    )


# The listing is always "one ledger, newest first". Declared out here because
# Entry.occurred_at is only an orderable attribute after the class exists.
Index("ix_entries_ledger_occurred", Entry.ledger_id, Entry.occurred_at.desc())
