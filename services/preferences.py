from services.supabase import supabase

def get_user_preferences(user_id: str) -> dict | None:
    """Fetch user preferences by their internal user_id."""
    response = (
        supabase.table("user_preferences")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return response.data[0] if response.data else None

def upsert_user_preferences(user_id: str, data: dict) -> dict:
    """Create or update user preferences."""
    # Ensure user_id is in the data to be upserted
    upsert_data = data.copy()
    upsert_data["user_id"] = user_id
    
    response = (
        supabase.table("user_preferences")
        .upsert(upsert_data, on_conflict="user_id")
        .execute()
    )
    return response.data[0] if response.data else {}
