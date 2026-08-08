"""Prove both API keys work, before wiring anything to them.

Neither provider has ever been exercised against the live services — there was
no key here to test with. This is the first thing to run once there is one,
because the failure modes are all boring and all easier to read here than
through the app: a key restricted to the wrong API, a model id that has been
retired, billing not enabled, the API not turned on in the project.

    python -m scripts.check_ai              # both, using backend/.env
    python -m scripts.check_ai --vision     # just OCR
    python -m scripts.check_ai --tagger     # just category guessing
    python -m scripts.check_ai --slip path/to/real-slip.jpg
    python -m scripts.check_ai --compare   # ลองทุกโมเดล free tier แล้วเทียบ
    python -m scripts.check_ai --models    # ถาม API ว่าคีย์นี้เรียกโมเดลไหนได้บ้าง

With no --slip, Vision is tested against a slip this script draws itself.
That checks the key, the request shape and the parser end to end, but it says
nothing about real-world accuracy: a rendered image is clean type on white,
and a photograph of a phone screen is not. Run it once with --slip and a real
photo before trusting the numbers it fills in.
"""

import argparse
import asyncio
import io
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.ocr import GoogleVisionProvider  # noqa: E402
from app.slip_parser import parse_slip_text  # noqa: E402
from app.tagger import GeminiTagger  # noqa: E402

OK, BAD, INFO = "  ok  ", " FAIL ", "      "

SLIP_LINES = [
    ("K PLUS", 34),
    ("โอนเงินสำเร็จ", 26),
    ("08 ส.ค. 68  14:23", 22),
    ("", 10),
    ("จาก  นาย บอริวัฒน์ ว", 20),
    ("ธนาคารกสิกรไทย  xxx-x-x1234-x", 18),
    ("", 10),
    ("ไปยัง  ร้านกาแฟดอยช้าง", 20),
    ("พร้อมเพย์  010556xxxx", 18),
    ("", 14),
    ("จำนวนเงิน  85.50 บาท", 26),
    ("ค่าธรรมเนียม  0.00 บาท", 18),
    ("", 10),
    ("รหัสอ้างอิง 015082568142312345", 16),
]

CATEGORIES = [
    "อาหาร/เครื่องดื่ม", "เดินทาง", "บ้าน/บิล", "ของใช้ในบ้าน",
    "สุขภาพ", "บันเทิง", "ช้อปปิ้ง", "สัตว์เลี้ยง", "อื่นๆ",
]

# Names the seeded keyword table gets wrong, with the category a person would
# obviously pick. Having an expected answer is what turns "it replied" into a
# measurement — and the awkward ones are deliberate: Konvy is cosmetics not
# food, iCloud+ is a subscription not a phone bill, and ChatGPT Plus is the
# kind of name a model can talk itself into filing anywhere.
UNKNOWN_SHOPS = [
    ("After You สาขาสยาม", "อาหาร/เครื่องดื่ม"),
    ("บริษัท ซีพี ออลล์ จำกัด (มหาชน)", "อาหาร/เครื่องดื่ม"),
    ("Tops Daily", "อาหาร/เครื่องดื่ม"),
    ("ตัดผม", "อื่นๆ"),
    ("ค่างวดรถ Toyota Leasing", "เดินทาง"),
    ("Konvy", "ช้อปปิ้ง"),
    ("iCloud+", "บันเทิง"),
    ("ร้านขายยาฟาสซิโน", "สุขภาพ"),
    ("อาหารแมว Whiskas", "สัตว์เลี้ยง"),
    ("การประปานครหลวง", "บ้าน/บิล"),
]

# Worth comparing on a free key. Google does not publish per-model limits —
# the docs point at AI Studio — so the numbers below came from reading that
# dashboard directly, and the scores from running this script.
#
#   gemma-4-26b-a4b-it     30 RPM   14,400 RPD    10/10 on three runs
#   gemini-3.1-flash-lite  15 RPM      500 RPD    8, 6, 8
#   gemini-3.5-flash-lite  15 RPM      500 RPD    7, 6
#   gemini-3.5-flash        5 RPM       20 RPD    twenty a day is not a tier
#   gemma-4-31b-it         30 RPM   14,400 RPD    ignores responseSchema
#
# The last one is kept in the list on purpose: it fails loudly here rather
# than quietly in production, and it is the counterexample to "pick the bigger
# model".
CANDIDATE_MODELS = [
    "gemma-4-26b-a4b-it",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemma-4-31b-it",
]


