# MemoraX AI — Full-Stack Starter

A working, simplified implementation of the MemoraX AI architecture you sketched out.
It's a **real, runnable full-stack app** — not a mockup — built to swap in the
heavier pieces (real LLMs, vector DB, MongoDB) later without changing the shape of the system.

## What's actually implemented vs. simplified

| Module | In this starter | Full architecture |
|---|---|---|
| Auth (JWT) | ✅ Real JWT, SQLite users table | same, just swap SQLite → MongoDB |
| Conversation Engine | ✅ Stores every message | same |
| Memory Engine | ✅ Rule-based importance classifier + fact extractor | swap for an LLM-based extractor |
| Memory Retrieval | ✅ Keyword-overlap search | swap for ChromaDB/FAISS embeddings |
| Smart Task Manager | ✅ Regex date detection from "Remember: ..." messages | same idea, smarter NLP |
| Events / Calendar | ✅ Full CRUD, separate from tasks | same |
| Emotion Detection | ✅ Keyword-based | swap for a classifier model |
| Scam Detection | ✅ Rules engine with weighted risk score | same idea, expand rule set |
| Document Intelligence | ✅ Upload + keyword Q&A | swap for chunking + embeddings + real LLM |
| Notifications | ✅ Auto-generated for high-importance memories, tasks, events, scam alerts | same, push via websockets/FCM |
| Analytics dashboard | ✅ Conversations/day, emotion & importance breakdowns, task completion, avg scam risk (canvas charts) | same, add more dimensions |
| Settings | ✅ Theme (dark/light), voice toggle, notification toggle, AI engine selector — all persisted per-user | same |
| Voice Assistant | ✅ **Real** browser speech-to-text + text-to-speech (Web Speech API) | swap for Whisper (STT) + Kokoro (TTS) server-side models |
| AI replies | ⚠️ Rule-based mock responses | swap `generate_ai_reply()` for a real LLM call (Llama 3.1 / GPT) |

Every sidebar item from your original mockup (Dashboard, Conversations, Memories, Tasks,
Events, Documents, Voice Assistant, Analytics, Settings) is implemented and wired to a
real backend — nothing is just a static screenshot.

**On voice:** Whisper and Kokoro are full ML models that need a GPU/runtime to host
server-side — they're not something this kind of starter can bundle. The Voice Assistant
tab instead uses your browser's native Web Speech API, which is a real, working,
zero-install substitute: it actually listens, transcribes, sends the message to the same
`/api/chat` endpoint, and speaks the reply back. It's not a placeholder — try it in Chrome.

Everything is wired through real HTTP endpoints, so when you're ready to upgrade
a module (e.g. plug in Llama 3.1 via Ollama, or swap SQLite for MongoDB + ChromaDB),
you only touch that one function/file — the API contract with the frontend doesn't change.

## Project structure

```
memorax/
├── backend/
│   ├── main.py            # FastAPI app — all routes + rule-based AI engine
│   └── requirements.txt
└── frontend/
    └── index.html         # Single-file dashboard UI (vanilla JS, no build step)
```

## Run it

**1. Backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
This creates `memorax.db` (SQLite) automatically on first run.

**2. Frontend**
Just open `frontend/index.html` directly in your browser (double-click it, or
serve it with `python3 -m http.server 5500` from the `frontend/` folder).

The frontend talks to `http://127.0.0.1:8000/api` — edit the `API` constant at
the top of `index.html` if you deploy the backend elsewhere.

## Try it

1. Open the frontend → sign up with a name/email/password.
2. Go to **Conversations** and type: `I have an interview next week at Infosys`
   → a high-importance memory is created automatically, and a notification appears (bell icon).
3. Type: `Remember: Project submission on July 15`
   → a task is auto-created with that due date.
4. Type something like: `Your OTP is required, click this link to verify your account`
   → triggers a scam warning with a risk score, plus a notification.
5. Check the **Dashboard** — stats, recent memories, and upcoming tasks update live.
6. Go to **Events**, add an interview/exam/deadline with a date — separate calendar from action Tasks.
7. Go to **Documents**, upload a `.txt` file, then ask a question about its contents.
8. Go to **Voice Assistant** (use Chrome) — tap the mic, speak a message, MemoraX transcribes it,
   sends it through the same chat pipeline, and reads the reply back out loud.
9. Go to **Analytics** — see conversations-per-day, emotion breakdown, memory importance,
   task completion, and average scam risk as live bar charts.
10. Go to **Settings** — switch theme (dark/light), toggle voice replies, toggle notifications,
    and pick which AI engine label is shown (the actual engine is still rule-based until you
    wire up a real LLM — see below).

## Where to plug in the real AI later

- `generate_ai_reply()` in `main.py` — replace with a call to your LLM
  (Llama 3.1 / Gemma / GPT) via Ollama or an API, injecting `recalled_facts`
  as context — this is exactly the "LLM Orchestrator" box in your diagram.
- `recall_memories()` — replace keyword overlap with a ChromaDB/FAISS
  similarity search over embeddings.
- `extract_memory_fact()` / `classify_importance()` — replace with an LLM
  prompt that extracts structured facts + importance from the message.
- Swap the SQLite functions in `get_db()` for a MongoDB client — the table/
  collection shapes already match your original schema (users, conversations,
  memories, tasks, documents).
