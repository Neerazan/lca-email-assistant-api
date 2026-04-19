from fastapi import APIRouter, Request, Depends, HTTPException
from services.preferences import get_user_preferences, upsert_user_preferences
from services.store import reset_memories
from services.supabase import get_user_by_google_id
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class UserPreferencesUpdate(BaseModel):
    tone: Optional[str] = None
    length: Optional[str] = None
    signature: Optional[str] = None
    full_name: Optional[str] = None
    role_title: Optional[str] = None
    company: Optional[str] = None
    relationships: Optional[str] = None
    default_action: Optional[str] = None
    language: Optional[str] = None
    ask_clarifying_questions: Optional[bool] = None
    custom_instructions: Optional[str] = None
    save_history: Optional[bool] = None
    ai_memory_enabled: Optional[bool] = None

@router.get("/{google_id}")
async def get_prefs(google_id: str, request: Request):
    # Verify auth (optional, but good practice)
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    prefs = get_user_preferences(user["id"])
    return prefs or {}

@router.put("/{google_id}")
async def update_prefs(google_id: str, data: UserPreferencesUpdate, request: Request):
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Filter out None values to avoid overwriting with null
    update_data = data.model_dump(exclude_unset=True)
    
    prefs = upsert_user_preferences(user["id"], update_data)
    return {"success": True, "preferences": prefs}

@router.delete("/{google_id}/memory")
async def clear_memory(google_id: str, request: Request):
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await reset_memories(user["id"])
    return {"success": True}
