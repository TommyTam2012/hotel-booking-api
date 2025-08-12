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
