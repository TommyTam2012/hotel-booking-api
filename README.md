# BCM Demo – FastAPI + SQLite + LangChain Agent

## Overview
This project connects a **FastAPI** backend (with SQLite database) to a **LangChain** agent that can:
- Query FAQs from the database
- Retrieve recent enrollments
- Create new enrollments

The agent communicates with the backend via custom Python tools and can be extended to integrate with HeyGen or other frontends.

---

## Project Structure
```
bcm-demo/
  api/
    app.py           # FastAPI backend API
    agent_bcm.py     # LangChain agent client
    bcm.db           # SQLite database
```

---

## How It Works
### 1. FastAPI Backend
- `/health` – Check if API is running
- `/faq/{intent}` – Get FAQ answer by intent
- `/enroll` – Create a new enrollment
- `/enrollments/recent` – List recent enrollments (with optional filters)

### 2. SQLite Database
- `faq` table – Stores intents, questions, and answers
- `enrollments` table – Stores user signups

### 3. LangChain Agent
- **GetFAQ** – Fetch FAQ answer from `/faq/{intent}`
- **GetRecentEnrollments** – Fetch recent signups from `/enrollments/recent`
- **CreateEnrollment** – Post new signup to `/enroll`

---

## Running the System

### Step 1 — Start API Server (Window A)
```powershell
cd "C:\path\to\bcm-demo\api"
uvicorn app:app --reload --port 8000
```
Keep this running.

Check health:
```
http://127.0.0.1:8000/health
```

### Step 2 — Run LangChain Agent (Window B)
```powershell
cd "C:\path\to\bcm-demo\api"
python agent_bcm.py
```

---

## Environment Variables
You must have an OpenAI API key:
```powershell
setx OPENAI_API_KEY "sk-yourkeyhere"
```
Then close and reopen PowerShell.

(Optional for deployed API):
```powershell
setx BCM_API_URL "https://your-public-api.com"

# BCM Demo API – Render Deployment Guide

## Overview
This project is a FastAPI-based backend using SQLite for data storage.  
It’s deployed on **Render** with the working, tested dependency combo below.

---

## Working Environment (DO NOT CHANGE)
**Python version:** 3.11.9 (`runtime.txt` must contain this)  

**requirements.txt:**
fastapi==0.110.0
uvicorn[standard]==0.29.0
pydantic==2.8.2

*(Add any additional required libraries here if the app grows.)*

---

## Endpoints

| Method | Endpoint                     | Description |
|--------|------------------------------|-------------|
| GET    | `/health`                    | Health check |
| GET    | `/faq/{intent}`               | Get FAQ by intent |
| POST   | `/enroll`                     | Add new enrollment |
| GET    | `/enrollments/recent`         | Get recent enrollments (optional filter by `source`) |
| POST   | `/chat`                       | Echoes back the message (for LangChain/HeyGen integration) |

---

## Deployment Steps (Render)

1. **Set Python version**  
   Create `runtime.txt` at repo root:
3.11.9


2. **Pin dependencies**  
In `requirements.txt`, use the exact versions listed above.

3. **Set start command** in Render:  
uvicorn app:app --host 0.0.0.0 --port 10000


4. **Clear Build Cache** before first deploy with new versions.

5. **Verify** after deployment:  
- `/health` → `{ "ok": true }`  
- `/faq/TEST_INTENT` → seeded FAQ returns  
- `/enrollments/recent` → `[]` until you POST an enrollment  
- `/chat` (POST) → echoes message

---

## Notes
- SQLite DB (`bcm.db`) is stored in project root for simplicity.
- For production, restrict CORS `allow_origins` to known domains.
- `/chat` is POST-only — GET requests will return `405 Method Not Allowed`.

---

**Last verified deploy:** YYYY-MM-DD  
**Maintainer:** Tommy Tam

```

---

## Next Steps
- Add free chat mode to `agent_bcm.py` for live queries
- Connect to HeyGen UI for interactive voice/video
- Deploy FastAPI backend to a public server


