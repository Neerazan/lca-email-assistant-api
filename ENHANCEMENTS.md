# AI Email Assistant — Full Analysis & Enhancement Roadmap

## 1. Architecture Overview

```
┌─────────────────────────────────┐
│        Next.js Frontend         │
│  (Chat UI + Google Sign-in)     │
└────────────┬────────────────────┘
             │ REST + SSE
┌────────────▼────────────────────┐
│        FastAPI Backend          │
│  Auth Middleware                │
│  ├── /auth     — OAuth Router   │
│  ├── /chat     — Chat Router    │
│  ├── /prefs    — Prefs Router   │
│  └── /attach   — Upload Router  │
└──────┬──────────────┬───────────┘
       │              │
┌──────▼──────┐ ┌─────▼───────────┐
│  Supabase   │ │  LangGraph      │
│  - users    │ │  Agent (GPT-4o) │
│  - sessions │ │  - Gmail Tools  │
│  - messages │ │  - HITL midware │
│  - attach   │ │  - Memory store │
│  - prefs    │ │  - Checkpointer │
└─────────────┘ └─────┬───────────┘
                      │
               ┌──────▼──────┐
               │  Gmail API  │
               └─────────────┘
```

| Layer | Tech | Key Files |
|-------|------|-----------|
| **API Framework** | FastAPI + Uvicorn | `main.py` |
| **Auth** | Google OAuth code-flow, JWT access/refresh tokens, HttpOnly cookies | `routers/auth.py`, `utils/security.py` |
| **AI Agent** | LangGraph + LangChain + OpenAI GPT-4o | `agent/setup.py`, `agent/tools.py` |
| **Email** | Gmail API via langchain-google-community + raw MIME builder | `services/gmail.py` |
| **Database** | Supabase (PostgreSQL), psycopg async pool | `services/supabase.py`, `services/db.py` |
| **AI Memory** | LangGraph AsyncPostgresStore | `services/store.py` |
| **Attachments** | Supabase Storage + PDF/DOCX/XLSX/CSV/Image extractors | `services/attachment_extractor.py` |

---

## 2. Current Feature Inventory

### ✅ Fully Implemented
| Feature | Status |
|---------|--------|
| Google OAuth sign-in (auth-code flow) | ✅ |
| JWT access + refresh tokens w/ HttpOnly cookies | ✅ |
| Chat sessions (CRUD) | ✅ |
| Streaming SSE responses (token-by-token) | ✅ |
| Email search, read, thread fetch via Gmail API | ✅ |
| Send email with Human-in-the-Loop approval | ✅ |
| Create email drafts | ✅ |
| File attachments (upload, extract text/images, attach to emails) | ✅ |
| Persistent AI memory (save/delete facts about user) | ✅ |
| User preferences (tone, length, language, signature, relationships, etc.) | ✅ |
| Auto-generated session titles via GPT-4o-mini | ✅ |
| Message history trimming (token-aware) | ✅ |
| Token encryption (Fernet) for stored Google refresh tokens | ✅ |
| IDOR protection (session ownership, attachment ownership) | ✅ |
| Structured logging with daily rotation | ✅ |
| PostgreSQL-backed LangGraph checkpointer (persistent agent state) | ✅ |
| RLS enabled on all tables | ✅ |

---

## 3. Code Quality Observations & Bugs

### 🔴 Bugs / Risks

| Issue | Location | Severity |
|-------|----------|----------|
| **Access + refresh tokens use the same `SECRET_KEY` and algorithm** — A leaked access token's signature key could forge refresh tokens | `utils/security.py` | Medium |
| **No token type (`typ`) claim** in JWTs — access and refresh tokens are interchangeable | `utils/security.py` | Medium |
| **`GmailService` is instantiated per-tool-call** — each call rebuilds credentials and the Gmail API resource. No caching. | `agent/tools.py:31-32` | Medium (perf) |
| **Tests directory is empty** — zero test coverage | `tests/` | 🔴 High |

### 🟡 Code Smells

