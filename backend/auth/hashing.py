"""
Security, password hashing (bcrypt), and cryptographic evidence integrity (SHA-256).
Ensures forensic validity and chain of custody for law enforcement prosecution.
"""

import hashlib
from typing import Union
from passlib.context import CryptContext

# Password hashing scheme with PBKDF2-SHA256 (standard, fully compatible across all platforms & Python 3.13)
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def generate_sha256(content: Union[str, bytes]) -> str:
    """
    Generate SHA-256 hash of scraped intelligence data.
    Provides tamper-evident proof that scraped evidence was not modified post-extraction.
    """
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content

    return hashlib.sha256(content_bytes).hexdigest()


def verify_integrity(content: Union[str, bytes], expected_hash: str) -> bool:
    """Verify data integrity against an expected SHA-256 hash."""
    actual_hash = generate_sha256(content)
    return actual_hash.lower() == expected_hash.lower()
