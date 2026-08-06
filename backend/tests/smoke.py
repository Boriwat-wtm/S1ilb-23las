"""End-to-end smoke test, against a throwaway SQLite file.

Run: python -m tests.smoke        (from backend/, no services required)

The centre of gravity is the **isolation** section. Now that anyone can sign up
and ledgers are private by default, "user B cannot reach user A's book" is the
security property this app lives or dies by, so it is tested from every angle:
listing, reading, writing, category reuse, slip URLs, and member management.

Scope note — SQLite is a test harness here, not a supported runtime. Neon
Postgres is the database. The one thing this cannot check is timezone
semantics: SQLite has no TIMESTAMPTZ, so it drops the +07:00 offset and stores
local wall-clock text, which makes assertions about UTC day/month boundaries
meaningless. That maths lives in app/timeutil.py and is covered by
tests/test_timeutil.py instead.
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

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402

passed = failed = 0


def check(label: str, cond: bool, extra: object = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {extra}")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


Base.metadata.create_all(bind=engine)
client = TestClient(app)

# --------------------------------------------------------------------------
print("\n== signup ==")
r = client.post("/auth/register", json={
    "username": "bow", "display_name": "บอ", "password": "demo1234"})
check("register 201", r.status_code == 201, r.text)
BOW = auth(r.json()["access_token"])
check("register returns a session", r.json()["user"]["username"] == "bow", r.text)

r = client.post("/auth/register", json={
    "username": "fon", "display_name": "ฝน", "password": "demo1234"})
FON = auth(r.json()["access_token"])
check("second register 201", r.status_code == 201, r.text)

r = client.post("/auth/register", json={
    "username": "mallory", "display_name": "คนนอก", "password": "demo1234"})
MAL = auth(r.json()["access_token"])
check("third register 201", r.status_code == 201, r.text)

check("duplicate username -> 409", client.post("/auth/register", json={
    "username": "bow", "display_name": "x", "password": "demo1234"}).status_code == 409)
check("short password -> 422", client.post("/auth/register", json={
    "username": "shorty", "display_name": "x", "password": "abc"}).status_code == 422)
check("bad username charset -> 422", client.post("/auth/register", json={
    "username": "Bad Name!", "display_name": "x", "password": "demo1234"}).status_code == 422)
check("username too short -> 422", client.post("/auth/register", json={
    "username": "ab", "display_name": "x", "password": "demo1234"}).status_code == 422)

print("\n== login ==")
check("wrong password -> 401", client.post(
    "/auth/login", json={"username": "bow", "password": "nope"}).status_code == 401)
check("unknown user -> 401", client.post(
    "/auth/login", json={"username": "ghost", "password": "demo1234"}).status_code == 401)
r = client.post("/auth/login", json={"username": "bow", "password": "demo1234"})
check("login 200", r.status_code == 200, r.text)
check("no token -> 401", client.get("/auth/me").status_code == 401)
check("garbage token -> 401", client.get(
    "/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401)

print("\n== profile ==")
r = client.patch("/auth/me", headers=BOW, json={"display_name": "  บอ (แก้ชื่อ)  "})
check("update display name 200", r.status_code == 200, r.text)
check("display name is trimmed", r.json()["display_name"] == "บอ (แก้ชื่อ)", r.text)
check("username is unchanged", r.json()["username"] == "bow", r.text)
check("blank display name -> 422", client.patch(
    "/auth/me", headers=BOW, json={"display_name": "   "}).status_code == 422)
check("profile update needs auth",
      client.patch("/auth/me", json={"display_name": "x"}).status_code == 401)
client.patch("/auth/me", headers=BOW, json={"display_name": "บอ"})

print("\n== change password ==")
# A second session for the same account, to prove the change reaches it.
OTHER_DEVICE = auth(
    client.post("/auth/login", json={"username": "bow", "password": "demo1234"})
    .json()["access_token"]
)
check("the other device works before the change",
      client.get("/auth/me", headers=OTHER_DEVICE).status_code == 200)

check("wrong current password -> 400", client.post("/auth/password", headers=BOW, json={
    "current_password": "wrong", "new_password": "newsecret1"}).status_code == 400)
check("short new password -> 422", client.post("/auth/password", headers=BOW, json={
    "current_password": "demo1234", "new_password": "abc"}).status_code == 422)
check("reusing the same password -> 400", client.post("/auth/password", headers=BOW, json={
    "current_password": "demo1234", "new_password": "demo1234"}).status_code == 400)

r = client.post("/auth/password", headers=BOW, json={
    "current_password": "demo1234", "new_password": "newsecret1"})
check("change password 200", r.status_code == 200, r.text)
BOW = auth(r.json()["access_token"])

check("the caller stays signed in on its fresh token",
      client.get("/auth/me", headers=BOW).status_code == 200)
check("every other device is signed out",
      client.get("/auth/me", headers=OTHER_DEVICE).status_code == 401)
check("the old password no longer works", client.post(
    "/auth/login", json={"username": "bow", "password": "demo1234"}).status_code == 401)
check("the new one does", client.post(
    "/auth/login", json={"username": "bow", "password": "newsecret1"}).status_code == 200)

print("\n== ledgers ==")
r = client.post("/ledgers", headers=BOW, json={
    "name": "ของฉัน", "kind": "cashflow", "emoji": "🔒"})
check("create cashflow ledger 201", r.status_code == 201, r.text)
PRIVATE = r.json()
check("creator is owner", PRIVATE["my_role"] == "owner", PRIVATE)
check("starts empty", PRIVATE["totals"]["count"] == 0, PRIVATE["totals"])

r = client.post("/ledgers", headers=BOW, json={
    "name": "บ้านเรา", "kind": "cashflow", "emoji": "🏠"})
SHARED = r.json()
r = client.post("/ledgers", headers=BOW, json={
    "name": "หนี้รถ", "kind": "debt", "emoji": "🚙"})
DEBT = r.json()
check("create debt ledger 201", r.status_code == 201, r.text)

check("bad kind -> 422", client.post("/ledgers", headers=BOW, json={
    "name": "x", "kind": "crypto"}).status_code == 422)
check("blank name -> 422", client.post("/ledgers", headers=BOW, json={
    "name": "   "}).status_code == 422)

check("bo sees 3 ledgers", len(client.get("/ledgers", headers=BOW).json()) == 3)
check("fon sees none yet", len(client.get("/ledgers", headers=FON).json()) == 0)
check("ledger list needs auth", client.get("/ledgers").status_code == 401)

print("\n== default categories per kind ==")
cash_cats = client.get(f"/ledgers/{PRIVATE['id']}/categories", headers=BOW).json()
debt_cats = client.get(f"/ledgers/{DEBT['id']}/categories", headers=BOW).json()
check("cashflow ledger gets cashflow categories",
      any(c["name"].startswith("อาหาร") for c in cash_cats), [c["name"] for c in cash_cats])
check("debt ledger gets debt categories",
      any(c["name"] == "บัตรเครดิต" for c in debt_cats), [c["name"] for c in debt_cats])
check("debt ledger has no food category",
      not any(c["name"].startswith("อาหาร") for c in debt_cats))
check("categories are per-ledger, not shared",
      {c["id"] for c in cash_cats}.isdisjoint({c["id"] for c in debt_cats}))

FOOD = next(c["id"] for c in cash_cats if c["name"].startswith("อาหาร"))
CARD = next(c["id"] for c in debt_cats if c["name"] == "บัตรเครดิต")

print("\n== isolation: a stranger cannot reach someone else's ledger ==")
pid = PRIVATE["id"]
check("GET ledger -> 404 (not 403, which would confirm it exists)",
      client.get(f"/ledgers/{pid}", headers=MAL).status_code == 404)
check("list entries -> 404", client.get(
    f"/ledgers/{pid}/entries", headers=MAL).status_code == 404)
check("create entry -> 404", client.post(f"/ledgers/{pid}/entries", headers=MAL, json={
    "occurred_at": "2026-08-06T10:00:00", "description": "แอบลง",
    "amount": "10", "direction": "out"}).status_code == 404)
check("list categories -> 404", client.get(
    f"/ledgers/{pid}/categories", headers=MAL).status_code == 404)
check("category suggest -> 404", client.get(
    f"/ledgers/{pid}/categories/suggest?text=กาแฟ", headers=MAL).status_code == 404)
check("summary -> 404", client.get(
    f"/ledgers/{pid}/entries/summary", headers=MAL).status_code == 404)
check("csv export -> 404", client.get(
    f"/ledgers/{pid}/entries/export.csv", headers=MAL).status_code == 404)
check("member list -> 404", client.get(
    f"/ledgers/{pid}/members", headers=MAL).status_code == 404)
check("invite themselves in -> 404", client.post(
    f"/ledgers/{pid}/members", headers=MAL,
    json={"username": "mallory", "role": "editor"}).status_code == 404)
check("rename it -> 404", client.patch(
    f"/ledgers/{pid}", headers=MAL, json={"name": "ของฉันแล้ว"}).status_code == 404)
check("delete it -> 404", client.delete(f"/ledgers/{pid}", headers=MAL).status_code == 404)
check("slip upload -> 404", client.post(
    f"/ledgers/{pid}/slips/upload", headers=MAL,
    files={"file": ("s.jpg", b"x", "image/jpeg")}).status_code == 404)
check("nonexistent ledger id -> 404 too (indistinguishable)",
      client.get("/ledgers/999999", headers=MAL).status_code == 404)

print("\n== invite + roles ==")
sid = SHARED["id"]
r = client.post(f"/ledgers/{sid}/members", headers=BOW,
                json={"username": "fon", "role": "editor"})
check("invite editor 201", r.status_code == 201, r.text)
FON_MEMBER_ID = r.json()["id"]
check("invited with the right role", r.json()["role"] == "editor", r.text)

check("fon now sees exactly 1 ledger", len(client.get("/ledgers", headers=FON).json()) == 1)
check("fon still cannot see bow's private book",
      client.get(f"/ledgers/{pid}", headers=FON).status_code == 404)
check("fon still cannot see the debt book",
      client.get(f"/ledgers/{DEBT['id']}", headers=FON).status_code == 404)

check("inviting an unknown username -> 404", client.post(
    f"/ledgers/{sid}/members", headers=BOW,
    json={"username": "nobody", "role": "viewer"}).status_code == 404)
check("inviting twice -> 409", client.post(
    f"/ledgers/{sid}/members", headers=BOW,
    json={"username": "fon", "role": "viewer"}).status_code == 409)
check("inviting as owner role -> 422", client.post(
    f"/ledgers/{sid}/members", headers=BOW,
    json={"username": "mallory", "role": "owner"}).status_code == 422)
check("a non-owner member cannot invite", client.post(
    f"/ledgers/{sid}/members", headers=FON,
    json={"username": "mallory", "role": "viewer"}).status_code == 403)

print("\n== entries ==")
r = client.post(f"/ledgers/{sid}/entries", headers=BOW, json={
    "occurred_at": "2026-08-05T09:30:00", "description": "กาแฟเซเว่น",
    "amount": "45.00", "direction": "out"})
check("owner can write", r.status_code == 201, r.text)
E1 = r.json()
check("version starts at 1", E1["version"] == 1, E1)
check("naive time gets +07:00", E1["occurred_at"].endswith("+07:00"), E1["occurred_at"])
check("records who wrote it", E1["created_by"]["username"] == "bow", E1)

r = client.post(f"/ledgers/{sid}/entries", headers=FON, json={
    "occurred_at": "2026-08-06T12:00:00", "description": "เงินเดือน",
    "amount": "30000", "direction": "in"})
check("editor can write", r.status_code == 201, r.text)
E2 = r.json()
check("attributed to the editor, not the owner", E2["created_by"]["username"] == "fon")

bad = {"occurred_at": "2026-08-06T10:00:00", "description": "x", "amount": "10"}
check("amount 0 -> 422", client.post(
    f"/ledgers/{sid}/entries", headers=BOW, json={**bad, "amount": "0"}).status_code == 422)
check("negative amount -> 422", client.post(
    f"/ledgers/{sid}/entries", headers=BOW, json={**bad, "amount": "-5"}).status_code == 422)
check("blank description -> 422", client.post(
    f"/ledgers/{sid}/entries", headers=BOW, json={**bad, "description": " "}).status_code == 422)
check("bad direction -> 422", client.post(
    f"/ledgers/{sid}/entries", headers=BOW, json={**bad, "direction": "sideways"}).status_code == 422)

print("\n== a category from another ledger cannot be attached ==")
check("foreign category -> 422", client.post(f"/ledgers/{sid}/entries", headers=BOW, json={
    **bad, "category_id": CARD}).status_code == 422)
check("own category is fine", client.post(f"/ledgers/{sid}/entries", headers=BOW, json={
    **bad, "description": "ข้าวเที่ยง",
    "category_id": client.get(f"/ledgers/{sid}/categories", headers=BOW).json()[0]["id"],
}).status_code == 201)

print("\n== viewer is read-only ==")
r = client.post(f"/ledgers/{sid}/members", headers=BOW,
                json={"username": "mallory", "role": "viewer"})
MAL_MEMBER_ID = r.json()["id"]
check("viewer added", r.status_code == 201, r.text)
check("viewer can read", client.get(f"/ledgers/{sid}/entries", headers=MAL).json()["total"] == 3)
check("viewer cannot create -> 403", client.post(f"/ledgers/{sid}/entries", headers=MAL, json={
    "occurred_at": "2026-08-06T10:00:00", "description": "แอบลง",
    "amount": "10", "direction": "out"}).status_code == 403)
check("viewer cannot edit -> 403", client.put(
    f"/ledgers/{sid}/entries/{E1['id']}", headers=MAL,
    json={**E1, "version": E1["version"], "amount": "1"}).status_code == 403)
check("viewer cannot delete -> 403", client.delete(
    f"/ledgers/{sid}/entries/{E1['id']}", headers=MAL).status_code == 403)
check("viewer cannot rename the ledger -> 403", client.patch(
    f"/ledgers/{sid}", headers=MAL, json={"name": "x"}).status_code == 403)
check("viewer can see who else is in the book",
      len(client.get(f"/ledgers/{sid}/members", headers=MAL).json()) == 3)

print("\n== role changes and leaving ==")
check("owner promotes viewer to editor", client.patch(
    f"/ledgers/{sid}/members/{MAL_MEMBER_ID}", headers=BOW,
    json={"role": "editor"}).status_code == 200)
check("...and they can now write", client.post(f"/ledgers/{sid}/entries", headers=MAL, json={
    "occurred_at": "2026-08-06T13:00:00", "description": "ค่าน้ำ",
    "amount": "300", "direction": "out"}).status_code == 201)
check("owner's own role cannot be changed", client.patch(
    f"/ledgers/{sid}/members/{client.get(f'/ledgers/{sid}/members', headers=BOW).json()[0]['id']}",
    headers=BOW, json={"role": "viewer"}).status_code == 400)
check("a member can remove themselves", client.delete(
    f"/ledgers/{sid}/members/{MAL_MEMBER_ID}", headers=MAL).status_code == 204)
check("...and immediately loses all access",
      client.get(f"/ledgers/{sid}/entries", headers=MAL).status_code == 404)
check("owner cannot leave their own ledger", client.delete(
    f"/ledgers/{sid}/members/{client.get(f'/ledgers/{sid}/members', headers=BOW).json()[0]['id']}",
    headers=BOW).status_code == 400)

# Re-add mallory as a third party so removal-by-a-peer can be tested without
# the actor removing themselves, which is always allowed.
r = client.post(f"/ledgers/{sid}/members", headers=BOW,
                json={"username": "mallory", "role": "viewer"})
check("a non-owner member cannot remove someone else", client.delete(
    f"/ledgers/{sid}/members/{r.json()['id']}", headers=FON).status_code == 403)
check("...and the owner still can", client.delete(
    f"/ledgers/{sid}/members/{r.json()['id']}", headers=BOW).status_code == 204)
check("fon is still a member throughout",
      client.get(f"/ledgers/{sid}", headers=FON).status_code == 200)

print("\n== balances: same arithmetic for both kinds ==")
page = client.get(f"/ledgers/{sid}/entries", headers=BOW).json()
t = page["totals"]
# in 30000, out 45 + 10 + 300
check("total_in", Decimal(t["total_in"]) == Decimal("30000"), t)
check("total_out", Decimal(t["total_out"]) == Decimal("355"), t)
check("balance = in - out", Decimal(t["balance"]) == Decimal("29645"), t)

did = DEBT["id"]
client.post(f"/ledgers/{did}/entries", headers=BOW, json={
    "occurred_at": "2026-06-01T10:00:00", "description": "กู้ซื้อรถ",
    "amount": "300000", "direction": "in", "category_id": CARD})
for month in ("06", "07", "08"):
    client.post(f"/ledgers/{did}/entries", headers=BOW, json={
        "occurred_at": f"2026-{month}-25T10:00:00", "description": "ค่างวด",
        "amount": "7500", "direction": "out"})

s = client.get(f"/ledgers/{did}/entries/summary?month=2026-08", headers=BOW).json()
check("debt: lifetime balance is what is still owed",
      Decimal(s["lifetime"]["balance"]) == Decimal("277500"), s["lifetime"])
check("debt: period shows just this month's movement",
      Decimal(s["period"]["total_out"]) == Decimal("7500"), s["period"])
check("summary reports the ledger kind", s["kind"] == "debt", s)

print("\n== slip_ref dedupe is scoped per ledger ==")
slip = {"occurred_at": "2026-08-06T11:00:00", "description": "ค่าไฟ",
        "amount": "800", "direction": "out", "slip_ref": "SCB-REF-0001", "source": "qr"}
check("first use 201", client.post(
    f"/ledgers/{sid}/entries", headers=BOW, json=slip).status_code == 201)
r = client.post(f"/ledgers/{sid}/entries", headers=FON, json=slip)
check("same ref, same ledger -> 409", r.status_code == 409, r.text)
check("409 names the original", r.json()["detail"].get("duplicate_of_id") is not None)
check("same ref in a DIFFERENT ledger is allowed — a global unique would leak "
      "that a slip is already filed in someone else's book",
      client.post(f"/ledgers/{pid}/entries", headers=BOW, json=slip).status_code == 201)

print("\n== optimistic locking ==")
eid = E1["id"]
edit = {"occurred_at": "2026-08-05T09:30:00", "description": "กาแฟเซเว่น (แก้)",
        "amount": "50.00", "direction": "out", "version": 1}
r = client.put(f"/ledgers/{sid}/entries/{eid}", headers=BOW, json=edit)
check("first edit 200", r.status_code == 200, r.text)
check("version bumped", r.json()["version"] == 2, r.text)
r = client.put(f"/ledgers/{sid}/entries/{eid}", headers=FON, json=edit)
check("stale edit -> 409", r.status_code == 409, r.text)
check("409 reports the live version", r.json()["detail"].get("current_version") == 2)
check("the first edit survived", Decimal(client.get(
    f"/ledgers/{sid}/entries/{eid}", headers=FON).json()["amount"]) == Decimal("50.00"))
check("retry with fresh version 200", client.put(
    f"/ledgers/{sid}/entries/{eid}", headers=FON,
    json={**edit, "version": 2}).status_code == 200)

print("\n== entry ids do not cross ledgers ==")
check("reading a shared-book entry via the private book -> 404",
      client.get(f"/ledgers/{pid}/entries/{eid}", headers=BOW).status_code == 404)
check("editing it through the wrong ledger -> 404", client.put(
    f"/ledgers/{pid}/entries/{eid}", headers=BOW, json={**edit, "version": 3}).status_code == 404)
check("deleting it through the wrong ledger -> 404", client.delete(
    f"/ledgers/{pid}/entries/{eid}", headers=BOW).status_code == 404)

print("\n== filters, suggest, export ==")
check("filter direction=in", client.get(
    f"/ledgers/{sid}/entries?direction=in", headers=BOW).json()["total"] == 1)
check("filter by person", client.get(
    f"/ledgers/{sid}/entries?created_by_id={E2['created_by']['id']}",
    headers=BOW).json()["total"] == 1)
check("text search", client.get(
    f"/ledgers/{sid}/entries?q=กาแฟ", headers=BOW).json()["total"] == 1)
check("month filter", client.get(
    f"/ledgers/{sid}/entries?month=2026-08", headers=BOW).json()["total"] == 5)
check("empty month", client.get(
    f"/ledgers/{sid}/entries?month=2026-01", headers=BOW).json()["total"] == 0)
check("malformed month -> 422", client.get(
    f"/ledgers/{sid}/entries?month=aug", headers=BOW).status_code == 422)
check("pagination caps the page", len(client.get(
    f"/ledgers/{sid}/entries?limit=2", headers=BOW).json()["items"]) == 2)

# Note this is the *shared* ledger's food category, a different row from the
# private ledger's FOOD — which is the per-ledger isolation working.
SHARED_FOOD = next(
    c["id"]
    for c in client.get(f"/ledgers/{sid}/categories", headers=BOW).json()
    if c["name"].startswith("อาหาร")
)
check("suggest is scoped to this ledger's own categories", SHARED_FOOD != FOOD)
r = client.get(f"/ledgers/{sid}/categories/suggest?text=ซื้อกาแฟที่เซเว่น", headers=BOW).json()
check("suggest matches", r["category"] is not None and r["category"]["id"] == SHARED_FOOD, r)
check("suggest reports the keyword", r["matched_keyword"] == "เซเว่น", r)
check("suggest miss -> null", client.get(
    f"/ledgers/{sid}/categories/suggest?text=ไม่มีคำไหนตรง", headers=BOW).json()["category"] is None)

r = client.get(f"/ledgers/{did}/entries/export.csv", headers=BOW)
check("csv 200 for a Thai-named ledger", r.status_code == 200, r.text[:200])
check("utf-8 BOM for Excel", r.content.startswith(b"\xef\xbb\xbf"))
cd = r.headers.get("content-disposition", "")
check("filename is latin-1 safe with an RFC 5987 utf-8 form",
      "filename=" in cd and "filename*=UTF-8''" in cd, cd)
check("header is actually encodable", cd.encode("latin-1") is not None)
body = r.content.decode("utf-8-sig")
check("debt csv uses debt wording", "หนี้เพิ่ม" in body and "จ่ายคืน" in body, body[:200])
cash_csv = client.get(f"/ledgers/{sid}/entries/export.csv", headers=BOW).content.decode("utf-8-sig")
check("cashflow csv uses cashflow wording", "รายรับ" in cash_csv and "รายจ่าย" in cash_csv)

print("\n== slips (storage disabled) ==")
check("undecodable image -> 400, never 500", client.post(
    f"/ledgers/{sid}/slips/upload", headers=BOW,
    files={"file": ("s.jpg", b"not-an-image", "image/jpeg")}).status_code == 400)
check("non-image rejected", client.post(
    f"/ledgers/{sid}/slips/upload", headers=BOW,
    files={"file": ("s.txt", b"hello", "text/plain")}).status_code == 400)
check("entry without a slip -> 404", client.get(
    f"/ledgers/{sid}/entries/{eid}/slip", headers=BOW).status_code == 404)

print("\n== delete ==")
check("editor can delete an entry", client.delete(
    f"/ledgers/{sid}/entries/{eid}", headers=FON).status_code == 204)
check("then gone", client.get(
    f"/ledgers/{sid}/entries/{eid}", headers=BOW).status_code == 404)
check("non-owner cannot delete the ledger", client.delete(
    f"/ledgers/{sid}", headers=FON).status_code == 403)
check("owner can", client.delete(f"/ledgers/{sid}", headers=BOW).status_code == 204)
check("the ledger is gone for its members too",
      client.get(f"/ledgers/{sid}/entries", headers=FON).status_code == 404)
check("and drops off their list", len(client.get("/ledgers", headers=FON).json()) == 0)

print("\n== rate limiter ==")
rl = RateLimiter(max_hits=3, window_seconds=60, message="too many")
for i in range(3):
    rl.check("1.2.3.4")
try:
    rl.check("1.2.3.4")
    check("blocks over the limit", False, "no 429 raised")
except Exception as exc:  # HTTPException
    check("blocks over the limit", getattr(exc, "status_code", None) == 429, exc)
    check("sends Retry-After", "Retry-After" in getattr(exc, "headers", {}) or {})
rl.check("5.6.7.8")
check("limits are per-key", True)

print("\n== meta ==")
h = client.get("/health").json()
check("/health db ok", h.get("database") == "ok", h)
check("/openapi.json 200", client.get("/openapi.json").status_code == 200)

print(f"\n{'=' * 52}\n  {passed} passed, {failed} failed\n{'=' * 52}")
sys.exit(1 if failed else 0)
