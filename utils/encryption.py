"""
Fernet-based symmetric encryption for sensitive tokens (e.g., refresh_token).

Uses a key derived from the application's ENCRYPTION_KEY env var.
The key is stretched to a valid 32-byte Fernet key via SHA-256 + base64.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from utils.config import settings


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a URL-safe base64-encoded 32-byte key from an arbitrary secret string."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_fernet_key(settings.ENCRYPTION_KEY))


def encrypt_token(plain_text: str) -> str:
    """Encrypt a plain-text token. Returns a URL-safe base64 string."""
    return _fernet.encrypt(plain_text.encode()).decode()


def decrypt_token(cipher_text: str) -> str:
    """Decrypt a previously encrypted token. Raises ValueError on failure."""
    try:
        return _fernet.decrypt(cipher_text.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt token — key mismatch or corrupted data") from exc
