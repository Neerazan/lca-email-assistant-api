-- Migration: Add Google OAuth columns to users table
-- Run this in Supabase SQL Editor

-- Add google_id as unique identifier from Google OAuth 'sub' claim
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id TEXT UNIQUE;

-- Encrypted refresh token (Fernet-encrypted on the backend)
ALTER TABLE users ADD COLUMN IF NOT EXISTS refresh_token_encrypted TEXT;

-- Current Google access token (short-lived, ~1 hour)
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_token TEXT;

-- Full name and avatar from Google profile
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- Ensure created_at exists with a default
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Optional: Drop the old oauth_tokens table if it exists
-- DROP TABLE IF EXISTS oauth_tokens;
