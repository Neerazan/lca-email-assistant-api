import asyncio
import os
import sys

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg import AsyncConnection

SUPABASE_DB_URL = "postgresql://postgres.hzmotkzqwettvizwibab:NeeRajaN634@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

async def main():
    print("Connecting to DB...")
    async with await AsyncConnection.connect(SUPABASE_DB_URL) as aconn:
        async with aconn.cursor() as cur:
            print("Creating user_preferences table...")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  user_id               uuid REFERENCES users(id) ON DELETE CASCADE UNIQUE,

                  -- Tone & Style
                  tone                  text DEFAULT 'formal',
                  length                text DEFAULT 'medium',
                  signature             text,

                  -- Identity & Context
                  full_name             text,
                  role_title            text,
                  company               text,
                  relationships         text,

                  -- Behavior
                  default_action        text DEFAULT 'draft',
                  language              text DEFAULT 'en',
                  ask_clarifying_questions boolean DEFAULT true,

                  -- Custom Instructions
                  custom_instructions   text,

                  -- Privacy
                  save_history          boolean DEFAULT true,
                  ai_memory_enabled     boolean DEFAULT true,

                  created_at            timestamptz DEFAULT now(),
                  updated_at            timestamptz DEFAULT now()
                );
            """)
            await aconn.commit()
            print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
