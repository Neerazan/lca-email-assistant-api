import base64

def extract_body(payload):
    """Recursively parse the body to extract text."""
    mime_type = payload.get("mimeType")
    
    # If the current part is text/plain or text/html
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            
    if "parts" in payload:
        text_body = ""
        html_body = ""
        for part in payload["parts"]:
            body_part = extract_body(part)
            if part.get("mimeType") == "text/plain":
                text_body += body_part
            elif part.get("mimeType") == "text/html":
                html_body += body_part
            elif part.get("mimeType", "").startswith("multipart/"):
                text_body += body_part
        return text_body if text_body else html_body

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            
    return ""

payload1 = {
    "mimeType": "multipart/alternative",
    "parts": [
        {
            "mimeType": "text/plain",
            "body": {
                "data": base64.urlsafe_b64encode(b"Hello plain text").decode()
            }
        },
        {
            "mimeType": "text/html",
            "body": {
                "data": base64.urlsafe_b64encode(b"Hello html text").decode()
            }
        }
    ]
}

print(extract_body(payload1))