| Observation | Location |
|-------------|----------|
| Mixed `print()` and `logging` usage — most errors use `print()` instead of `logger.error()` | Throughout (`tools.py`, `chat.py`, `supabase.py`) |
| `get_current_user_id()` hits the DB on every single request to resolve `google_id → user_id`. Should cache or embed user_id in JWT | `services/auth_helpers.py:4-20` |
| Synchronous Supabase client used for most DB operations in an async FastAPI app — blocks the event loop | `services/supabase.py:12-14` |
| No rate limiting on any endpoint | `main.py` |
| No request validation/sanitization on chat `message` field (prompt injection surface) | `routers/chat.py:51-54` |
| `TAVILY_API_KEY` is configured but never used anywhere in the codebase | `utils/config.py` |

---

## 4. Enhancement Roadmap

### 🏁 Quick Wins (1-2 hours each)

| # | Enhancement | Impact | Details |
|---|-------------|--------|---------|
| 1 | **Add `typ` claim to JWTs** | Security | Add `"typ": "access"` / `"typ": "refresh"` to token payloads, validate on decode |
| 2 | **Replace all `print()` with `logging`** | Observability | Use `logger.info/warning/error` consistently across all modules |
| 3 | **Add `/health` endpoint with dependency checks** | Ops | Check DB connection, Redis, Gmail API reachability |
| 4 | **Add message length validation** | Security | Reject `message` > 10,000 chars in `ChatRequest` |
| 5 | **Cache `GmailService` per user per request** | Performance | Avoid re-creating credentials + API resource per tool call |
| 6 | **Add `user_id` to JWT claims** | Performance | Skip the DB lookup in `get_current_user_id()` on every request |

### 🔧 Medium Effort (half-day to 1-2 days)

| # | Enhancement | Impact | Details |
|---|-------------|--------|---------|
| 7 | **Rate limiting** | Security | Add `slowapi` or custom middleware — e.g., 20 chat requests/min per user, 5 uploads/min |
| 8 | **Email label/category management** | Feature | Add tools: `add_label`, `remove_label`, `list_labels`. Let agent categorize emails |
| 9 | **Mark as read/unread** | Feature | Add `mark_read` and `mark_unread` tools via Gmail API |
| 10 | **Archive/trash emails** | Feature | Add `archive_email` and `trash_email` tools with HITL confirmation |
| 11 | **Star/unstar emails** | Feature | Quick toggle via Gmail API |
| 12 | **Reply-in-thread support** | Feature | Currently `send_email` doesn't set `In-Reply-To` / `References` headers for threading |
| 13 | **Forward email** | Feature | New tool to forward an existing email to another recipient |
| 14 | **Email templates** | Feature | Let users save reusable email templates ("out of office", "follow-up", etc.) and reference them by name |
| 15 | **Scheduled email sending** | Feature | Queue emails with a send-at timestamp; use a background job (Celery/APScheduler) to dispatch |
| 16 | **Webhook for new emails** | Feature | Google Pub/Sub push notifications for real-time inbox updates, instead of polling |
| 17 | **Write proper test suite** | Quality | Unit tests for tools, services; integration tests for auth flow, chat streaming |
| 18 | **Async Supabase client** | Performance | Replace sync `supabase` client with async-compatible queries to avoid blocking the event loop |
| 19 | **Attachment virus scanning** | Security | Integrate ClamAV or a cloud scanning API before storing uploads |
| 20 | **Session export** | Feature | Export entire chat conversation as PDF/Markdown |

### 🚀 Major Features (multi-day)

