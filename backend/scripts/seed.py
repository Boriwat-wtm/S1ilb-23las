"""Seed the database: two fixed accounts + the starter category keyword map.

Safe to re-run. Existing users are never touched (except via --reset-password)
and existing categories/keywords are matched by name and left alone.

Usage (from backend/):
    python -m scripts.seed
    python -m scripts.seed --reset-password boriwat=newsecret

Accounts come from the SEED_USERS env var:
    SEED_USERS="boriwat:บอ:secret1,fon:ฝน:secret2"     # user:display:password
If it is unset, random passwords are generated and printed once.
"""

import argparse
import os
import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Category, CategoryKeyword, User  # noqa: E402
from app.security import hash_password  # noqa: E402

# --------------------------------------------------------------------------
# starter category map — edit freely, re-running only adds what is missing
# --------------------------------------------------------------------------
CATEGORIES: list[tuple[str, str, int, list[str]]] = [
    ("อาหาร/เครื่องดื่ม", "🍜", 10, [
        "เซเว่น", "7-11", "seven", "โลตัส", "lotus", "บิ๊กซี", "big c", "แม็คโคร", "makro",
        "kfc", "mcdonald", "แมค", "พิซซ่า", "pizza", "starbucks", "สตาร์บัค",
        "อเมซอน", "amazon", "กาแฟ", "coffee", "ชานม", "ข้าว", "ก๋วยเตี๋ยว",
        "หมูกระทะ", "ชาบู", "ส้มตำ", "grabfood", "lineman", "foodpanda", "robinhood",
    ]),
    ("เดินทาง", "🚗", 20, [
        "แกร็บ", "grab", "bolt", "taxi", "แท็กซี่", "bts", "mrt", "รถไฟฟ้า",
        "วิน", "มอเตอร์ไซค์", "น้ำมัน", "ปตท", "ptt", "บางจาก", "shell", "เชลล์",
        "esso", "caltex", "ทางด่วน", "easy pass", "ที่จอดรถ",
    ]),
    ("บ้าน/บิล", "🏠", 30, [
        "ค่าไฟ", "การไฟฟ้า", "ค่าน้ำ", "การประปา", "ค่าเช่า", "ค่าห้อง", "ส่วนกลาง",
        "internet", "อินเทอร์เน็ต", "true", "ais", "dtac", "ค่าโทรศัพท์",
    ]),
    ("ของใช้ในบ้าน", "🧺", 40, [
        "watsons", "วัตสัน", "boots", "ikea", "homepro", "โฮมโปร", "ไทวัสดุ",
        "ผงซักฟอก", "ทิชชู่", "น้ำยา",
    ]),
    ("สุขภาพ", "💊", 50, [
        "โรงพยาบาล", "คลินิก", "ร้านยา", "หมอ", "ทันตกรรม", "ฟิตเนส", "fitness", "ยิม",
    ]),
    ("บันเทิง", "🎬", 60, [
        "netflix", "spotify", "youtube", "disney", "viu", "iqiyi", "เกม", "steam",
        "โรงหนัง", "major", "หนัง",
    ]),
    ("ช้อปปิ้ง", "👕", 70, [
        "shopee", "ช้อปปี้", "lazada", "ลาซาด้า", "tiktok", "uniqlo", "h&m", "zara",
        "เสื้อ", "รองเท้า",
    ]),
    ("สัตว์เลี้ยง", "🐱", 80, [
        "อาหารแมว", "อาหารหมา", "petshop", "สัตวแพทย์", "ทรายแมว",
    ]),
    ("ของขวัญ/สังสรรค์", "🎁", 90, [
        "ของขวัญ", "งานแต่ง", "ทำบุญ", "ซองงาน", "วันเกิด",
    ]),
    ("อื่นๆ", "💸", 999, []),
]


def random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def parse_seed_users() -> list[tuple[str, str, str | None]]:
    raw = os.getenv("SEED_USERS", "").strip()
    if not raw:
        return [("boriwat", "บอ", None), ("partner", "แฟน", None)]

    out: list[tuple[str, str, str | None]] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) != 3:
            raise SystemExit(f"SEED_USERS รูปแบบผิดที่ {chunk!r} (ต้องเป็น user:display:password)")
        out.append((parts[0].strip().lower(), parts[1].strip(), parts[2]))
    return out


def seed_users(db) -> None:
    created: list[tuple[str, str]] = []
    for username, display_name, password in parse_seed_users():
        existing = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        if existing:
            print(f"  = user {username!r} มีอยู่แล้ว ข้าม")
            continue
        pw = password or random_password()
        db.add(
            User(
                username=username,
                display_name=display_name,
                password_hash=hash_password(pw),
            )
        )
        created.append((username, pw if not password else "(จาก SEED_USERS)"))
        print(f"  + user {username!r} ({display_name})")
    db.commit()

    generated = [(u, p) for u, p in created if p != "(จาก SEED_USERS)"]
    if generated:
        print("\n  ⚠ รหัสผ่านที่สุ่มให้ — แสดงครั้งเดียว เก็บไว้เดี๋ยวนี้:")
        for username, pw in generated:
            print(f"      {username} : {pw}")
        print()


def seed_categories(db) -> None:
    for name, emoji, sort_order, keywords in CATEGORIES:
        category = db.execute(
            select(Category).where(Category.name == name)
        ).scalar_one_or_none()
        if category is None:
            category = Category(name=name, emoji=emoji, sort_order=sort_order)
            db.add(category)
            db.flush()
            print(f"  + category {emoji} {name}")

        for kw in keywords:
            kw = kw.lower().strip()
            exists = db.execute(
                select(CategoryKeyword).where(CategoryKeyword.keyword == kw)
            ).scalar_one_or_none()
            if exists is None:
                db.add(
                    CategoryKeyword(
                        keyword=kw, category_id=category.id, priority=0
                    )
                )
    db.commit()


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
    parser.add_argument("--reset-password", metavar="user=newpass")
    parser.add_argument(
        "--skip-users", action="store_true", help="seed แต่หมวดหมู่อย่างเดียว"
    )
    args = parser.parse_args()

    print("→ สร้างตาราง (ถ้ายังไม่มี)")
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if args.reset_password:
            reset_password(db, args.reset_password)
            return
        if not args.skip_users:
            print("→ ผู้ใช้")
            seed_users(db)
        print("→ หมวดหมู่ + keywords")
        seed_categories(db)

    print("เสร็จแล้ว")


if __name__ == "__main__":
    main()
