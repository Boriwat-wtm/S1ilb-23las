from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from sqlalchemy import Numeric, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from ..deps import CurrentUser, DbSession, LedgerAdmin, LedgerRead
from ..ledger_defaults import seed_ledger_categories
from ..models import (
    DIR_IN,
    DIR_OUT,
    ROLE_OWNER,
    Entry,
    Ledger,
    LedgerMember,
    User,
)
from ..schemas import (
    LedgerCreate,
    LedgerOut,
    LedgerTotals,
    LedgerUpdate,
    MemberInvite,
    MemberOut,
    MemberRoleUpdate,
    UserOut,
)
from ..storage import delete_slip

router = APIRouter(prefix="/ledgers", tags=["ledgers"])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _sum_direction(direction: str):
    return func.coalesce(
        func.sum(case((Entry.direction == direction, Entry.amount), else_=0)),
        0,
    ).cast(Numeric(14, 2))


def totals_for(db, ledger_ids: list[int]) -> dict[int, LedgerTotals]:
    """One grouped query for every ledger, rather than N per-ledger queries."""
    if not ledger_ids:
        return {}
    rows = db.execute(
        select(
            Entry.ledger_id,
            _sum_direction(DIR_IN),
            _sum_direction(DIR_OUT),
            func.count(Entry.id),
        )
        .where(Entry.ledger_id.in_(ledger_ids))
        .group_by(Entry.ledger_id)
    ).all()
    return {
        ledger_id: LedgerTotals(
            total_in=Decimal(tin),
            total_out=Decimal(tout),
            balance=Decimal(tin) - Decimal(tout),
            count=count,
        )
        for ledger_id, tin, tout, count in rows
    }


def member_counts_for(db, ledger_ids: list[int]) -> dict[int, int]:
    if not ledger_ids:
        return {}
    rows = db.execute(
        select(LedgerMember.ledger_id, func.count(LedgerMember.id))
        .where(LedgerMember.ledger_id.in_(ledger_ids))
        .group_by(LedgerMember.ledger_id)
    ).all()
    return dict(rows)


def _to_out(ledger: Ledger, role: str, totals: LedgerTotals, members: int) -> LedgerOut:
    return LedgerOut(
        id=ledger.id,
        name=ledger.name,
        kind=ledger.kind,
        emoji=ledger.emoji,
        note=ledger.note,
        archived=ledger.archived,
        owner=UserOut.model_validate(ledger.owner),
        created_at=ledger.created_at,
        my_role=role,
        member_count=members,
        totals=totals,
    )


# --------------------------------------------------------------------------
# ledgers
# --------------------------------------------------------------------------
@router.get("", response_model=list[LedgerOut])
def list_my_ledgers(
    db: DbSession,
    current_user: CurrentUser,
    include_archived: bool = Query(False),
) -> list[LedgerOut]:
    """Only ledgers the caller is a member of. There is no endpoint that lists
    anyone else's, and no way to reach one by guessing an id."""
    stmt = (
        select(Ledger, LedgerMember.role)
        .join(LedgerMember, LedgerMember.ledger_id == Ledger.id)
        .options(joinedload(Ledger.owner))
        .where(LedgerMember.user_id == current_user.id)
        .order_by(Ledger.archived, Ledger.created_at.desc())
    )
    if not include_archived:
        stmt = stmt.where(Ledger.archived.is_(False))

    rows = db.execute(stmt).all()
    ids = [ledger.id for ledger, _ in rows]
    totals = totals_for(db, ids)
    counts = member_counts_for(db, ids)

    return [
        _to_out(ledger, role, totals.get(ledger.id, LedgerTotals()), counts.get(ledger.id, 1))
        for ledger, role in rows
    ]


@router.post("", response_model=LedgerOut, status_code=status.HTTP_201_CREATED)
def create_ledger(
    payload: LedgerCreate, db: DbSession, current_user: CurrentUser
) -> LedgerOut:
    ledger = Ledger(
        name=payload.name,
        kind=payload.kind,
        emoji=payload.emoji,
        note=payload.note,
        owner_id=current_user.id,
    )
    db.add(ledger)
    db.flush()

    # The owner gets a normal membership row, so permission checks have exactly
    # one shape and there is no "unless you own it" branch anywhere.
    db.add(
        LedgerMember(ledger_id=ledger.id, user_id=current_user.id, role=ROLE_OWNER)
    )
    seed_ledger_categories(db, ledger.id, ledger.kind)
    db.commit()
    db.refresh(ledger)

    return _to_out(ledger, ROLE_OWNER, LedgerTotals(), 1)


