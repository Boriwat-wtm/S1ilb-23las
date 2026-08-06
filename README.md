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
| 0 — สมัคร Vercel / Render / Neon / Supabase | 🔲 ต้องทำเอง |
| 1 — Schema + Backend | ✅ |
| 3 — Frontend | ✅ |
| 4 — PWA | ✅ |
| 5 — Deploy | 🔲 config พร้อมแล้ว ทำตาม runbook ข้างล่าง |
| 2 — OCR | ⏸️ พักไว้ ใช้ Google Vision ทีหลัง (seam ทำไว้แล้ว) |
| 6 — ทดสอบก่อนใช้จริง | 🔲 |
| 7 — ติดตั้งบนมือถือ | 🔲 |
| 8 — เฝ้าระวังหลังใช้จริง | 🔲 |

---

## การตัดสินใจที่ล็อกไว้แล้ว

**รูปสลิปเก็บที่ Supabase Storage แบบ private bucket** — ไม่ใช่ใน Postgres (DB บวมชน quota) และไม่ใช่ Cloudinary (free tier เป็น public URL ไม่มี auth ส่วนสลิปมีชื่อ เลขบัญชีบางส่วน ยอดเงิน) เก็บแค่ object path ใน DB แล้วออก signed URL อายุสั้นตอนขอดู

**รูปถูกย่อและถอด metadata ก่อนอัปโหลดเสมอ** — ย่อด้านยาวเหลือ 1200px, JPEG q75 ได้ประมาณ 100KB/ใบ การ re-encode ทิ้ง EXIF (รวม GPS) ไปในตัว ~100 ใบ/เดือน ≈ 10MB/เดือน

**OCR ไม่เคยอยู่บน critical path** — ฟอร์มคือ source of truth เสมอ อ่านสลิปไม่ออกคือผลลัพธ์ปกติ ไม่ใช่ error: API ตอบ 200 พร้อมช่องว่าง แล้วผู้ใช้กรอกเอง `app/ocr.py` มี timeout 15 วิ และ `extract()` ไม่มีทาง raise

**QR บนสลิปไทยใช้กันลงซ้ำ ไม่ใช่ดึงยอด** — mini-QR บนสลิปโอนเก็บ *slip verification reference* (ธนาคารต้นทาง + เลขอ้างอิง) ไม่ได้เก็บจำนวนเงินหรือวันที่ ค่าจริงของมันคือเป็น unique key กันสองคนลงสลิปใบเดียวกัน (`transactions.slip_ref` UNIQUE) ยอดกับวันที่ยังต้องมาจาก OCR อยู่ดี

**แก้พร้อมกัน = optimistic locking** — ทุกแถวมี `version` client ส่ง version ที่อ่านมากลับไปตอน PUT ไม่ตรงได้ 409 พร้อมบอก version ปัจจุบัน แทนที่จะทับงานอีกฝ่ายเงียบๆ

**ไม่มี SQLite ใน dev** — ต่อ Neon ตรงตั้งแต่วันแรก ไม่ต้องมาไล่ syntax ต่างทีหลัง (SQLite โผล่แค่ใน `tests/smoke.py` ในฐานะ harness ดูข้อจำกัดในไฟล์)

---

## Deploy runbook

ลำดับสำคัญ เพราะ Render ต้องรู้โดเมน Vercel และ Vercel ต้องรู้ URL ของ Render — ไก่กับไข่ ต้องเดินสองรอบ

### 1. Neon
สร้าง project → เลือก region **Singapore** → คัดลอก **pooled connection string** (`...-pooler...`) เก็บไว้

### 2. Supabase (เก็บรูปสลิปอย่างเดียว ไม่ได้ใช้ DB ของมัน)
สร้าง project → **Storage → New bucket** ชื่อ `slips` → **ปิด Public bucket ให้แน่ใจ**
เอา **Project URL** กับ **service_role key** (Settings → API) เก็บไว้ — service_role ข้าม RLS ได้ ห้ามหลุดไปฝั่ง frontend เด็ดขาด

### 3. เตรียมฐานข้อมูล (รันจากเครื่องตัวเอง ยิงตรงไป Neon)
Render free ไม่มี shell เลยต้อง seed จากเครื่อง

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
DATABASE_URL="<neon-connection-string>" \
SEED_USERS="boriwat:บอ:รหัสของคุณ,fon:ฝน:รหัสของแฟน" \
  python -m scripts.seed
```

สร้างตาราง + 2 users + 10 หมวดหมู่ + keyword ประมาณ 90 คำ รันซ้ำได้ไม่ทับของเดิม

### 4. Render
New → **Blueprint** → เลือก repo นี้ (มันอ่าน `render.yaml` เอง)
ใส่ env var ที่ marked `sync: false`:

| key | ค่า |
|---|---|
| `DATABASE_URL` | connection string จาก Neon |
| `CORS_ORIGINS` | ใส่ `https://localhost` ไปพลางก่อน แล้วกลับมาแก้ในข้อ 6 |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SERVICE_KEY` | service_role key |

`JWT_SECRET` Render สุ่มให้เอง
Deploy เสร็จ เปิด `https://<ชื่อ>.onrender.com/health` ต้องได้ `"database":"ok"`

