"""End-to-end smoke test of the API, against a throwaway SQLite file.

Run: python -m tests.smoke        (from backend/, no services required)

Scope note — SQLite is a *test harness here, not a supported runtime*. Neon
Postgres is the database. The one thing this harness genuinely cannot check is
timezone semantics: SQLite has no TIMESTAMPTZ, so it silently drops the +07:00
offset and stores local wall-clock text, which makes any assertion about UTC
day/month boundaries meaningless (and misleadingly red). That maths lives in
app/timeutil.py and is covered by tests/test_timeutil.py instead.

Everything else here — auth, validation, dedupe, optimistic locking, filters,
aggregation, CSV, deletion — behaves identically on both engines.
"""

import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_FILE = Path(tempfile.gettempdir()) / "bank_smoke.sqlite3"
DB_FILE.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"
os.environ["JWT_SECRET"] = "smoke-secret"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["OCR_PROVIDER"] = "none"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CategoryKeyword, User  # noqa: E402
from app.security import hash_password  # noqa: E402

passed = failed = 0


def check(label: str, cond: bool, extra: object = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {extra}")


# --------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    db.add_all([
        User(username="bo", display_name="บอ", password_hash=hash_password("pw-bo")),
        User(username="fon", display_name="ฝน", password_hash=hash_password("pw-fon")),
    ])
    food = Category(name="อาหาร/เครื่องดื่ม", emoji="🍜", sort_order=10)
    travel = Category(name="เดินทาง", emoji="🚗", sort_order=20)
    db.add_all([food, travel])
    db.flush()
    db.add_all([
        CategoryKeyword(keyword="เซเว่น", category_id=food.id),
        CategoryKeyword(keyword="กาแฟ", category_id=food.id),
        CategoryKeyword(keyword="แกร็บ", category_id=travel.id),
    ])
    db.commit()

client = TestClient(app)

print("\n== meta ==")
r = client.get("/health")
check("/health 200", r.status_code == 200, r.text)
check("/health reports db ok", r.json().get("database") == "ok", r.text)
check("/health reports storage disabled", r.json().get("storage") == "disabled", r.text)
check("/openapi.json 200", client.get("/openapi.json").status_code == 200)

print("\n== auth ==")
check("no token -> 401", client.get("/auth/me").status_code == 401)
check("bad password -> 401", client.post(
    "/auth/login", json={"username": "bo", "password": "nope"}).status_code == 401)
check("unknown user -> 401", client.post(
    "/auth/login", json={"username": "ghost", "password": "x"}).status_code == 401)

r = client.post("/auth/login", json={"username": "bo", "password": "pw-bo"})
check("login 200", r.status_code == 200, r.text)
H_BO = {"Authorization": f"Bearer {r.json()['access_token']}"}
check("login returns the user", r.json()["user"]["display_name"] == "บอ", r.text)

r = client.post("/auth/login", json={"username": "fon", "password": "pw-fon"})
H_FON = {"Authorization": f"Bearer {r.json()['access_token']}"}