@router.get("/{ledger_id}", response_model=LedgerOut)
def get_ledger(ctx: LedgerRead, db: DbSession) -> LedgerOut:
    totals = totals_for(db, [ctx.ledger.id]).get(ctx.ledger.id, LedgerTotals())
    counts = member_counts_for(db, [ctx.ledger.id]).get(ctx.ledger.id, 1)
    return _to_out(ctx.ledger, ctx.role, totals, counts)


@router.patch("/{ledger_id}", response_model=LedgerOut)
def update_ledger(payload: LedgerUpdate, ctx: LedgerAdmin, db: DbSession) -> LedgerOut:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(ctx.ledger, field, value)
    db.commit()
    db.refresh(ctx.ledger)

    totals = totals_for(db, [ctx.ledger.id]).get(ctx.ledger.id, LedgerTotals())
    counts = member_counts_for(db, [ctx.ledger.id]).get(ctx.ledger.id, 1)
    return _to_out(ctx.ledger, ctx.role, totals, counts)


@router.delete("/{ledger_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ledger(
    ctx: LedgerAdmin, db: DbSession, background_tasks: BackgroundTasks
) -> Response:
    """Deletes the book and everything in it. Entries, categories and
    memberships cascade; slip objects are cleaned up afterwards, best effort."""
    slip_paths = (
        db.execute(
            select(Entry.slip_path).where(
                Entry.ledger_id == ctx.ledger.id, Entry.slip_path.is_not(None)
            )
        )
        .scalars()
        .all()
    )

    db.delete(ctx.ledger)
    db.commit()

    for path in slip_paths:
        background_tasks.add_task(delete_slip, path)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# members
# --------------------------------------------------------------------------
@router.get("/{ledger_id}/members", response_model=list[MemberOut])
def list_members(ctx: LedgerRead, db: DbSession) -> list[MemberOut]:
    """Any member can see who else is in the book — being able to see who is
    reading your finances is part of the point."""
    rows = (
        db.execute(
            select(LedgerMember)
            .options(joinedload(LedgerMember.user))
            .where(LedgerMember.ledger_id == ctx.ledger.id)
            .order_by(LedgerMember.created_at)
        )
        .scalars()
        .all()
    )
    return [MemberOut.model_validate(m) for m in rows]


@router.post(
    "/{ledger_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED
)
def invite_member(payload: MemberInvite, ctx: LedgerAdmin, db: DbSession) -> MemberOut:
    user = db.execute(
        select(User).where(User.username == payload.username)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ไม่พบผู้ใช้ '{payload.username}' — ให้เขาสมัครก่อนแล้วค่อยเชิญ",
        )
    if user.id == ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="คุณอยู่ในสมุดนี้อยู่แล้ว"
        )

    member = LedgerMember(
        ledger_id=ctx.ledger.id,
        user_id=user.id,
        role=payload.role,
        invited_by_id=ctx.user.id,
    )
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.username}' อยู่ในสมุดนี้แล้ว",
        ) from None

    db.refresh(member)
    return MemberOut.model_validate(member)


@router.patch("/{ledger_id}/members/{member_id}", response_model=MemberOut)
def update_member_role(
    member_id: int, payload: MemberRoleUpdate, ctx: LedgerAdmin, db: DbSession
) -> MemberOut:
    member = db.get(LedgerMember, member_id)
    if member is None or member.ledger_id != ctx.ledger.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบสมาชิกคนนี้"
        )
    if member.role == ROLE_OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="เปลี่ยนสิทธิ์ของเจ้าของสมุดไม่ได้",
        )

    member.role = payload.role
    db.commit()
    db.refresh(member)
    return MemberOut.model_validate(member)


@router.delete("/{ledger_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_id: int, ctx: LedgerRead, db: DbSession) -> Response:
    """The owner can remove anyone; anyone can remove themselves (leave)."""
    member = db.get(LedgerMember, member_id)
    if member is None or member.ledger_id != ctx.ledger.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบสมาชิกคนนี้"
        )

    removing_self = member.user_id == ctx.user.id
    if not (ctx.can_admin or removing_self):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="เฉพาะเจ้าของสมุดเท่านั้นที่เอาคนอื่นออกได้",
        )
    if member.role == ROLE_OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="เจ้าของออกจากสมุดตัวเองไม่ได้ ถ้าไม่ใช้แล้วให้เก็บเข้าคลังหรือลบทิ้ง",
        )

    db.delete(member)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
