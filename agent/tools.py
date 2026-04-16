from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from services.gmail import GmailService


@tool
def list_user_emails(query: str, max_results: int, config: RunnableConfig) -> str:
    """
    Search and list emails from the user's Gmail account.
    
    Args:
        query: Gmail search query (e.g., "is:unread", "from:boss@example.com").
        max_results: Maximum number of emails to return (default is 10, keep it small).
    """

    # print("Query: ", query)
    # print("Max Results: ", max_results)
    # print("Config: ", config)
    google_id = config.get("configurable", {}).get("google_id")
    if not google_id:
        return "Error: User is not authenticated or google_id is missing."
        
    try:
        service = GmailService(google_id)
        # Fetching paginated with full snippets
        result = service.list_emails_paginated(query=query, page=1, page_size=max_results)
        # print("Result: ", result)
        
        emails = result.get("emails", [])
        # print("Emails: ",emails)
        if not emails:
            return "No emails found matching the query."
            
        output = [f"Found {len(emails)} emails:"]
        for email in emails:
            output.append(
                f"\n--- Email ID: {email['id']} ---"
                f"\nFrom: {email['from']}"
                f"\nTo: {email['to']}"
                f"\nSubject: {email['subject']}"
                f"\nDate: {email['date']}"
                f"\nSnippet: {email['snippet']}..."
                f"\nBody:\n{email.get('body', 'No body content available.')}"
            )
        
        # print("OutPut: ", output)
            
        return "\n".join(output)
        
    except Exception as e:
        return f"Error fetching emails: {str(e)}"

@tool
def get_user_email_details(msg_id: str, config: RunnableConfig) -> str:
    """
    Get full metadata details of a specific email by its message ID.
    
    Args:
        msg_id: The exact ID of the email to retrieve details for.
    """
    google_id = config.get("configurable", {}).get("google_id")
    if not google_id:
        return "Error: User is not authenticated."

    try:
        service = GmailService(google_id)
        email = service.get_email_details(msg_id=msg_id, format="full")
        
        output = (
            f"--- Email ID: {email['id']} ---\n"
            f"From: {email['from']}\n"
            f"To: {email['to']}\n"
            f"Subject: {email['subject']}\n"
            f"Date: {email['date']}\n"
            f"Thread ID: {email['thread_id']}\n"
            f"Snippet: {email['snippet']}\n"
            f"Body:\n{email.get('body', 'No body content available.')}\n"
        )
        return output
    except Exception as e:
        return f"Error retrieving email details: {str(e)}"
