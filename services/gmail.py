from google.oauth2.credentials import Credentials
from langchain_google_community import GmailToolkit
from langchain_google_community.gmail.utils import build_resource_service

from services.supabase import get_user_tokens
from utils.config import settings
from utils.encryption import decrypt_token
import base64

import re

def clean_html(raw_html: str) -> str:
    # Remove styles and scripts
    cleaner = re.compile('<style.*?>.*?</style>', re.IGNORECASE | re.DOTALL)
    text = re.sub(cleaner, '', raw_html)
    cleaner = re.compile('<script.*?>.*?</script>', re.IGNORECASE | re.DOTALL)
    text = re.sub(cleaner, '', text)
    # Remove HTML tags
    cleaner = re.compile('<.*?>')
    text = re.sub(cleaner, ' ', text)
    # Replace multiple spaces/newlines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def extract_email_body(payload: dict) -> str:
    """Recursively parse the body to extract text/plain or fallback to cleaned text/html."""
    mime_type = payload.get("mimeType")
    
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            
    if "parts" in payload:
        text_body = ""
        html_body = ""
        for part in payload["parts"]:
            body_part = extract_email_body(part)
            if part.get("mimeType") == "text/plain":
                text_body += body_part
            elif part.get("mimeType") == "text/html":
                html_body += body_part
            elif part.get("mimeType", "").startswith("multipart/"):
                text_body += body_part
        return text_body if text_body else clean_html(html_body)

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            raw_html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            return clean_html(raw_html)
            
    if "body" in payload and "data" in payload["body"]:
        data = payload["body"]["data"]
        raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return clean_html(raw) if "<html" in raw.lower() or "<body" in raw.lower() else raw

    return ""

def get_user_credentials(google_id: str) -> Credentials:
    """
    Fetch tokens from the database, decrypt the refresh token, 
    and manually construct a Google Credentials object.
    """
    # 1. Fetch user tokens from Supabase
    token_data = get_user_tokens(google_id)
    if not token_data or not token_data.get("refresh_token_encrypted"):
        raise ValueError(f"No Google tokens found for google_id: {google_id}")

    # 2. Decrypt the refresh token
    access_token = token_data.get("access_token")
    refresh_token = decrypt_token(token_data["refresh_token_encrypted"])

    # 3. Formulate the Credentials object dynamically
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=[
            "https://mail.google.com/",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        ],
    )


class GmailService:
    """
    A service class representing a Gmail API connection for a specific user.
    """
    def __init__(self, google_id: str):
        self.google_id = google_id
        self.credentials = get_user_credentials(google_id)
        self.api_resource = build_resource_service(credentials=self.credentials)

    def get_toolkit(self) -> GmailToolkit:
        """Returns a LangChain GmailToolkit for this user."""
        return GmailToolkit(api_resource=self.api_resource)

    def list_emails(
        self,
        query: str = "",
        max_results: int = 10,
        page_token: str = None,
        label_ids: list = None,
    ):
        """List emails with filters and pagination."""
        params = {
            "userId": "me",
            "maxResults": max_results,
            "q": query,
        }
        if page_token:
            params["pageToken"] = page_token
        if label_ids:
            params["labelIds"] = label_ids  # e.g. ["INBOX", "UNREAD"]

        response = self.api_resource.users().messages().list(**params).execute()

        messages = response.get("messages", [])
        next_page_token = response.get("nextPageToken")
        result_size = response.get("resultSizeEstimate", 0)

        return messages, next_page_token, result_size

    def get_email_details(self, msg_id: str, format: str = "full"):
        """format options: 'metadata', 'full', 'raw', 'minimal'"""
        msg = (
            self.api_resource.users()
            .messages()
            .get(
                userId="me",
                id=msg_id,
                format=format,
            )
            .execute()
        )

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body = extract_email_body(msg["payload"])

        return {
            "id": msg["id"],
            "thread_id": msg["threadId"],
            "snippet": msg["snippet"],
            "from": headers.get("From"),
            "to": headers.get("To"),
            "subject": headers.get("Subject"),
            "date": headers.get("Date"),
            "labels": msg.get("labelIds", []),
            "body": body,
        }

    def list_emails_paginated(
        self,
        query: str = "",
        page: int = 1,
        page_size: int = 10,
    ):
        """Fetch a specific page of results."""
        messages, next_token, total = self.list_emails(query=query, max_results=page_size)
        current_page = 1
        # print("Messages: ", messages)
        # print("next_token: ", next_token)
        # print("Total: ", total)

        # Advance through pages until we reach the desired page
        while current_page < page and next_token:
            messages, next_token, _ = self.list_emails(
                query=query,
                max_results=page_size,
                page_token=next_token,
            )
            current_page += 1

        # Fetch details for each message
        detailed = [self.get_email_details(m["id"]) for m in messages]

        return {
            "emails": detailed,
            "next_page_token": next_token,
            "has_more": next_token is not None,
            "page": current_page,
        }