| # | Enhancement | Impact | Details |
|---|-------------|--------|---------|
| 21 | **Multi-account support** | Feature | Let users link multiple Gmail accounts; agent can query across accounts with `@work` / `@personal` syntax |
| 22 | **Email analytics dashboard** | Feature | API endpoints for: emails sent/received per day, top senders, response time stats. Power a frontend dashboard |
| 23 | **Smart email prioritization** | AI | Agent auto-classifies incoming emails by urgency/importance using embeddings or LLM scoring |
| 24 | **Email summarization digest** | AI | Scheduled daily/weekly digest: "Here are the 5 most important emails you haven't replied to" |
| 25 | **Contact management** | Feature | Build a contacts table from email history; agent can reference "email my manager" without specifying address |
| 26 | **RAG over email history** | AI | Index past emails with embeddings (pgvector in Supabase) for semantic search: "Find that email about the Q3 budget from last month" |
| 27 | **Calendar integration** | Feature | Connect Google Calendar; agent can check availability, schedule meetings from email context |
| 28 | **Voice input/output** | Feature | Whisper STT → chat → TTS response. Hands-free email management |
| 29 | **Multi-LLM support** | Feature | Add support for Anthropic Claude, Google Gemini as alternative models. Let user choose in preferences |
| 30 | **Usage tracking & billing** | Ops | Track token usage per user, implement usage quotas or credit system |
| 31 | **WebSocket upgrade** | Performance | Replace SSE with WebSocket for bidirectional real-time communication |
| 32 | **Plugin/extension system** | Architecture | Let users add custom tools (Slack notifications, Notion integration, CRM updates) |

---

## 5. Prioritized Recommendation

Top 5 things to do next, in order:

| Priority | Item | Why |
|----------|------|-----|
| **P0** | Add JWT `typ` claims + separate signing keys | Security hardening — prevents token confusion attacks |
| **P1** | Reply-in-thread support for `send_email` | Core UX gap — replies don't thread properly in Gmail |
| **P2** | Email label management + mark read/unread | The most commonly requested "what else can I do" features |
| **P3** | Write test suite | Zero test coverage is a ticking time bomb for regressions |
| **P4** | Rate limiting | Protect against abuse and runaway costs |

---

## 6. File Map

```
lca-email-assistant/
├── main.py                          # FastAPI app, lifespan, middleware stack
├── pyproject.toml                   # Dependencies (uv-managed)
│
├── agent/
│   ├── setup.py                     # LLM + tools + agent creation + HITL config
│   ├── tools.py                     # 7 tools: search, get, thread, send, draft, memory save/delete
│   ├── prompt_builder.py            # Dynamic system prompt + history trimming
│   └── utils.py                     # HITL interrupt serialization
│
├── routers/
│   ├── auth.py                      # /auth/google/code, /auth/refresh, /auth/logout
│   ├── chat.py                      # /chat/stream (SSE), /chat/resume, session CRUD
│   ├── preferences.py               # /preferences/{google_id} GET/PUT, memory clear
│   └── attachments.py               # /attachments/upload, list, delete
│
├── services/
│   ├── gmail.py                     # GmailService class, email body extraction, raw MIME building
│   ├── supabase.py                  # All DB operations (users, sessions, messages, attachments)
│   ├── db.py                        # Shared psycopg async connection pool
│   ├── store.py                     # LangGraph AsyncPostgresStore for AI memory
│   ├── preferences.py               # user_preferences table queries
│   ├── auth_helpers.py              # get_current_user_id, ownership verification
│   ├── attachments.py               # LoadedAttachment dataclass, file download
│   └── attachment_extractor.py      # PDF/DOCX/XLSX/CSV/image content extraction
│
├── middlewares/
│   └── auth.py                      # Bearer token validation, public path allowlist
│
├── utils/
│   ├── config.py                    # Pydantic Settings (env vars)
│   ├── security.py                  # JWT create/verify for access + refresh tokens
│   ├── encryption.py                # Fernet encrypt/decrypt for Google refresh tokens
│   ├── google_auth.py               # Google ID token verify, auth code exchange, token refresh
│   └── logger.py                    # Logging setup + request logging middleware
│
├── scripts/
│   ├── 001_add_google_oauth_columns.sql
│   ├── 002_recreate_tables.sql      # Full schema (users, sessions, messages, attachments + RLS)
│   ├── 003_add_chat_attachments.sql
│   ├── cleanup_expired_attachments.py
│   └── migrate.py / run_migration.py
│
└── tests/                           # ⚠️ Empty — no tests exist
```
