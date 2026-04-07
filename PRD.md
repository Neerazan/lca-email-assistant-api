# AI Email Assistant — Project Description & PRD

## 📄 Project Description
AI Email Assistant is a web application that lets users sign in with their Google account, grant Gmail access, and interact with their emails through a conversational AI chatbot. Instead of manually opening and managing emails, users can simply chat — asking things like "Do I have any unread emails?", "Summarize my emails from today", or "Reply to John saying I'll be there at 3pm". Before any email is sent, the assistant always asks for the user's confirmation, keeping the human in control at all times.

---

# 📋 PRD: AI Email Assistant

## 1. 🧠 Overview
AI Email Assistant is a human-in-the-loop conversational agent that connects to a user's Gmail account and allows them to manage their inbox through natural language chat. The system is built with a modern full-stack architecture, combining a Next.js frontend, FastAPI backend, LangGraph-powered AI agent, and Supabase for data persistence.

## 2. 🎯 Goals
*   Let users manage their Gmail inbox through natural language
*   Ensure no email is ever sent without explicit user approval
*   Provide a clean, responsive chat UI with streaming responses
*   Store user data and chat history securely
*   Build a solid, extensible foundation for future features

## 3. 👤 Target Users
Regular Gmail users who receive high volumes of email and want a faster, conversational way to triage, read, summarize, and respond to their inbox without leaving a chat interface.

## 4. 🧩 Core Features (MVP)

### 4.1 Authentication
*   Sign in with Google via Supabase Auth
*   Request Gmail read and send permissions (OAuth scopes) during sign-in
*   Store OAuth tokens securely in Supabase Vault
*   Auto-refresh tokens when expired

### 4.2 Chat Interface
*   Persistent chat window with message history
*   Streaming AI responses (token by token)
*   New chat session per conversation
*   Chat history saved to Supabase per user

### 4.3 Email Operations (via Gmail API)
The AI agent can perform the following actions through natural language:

| User Says | Agent Does |
| :--- | :--- |
| "Any new emails?" | Fetches recent unread emails |
| "Any emails from john@example.com?" | Searches emails by sender |
| "Summarize my unread emails" | Fetches and summarizes unread messages |
| "Read my latest email" | Fetches and displays the most recent email |
| "Reply to John saying I'll be there at 3pm" | Drafts reply → asks user to confirm → sends |
| "Send an email to sarah@example.com about the meeting" | Drafts email → asks user to confirm → sends |

### 4.4 Human-in-the-Loop (Send Approval)
*   Agent always pauses before sending any email
*   Shows the user the drafted email (recipient, subject, body)
*   User must explicitly click **"Approve & Send"** or **"Cancel"**
*   Only after approval does the agent call the Gmail send API

### 4.5 Streaming Responses
*   All AI responses stream in real time to the chat UI
*   User sees tokens appear progressively, not all at once

## 5. 🏗️ System Architecture
```text
┌─────────────────────────────────┐
│        Next.js Frontend         │
│  (Chat UI + Google Sign-in)     │
│       hosted on Vercel          │
└────────────┬────────────────────┘
             │ REST + SSE
┌────────────▼────────────────────┐
│        FastAPI Backend          │
│  (Auth, Sessions, Chat API)     │
│      hosted on Railway          │
└──────┬──────────────┬───────────┘
       │              │
┌──────▼──────┐ ┌─────▼───────────┐
│  Supabase   │ │  LangGraph      │
│  - users    │ │  Agent          │
│  - tokens   │ │  - Gmail Tools  │
│  - sessions │ │  - LLM Chains   │
│  - history  │ │  - HITL node    │
└─────────────┘ └─────┬───────────┘
                      │
               ┌──────▼──────┐
               │  Gmail API  │
               └─────────────┘
```

## 6. 🔄 User Flow
1.  **User visits app**
    *   → clicks "Sign in with Google"
    *   → grants Gmail read + send permission
    *   → redirected to chat interface
2.  **User types a message**
    *   → FastAPI receives message
    *   → LangGraph agent processes it
    *   → agent calls Gmail tools if needed
    *   → response streams back to UI
3.  **User asks to send/reply to an email**
    *   → agent drafts the email
    *   → agent **PAUSES** and shows draft to user
    *   → user clicks "Approve & Send" or "Cancel"
    *   → if approved → Gmail API sends the email
    *   → agent confirms in chat