### 5. Vercel
Import repo → **Root Directory = `frontend`** (สำคัญ ไม่งั้น build ไม่เจอ)
Environment Variable: `VITE_API_URL` = URL ของ Render (ไม่มี `/` ปิดท้าย)
Deploy → จด production domain ไว้

> `VITE_*` ถูก inline ตอน build ไม่ใช่ตอน run — แก้ค่าแล้วต้อง **Redeploy** ถึงจะมีผล

### 6. กลับไป Render
แก้ `CORS_ORIGINS` เป็นโดเมน Vercel จริง เช่น `https://bank-xxxx.vercel.app` → save (Render redeploy เอง)

> preview deployment ของ Vercel ใช้โดเมนคนละอันทุกครั้ง จะติด CORS ถ้าไม่ได้ใส่ไว้ด้วย ใช้ production domain เป็นหลัก

### 7. ทดสอบ
เปิดโดเมน Vercel บนคอม → เปิด DevTools Console → login
ถ้าเจอ CORS error แปลว่าข้อ 6 ยังไม่ตรง ถ้าค้างที่หน้าปลุกนานๆ แปลว่า Render กำลัง cold start (ปกติรอบแรก 30–60 วิ)

### 8. ติดตั้งบนมือถือ
Safari → เปิดโดเมน Vercel → Share → **Add to Home Screen** ทำทั้งสองเครื่อง

---

## Backend

### รันในเครื่อง

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate บน mac/linux
pip install -r requirements.txt

cp .env.example .env            # แล้วเติม DATABASE_URL จาก Neon + JWT_SECRET
python -m scripts.seed

uvicorn app.main:app --reload   # http://localhost:8000/docs
```

เปลี่ยนรหัสผ่านทีหลัง: `python -m scripts.seed --reset-password boriwat=รหัสใหม่`

### เทสต์

```bash
python -m tests.smoke          # 65 checks — ทั้ง API บน SQLite ชั่วคราว ไม่ต้องต่ออะไร
python -m tests.test_timeutil  # 25 checks — คณิตศาสตร์ timezone
```

### Endpoints

| | |
|---|---|
| `GET /health` | ปลุก Render + warm Neon ในครั้งเดียว ตอบ 200 เสมอ บอกสถานะ db/storage ใน body |
| `POST /auth/login` · `GET /auth/me` · `GET /auth/users` | JWT อายุ 30 วัน |
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

```bash
cd frontend
npm install
cp .env.example .env.local      # ชี้ VITE_API_URL ไปที่ backend
npm run dev                     # http://localhost:5173
```

หน้าจอ: หน้าปลุก backend → login → รายการ (กรองตามเดือน/คน/หมวด/ค้นหา) → เพิ่ม/แก้ → สรุป + export CSV

โครงสร้าง:

| ไฟล์ | หน้าที่ |
|---|---|
| `src/api/client.js` | fetch wrapper ตัวเดียว จัดการ token, 401, error shape |
| `src/components/WakeScreen.jsx` | poll `/health` จน stack ตอบ แยก "Render ยังหลับ" กับ "Neon ยังตื่นไม่เต็มที่" |
| `src/components/TransactionForm.jsx` | ใช้ร่วมกันทั้งหน้าเพิ่มและหน้าแก้ |
| `src/utils/format.js` | เงิน/วันที่ ตรึงเป็น `Asia/Bangkok` ไม่อิง timezone ของเครื่อง |

---

## ยังไม่ได้ทำ / ต้องระวัง

- **ยังไม่ได้ยืนยัน datetime round-trip บน Postgres จริง** — SQLite แทน `TIMESTAMPTZ` ไม่ได้ (ทิ้ง offset เก็บเป็น local wall-clock text) เลข timezone เองเทสต์ครบใน `tests/test_timeutil.py` แล้ว แต่ตอนต่อ Neon ครั้งแรกให้ลงรายการตอนดึกๆ (เที่ยงคืน–ตี 7) หนึ่งรายการ แล้วเช็คว่าอยู่ถูกวันไหม
- **ยังไม่ได้ทดสอบบนมือถือจริง** — cold start, กล้อง, Add to Home Screen
- **OCR ยังไม่ต่อ** — `OCR_PROVIDER=none` ทุกอย่างกรอกมือ พอจะต่อ Google Vision แก้ที่ `GoogleVisionProvider.extract()` ที่เดียว ไม่ต้องแตะ schema หรือ frontend
- **ลบรายการแล้วรูปสลิปถูกลบแบบ best-effort** — ถ้า storage ล่มตอนนั้น จะเหลือไฟล์กำพร้าค้างไว้ (ยอมได้ ดีกว่าลบรายการไม่สำเร็จ)
- **แก้สลิปออกจากรายการเดิม ไม่ลบไฟล์ใน bucket**

## Backup

`GET /transactions/export.csv` หรือปุ่มในหน้าสรุป ควร export เก็บเป็นระยะ ไม่ปล่อยให้ข้อมูลติดอยู่ใน Neon อย่างเดียว

## เรื่อง quota

Render free 750 ชม./เดือน — service เดียวรัน 24/7 กินประมาณ 730 ชม. ถ้าอยากตัดปัญหา cold start ด้วยการตั้ง cron ping `/health` ทุก 10 นาที ทำได้ แต่จะกินโควตาเกือบหมด เหลือที่ให้ service ฟรีตัวที่สองไม่ได้อีก