TAEASLA – FastAPI Backend (Enrollments + Courses + Email + HeyGen)

Last updated: 2025-09-23
This README replaces the Sept 10 draft and reflects our current, working stack: FastAPI + SQLite, Chinese enrollment form, seat-deducting /enroll, Gmail SMTP email alerts, course CRUD, and HeyGen streaming token/proxy. (The Sept 10 README covered the earlier BCM demo with LangChain tooling and simpler endpoints. )

What’s new since Sept 10

Branding: All “BCM” text migrated to TAEASLA.

Enroll flow: /enroll deducts seats on the selected course; enrollments are stored and admin email notifications are sent via Gmail SMTP App Password.

Chinese front-end form: enroll.html is localized and includes a 课程下拉菜单 that maps to /courses (shows ID & remaining seats).

Courses module: CRUD endpoints + CSV export + summary; seat counts decrease on each successful enrollment.

Assistant module: Rule-based endpoints (/assistant/intro, /assistant/prompt, /assistant/answer) for lightweight, deterministic replies.

HeyGen integration: /heygen/token, /heygen/proxy/*, /heygen/interrupt for streaming avatars.

CORS: Configurable via env var instead of hardcoded origins.

Project structure (current)
repo-root/
  app.py                 # FastAPI app with enrollments, courses, assistant, HeyGen proxy
  static/
    enroll.html          # Chinese UI form (posts to /enroll)
  requirements.txt
  runtime.txt
  (sqlite) bcm_demo.db   # SQLite database (consider moving to mounted disk in prod)


Earlier draft referenced api/app.py, agent_bcm.py, and a simpler endpoints set from the BCM demo. This README supersedes it.

Running locally
1) Python & deps

Python: 3.11.9 (pin in runtime.txt)

requirements.txt (min):

fastapi==0.110.0
uvicorn[standard]==0.29.0
pydantic==2.8.2
httpx==0.27.2


(Gmail SMTP uses stdlib smtplib; no extra package required.)

2) Launch
uvicorn app:app --reload --port 8000
# Open: http://127.0.0.1:8000/docs

Environment variables
Key	Purpose	Example
ADMIN_KEY	Admin auth for protected endpoints (X-Admin-Key)	a-strong-random-string
SMTP_USER	Gmail address to send from	tommytam2012@gmail.com
SMTP_PASS	Gmail App Password (not your login password)	xxxx xxxx xxxx xxxx
SMTP_TO	Admin notification recipient	tommytam2012@gmail.com
SMTP_HOST	SMTP host	smtp.gmail.com
SMTP_PORT	SMTP port (SSL)	465
HEYGEN_API_KEY	HeyGen API key	(secret)
HEYGEN_AVATAR_ID	Default avatar id	(id)
CORS_ORIGINS	CSV list of allowed origins	https://your-frontend.app,http://localhost:3000
Endpoints
Health & static

GET /health → { "ok": true }

GET / → redirects to /static/enroll.html

Enrollment

POST /enroll
Body:

{
  "name": "Test Student",
  "email": "student@example.com",
  "phone": "+852 9123 4567",
  "notes": "……",
  "course_id": 2      // optional; if set, seats are deducted on this course
}


Behavior:

Validates required fields

Deducts 1 seat from the target course (selected by course_id; if absent, falls back to the latest course)

Inserts an enrollments row (stores course_id)

Queues Gmail SMTP email to admin with Reply-To set to student

GET /enrollments/recent (admin) → latest enrollments (supports X-Admin-Key header)

Courses

POST /admin/courses (admin) → add a course (or use POST /courses with admin guard)

GET /courses → list courses (desc by id; includes seats)

GET /courses/{id} → course by id

GET /courses/summary → human-readable “latest course” summary

DELETE /courses/{id} (admin) → delete a course

GET /courses/export.csv → CSV export for courses

Course model:

{
  "name": "TAEASLA 英语强化班（Level 1）",
  "fee": 8800,
  "start_date": "2025-10-01",
  "end_date": "2025-11-12",
  "time": "Tue/Thu 7–9pm",
  "venue": "TAEASLA Center - Jordan",
  "seats": 30
}

FAQ (minimal DB)

GET /faq → list FAQs

POST /faq (admin) → add

Assistant (rule-based)

GET /assistant/intro → intro string

GET /assistant/prompt → enforced rules + enroll link

POST /assistant/answer → short answer + enroll prompt (no LLM needed)

Fees & schedule (lightweight examples)

GET /fees/{program_code} → GI, HKDSE examples w/ HKD fees

GET /schedule?season=summer → summer schedule sample

HeyGen streaming

POST /heygen/token → creates a streaming session token

ANY /heygen/proxy/{subpath} → generic JSON proxy to HeyGen API

POST /heygen/interrupt → interrupt a live session

Misc

GET /stream → SSE hello/world (example)

Chinese enrollment form (static)

Path: static/enroll.html

UI: 全中文标签 + 课程下拉菜单（预置：自然拼读、拼写、语法、青少年雅思、呈分试、Band 1 入学试、香港中学文凭试、雅思、托福）

On load, it calls GET /courses, matches names (包含匹配) to display ID & 余位 per option; submits course_id with the form so the backend deducts the correct seat.

Success shows: ✅ 谢谢！您的申请已收到。

Email notifications (Gmail SMTP)

Uses smtplib.SMTP_SSL to send an admin alert on each successful enrollment.

Set SMTP_PASS to a Gmail App Password (Google Account → Security → App Passwords).

We set Reply-To to the student’s email so you can reply from your inbox directly.

Render deployment (summary)

runtime.txt

3.11.9


requirements.txt (see above)

Start command

uvicorn app:app --host 0.0.0.0 --port 10000


Env vars
Set ADMIN_KEY, SMTP vars, HEYGEN_*, CORS_ORIGINS.

Persistence (important for SQLite)
Attach a Render Disk and either:

change DB_PATH to a mounted path like /data/bcm_demo.db, or

symlink the db file to the mount.
Otherwise, the DB resets on redeploy.

Admin quick actions (Swagger)

Seed a course: POST /admin/courses (with X-Admin-Key)

Verify: GET /courses

Test seat deduction: POST /enroll → GET /courses again (seats decrement)

Export: GET /courses/export.csv

Check logs/emails: verify admin inbox receives the enrollment alert

Roadmap

Hotel module (new thread): room-type inventory (豪华房/海景房/市景房/套房/迷你套房), date-range availability, payment gateway per-client (Stripe/PayPal or escrow), guest confirmation emails, and an admin dashboard.

Optional student auto-reply: send a confirmation email to the student after /enroll.

License / Maintainer

Maintainer: Tommy Tam

This repo supersedes the “BCM Demo – FastAPI + SQLite + LangChain Agent” README (Sept 10).

README — BCM Demo Hotel API (Rooms & Calendar)
📌 Overview

This project serves as a combined backend for:

BCM demo (courses, enrollments, FAQ, etc.)

Hotel booking demo (room types, availability, bookings)

It uses FastAPI (app.py) and SQLite for storage.

📂 Database

Active database: bcm_demo.db

Tables in use for hotel:

room_types — master list of room categories.

room_inventory — per-date overrides (availability, price).

bookings — reservations.

⚠️ Ignore hotel.db — it’s an older experiment and not wired into the running app.

🛠️ Running the Server

From project root:

.\.venv\Scripts\Activate.ps1
uvicorn app:app --reload

🌐 Endpoints

Swagger docs: http://127.0.0.1:8000/docs

Static calendar page: http://127.0.0.1:8000/static/index.html

Room types list: GET http://127.0.0.1:8000/room_types

🏨 Current Room Types

Seeded in bcm_demo.db → room_types:

Deluxe

Suite

Standard Queen

Standard Twin

Superior Queen (City View)

Deluxe Twin

Family Quad

Executive Suite

✅ Checklist

Use bcm_demo.db for all inserts/queries.

Launch with app:app, not main:app.

Verify new rooms via GET /room_types.

Test UI via /static/index.html.