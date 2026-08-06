# Bank — บัญชีรายจ่ายสองคน

แอปบันทึกรายจ่ายร่วมสำหรับสองคน อัปโหลดสลิป → กรอก/แก้ → ดูสรุปรายเดือน
ติดตั้งบนมือถือเป็น PWA

```
React (Vercel)  ──HTTPS──▶  FastAPI (Render)  ──▶  Postgres (Neon)
                                    │
                                    └──▶  Supabase Storage (private bucket)
```

| ส่วน | ที่อยู่ | Free tier ที่ต้องเฝ้า |
|---|---|---|
| Frontend | Vercel | – |
| Backend | Render | 750 ชม./เดือน, 0.1 vCPU, 512MB, sleep หลังไม่ใช้ 15 นาที |
| Database | Neon | 0.5GB, autosuspend หลัง idle |
| รูปสลิป | Supabase Storage (private) | 1GB |

---

## สถานะ

| Phase | สถานะ |
|---|---|
| 0 — บัญชี/เครื่องมือ | 🔲 ผู้ใช้ทำเอง (Vercel / Render / Neon / Supabase) |
| 1 — Schema + Backend | ✅ เสร็จ |
| 1.5 — Deploy hello-world ทะลุทั้งสาย | 🔲 |
| 2 — OCR | ⏸️ พักไว้ ใช้ Google Vision ทีหลัง (seam ทำไว้แล้ว) |
| 3 — Frontend | 🔲 |
| 4 — PWA | 🔲 |
| 5–8 | 🔲 |

---

## การตัดสินใจที่ล็อกไว้แล้ว

**รูปสลิปเก็บที่ Supabase Storage แบบ private bucket** — ไม่ใช่ใน Postgres (DB บวมชน quota) และไม่ใช่ Cloudinary (free tier เป็น public URL ไม่มี auth ส่วนสลิปมีชื่อ เลขบัญชีบางส่วน ยอดเงิน) เก็บแค่ object path ใน DB แล้วออก signed URL อายุสั้นตอนขอดู

**รูปถูกย่อและถอด metadata ก่อนอัปโหลดเสมอ** — ย่อด้านยาวเหลือ 1200px, JPEG q75 ได้ประมาณ 100KB/ใบ การ re-encode ทิ้ง EXIF (รวม GPS) ไปในตัว ~100 ใบ/เดือน ≈ 10MB/เดือน

**OCR ไม่เคยอยู่บน critical path** — ฟอร์มคือ source of truth เสมอ อ่านสลิปไม่ออกคือผลลัพธ์ปกติ ไม่ใช่ error: API ตอบ 200 พร้อมช่องว่าง แล้วผู้ใช้กรอกเอง `app/ocr.py` มี timeout 15 วิ และ `extract()` ไม่มีทาง raise

**QR บนสลิปไทยใช้กันลงซ้ำ ไม่ใช่ดึงยอด** — mini-QR บนสลิปโอนเก็บ *slip verification reference* (ธนาคารต้นทาง + เลขอ้างอิง) ไม่ได้เก็บจำนวนเงินหรือวันที่ ค่าจริงของมันคือเป็น unique key กันสองคนลงสลิปใบเดียวกัน (`transactions.slip_ref` UNIQUE) ยอดกับวันที่ยังต้องมาจาก OCR อยู่ดี

**แก้พร้อมกัน = optimistic locking** — ทุกแถวมี `version` client ส่ง version ที่อ่านมากลับไปตอน PUT ไม่ตรงได้ 409 พร้อมบอก version ปัจจุบัน แทนที่จะทับงานอีกฝ่ายเงียบๆ

**ไม่มี SQLite ใน dev** — ต่อ Neon ตรงตั้งแต่วันแรก ไม่ต้องมาไล่ syntax ต่างทีหลัง (SQLite โผล่แค่ใน `tests/smoke.py` ในฐานะ harness ดูข้อจำกัดในไฟล์)

---

## Backend

### รันในเครื่อง

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate บน mac/linux
pip install -r requirements.txt

cp .env.example .env            # แล้วเติม DATABASE_URL จาก Neon + JWT_SECRET
python -m scripts.seed          # สร้าง 2 users + หมวดหมู่ + keywords

uvicorn app.main:app --reload   # http://localhost:8000/docs
```

`scripts/seed.py` รันซ้ำได้ ไม่ทับของเดิม ถ้าไม่ตั้ง `SEED_USERS` มันจะสุ่มรหัสผ่านให้แล้วพิมพ์ออกมาครั้งเดียว
เปลี่ยนรหัสทีหลัง: `python -m scripts.seed --reset-password boriwat=รหัสใหม่`

### เทสต์

```bash
python -m tests.smoke          # 65 checks — ทั้ง API บน SQLite ชั่วคราว ไม่ต้องต่ออะไร
python -m tests.test_timeutil  # 25 checks — คณิตศาสตร์ timezone
```

### Endpoints

| | |
|---|---|
| `GET /health` | ปลุก Render + warm Neon ในครั้งเดียว ตอบ 200 เสมอ บอกสถานะ db/storage ใน body |
| `POST /auth/login` → `GET /auth/me` → `GET /auth/users` | JWT อายุ 30 วัน |
| `GET /categories` · `GET /categories/suggest?text=` | เดาหมวดหมู่จากตาราง keyword |
| `GET/POST /transactions` · `GET/PUT/DELETE /transactions/{id}` | PUT ต้องส่ง `version` |
| `GET /transactions/summary?month=YYYY-MM` | ยอดรวม + แยกตามหมวด/ตามคน |
| `GET /transactions/export.csv` | สำรองข้อมูล (UTF-8 BOM เปิดใน Excel ไทยไม่เพี้ยน) |
| `GET /transactions/{id}/slip` | signed URL อายุสั้น |
| `POST /slips/upload` | อัปโหลด + พยายามอ่าน — อ่านไม่ออกก็ยัง 200 |

### Timezone

เก็บเป็น UTC (`TIMESTAMPTZ`) ทั้งหมด แสดงผลและกรองด้วย `Asia/Bangkok`
Render กับ Neon เป็น UTC — รายการที่ลงตอนเที่ยงคืนถึงตี 7 จะตกไปเป็นวัน UTC ก่อนหน้า ซึ่งเป็นวิธีที่ dashboard กรองรายเดือนแล้วแถวหายเงียบๆ
`app/timeutil.py` เลยคำนวณขอบเขตเป็นเวลาไทยก่อนแล้วค่อยแปลงเป็น UTC instant (ได้ใช้ index ด้วย ไม่ต้อง `AT TIME ZONE` รายแถว)

---

## Frontend

ยังไม่ได้ทำ

---

## Backup

`GET /transactions/export.csv` เป็นทางออกของข้อมูล ควร export เก็บเป็นระยะ ไม่ปล่อยให้ข้อมูลติดอยู่ใน Neon อย่างเดียว
