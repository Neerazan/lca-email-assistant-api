from fastapi import APIRouter, Request, Depends, HTTPException, Response
from services.preferences import get_user_preferences, upsert_user_preferences
from services.store import reset_memories
from services.supabase import get_user_by_google_id
from services.auth_helpers import verify_google_id_match
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
    verify_google_id_match(request, google_id)
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    prefs = get_user_preferences(user["id"])
    return prefs or {}

@router.put("/{google_id}")
async def update_prefs(google_id: str, data: UserPreferencesUpdate, request: Request):
    verify_google_id_match(request, google_id)
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Filter out None values to avoid overwriting with null
    update_data = data.model_dump(exclude_unset=True)
    
    prefs = upsert_user_preferences(user["id"], update_data)
    return {"success": True, "preferences": prefs}

@router.delete("/{google_id}/memory")
async def clear_memory(google_id: str, request: Request):
    verify_google_id_match(request, google_id)
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await reset_memories(user["id"])
    return {"success": True}

@router.delete("/{google_id}")
async def delete_account(google_id: str, request: Request, response: Response):
    """
    Permanently delete the user account and clear session cookies.
    """
    from services.supabase import delete_user
    from utils.config import settings

    verify_google_id_match(request, google_id)
    
    # 1. Delete user from Supabase
    delete_user(google_id)

    # 2. Clear the app_refresh_token cookie
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        "app_refresh_token",
        httponly=True,
        samesite="none" if is_prod else "lax",
        secure=is_prod,
        path="/",
    )

    return {"success": True, "message": "Account deleted successfully"}
