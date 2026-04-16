from typing import List, Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from services.gmail import GmailService


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
    """
    original_tool = _get_toolkit_tool(config, "search_gmail")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    return original_tool.invoke({"query": query, "max_results": max_results})


@tool
def get_email(message_id: str, config: RunnableConfig) -> str:
    """
    Get a specific email message by its ID.

    Args:
        message_id: The unique ID of the email message to retrieve.
    """
    original_tool = _get_toolkit_tool(config, "get_gmail_message")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    return original_tool.invoke({"message_id": message_id})


@tool
def get_thread(thread_id: str, config: RunnableConfig) -> str:
    """
    Get a specific email thread by its thread ID.

    Args:
        thread_id: The unique ID of the email thread to retrieve.
    """
    original_tool = _get_toolkit_tool(config, "get_gmail_thread")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    return original_tool.invoke({"thread_id": thread_id})


@tool
def send_email(
    message: str,
    to: str,
    subject: str,
    config: RunnableConfig,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
) -> str:
    """
    Send an email message.

    Args:
        message: The body/content of the email to send.
        to: The recipient's email address.
        subject: The subject line of the email.
        cc: Optional list of CC recipients.
        bcc: Optional list of BCC recipients.
    """
    original_tool = _get_toolkit_tool(config, "send_gmail_message")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    args = {"message": message, "to": [to], "subject": subject}
    if cc:
        args["cc"] = cc
    if bcc:
        args["bcc"] = bcc
    return original_tool.invoke(args)


@tool
def create_draft(
    message: str,
    to: str,
    subject: str,
    config: RunnableConfig,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
) -> str:
    """
    Create a draft email.

    Args:
        message: The body/content of the draft email.
        to: The recipient's email address.
        subject: The subject line of the draft.
        cc: Optional list of CC recipients.
        bcc: Optional list of BCC recipients.
    """
    original_tool = _get_toolkit_tool(config, "create_gmail_draft")
    if not original_tool:
        return "Error: User is not authenticated or google_id is missing."
    args = {"message": message, "to": [to], "subject": subject}
    if cc:
        args["cc"] = cc
    if bcc:
        args["bcc"] = bcc
    return original_tool.invoke(args)
