"""
MemoraX AI — Backend Starter
A simplified, self-contained FastAPI backend implementing the core modules
from the MemoraX AI architecture using SQLite (instead of MongoDB) and a
rule-based "LLM Orchestrator" (instead of Llama/GPT) so the whole thing runs
with zero external services or API keys.

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
"""

import hashlib
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta

import jwt
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# ...other imports...

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://parth0777-o.github.io"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ...rest of your routes...
# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get("MEMORAX_SECRET", "memorax-dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_EXP_HOURS = 24 * 7
DB_PATH = os.path.join(os.path.dirname(__file__), "memorax.db")

app = FastAPI(title="MemoraX AI API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, name TEXT, email TEXT UNIQUE,
            password_hash TEXT, created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, user_id TEXT, role TEXT, message TEXT,
            emotion TEXT, scam_risk INTEGER, created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY, user_id TEXT, fact TEXT, category TEXT,
            importance TEXT, created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, user_id TEXT, title TEXT, due_date TEXT,
            status TEXT, created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, user_id TEXT, filename TEXT, content TEXT,
            created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, user_id TEXT, title TEXT, event_date TEXT,
            event_type TEXT, notes TEXT, created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            user_id TEXT PRIMARY KEY, theme TEXT DEFAULT 'dark',
            voice_replies INTEGER DEFAULT 1, notifications INTEGER DEFAULT 1,
            llm_provider TEXT DEFAULT 'rule-based'
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY, user_id TEXT, message TEXT, is_read INTEGER DEFAULT 0,
            created_at TEXT
        )""")


init_db()

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return hashlib.sha256((SECRET_KEY + password).encode()).hexdigest()


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGO)


def get_current_user(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["sub"]


# ---------------------------------------------------------------------------
# "AI Engine" — rule-based memory / emotion / scam / task modules
# Stand-ins for the LLM Orchestrator + Memory Engine in the architecture doc.
# ---------------------------------------------------------------------------
IMPORTANT_KEYWORDS = [
    "interview", "exam", "project", "submission", "deadline", "goal",
    "favorite", "favourite", "prefer", "career", "university", "job",
    "applied", "hackathon", "graduate", "birthday", "anniversary",
]

EMOTION_KEYWORDS = {
    "stressed": ["stressed", "overwhelmed", "anxious", "pressure"],
    "sad": ["sad", "down", "depressed", "upset", "tired", "exhausted"],
    "angry": ["angry", "furious", "annoyed", "frustrated", "mad"],
    "happy": ["happy", "excited", "great", "awesome", "glad", "thrilled"],
}

SCAM_RULES = {
    "otp": 30,
    "one time password": 30,
    "bank account": 25,
    "urgent transfer": 25,
    "gift card": 20,
    "click this link": 20,
    "verify your account": 20,
    "lottery": 25,
    "won a prize": 25,
    "kyc update": 20,
    "send money": 20,
}

MONTHS = (
    "january|february|march|april|may|june|july|august|september|"
    "october|november|december"
)
DATE_PATTERN = re.compile(
    rf"\b((?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?)\b", re.IGNORECASE
)
RELATIVE_DATE_PATTERN = re.compile(r"\bnext\s+(week|month)\b", re.IGNORECASE)


def detect_emotion(text: str) -> str:
    lowered = text.lower()
    for emotion, words in EMOTION_KEYWORDS.items():
        if any(w in lowered for w in words):
            return emotion
    return "neutral"


def detect_scam_risk(text: str) -> int:
    lowered = text.lower()
    score = 0
    for phrase, weight in SCAM_RULES.items():
        if phrase in lowered:
            score += weight
    return min(score, 100)


def classify_importance(text: str) -> str:
    lowered = text.lower()
    hits = sum(1 for kw in IMPORTANT_KEYWORDS if kw in lowered)
    if hits >= 2:
        return "high"
    if hits == 1:
        return "medium"
    return "low"


def extract_memory_fact(text: str):
    """Small heuristic 'memory extractor' — turns first-person statements
    into stored third-person facts."""
    lowered = text.strip()
    if not lowered:
        return None
    if not any(kw in lowered.lower() for kw in IMPORTANT_KEYWORDS):
        return None
    fact = lowered
    fact = re.sub(r"^i\s+", "User ", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^i'm\s+", "User is ", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^my\s+", "User's ", fact, flags=re.IGNORECASE)
    if not fact.lower().startswith("user"):
        fact = "User said: " + lowered
    return fact[:280]


def try_extract_task(text: str):
    """Detects 'Remember: ... on <date>' style task creation."""
    lowered = text.lower()
    if "remember" not in lowered and "submission" not in lowered and "deadline" not in lowered:
        return None
    date_match = DATE_PATTERN.search(text)
    rel_match = RELATIVE_DATE_PATTERN.search(text)
    due_date = None
    if date_match:
        try:
            parsed = datetime.strptime(date_match.group(1), "%B %d")
            due_date = parsed.replace(year=datetime.utcnow().year).date().isoformat()
        except ValueError:
            due_date = date_match.group(1)
    elif rel_match:
        days = 7 if rel_match.group(1) == "week" else 30
        due_date = (datetime.utcnow() + timedelta(days=days)).date().isoformat()
    title = re.sub(r"(?i)remember[:,]?\s*", "", text).strip()
    title = title[:120] if title else "New Task"
    if due_date is None:
        return None
    return {"title": title, "due_date": due_date}


def generate_ai_reply(user_id: str, message: str, recalled_facts):
    """Stand-in for the LLM Orchestrator. In production this would call
    Llama 3.1 / Gemma / GPT with the recalled memories injected as context."""
    lowered = message.lower()
    if recalled_facts:
        context_line = " I recall that " + "; ".join(recalled_facts[:2]) + "."
    else:
        context_line = ""
    if "?" in message:
        return f"Good question.{context_line} Could you tell me a bit more so I can help precisely?"
    if any(w in lowered for w in EMOTION_KEYWORDS["sad"]):
        return "You've been working hard lately. Would you like a short break, or want to talk it through?"
    if any(w in lowered for w in EMOTION_KEYWORDS["stressed"]):
        return "That sounds like a lot to carry. Want me to help break your tasks down?"
    return f"Got it — I've noted that.{context_line} I'll keep this in mind going forward."


def recall_memories(user_id: str, message: str, limit: int = 3):
    """Simple keyword-overlap retrieval, standing in for the Vector DB /
    embedding similarity search (ChromaDB/FAISS) in the full architecture."""
    words = set(re.findall(r"[a-zA-Z]{4,}", message.lower()))
    if not words:
        return []
    with get_db() as conn:
        rows = conn.execute(
            "SELECT fact FROM memories WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    scored = []
    for row in rows:
        fact_words = set(re.findall(r"[a-zA-Z]{4,}", row["fact"].lower()))
        overlap = len(words & fact_words)
        if overlap > 0:
            scored.append((overlap, row["fact"]))
    scored.sort(reverse=True)
    return [f for _, f in scored[:limit]]


def push_notification(user_id: str, message: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO notifications (id, user_id, message, is_read, created_at) VALUES (?, ?, ?, 0, ?)",
            (str(uuid.uuid4()), user_id, message, datetime.utcnow().isoformat()),
        )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    message: str


class TaskRequest(BaseModel):
    title: str
    due_date: str = None


class DocAskRequest(BaseModel):
    document_id: str
    question: str


class EventRequest(BaseModel):
    title: str
    event_date: str
    event_type: str = "general"
    notes: str = None


class SettingsRequest(BaseModel):
    theme: str = None
    voice_replies: bool = None
    notifications: bool = None
    llm_provider: str = None


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.post("/api/auth/register")
def register(req: RegisterRequest):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (req.email,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, req.name, req.email, hash_password(req.password), datetime.utcnow().isoformat()),
        )
        conn.execute("INSERT INTO settings (user_id) VALUES (?)", (user_id,))
    token = create_token(user_id)
    return {"token": token, "user": {"id": user_id, "name": req.name, "email": req.email}}


@app.post("/api/auth/login")
def login(req: LoginRequest):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (req.email,)
        ).fetchone()
    if not row or row["password_hash"] != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(row["id"])
    return {"token": token, "user": {"id": row["id"], "name": row["name"], "email": row["email"]}}


@app.get("/api/auth/me")
def me(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        row = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)


# ---------------------------------------------------------------------------
# Chat / Conversation Engine + Memory Engine
# ---------------------------------------------------------------------------
@app.post("/api/chat")
def chat(req: ChatRequest, user_id: str = Depends(get_current_user)):
    now = datetime.utcnow().isoformat()
    emotion = detect_emotion(req.message)
    scam_risk = detect_scam_risk(req.message)
    recalled = recall_memories(user_id, req.message)

    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (id, user_id, role, message, emotion, scam_risk, created_at) "
            "VALUES (?, ?, 'user', ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, req.message, emotion, scam_risk, now),
        )

    memory_created = None
    fact = extract_memory_fact(req.message)
    if fact:
        importance = classify_importance(req.message)
        mem_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO memories (id, user_id, fact, category, importance, created_at) "
                "VALUES (?, ?, ?, 'episodic', ?, ?)",
                (mem_id, user_id, fact, importance, now),
            )
        memory_created = {"id": mem_id, "fact": fact, "importance": importance}
        if importance == "high":
            push_notification(user_id, f"New high-importance memory: {fact[:80]}")

    task_created = None
    task_info = try_extract_task(req.message)
    if task_info:
        task_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO tasks (id, user_id, title, due_date, status, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (task_id, user_id, task_info["title"], task_info["due_date"], now),
            )
        task_created = {"id": task_id, **task_info}
        push_notification(user_id, f"New task created: {task_info['title']} (due {task_info['due_date']})")

    ai_reply = generate_ai_reply(user_id, req.message, recalled)
    if scam_risk >= 50:
        push_notification(user_id, f"⚠️ Potential scam detected in your message (risk {scam_risk}%)")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (id, user_id, role, message, emotion, scam_risk, created_at) "
            "VALUES (?, ?, 'ai', ?, NULL, NULL, ?)",
            (str(uuid.uuid4()), user_id, ai_reply, now),
        )

    return {
        "reply": ai_reply,
        "emotion": emotion,
        "scam_risk": scam_risk,
        "scam_alert": scam_risk >= 50,
        "memory_created": memory_created,
        "task_created": task_created,
        "recalled_memories": recalled,
    }


@app.get("/api/conversations")
def list_conversations(user_id: str = Depends(get_current_user), limit: int = 50):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------
@app.get("/api/memories")
def list_memories(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@app.get("/api/tasks")
def list_tasks(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY due_date ASC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/tasks")
def create_task(req: TaskRequest, user_id: str = Depends(get_current_user)):
    task_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (id, user_id, title, due_date, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (task_id, user_id, req.title, req.due_date, datetime.utcnow().isoformat()),
        )
    return {"id": task_id, "title": req.title, "due_date": req.due_date, "status": "pending"}


@app.put("/api/tasks/{task_id}/complete")
def complete_task(task_id: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'completed' WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Document Intelligence (simplified — no real embeddings, keyword search
# stands in for chunking + vector DB retrieval)
# ---------------------------------------------------------------------------
@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...), user_id: str = Depends(get_current_user)):
    raw = await file.read()
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    doc_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO documents (id, user_id, filename, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (doc_id, user_id, file.filename, text, datetime.utcnow().isoformat()),
        )
    return {"id": doc_id, "filename": file.filename, "chars": len(text)}


@app.get("/api/documents")
def list_documents(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, filename, created_at, length(content) as chars FROM documents "
            "WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/documents/ask")
def ask_document(req: DocAskRequest, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?",
            (req.document_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    paragraphs = [p for p in row["content"].split("\n") if p.strip()]
    q_words = set(re.findall(r"[a-zA-Z]{4,}", req.question.lower()))
    best, best_score = None, 0
    for p in paragraphs:
        p_words = set(re.findall(r"[a-zA-Z]{4,}", p.lower()))
        score = len(q_words & p_words)
        if score > best_score:
            best, best_score = p, score
    if not best:
        return {"answer": "I couldn't find anything relevant to that in the document."}
    return {"answer": best[:500]}


# ---------------------------------------------------------------------------
# Dashboard / Analytics
# ---------------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        convo_count = conn.execute(
            "SELECT COUNT(*) c FROM conversations WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
        memory_count = conn.execute(
            "SELECT COUNT(*) c FROM memories WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
        pending_tasks = conn.execute(
            "SELECT COUNT(*) c FROM tasks WHERE user_id = ? AND status = 'pending'", (user_id,)
        ).fetchone()["c"]
        completed_tasks = conn.execute(
            "SELECT COUNT(*) c FROM tasks WHERE user_id = ? AND status = 'completed'", (user_id,)
        ).fetchone()["c"]
        recent_memories = conn.execute(
            "SELECT * FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (user_id,)
        ).fetchall()
        upcoming_tasks = conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY due_date ASC LIMIT 5",
            (user_id,),
        ).fetchall()

    total_tasks = pending_tasks + completed_tasks
    productivity = round((completed_tasks / total_tasks) * 100) if total_tasks else 0

    return {
        "conversations": convo_count,
        "memories": memory_count,
        "tasks_pending": pending_tasks,
        "tasks_completed": completed_tasks,
        "productivity_score": productivity,
        "recent_memories": [dict(r) for r in recent_memories],
        "upcoming_tasks": [dict(r) for r in upcoming_tasks],
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "time": time.time()}


# ---------------------------------------------------------------------------
# Events (calendar-style entries, distinct from action tasks)
# ---------------------------------------------------------------------------
@app.get("/api/events")
def list_events(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE user_id = ? ORDER BY event_date ASC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/events")
def create_event(req: EventRequest, user_id: str = Depends(get_current_user)):
    event_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO events (id, user_id, title, event_date, event_type, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, user_id, req.title, req.event_date, req.event_type, req.notes,
             datetime.utcnow().isoformat()),
        )
    push_notification(user_id, f"New event added: {req.title} on {req.event_date}")
    return {"id": event_id, **req.dict()}


@app.delete("/api/events/{event_id}")
def delete_event(event_id: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM events WHERE id = ? AND user_id = ?", (event_id, user_id))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@app.get("/api/notifications")
def list_notifications(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 30",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.put("/api/notifications/{notif_id}/read")
def mark_notification_read(notif_id: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
            (notif_id, user_id),
        )
    return {"ok": True}


@app.put("/api/notifications/read-all")
def mark_all_notifications_read(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@app.get("/api/settings")
def get_settings(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            conn.execute("INSERT INTO settings (user_id) VALUES (?)", (user_id,))
            row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row)


@app.put("/api/settings")
def update_settings(req: SettingsRequest, user_id: str = Depends(get_current_user)):
    fields, values = [], []
    if req.theme is not None:
        fields.append("theme = ?"); values.append(req.theme)
    if req.voice_replies is not None:
        fields.append("voice_replies = ?"); values.append(int(req.voice_replies))
    if req.notifications is not None:
        fields.append("notifications = ?"); values.append(int(req.notifications))
    if req.llm_provider is not None:
        fields.append("llm_provider = ?"); values.append(req.llm_provider)
    if fields:
        with get_db() as conn:
            conn.execute("SELECT 1 FROM settings WHERE user_id = ?", (user_id,)).fetchone() or \
                conn.execute("INSERT INTO settings (user_id) VALUES (?)", (user_id,))
            conn.execute(f"UPDATE settings SET {', '.join(fields)} WHERE user_id = ?", (*values, user_id))
    return get_settings(user_id)


# ---------------------------------------------------------------------------
# Analytics — richer breakdowns for the Analytics tab
# ---------------------------------------------------------------------------
@app.get("/api/analytics")
def analytics(user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        by_day = conn.execute(
            "SELECT substr(created_at,1,10) as day, COUNT(*) c FROM conversations "
            "WHERE user_id = ? AND role = 'user' GROUP BY day ORDER BY day DESC LIMIT 14",
            (user_id,),
        ).fetchall()
        importance_breakdown = conn.execute(
            "SELECT importance, COUNT(*) c FROM memories WHERE user_id = ? GROUP BY importance",
            (user_id,),
        ).fetchall()
        emotion_breakdown = conn.execute(
            "SELECT emotion, COUNT(*) c FROM conversations WHERE user_id = ? AND emotion IS NOT NULL "
            "GROUP BY emotion",
            (user_id,),
        ).fetchall()
        avg_scam_risk = conn.execute(
            "SELECT AVG(scam_risk) a FROM conversations WHERE user_id = ? AND scam_risk IS NOT NULL",
            (user_id,),
        ).fetchone()["a"]
        task_completion = conn.execute(
            "SELECT status, COUNT(*) c FROM tasks WHERE user_id = ? GROUP BY status",
            (user_id,),
        ).fetchall()

    return {
        "conversations_by_day": [dict(r) for r in reversed(by_day)],
        "memory_importance_breakdown": [dict(r) for r in importance_breakdown],
        "emotion_breakdown": [dict(r) for r in emotion_breakdown],
        "avg_scam_risk": round(avg_scam_risk or 0, 1),
        "task_completion": [dict(r) for r in task_completion],
    }
