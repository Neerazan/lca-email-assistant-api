import sys
from pathlib import Path

# Add project root to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.supabase import supabase

response = supabase.table("users").select("*").execute()
print("Connection successful:", response)
