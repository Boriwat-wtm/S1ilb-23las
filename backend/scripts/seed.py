"""Create tables, and optionally a demo account to poke at.

Signup is public now, so seeding users is a development convenience rather than
a deployment step. Against Neon the only thing this is really needed for is
`--tables-only`, which creates the schema before the first request arrives.

Usage (from backend/):
    python -m scripts.seed --tables-only
    python -m scripts.seed --demo
    python -m scripts.seed --reset-password bow=newsecret
"""

import argparse
import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.ledger_defaults import seed_ledger_categories  # noqa: E402
from app.models import (  # noqa: E402
    KIND_CASHFLOW,
    KIND_DEBT,
    ROLE_EDITOR,
    ROLE_OWNER,
    Ledger,
    LedgerMember,
    User,
)
from app.security import hash_password  # noqa: E402


def random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_or_create_user(db, username: str, display_name: str, password: str) -> User:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user:
        print(f"  = ผู้ใช้ {username!r} มีอยู่แล้ว")
        return user
    user = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    print(f"  + ผู้ใช้ {username!r} ({display_name})  รหัสผ่าน: {password}")
    return user


def create_ledger(db, owner: User, name: str, kind: str, emoji: str) -> Ledger:
    existing = db.execute(
        select(Ledger).where(Ledger.owner_id == owner.id, Ledger.name == name)
    ).scalar_one_or_none()
    if existing:
        print(f"  = สมุด {name!r} มีอยู่แล้ว")
        return existing

    ledger = Ledger(name=name, kind=kind, emoji=emoji, owner_id=owner.id)
    db.add(ledger)
    db.flush()
    db.add(LedgerMember(ledger_id=ledger.id, user_id=owner.id, role=ROLE_OWNER))
    seed_ledger_categories(db, ledger.id, kind)
    print(f"  + สมุด {emoji} {name} ({kind})")
    return ledger


def seed_demo(db) -> None:
    print("→ ผู้ใช้ตัวอย่าง")
    bow = get_or_create_user(db, "bow", "บอ", "demo1234")
    fon = get_or_create_user(db, "fon", "ฝน", "demo1234")

    print("→ สมุดตัวอย่าง")
    private = create_ledger(db, bow, "ของฉัน", KIND_CASHFLOW, "🔒")
    shared = create_ledger(db, bow, "บ้านเรา", KIND_CASHFLOW, "🏠")
    debt = create_ledger(db, bow, "หนี้รถ", KIND_DEBT, "🚙")

    # fon is an editor on the shared book only — the private one and the debt
    # book stay invisible to them, which is the whole point of the model.
    for ledger in (shared,):
        exists = db.execute(
            select(LedgerMember).where(
                LedgerMember.ledger_id == ledger.id, LedgerMember.user_id == fon.id
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                LedgerMember(
                    ledger_id=ledger.id,
                    user_id=fon.id,
                    role=ROLE_EDITOR,
                    invited_by_id=bow.id,
                )
            )
            print(f"  + เชิญ fon เข้า {ledger.name!r} เป็น editor")

    db.commit()
    print(f"\n  bow เห็น 3 สมุด / fon เห็นแค่ {shared.name!r}")


def reset_password(db, spec: str) -> None:
    if "=" not in spec:
        raise SystemExit("--reset-password ต้องเป็นรูปแบบ username=newpassword")
    username, _, new_pw = spec.partition("=")
    user = db.execute(
        select(User).where(User.username == username.strip().lower())
    ).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"ไม่พบผู้ใช้ {username!r}")
    user.password_hash = hash_password(new_pw)
    db.commit()
    print(f"  ✓ เปลี่ยนรหัสผ่านของ {user.username} แล้ว")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Bank database")
    parser.add_argument("--tables-only", action="store_true", help="สร้างตารางอย่างเดียว")
    parser.add_argument("--demo", action="store_true", help="สร้างผู้ใช้+สมุดตัวอย่าง")
    parser.add_argument("--reset-password", metavar="user=newpass")
    args = parser.parse_args()

    print("→ สร้างตาราง (ถ้ายังไม่มี)")
    Base.metadata.create_all(bind=engine)

    if args.tables_only:
        print("เสร็จแล้ว")
        return

    with SessionLocal() as db:
        if args.reset_password:
            reset_password(db, args.reset_password)
            return
        if args.demo:
            seed_demo(db)
        else:
            print("\nไม่ได้ระบุอะไรเพิ่ม — signup เปิดสาธารณะแล้ว สมัครผ่านหน้าเว็บได้เลย")
            print("ถ้าอยากได้ข้อมูลตัวอย่างสำหรับ dev ใช้:  python -m scripts.seed --demo")

    print("เสร็จแล้ว")


if __name__ == "__main__":
    main()