def draw_slip() -> bytes:
    """Render a plausible Thai transfer slip. Clean type, not a photograph."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 620, 900
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font_path = r"C:\Windows\Fonts\LeelawUI.ttf"

    y = 60
    for text, size in SLIP_LINES:
        if text:
            try:
                font = ImageFont.truetype(font_path, size)
            except OSError:
                font = ImageFont.load_default()
            draw.text((50, y), text, font=font, fill=(20, 20, 20))
        y += size + 18

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


async def check_vision(slip_path: str | None) -> bool:
    print("\n=== Google Vision (อ่านสลิป) ===")
    if not settings.google_vision_api_key:
        print(BAD, "ยังไม่ได้ตั้ง GOOGLE_VISION_API_KEY ใน backend/.env")
        return False
    print(INFO, f"key ...{settings.google_vision_api_key[-6:]}")

    if slip_path:
        data = Path(slip_path).read_bytes()
        print(INFO, f"ใช้สลิปจริง: {slip_path} ({len(data):,} bytes)")
    else:
        data = draw_slip()
        print(INFO, f"ใช้สลิปที่วาดขึ้นเอง ({len(data):,} bytes) — ไม่ใช่รูปถ่ายจริง")

    result = await GoogleVisionProvider().extract(data)

    if result.error:
        print(BAD, result.error)
        return False
    if not result.raw_text:
        print(BAD, "เรียก API ผ่าน แต่ไม่ได้ข้อความกลับมาเลย")
        return False

    print(OK, "เรียก API สำเร็จ")
    print(INFO, "--- ข้อความที่อ่านได้ ---")
    for line in result.raw_text.strip().splitlines()[:20]:
        print(INFO, f"  {line}")

    parsed = parse_slip_text(result.raw_text)
    print(INFO, "--- แกะออกมาได้ ---")
    for label, value in (
        ("จำนวนเงิน", parsed["amount"]),
        ("วันเวลา", parsed["occurred_at"]),
        ("ผู้รับ", parsed["description"]),
        ("เลขอ้างอิง", parsed["reference"]),
    ):
        mark = OK if value is not None else INFO
        print(mark, f"{label:<12} {value if value is not None else '— อ่านไม่ออก'}")

    # An amount that comes back wrong is worse than one that comes back empty,
    # so the synthetic case asserts the exact figure it drew.
    if not slip_path:
        from decimal import Decimal

        if parsed["amount"] == Decimal("85.50"):
            print(OK, "ยอดตรงกับที่วาดไว้ (85.50)")
        else:
            print(BAD, f"ยอดไม่ตรง — วาดไว้ 85.50 ได้ {parsed['amount']}")
            return False
    return True


async def list_models() -> bool:
    """Ask the key what it can actually reach.

    Google does not publish per-model free-tier limits — the docs say to look
    in AI Studio — and the third-party numbers floating around disagree with
    each other. This is the part that *is* authoritative: the API will say
    exactly which models this key may call. The per-minute figures still have
    to be read from aistudio.google.com/rate-limit, which is per account.
    """
    print("\n=== โมเดลที่คีย์นี้เรียกได้จริง ===")
    if not settings.gemini_api_key:
        print(BAD, "ยังไม่ได้ตั้ง GEMINI_API_KEY ใน backend/.env")
        return False

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": settings.gemini_api_key, "pageSize": 200},
        )
    if resp.status_code != 200:
        print(BAD, f"เรียกไม่สำเร็จ ({resp.status_code}) {resp.text[:160]}")
        return False

    models = resp.json().get("models", [])
    usable = [
        m
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
        and "gemini" in m.get("name", "")
    ]
    # Newest generations first, lite before full — that ordering is roughly
    # the order worth trying for a cheap classification job.
    usable.sort(key=lambda m: m.get("name", ""), reverse=True)

    print(INFO, f"ทั้งหมด {len(models)} โมเดล · เรียก generateContent ได้ {len(usable)}")
    print(INFO, "")
    for m in usable:
        mid = m["name"].removeprefix("models/")
        if "lite" not in mid and "flash" not in mid:
            continue
        limit = m.get("inputTokenLimit", "?")
        print(INFO, f"  {mid:<44} context {limit:>9}")

    print(INFO, "")
    print(INFO, "RPM/RPD ของบัญชีคุณดูที่ https://aistudio.google.com/rate-limit")
    print(INFO, "เอกสาร Google ไม่ประกาศตัวเลขนี้ และ blog ข้างนอกก็ขัดกันเอง")
    return True


async def score_model(model: str) -> tuple[int, int, float, list[str]]:
    """Run the whole shop list through one model. Returns hits, total, seconds
    and the lines to print."""
    original = settings.gemini_model
    settings.gemini_model = model
    tagger = GeminiTagger()
    lines: list[str] = []
    hits = 0
    started = time.perf_counter()
    try:
        for shop, expected in UNKNOWN_SHOPS:
            tag = await tagger.tag(shop, CATEGORIES)
            if tag.error:
                lines.append(f"{BAD}{shop:<34} {tag.error}")
                continue
            good = tag.category_name == expected
            hits += good
            mark = OK if good else BAD
            got = tag.category_name if good else f"{tag.category_name}  (คาดว่า {expected})"
            lines.append(f"{mark}{shop:<34} -> {got}   คำที่จำ {tag.keyword!r}")
    finally:
        settings.gemini_model = original
    return hits, len(UNKNOWN_SHOPS), time.perf_counter() - started, lines


async def check_tagger(models: list[str]) -> bool:
    print("\n=== Gemini (เดาหมวดหมู่) ===")
    if not settings.gemini_api_key:
        print(BAD, "ยังไม่ได้ตั้ง GEMINI_API_KEY ใน backend/.env")
        return False
    print(INFO, f"key ...{settings.gemini_api_key[-6:]}")

    scores = []
    for model in models:
        print(f"\n--- {model} ---")
        hits, total, secs, lines = await score_model(model)
        for line in lines:
            print(line)
        per_call = secs / total if total else 0
        print(INFO, f"ถูก {hits}/{total}   ใช้เวลา {secs:.1f}s   เฉลี่ย {per_call:.2f}s/ครั้ง")
        scores.append((model, hits, total, per_call))

    if len(scores) > 1:
        print("\n=== เทียบกัน ===")
        print(INFO, f"{'model':<26} {'ถูก':>7}   {'วินาที/ครั้ง':>12}")
        for model, hits, total, per_call in sorted(
            scores, key=lambda s: (-s[1], s[3])
        ):
            print(INFO, f"{model:<26} {hits:>3}/{total:<3}   {per_call:>12.2f}")
        print(INFO, "")
        print(INFO, "เท่ากันเมื่อไหร่ให้เลือกตัวที่เร็วกว่า — งานนี้ไม่ต้องใช้โมเดลฉลาด")
        print(INFO, "RPM ของ free tier ดูได้ที่ aistudio.google.com เอกสารไม่ได้ระบุไว้")

    return any(hits > 0 for _, hits, _, _ in scores)


async def main() -> int:
    parser = argparse.ArgumentParser(description="ทดสอบ API key ของ Vision และ Gemini")
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--tagger", action="store_true")
    parser.add_argument("--slip", metavar="PATH", help="ทดสอบด้วยรูปสลิปจริง")
    parser.add_argument(
        "--model",
        metavar="ID",
        help="โมเดลที่จะลอง คั่นด้วย comma (ไม่ใส่ = ใช้ GEMINI_MODEL)",
    )
    parser.add_argument(
        "--models",
        action="store_true",
        help="ถาม API ว่าคีย์นี้เรียกโมเดลไหนได้ (ไม่กินโควตาการเดา)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="ลองทุกโมเดล free tier กับชุดเดียวกัน แล้วเทียบผล",
    )
    args = parser.parse_args()

    if args.models:
        return 0 if await list_models() else 1

    run_vision = args.vision or not (args.tagger or args.compare)
    run_tagger = args.tagger or args.compare or not args.vision

    if args.compare:
        models = CANDIDATE_MODELS
    elif args.model:
        models = [m.strip() for m in args.model.split(",") if m.strip()]
    else:
        models = [settings.gemini_model]

    results = []
    if run_vision:
        results.append(await check_vision(args.slip))
    if run_tagger:
        results.append(await check_tagger(models))

    print()
    if all(results):
        print("ผ่านทั้งหมด — ตั้ง OCR_PROVIDER=google และ TAGGER_PROVIDER=gemini ได้เลย")
        return 0
    print("มีอันที่ยังไม่ผ่าน ดูข้อความข้างบน")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
