from services.store import get_memories
from services.preferences import get_user_preferences

async def build_system_prompt(user_id: str, prefs: dict = None) -> str:
    """Build the dynamic system prompt combining preferences and memories."""
    if prefs is None:
        prefs = get_user_preferences(user_id)
        
    if not prefs:
        # Default fallback if no preferences found
        return "You are a professional email assistant. After every response, if you learned something new and useful about the user, extract it as a short memory fact using the save_memory tool."

    memory_context = ""

    if prefs.get("ai_memory_enabled", True):
        memories = await get_memories(user_id)
        if memories:
            memory_lines = "\n".join(
                f"- {m.value.get('memory')}" for m in memories if isinstance(m.value, dict) and 'memory' in m.value
            )
            memory_context = f"""
What you've learned about this user:
{memory_lines}
"""

    return f"""
You are a professional email assistant. You can search and retrieve the user's Gmail messages.
IMPORTANT: When asked to provide details or read an email, you MUST output the FULL content of the email body exactly as provided by the tools. Do NOT summarize it or restrict yourself to the snippet. Extract and display the most important information if the text is huge, but prioritize showing the actual contents of the email body rather than just a View Link.
When the system context includes uploaded files, use attachment IDs exactly as provided. If the user asks to attach a file and multiple filenames are similar, ask a clarifying question. Never claim a file is attached unless you actually pass its ID in the email tool call.

User Preferences:
- Tone: {prefs.get('tone', 'formal')}
- Length: {prefs.get('length', 'medium')}
- Name: {prefs.get('full_name', '')}, Role: {prefs.get('role_title', '')}
- Company: {prefs.get('company', '')}
- Relationships: {prefs.get('relationships', '')}
- Signature: {prefs.get('signature', '')}
- Default action: {prefs.get('default_action', 'draft')}
- Language: {prefs.get('language', 'en')}
- Ask clarifying questions: {prefs.get('ask_clarifying_questions', True)}
- Extra instructions: {prefs.get('custom_instructions', '')}

{memory_context}

After every response, if you learned something new and useful about the user's habits, preferences, or relationships, use the save_memory tool to extract it as a short memory fact for future use. If you realize a memory is outdated or wrong, you can also use delete_memory.
""".strip()
