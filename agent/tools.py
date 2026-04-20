from typing import List, Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from services.gmail import GmailService
from services.attachments import load_attachments_for_user
from services.store import save_memory, delete_memory
from services.supabase import get_user_by_google_id
import uuid


def _is_uuid_like(value: str) -> bool:
    """Return True when the input is a UUID string."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _safe_tool_invoke(original_tool, args: dict, tool_name: str) -> str:
    """Invoke toolkit tool and normalize exceptions into model-safe errors."""
    try:
        return original_tool.invoke(args)
    except Exception as exc:
        print(f"[ERROR] Tool invoke failed for {tool_name}: {exc}")
        return (
            f"Error: Failed to run {tool_name}. "
            "Please verify your inputs and try again."
        )


def _get_toolkit_tool(config: RunnableConfig, tool_name: str):
    """Helper to get a specific tool from the Gmail toolkit."""
    google_id = config.get("configurable", {}).get("google_id")
    if not google_id:
        return None
    service = GmailService(google_id)
    toolkit = service.get_toolkit()
    return next((t for t in toolkit.get_tools() if t.name == tool_name), None)


@tool
def search_emails(query: str, config: RunnableConfig, max_results: int = 10) -> str:
    """
    Search Gmail emails using a query string.

    Args:
        query: Gmail search query (e.g., "is:unread", "from:boss@example.com").
        max_results: Maximum number of emails to return (default 10).
            Returned message/thread IDs should be used for get_email/get_thread.
    """
    original_tool = _get_toolkit_tool(config, "search_gmail")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    return _safe_tool_invoke(
        original_tool,
        {"query": query, "max_results": max_results},
        "search_gmail",
    )


@tool
def get_email(message_id: str, config: RunnableConfig) -> str:
    """
    Get a specific email message by its ID.

    Args:
        message_id: Gmail message resource ID returned by search/thread tools.
            Do not pass chat/session/attachment UUIDs.
    """
    if _is_uuid_like(message_id):
        return (
            "Error: Invalid Gmail message_id format. "
            "Use a Gmail message ID returned by search_emails or get_thread."
        )
    original_tool = _get_toolkit_tool(config, "get_gmail_message")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    return _safe_tool_invoke(
        original_tool,
        {"message_id": message_id},
        "get_gmail_message",
    )


@tool
def get_thread(thread_id: str, config: RunnableConfig) -> str:
    """
    Get a specific email thread by its thread ID.

    Args:
        thread_id: Gmail thread ID returned by Gmail search/thread APIs.
    """
    if _is_uuid_like(thread_id):
        return (
            "Error: Invalid Gmail thread_id format. "
            "Use a Gmail thread ID returned by search_emails or get_thread."
        )
    original_tool = _get_toolkit_tool(config, "get_gmail_thread")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    return _safe_tool_invoke(
        original_tool,
        {"thread_id": thread_id},
        "get_gmail_thread",
    )


@tool
def send_email(
    message: str,
    to: str,
    subject: str,
    config: RunnableConfig,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
) -> str:
    """
    Send an email message.

    Args:
        message: The body/content of the email to send.
        to: The recipient's email address.
        subject: The subject line of the email.
        cc: Optional list of CC recipients.
        bcc: Optional list of BCC recipients.
        attachments: Optional list of uploaded attachment IDs.
    """
    google_id = config.get("configurable", {}).get("google_id")
    thread_id = config.get("configurable", {}).get("thread_id")
    if not google_id:
        return "Error: User is not authenticated or google_id is missing."

    if attachments:
        user = get_user_by_google_id(google_id)
        if not user:
            return "Error: User is not authenticated or google_id is missing."
        try:
            loaded = load_attachments_for_user(
                attachment_ids=attachments,
                user_id=user["id"],
                thread_id=thread_id,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        service = GmailService(google_id)
        try:
            return service.send_raw_email(
                message=message,
                subject=subject,
                to=[to],
                cc=cc,
                bcc=bcc,
                attachments=[
                    {
                        "filename": item.filename,
                        "mime_type": item.mime_type,
                        "content": item.content,
                    }
                    for item in loaded
                ],
            )
        except Exception as exc:
            print(f"[ERROR] send_raw_email failed: {exc}")
            return "Error: Failed to send email. Please try again."

    original_tool = _get_toolkit_tool(config, "send_gmail_message")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    args = {"message": message, "to": [to], "subject": subject}
    if cc:
        args["cc"] = cc
    if bcc:
        args["bcc"] = bcc
    return _safe_tool_invoke(original_tool, args, "send_gmail_message")


@tool
def create_draft(
    message: str,
    to: str,
    subject: str,
    config: RunnableConfig,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
) -> str:
    """
    Create a draft email.

    Args:
        message: The body/content of the draft email.
        to: The recipient's email address.
        subject: The subject line of the draft.
        cc: Optional list of CC recipients.
        bcc: Optional list of BCC recipients.
        attachments: Optional list of uploaded attachment IDs.
    """
    google_id = config.get("configurable", {}).get("google_id")
    thread_id = config.get("configurable", {}).get("thread_id")
    if not google_id:
        return "Error: User is not authenticated or google_id is missing."

    if attachments:
        user = get_user_by_google_id(google_id)
        if not user:
            return "Error: User is not authenticated or google_id is missing."
        try:
            loaded = load_attachments_for_user(
                attachment_ids=attachments,
                user_id=user["id"],
                thread_id=thread_id,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        service = GmailService(google_id)
        try:
            return service.create_raw_draft(
                message=message,
                subject=subject,
                to=[to],
                cc=cc,
                bcc=bcc,
                attachments=[
                    {
                        "filename": item.filename,
                        "mime_type": item.mime_type,
                        "content": item.content,
                    }
                    for item in loaded
                ],
            )
        except Exception as exc:
            print(f"[ERROR] create_raw_draft failed: {exc}")
            return "Error: Failed to create draft. Please try again."

    original_tool = _get_toolkit_tool(config, "create_gmail_draft")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    args = {"message": message, "to": [to], "subject": subject}
    if cc:
        args["cc"] = cc
    if bcc:
        args["bcc"] = bcc
    return _safe_tool_invoke(original_tool, args, "create_gmail_draft")


@tool
async def save_memory_tool(key: str, memory_fact: str, config: RunnableConfig) -> str:
    """
    Save a new fact about the user to their persistent AI memory.
    
    Args:
        key: A short, unique, snake_case identifier for this memory (e.g., 'boss_name', 'prefers_casual_tone').
        memory_fact: The full sentence describing what you learned about the user.
    """
    google_id = config.get("configurable", {}).get("google_id")
    if not google_id:
        return "Error: missing google_id in config"
    user = get_user_by_google_id(google_id)
    if not user:
        return "Error: user not found"
        
    await save_memory(user["id"], key, {"memory": memory_fact})
    return f"Successfully saved memory: {key}"


@tool
async def delete_memory_tool(key: str, config: RunnableConfig) -> str:
    """
    Delete a specific memory fact about the user from their persistent AI memory.
    
    Args:
        key: The short, unique identifier of the memory to delete.
    """
    google_id = config.get("configurable", {}).get("google_id")
    if not google_id:
        return "Error: missing google_id in config"
    user = get_user_by_google_id(google_id)
    if not user:
        return "Error: user not found"
        
    await delete_memory(user["id"], key)
    return f"Successfully deleted memory: {key}"
