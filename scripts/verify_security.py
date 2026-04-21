import httpx
import asyncio
import sys

# This script verifies that IDOR checks are working.
# It requires a valid access token for a user.

API_URL = "http://localhost:8000"

async def test_idor(token: str, other_user_google_id: str, other_session_id: str):
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"--- Testing IDOR on Preferences ---")
    res = await httpx.get(f"{API_URL}/preferences/{other_user_google_id}", headers=headers)
    print(f"GET /preferences/{other_user_google_id}: {res.status_code} (Expected: 403)")
    
    print(f"\n--- Testing IDOR on Chat Messages ---")
    res = await httpx.get(f"{API_URL}/chat/sessions/{other_session_id}/messages", headers=headers)
    print(f"GET /chat/sessions/{other_session_id}/messages: {res.status_code} (Expected: 403 or 404)")
    
    print(f"\n--- Testing IDOR on Session Deletion ---")
    res = await httpx.delete(f"{API_URL}/chat/sessions/{other_session_id}", headers=headers)
    print(f"DELETE /chat/sessions/{other_session_id}: {res.status_code} (Expected: 403 or 404)")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python verify_security.py <token> <other_google_id> <other_session_id>")
        sys.exit(1)
    
    token = sys.argv[1]
    other_google_id = sys.argv[2]
    other_session_id = sys.argv[3]
    
    asyncio.run(test_idor(token, other_google_id, other_session_id))
