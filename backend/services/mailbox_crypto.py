"""Symmetric encryption helper for mailbox SMTP/IMAP credentials.

We use Fernet (AES-128-CBC + HMAC-SHA256) because it's included in the
``cryptography`` package we already ship and it gives us authenticated
encryption out of the box. The key lives in the ``MAILBOX_ENCRYPTION_KEY``
env var (urlsafe base64, 32 bytes). Rotating the key requires re-writing
every mailbox row — not supported in v1.

Callers should only ever encrypt on write and decrypt on send/poll. Never
log decrypted values.
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from config import MAILBOX_ENCRYPTION_KEY

logger = logging.getLogger(__name__)

_FERNET: Fernet | None = None


class MailboxCryptoError(RuntimeError):
    """Raised when the MAILBOX_ENCRYPTION_KEY is missing or a ciphertext fails to decrypt."""


def _cipher() -> Fernet:
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    if not MAILBOX_ENCRYPTION_KEY:
        raise MailboxCryptoError(
            "MAILBOX_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and set it in the backend environment."
        )
    try:
        _FERNET = Fernet(MAILBOX_ENCRYPTION_KEY.encode("utf-8"))
    except Exception as exc:
        raise MailboxCryptoError(
            f"MAILBOX_ENCRYPTION_KEY is not a valid Fernet key (urlsafe base64, 32 bytes): {exc}"
        ) from exc
    return _FERNET


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext password to a urlsafe base64 ciphertext string."""
    if plaintext is None:
        raise MailboxCryptoError("Cannot encrypt None; pass an empty string instead.")
    token = _cipher().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a ciphertext back to the original password."""
    if not ciphertext:
        raise MailboxCryptoError("Empty ciphertext; mailbox credentials are missing.")
    try:
        return _cipher().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise MailboxCryptoError(
            "Failed to decrypt mailbox credentials — likely a key rotation or corrupted row."
        ) from exc


def is_configured() -> bool:
    """Safe pre-flight check for routers that want to 503 cleanly when the key is missing."""
    return bool(MAILBOX_ENCRYPTION_KEY)
