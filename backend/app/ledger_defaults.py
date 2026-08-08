"""Starter categories copied into a ledger when it is created.

Copied, not shared: categories live inside a ledger, so each book can be
renamed and pruned without touching anyone else's. The cost is a few dozen
duplicated keyword rows per ledger, which is nothing next to the alternative of
one member's custom category showing up in someone else's private book.
"""

from sqlalchemy.orm import Session

from .models import KIND_CASHFLOW, KIND_DEBT, KW_SEED, Category, CategoryKeyword

# (name, emoji, sort_order, keywords)
CASHFLOW_CATEGORIES: list[tuple[str, str, int, list[str]]] = [
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
    ("เงินเดือน/รายรับ", "💰", 100, [
        "เงินเดือน", "salary", "โบนัส", "bonus", "ค่าจ้าง", "ฟรีแลนซ์", "freelance",
        "ขายของ", "ดอกเบี้ยรับ",
    ]),
    ("อื่นๆ", "💸", 999, []),
]

DEBT_CATEGORIES: list[tuple[str, str, int, list[str]]] = [
    ("บัตรเครดิต", "💳", 10, ["บัตรเครดิต", "credit card", "บัตร"]),
    ("เงินกู้ธนาคาร", "🏦", 20, ["เงินกู้", "สินเชื่อ", "ธนาคาร", "loan"]),
    ("ผ่อนสินค้า", "📱", 30, ["ผ่อน", "installment", "มือถือ", "โน้ตบุ๊ก"]),
    ("ผ่อนรถ", "🚙", 40, ["ค่างวดรถ", "ผ่อนรถ", "ลีสซิ่ง"]),
    ("ผ่อนบ้าน", "🏡", 50, ["ผ่อนบ้าน", "คอนโด", "จำนอง"]),
    ("ยืมคนรู้จัก", "👥", 60, ["ยืม", "ขอยืม", "ติดไว้"]),
    ("ดอกเบี้ย/ค่าปรับ", "📈", 70, ["ดอกเบี้ย", "ค่าปรับ", "ค่าธรรมเนียม"]),
    ("อื่นๆ", "💸", 999, []),
]

TEMPLATES = {
    KIND_CASHFLOW: CASHFLOW_CATEGORIES,
    KIND_DEBT: DEBT_CATEGORIES,
}


def seed_ledger_categories(db: Session, ledger_id: int, kind: str) -> None:
    """Populate a brand-new ledger. Caller commits."""
    for name, emoji, sort_order, keywords in TEMPLATES.get(kind, CASHFLOW_CATEGORIES):
        category = Category(
            ledger_id=ledger_id, name=name, emoji=emoji, sort_order=sort_order
        )
        db.add(category)
        db.flush()
        for kw in keywords:
            db.add(
                CategoryKeyword(
                    ledger_id=ledger_id,
                    keyword=kw.lower().strip(),
                    category_id=category.id,
                    source=KW_SEED,
                )
            )
