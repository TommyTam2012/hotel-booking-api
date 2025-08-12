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
```

---

## Next Steps
- Add free chat mode to `agent_bcm.py` for live queries
- Connect to HeyGen UI for interactive voice/video
- Deploy FastAPI backend to a public server
