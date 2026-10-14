"""Encryption of secrets at rest (Gmail OAuth tokens) with Fernet (AES-128-CBC + HMAC)."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.core.errors import AppError


class EncryptionNotConfiguredError(AppError):
    status_code = 503
    code = "ENCRYPTION_NOT_CONFIGURED"
    message = "TOKEN_ENCRYPTION_KEY is missing."


class TokenCipher:
    def __init__(self, key: str) -> None:
        if not key:
            raise EncryptionNotConfiguredError()
        self._fernet = Fernet(key.encode())

    @classmethod
    def from_settings(cls, settings: Settings) -> "TokenCipher":
        return cls(settings.token_encryption_key)

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode())

    def decrypt(self, value: bytes) -> str:
        try:
            return self._fernet.decrypt(value).decode()
        except InvalidToken as exc:  # key changed: the user must reconnect
            raise EncryptionNotConfiguredError(
                "Stored tokens cannot be decrypted (TOKEN_ENCRYPTION_KEY changed). "
                "Reconnect Gmail.",
                code="TOKEN_DECRYPT_FAILED",
            ) from exc