check("garbage token -> 401", client.get(
    "/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401)
check("/auth/me", client.get("/auth/me", headers=H_BO).json()["username"] == "bo")
check("/auth/users lists both", len(client.get("/auth/users", headers=H_BO).json()) == 2)

print("\n== categories ==")
cats = client.get("/categories", headers=H_BO).json()
check("lists categories", len(cats) == 2, cats)
food_id = next(c["id"] for c in cats if c["name"].startswith("อาหาร"))
travel_id = next(c["id"] for c in cats if c["name"] == "เดินทาง")

check("suggest: food", client.get("/categories/suggest", params={"text": "ซื้อกาแฟที่เซเว่น"},
                                  headers=H_BO).json()["category"]["id"] == food_id)
check("suggest: travel", client.get("/categories/suggest", params={"text": "เรียกแกร็บไปทำงาน"},
                                    headers=H_BO).json()["category"]["id"] == travel_id)
check("suggest: no match -> null", client.get(
    "/categories/suggest", params={"text": "ไม่มีคำไหนตรงเลย"},
    headers=H_BO).json()["category"] is None)
check("suggest: empty text -> null", client.get(
    "/categories/suggest", params={"text": ""}, headers=H_BO).json()["category"] is None)

print("\n== create + validation ==")
r = client.post("/transactions", headers=H_BO, json={
    "occurred_at": "2026-08-05T09:30:00",  # naive == Bangkok wall clock
    "description": "กาแฟเซเว่น", "amount": "45.00", "category_id": food_id})
check("create 201", r.status_code == 201, r.text)
tx1 = r.json()
check("added_by is the caller, not client-supplied", tx1["added_by"]["username"] == "bo")
check("version starts at 1", tx1["version"] == 1, tx1)
check("naive input gets +07:00", tx1["occurred_at"].endswith("+07:00"), tx1["occurred_at"])
check("defaults to source=manual", tx1["source"] == "manual", tx1)

r = client.post("/transactions", headers=H_FON, json={
    "occurred_at": "2026-08-06T12:00:00", "description": "แกร็บกลับบ้าน",
    "amount": "120.50", "category_id": travel_id})
tx2 = r.json()
check("second create 201", r.status_code == 201, r.text)

bad = {"occurred_at": "2026-08-06T10:00:00", "description": "x", "amount": "10"}
check("amount 0 -> 422", client.post(
    "/transactions", headers=H_BO, json={**bad, "amount": "0"}).status_code == 422)
check("blank description -> 422", client.post(
    "/transactions", headers=H_BO, json={**bad, "description": "   "}).status_code == 422)
check("unknown category -> 422", client.post(
    "/transactions", headers=H_BO, json={**bad, "category_id": 9999}).status_code == 422)
check("bogus source -> 422", client.post(
    "/transactions", headers=H_BO, json={**bad, "source": "telepathy"}).status_code == 422)
check("create needs auth", client.post("/transactions", json=bad).status_code == 401)

print("\n== dedupe by slip_ref ==")
dup = {"occurred_at": "2026-08-06T11:00:00", "description": "ค่าน้ำ",
       "amount": "300", "slip_ref": "SCB-REF-0001", "source": "qr"}
check("first slip 201", client.post(
    "/transactions", headers=H_BO, json=dup).status_code == 201)
r = client.post("/transactions", headers=H_FON, json=dup)
check("same slip from the other phone -> 409", r.status_code == 409, r.text)
check("409 points at the original", r.json()["detail"].get("duplicate_of_id") is not None, r.text)

print("\n== optimistic locking ==")
tid = tx1["id"]
edit = {"occurred_at": "2026-08-05T09:30:00", "description": "กาแฟเซเว่น (แก้แล้ว)",
        "amount": "50.00", "category_id": food_id, "version": 1}
r = client.put(f"/transactions/{tid}", headers=H_BO, json=edit)
check("first edit 200", r.status_code == 200, r.text)
check("version bumped to 2", r.json()["version"] == 2, r.text)
check("edit applied", Decimal(r.json()["amount"]) == Decimal("50.00"), r.text)

r = client.put(f"/transactions/{tid}", headers=H_FON, json=edit)  # still claims version 1
check("stale edit -> 409, not silent overwrite", r.status_code == 409, r.text)
check("409 reports the live version", r.json()["detail"].get("current_version") == 2, r.text)
check("the other person's edit survived",
      Decimal(client.get(f"/transactions/{tid}", headers=H_FON).json()["amount"])
      == Decimal("50.00"))

check("retry with fresh version 200", client.put(
    f"/transactions/{tid}", headers=H_FON, json={**edit, "version": 2}).status_code == 200)
check("edit missing row -> 404", client.put(
    "/transactions/99999", headers=H_BO, json={**edit, "version": 1}).status_code == 404)

print("\n== filters ==")
page = client.get("/transactions", params={"month": "2026-08"}, headers=H_BO).json()
check("month filter finds all 3", page["total"] == 3, page["total"])
# 50.00 (edited) + 120.50 + 300 — the sum covers the whole filter, not one page
check("page total_amount sums the filter, not the page",
      Decimal(page["total_amount"]) == Decimal("470.50"), page["total_amount"])
check("newest first", page["items"][0]["id"] == tx2["id"],
      [i["description"] for i in page["items"]])
check("empty month -> 0", client.get(
    "/transactions", params={"month": "2026-07"}, headers=H_BO).json()["total"] == 0)
check("malformed month -> 422", client.get(
    "/transactions", params={"month": "aug"}, headers=H_BO).status_code == 422)
check("filter by person", client.get(
    "/transactions", params={"added_by_id": tx2["added_by"]["id"]},
    headers=H_BO).json()["total"] == 1)
check("filter by category", client.get(
    "/transactions", params={"category_id": travel_id}, headers=H_BO).json()["total"] == 1)
check("text search on description", client.get(
    "/transactions", params={"q": "แกร็บ"}, headers=H_BO).json()["total"] == 1)
check("single-day filter", client.get(
    "/transactions", params={"date_from": "2026-08-05", "date_to": "2026-08-05"},
    headers=H_BO).json()["total"] == 1)
check("pagination", client.get(
    "/transactions", params={"limit": 2}, headers=H_BO).json()["total"] == 3)
check("limit caps the page", len(client.get(
    "/transactions", params={"limit": 2}, headers=H_BO).json()["items"]) == 2)

print("\n== summary ==")
s = client.get("/transactions/summary", params={"month": "2026-08"}, headers=H_BO).json()
check("summary total", Decimal(s["total"]) == Decimal("470.50"), s["total"])
check("summary count", s["count"] == 3, s)
check("grouped by both people", len(s["by_user"]) == 2, s["by_user"])
check("category totals present", len(s["by_category"]) >= 2, s["by_category"])
check("summary defaults to the current month",
      client.get("/transactions/summary", headers=H_BO).status_code == 200)

print("\n== export ==")
r = client.get("/transactions/export.csv", params={"month": "2026-08"}, headers=H_BO)
check("csv 200", r.status_code == 200)
check("utf-8 BOM so Excel reads Thai", r.content.startswith(b"\xef\xbb\xbf"), r.content[:6])
check("header + 3 rows", len(r.content.decode("utf-8-sig").strip().splitlines()) == 4)
check("served as a download", "attachment" in r.headers.get("content-disposition", ""))

print("\n== slips (storage disabled) ==")
check("no slip on this tx -> 404",
      client.get(f"/transactions/{tid}/slip", headers=H_BO).status_code == 404)
r = client.post("/slips/upload", headers=H_BO,
                files={"file": ("s.jpg", b"not-an-image", "image/jpeg")})
check("undecodable upload -> 400, never 500", r.status_code == 400, r.status_code)
r = client.post("/slips/upload", headers=H_BO,
                files={"file": ("s.txt", b"hello", "text/plain")})
check("non-image rejected", r.status_code == 400, r.status_code)

print("\n== delete ==")
check("delete 204", client.delete(f"/transactions/{tid}", headers=H_FON).status_code == 204)
check("then gone", client.get(f"/transactions/{tid}", headers=H_BO).status_code == 404)
check("delete twice -> 404", client.delete(f"/transactions/{tid}", headers=H_BO).status_code == 404)

print(f"\n{'=' * 46}\n  {passed} passed, {failed} failed\n{'=' * 46}")
sys.exit(1 if failed else 0)
