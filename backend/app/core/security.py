import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Argon2id (Phase 1 §6).
_password_hash = PasswordHash((Argon2Hasher(),))
# Used to keep login timing the same whether or not the email exists.
_DUMMY_HASH = _password_hash.hash("timing-equaliser-not-a-real-password")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
RESET_TOKEN_TYPE = "password_reset"
FILE_TOKEN_TYPE = "file"


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    """Constant-effort check: always runs one Argon2 verification."""
    if hashed is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, hashed)


# --- Access tokens (JWT, short-lived, kept in browser memory) ---


class InvalidTokenError(Exception):
    def __init__(self, expired: bool = False) -> None:
        self.expired = expired
        super().__init__("expired" if expired else "invalid")


def create_access_token(user_id: uuid.UUID, secret_key: str, minutes: int) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires_in = minutes * 60
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM), expires_in


def decode_access_token(token: str, secret_key: str) -> uuid.UUID:
    return _decode(token, secret_key, ACCESS_TOKEN_TYPE)[0]


# --- Refresh tokens (opaque random strings; only their SHA-256 is stored) ---


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Password-reset tokens (JWT bound to the current password hash → single use) ---


def _password_fingerprint(hashed_password: str, secret_key: str) -> str:
    digest = hmac.new(secret_key.encode(), hashed_password.encode(), hashlib.sha256)
    return digest.hexdigest()[:16]


def create_password_reset_token(
    user_id: uuid.UUID, hashed_password: str, secret_key: str, minutes: int
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": RESET_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "pwd": _password_fingerprint(hashed_password, secret_key),
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


@dataclass(frozen=True)
class ResetTokenClaims:
    user_id: uuid.UUID
    password_fingerprint: str

    def matches(self, hashed_password: str, secret_key: str) -> bool:
        expected = _password_fingerprint(hashed_password, secret_key)
        return hmac.compare_digest(self.password_fingerprint, expected)


def decode_password_reset_token(token: str, secret_key: str) -> ResetTokenClaims:
    user_id, payload = _decode(token, secret_key, RESET_TOKEN_TYPE)
    return ResetTokenClaims(user_id=user_id, password_fingerprint=str(payload.get("pwd", "")))


# --- Signed file links (short-lived; issued only to the owner of the file) ---


@dataclass(frozen=True)
class FileTokenClaims:
    owner_id: uuid.UUID
    key: str
    filename: str
    content_type: str


def create_file_token(claims: FileTokenClaims, secret_key: str, minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(claims.owner_id),
        "type": FILE_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "key": claims.key,
        "name": claims.filename,
        "ct": claims.content_type,
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def decode_file_token(token: str, secret_key: str) -> FileTokenClaims:
    owner_id, payload = _decode(token, secret_key, FILE_TOKEN_TYPE)
    try:
        return FileTokenClaims(
            owner_id=owner_id,
            key=str(payload["key"]),
            filename=str(payload["name"]),
            content_type=str(payload["ct"]),
        )
    except KeyError as exc:
        raise InvalidTokenError() from exc


def _decode(token: str, secret_key: str, expected_type: str) -> tuple[uuid.UUID, dict]:
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError(expired=True) from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError()
    try:
        return uuid.UUID(payload["sub"]), payload
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError() from exc
