from fastapi import HTTPException, Request, status
from services.supabase import get_chat_session, get_attachment_by_id, get_user_by_google_id

def get_current_user_id(request: Request) -> str:
    """Extract user UUID from request state."""
    user_payload = getattr(request.state, "user", None)
    if not user_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    google_id = user_payload.get("sub")
    user = get_user_by_google_id(google_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User record not found"
        )
    return user["id"]

def verify_session_ownership(session_id: str, user_id: str):
    """Ensure the chat session belongs to the user."""
    session = get_chat_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    if str(session["user_id"]) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not own this session"
        )
    return session

def verify_attachment_ownership(attachment_id: str, user_id: str):
    """Ensure the attachment belongs to the user."""
    attachment = get_attachment_by_id(attachment_id, user_id)
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found or access denied"
        )
    return attachment

def verify_google_id_match(request: Request, path_google_id: str):
    """Verify that the google_id in path matches the token's sub claim."""
    user_payload = getattr(request.state, "user", None)
    if not user_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    token_google_id = user_payload.get("sub")
    if token_google_id != path_google_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Google ID mismatch"
        )
