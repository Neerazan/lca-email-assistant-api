-- Full Schema Recreation Script
-- WARNING: Running these DROP statements will DELETE all existing data.

DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS chat_sessions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Enable UUID extension if not already enabled (Supabase usually has this by default)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- --------------------------------------------------------
-- 1. USERS TABLE
-- --------------------------------------------------------
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT NOT NULL,
    google_id TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    access_token TEXT,
    refresh_token_encrypted TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger to auto-update updated_at column on users
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_modtime
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE PROCEDURE update_modified_column();


-- --------------------------------------------------------
-- 2. CHAT SESSIONS TABLE
-- --------------------------------------------------------
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster lookup of a user's sessions
CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);


-- --------------------------------------------------------
-- 3. CHAT MESSAGES TABLE
-- --------------------------------------------------------
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster lookup of messages in a session
CREATE INDEX idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX idx_chat_messages_created_at ON chat_messages(created_at);

-- --------------------------------------------------------
-- 4. RLS POLICIES (Optional but recommended for Supabase)
-- --------------------------------------------------------
-- If you are using the Service Role Key on the backend, RLS won't block backend operations.
-- But it's good practice to enable RLS so the Anon Key can't maliciously access data.

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

-- If you ever query from the frontend natively using Anon Key, you'd add policies here. 
-- Since your FastAPI backend handles all queries using the Service Role Key, 
-- simple "deny all" policies apply to the Anon key by default, which is perfect for security.