## 7. 🖥️ UI Design

### Pages
| Page | Description |
| :--- | :--- |
| `/` | Landing page with app description and "Sign in with Google" button |
| `/chat` | Main chat interface (protected route, requires auth) |

### Chat Page Layout
```text
┌─────────────────────────────────────────┐
│  Header: logo + user avatar + sign out  │
├─────────────────────────────────────────┤
│                                         │
│         Chat message history            │
│                                         │
│  [User]: Any new emails?                │
│  [AI]: You have 3 unread emails...      │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │  📧 Draft Email Preview         │    │
│  │  To: john@example.com           │    │
│  │  Subject: Re: Meeting           │    │
│  │  Body: I'll be there at 3pm...  │    │
│  │  [Approve & Send]  [Cancel]     │    │
│  └─────────────────────────────────┘    │
│                                         │
├─────────────────────────────────────────┤
│  [Type a message...]          [Send]    │
└─────────────────────────────────────────┘
```

## 8. ⚙️ Tech Stack
| Layer | Technology |
| :--- | :--- |
| Frontend | Next.js 14, Tailwind CSS, Vercel AI SDK |
| Backend | FastAPI (Python) |
| AI Agent | LangChain, LangGraph, OpenAI GPT-4o |
| Auth | Supabase Auth (Google OAuth 2.0) |
| Database | Supabase (PostgreSQL) |
| Email | Gmail API |
| Agent Memory | LangGraph InMemorySaver |
| Frontend Hosting | Vercel |
| Backend Hosting | Railway |

## 9. 📁 Project Structure
```text
ai-email-assistant/
│
├── frontend/                          # Next.js app
│   ├── app/
│   │   ├── page.tsx                   # Landing page
│   │   ├── chat/
│   │   │   └── page.tsx               # Chat interface
│   │   └── api/
│   │       └── chat/
│   │           └── route.ts           # Proxy to FastAPI
│   ├── components/
│   │   ├── ChatWindow.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── EmailDraftCard.tsx         # Approval UI
│   │   └── StreamingMessage.tsx
│   └── lib/
│       └── supabaseClient.ts
│
└── backend/                           # FastAPI app
    ├── main.py                        # App entry point
    ├── routers/
    │   ├── auth.py                    # OAuth + token handling
    │   └── chat.py                    # Chat + SSE endpoint
    ├── agent/
    │   ├── graph.py                   # LangGraph workflow
    │   ├── nodes.py                   # classify, summarize, reply nodes
    │   ├── state.py                   # Agent state schema
    │   └── tools.py                   # Gmail tools
    ├── services/
    │   ├── gmail.py                   # Gmail API wrapper
    │   └── supabase.py                # Supabase client + queries
    ├── utils/
    │   └── prompts.py                 # LLM prompt templates
    └── requirements.txt
```

## 10. 🗄️ Database Schema (Supabase)

```sql
-- Users (mostly handled by Supabase Auth)
users (id, email, full_name, avatar_url, created_at)

-- OAuth tokens (encrypted via Supabase Vault)
oauth_tokens (id, user_id, access_token, refresh_token, expires_at)

-- Chat sessions
chat_sessions (id, user_id, title, created_at)

-- Chat messages
chat_messages (id, session_id, role, content, created_at)
```

## 11. ⚠️ Constraints
*   No email is ever sent without explicit user approval
*   OAuth tokens must be stored encrypted, never in plain text
*   MVP uses `InMemorySaver` — agent state is lost on server restart
*   No bulk email operations (no "delete all", "mark all read")
*   Single Gmail account per user for MVP

## 12. ✅ Success Criteria
*   [ ] User can sign in with Google and grant Gmail access
*   [ ] User can ask about their emails in natural language
*   [ ] Agent fetches and summarizes real Gmail data
*   [ ] Agent always pauses and shows draft before sending
*   [ ] Responses stream in real time in the chat UI
*   [ ] Chat history is saved and retrievable
*   [ ] App is deployed and accessible via public URL

## 13. 🚀 Future Improvements (Post-MVP)
*   Email categorization and labeling
*   Scheduled email sending
*   Multiple email account support
*   Persistent LangGraph memory (Redis checkpointer)
*   Email attachments support
*   Mobile app