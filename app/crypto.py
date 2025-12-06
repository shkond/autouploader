"""Cryptographic utilities for token encryption.

Uses Fernet symmetric encryption from the cryptography library.
The encryption key is derived from the SECRET_KEY setting.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Get or create Fernet instance with derived key.
    
    Uses SECRET_KEY from settings, hashed to 32 bytes for Fernet.
    
    Returns:
        Fernet instance for encryption/decryption
    """
    from app.config import get_settings

    settings = get_settings()
    secret_key = settings.secret_key

    # Derive a 32-byte key from SECRET_KEY using SHA-256
    key_bytes = hashlib.sha256(secret_key.encode()).digest()
    # Fernet requires base64-encoded 32-byte key
    fernet_key = base64.urlsafe_b64encode(key_bytes)

    return Fernet(fernet_key)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string.
    
    Args:
        plaintext: The token to encrypt
        
    Returns:
        Base64-encoded encrypted token
    """
    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(plaintext.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    """Decrypt an encrypted token string.
    
    Args:
        ciphertext: Base64-encoded encrypted token
        
    Returns:
        Decrypted plaintext token
        
    Raises:
        InvalidToken: If decryption fails
    """
    fernet = _get_fernet()
    decrypted_bytes = fernet.decrypt(ciphertext.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


def clear_fernet_cache() -> None:
    """Clear the cached Fernet instance.
    
    Useful for testing with different keys.
    """
    _get_fernet.cache_clear()
