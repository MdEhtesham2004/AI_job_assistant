import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import ApprovedUser
from app.core.config import Settings
from app.core.security import create_access_token, hash_token
from app.services.auth import AuthService, ClientInfo
from tests.helpers import PASSWORD, bearer, db, login, register, set_status

NEW_PASSWORD = "another-strong-passphrase"
COOKIE = "refresh_token"


@pytest.fixture
def app_with_protected_route(app: FastAPI) -> FastAPI:
    @app.get("/api/v1/test/approved-only")
    async def approved_only(user: ApprovedUser) -> dict[str, str]:
        return {"email": user.email}

    return app


# ---------- registration ----------


def test_register_creates_pending_account_and_session(client: TestClient) -> None:
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["approval_status"] == "pending"
    assert body["user"]["role"] == "user"
    assert "hashed_password" not in body["user"]

    cookie = response.headers["set-cookie"].lower()
    assert f"{COOKIE}=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie


def test_register_rejects_duplicate_email_case_insensitively(client: TestClient) -> None:
    register(client, "Taken@Example.com")

    response = register(client, "taken@example.com")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"password": "short"}, "VALIDATION_ERROR"),
        ({"password": "aaaaaaaaaaaa"}, "WEAK_PASSWORD"),
        ({"email": "not-an-email"}, "VALIDATION_ERROR"),
        ({"full_name": "   "}, "VALIDATION_ERROR"),
    ],
)
def test_register_validates_input(client: TestClient, payload: dict, code: str) -> None:
    body = {"email": "new@example.com", "full_name": "New", "password": PASSWORD, **payload}

    response = client.post("/api/v1/auth/register", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_passwords_are_stored_hashed(client: TestClient, migrated_database: str) -> None:
    register(client)

    (stored,) = db(migrated_database, "SELECT hashed_password FROM users")[0]
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


# ---------- login ----------


def test_login_returns_session_and_updates_last_login(
    client: TestClient, migrated_database: str
) -> None:
    register(client)

    response = login(client)

    assert response.status_code == 200
    assert response.json()["user"]["last_login_at"] is not None


@pytest.mark.parametrize(
    ("email", "password"),
    [("new@example.com", "wrong-password-123"), ("nobody@example.com", PASSWORD)],
)
def test_login_failure_does_not_reveal_which_part_was_wrong(
    client: TestClient, email: str, password: str
) -> None:
    register(client)

    response = login(client, email, password)

    assert response.status_code == 401
    assert response.json()["error"] == {
        **response.json()["error"],
        "code": "INVALID_CREDENTIALS",
        "message": "Incorrect email or password.",
    }


@pytest.mark.parametrize(
    ("approval", "active", "code"),
    [("rejected", True, "ACCOUNT_REJECTED"), ("approved", False, "ACCOUNT_DEACTIVATED")],
)
def test_rejected_or_deactivated_accounts_cannot_sign_in(
    client: TestClient, migrated_database: str, approval: str, active: bool, code: str
) -> None:
    register(client)
    set_status(migrated_database, "new@example.com", approval, active)

    response = login(client)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == code


def test_login_is_rate_limited(client: TestClient) -> None:
    for _ in range(10):
        login(client, "nobody@example.com", "wrong-password-123")

    response = login(client, "nobody@example.com", "wrong-password-123")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert int(response.headers["Retry-After"]) >= 1


# ---------- access tokens & approval ----------


def test_me_requires_a_token(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_rejects_invalid_and_expired_tokens(client: TestClient, settings: Settings) -> None:
    user_id = register(client).json()["user"]["id"]
    expired, _ = create_access_token(user_id, settings.secret_key, minutes=-1)  # type: ignore[arg-type]

    invalid = client.get("/api/v1/users/me", headers=bearer("not-a-token"))
    old = client.get("/api/v1/users/me", headers=bearer(expired))

    assert invalid.json()["error"]["code"] == "INVALID_TOKEN"
    assert old.status_code == 401
    assert old.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_token_signed_with_another_key_is_rejected(client: TestClient) -> None:
    user_id = register(client).json()["user"]["id"]
    forged, _ = create_access_token(user_id, "x" * 40, minutes=5)  # type: ignore[arg-type]

    response = client.get("/api/v1/users/me", headers=bearer(forged))

    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_pending_user_can_see_profile_but_not_features(
    app_with_protected_route: FastAPI, migrated_database: str
) -> None:
    with TestClient(app_with_protected_route) as client:
        token = register(client).json()["access_token"]

        me = client.get("/api/v1/users/me", headers=bearer(token))
        feature = client.get("/api/v1/test/approved-only", headers=bearer(token))
        assert me.status_code == 200
        assert feature.status_code == 403
        assert feature.json()["error"]["code"] == "ACCOUNT_PENDING"

        set_status(migrated_database, "new@example.com", "approved")
        assert client.get("/api/v1/test/approved-only", headers=bearer(token)).status_code == 200


def test_deactivation_takes_effect_immediately(client: TestClient, migrated_database: str) -> None:
    token = register(client).json()["access_token"]
    set_status(migrated_database, "new@example.com", "approved", active=False)

    response = client.get("/api/v1/users/me", headers=bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_DEACTIVATED"


# ---------- refresh rotation ----------


def test_refresh_rotates_the_cookie(client: TestClient) -> None:
    register(client)
    first_cookie = client.cookies.get(COOKIE)

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert client.cookies.get(COOKIE) != first_cookie


def test_refresh_without_cookie_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_reusing_a_rotated_token_revokes_the_whole_session(
    client: TestClient, migrated_database: str
) -> None:
    register(client)
    stolen = client.cookies.get(COOKIE)
    client.post("/api/v1/auth/refresh")  # legitimate rotation
    current = client.cookies.get(COOKIE)
    # Move the rotation outside the race grace window.
    db(
        migrated_database,
        "UPDATE auth_refresh_tokens SET revoked_at = now() - interval '1 minute' "
        "WHERE revoked_at IS NOT NULL",
    )

    client.cookies.set(COOKIE, stolen, path="/api/v1/auth")
    reuse = client.post("/api/v1/auth/refresh")
    client.cookies.set(COOKIE, current, path="/api/v1/auth")
    after = client.post("/api/v1/auth/refresh")

    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "AUTH_REQUIRED"
    assert after.status_code == 401  # the legitimate token was revoked too


def test_parallel_refresh_is_a_retryable_race_not_theft(client: TestClient) -> None:
    register(client)
    old = client.cookies.get(COOKIE)
    client.post("/api/v1/auth/refresh")  # tab A rotates
    current = client.cookies.get(COOKIE)

    client.cookies.set(COOKIE, old, path="/api/v1/auth")
    racing = client.post("/api/v1/auth/refresh")  # tab B, same old cookie, moments later
    client.cookies.set(COOKIE, current, path="/api/v1/auth")
    retry = client.post("/api/v1/auth/refresh")

    assert racing.status_code == 401
    assert racing.json()["error"]["code"] == "REFRESH_RACE"
    assert retry.status_code == 200  # the session survives


def test_expired_refresh_token_is_rejected(client: TestClient, migrated_database: str) -> None:
    register(client)
    db(migrated_database, "UPDATE auth_refresh_tokens SET expires_at = now() - interval '1 day'")

    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_only_token_hashes_are_stored(client: TestClient, migrated_database: str) -> None:
    register(client)
    raw = client.cookies.get(COOKIE)

    rows = db(migrated_database, "SELECT token_hash FROM auth_refresh_tokens")
    assert rows == [(hash_token(raw),)]


# ---------- logout ----------


def test_logout_revokes_the_session_and_clears_the_cookie(client: TestClient) -> None:
    register(client)
    raw = client.cookies.get(COOKIE)

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert f'{COOKIE}=""' in response.headers["set-cookie"] or "max-age=0" in (
        response.headers["set-cookie"].lower()
    )
    client.cookies.set(COOKIE, raw, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_without_session_is_harmless(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204


# ---------- change password ----------


def test_change_password_requires_the_current_password(client: TestClient) -> None:
    token = register(client).json()["access_token"]

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong-password-123", "new_password": NEW_PASSWORD},
        headers=bearer(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"


def test_change_password_signs_out_other_devices(app: FastAPI) -> None:
    with TestClient(app) as laptop, TestClient(app) as phone:
        token = register(laptop).json()["access_token"]
        login(phone)

        response = laptop.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=bearer(token),
        )

        assert response.status_code == 200
        assert phone.post("/api/v1/auth/refresh").status_code == 401  # other device signed out
        assert laptop.post("/api/v1/auth/refresh").status_code == 200  # this device keeps going
        assert login(laptop, password=PASSWORD).status_code == 401
        assert login(laptop, password=NEW_PASSWORD).status_code == 200


# ---------- password reset ----------


def test_forgot_password_answers_the_same_for_unknown_emails(client: TestClient) -> None:
    register(client)

    known = client.post("/api/v1/auth/forgot-password", json={"email": "new@example.com"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


async def _reset_token(settings: Settings, email: str) -> str:
    from app.db.session import create_engine, create_session_factory

    engine = create_engine(settings)
    async with create_session_factory(engine)() as session:
        token = await AuthService(session, settings).request_password_reset(email, ClientInfo())
    await engine.dispose()
    assert token
    return token


def test_reset_password_works_once(client: TestClient, settings: Settings) -> None:
    register(client)
    token = asyncio.run(_reset_token(settings, "new@example.com"))

    first = client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    second = client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "third-password-xyz"}
    )

    assert first.status_code == 200
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "INVALID_RESET_TOKEN"
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_reset_password_rejects_garbage_tokens(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "garbage-token-value", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RESET_TOKEN"


# ---------- audit ----------


def test_auth_events_are_audited(client: TestClient, migrated_database: str) -> None:
    register(client)
    login(client)
    login(client, password="wrong-password-123")
    client.post("/api/v1/auth/logout")

    actions = [
        row[0]
        for row in db(
            migrated_database, "SELECT action FROM audit_logs ORDER BY created_at, action"
        )
    ]
    assert actions == ["auth.register", "auth.login", "auth.login_failed", "auth.logout"]


def test_access_token_lifetime_matches_settings(settings: Settings) -> None:
    _, expires_in = create_access_token(
        "00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
        settings.secret_key,
        settings.access_token_minutes,
    )
    assert expires_in == settings.access_token_minutes * 60
