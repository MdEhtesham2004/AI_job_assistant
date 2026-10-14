"""Shared helpers for API tests (sync TestClient + direct SQL on the test database)."""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

PASSWORD = "correct-horse-battery"


def db(database_url: str, sql: str, **params: object) -> list[tuple]:
    """Run one SQL statement against the test database from a sync test."""

    async def run() -> list[tuple]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params)
            rows = list(result.fetchall()) if result.returns_rows else []
        await engine.dispose()
        return rows

    return asyncio.run(run())


def register(client: TestClient, email: str = "new@example.com", **extra: str):
    body = {"email": email, "full_name": "New Person", "password": PASSWORD, **extra}
    return client.post("/api/v1/auth/register", json=body)


def login(client: TestClient, email: str = "new@example.com", password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def set_status(url: str, email: str, approval: str = "approved", active: bool = True) -> None:
    db(
        url,
        "UPDATE users SET approval_status = :s, is_active = :a WHERE email = :e",
        s=approval,
        a=active,
        e=email,
    )


def set_platform(url: str, **values: object) -> None:
    """Set Settings › Platform values. Tests truncate every table (app_settings too): upsert."""
    cols = ", ".join(values)
    params = ", ".join(f":{c}" for c in values)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in values)
    db(
        url,
        f"INSERT INTO app_settings (id, {cols}) VALUES (1, {params}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}",
        **values,
    )


def make_user(
    client: TestClient,
    url: str,
    email: str,
    *,
    approval: str = "approved",
    role: str = "user",
    active: bool = True,
) -> tuple[str, dict[str, str]]:
    """Register a user, set its status/role directly, return (user_id, auth headers)."""
    response = register(client, email)
    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]
    db(
        url,
        "UPDATE users SET approval_status = :s, role = :r, is_superuser = :su, is_active = :a "
        "WHERE id = :id",
        s=approval,
        r=role,
        su=role == "admin",
        a=active,
        id=user_id,
    )
    return user_id, bearer(response.json()["access_token"])
