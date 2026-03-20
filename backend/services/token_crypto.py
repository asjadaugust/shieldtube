"""Fernet-based token encryption for OAuth tokens at rest."""

from backend.config import settings

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        key = settings.token_encryption_key
        if not key:
            return None
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns plaintext unchanged if no key configured."""
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token string. Gracefully returns input unchanged if not encrypted or no key."""
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        # Graceful fallback: value is pre-encryption plaintext
        return ciphertext
