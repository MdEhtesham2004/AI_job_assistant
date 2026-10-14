"""Admin › Users: approvals, deactivation, roles, and admin-only access."""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import db, login, make_user

BASE = "/api/v1/admin/users"


@pytest.fixture
def admin(client: TestClient, migrated_database: str) -> dict[str, str]:
    _, headers = make_user(client, migrated_database, "admin@example.com", role="admin")
    return headers


# ---------- access control ----------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", BASE),
        ("get", f"{BASE}/counts"),
        ("get", f"{BASE}/00000000-0000-0000-0000-000000000000"),
        ("post", f"{BASE}/00000000-0000-0000-0000-000000000000/approve"),
        ("post", f"{BASE}/00000000-0000-0000-0000-000000000000/deactivate"),
        ("patch", f"{BASE}/00000000-0000-0000-0000-000000000000/role"),
    ],
)
def test_admin_endpoints_reject_normal_users(
    client: TestClient, migrated_database: str, method: str, path: str
) -> None:
    _, user = make_user(client, migrated_database, "user@example.com")

    response = client.request(method, path, json={"role": "admin"}, headers=user)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_admin_endpoints_require_sign_in(client: TestClient) -> None:
    assert client.get(BASE).status_code == 401


def test_unknown_user_returns_404(client: TestClient, admin: dict[str, str]) -> None:
    response = client.get(f"{BASE}/00000000-0000-0000-0000-000000000000", headers=admin)

    assert response.status_code == 404


# ---------- listing ----------


def test_list_shows_pending_first_and_filters(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    make_user(client, migrated_database, "approved@example.com")
    make_user(client, migrated_database, "waiting@example.com", approval="pending")
    make_user(client, migrated_database, "gone@example.com", active=False)

    everyone = client.get(BASE, headers=admin).json()
    pending = client.get(BASE, params={"status": "pending"}, headers=admin).json()
    deactivated = client.get(BASE, params={"status": "deactivated"}, headers=admin).json()
    search = client.get(BASE, params={"q": "WAIT"}, headers=admin).json()

    assert everyone["total"] == 4
    assert everyone["items"][0]["email"] == "waiting@example.com"
    assert [u["email"] for u in pending["items"]] == ["waiting@example.com"]
    assert [u["email"] for u in deactivated["items"]] == ["gone@example.com"]
    assert [u["email"] for u in search["items"]] == ["waiting@example.com"]


def test_list_is_paginated(client: TestClient, migrated_database: str, admin) -> None:
    for i in range(3):
        make_user(client, migrated_database, f"u{i}@example.com")

    body = client.get(BASE, params={"page": 2, "page_size": 2}, headers=admin).json()

    assert body["total"] == 4
    assert body["page"] == 2
    assert len(body["items"]) == 2


def test_counts_per_status(client: TestClient, migrated_database: str, admin) -> None:
    make_user(client, migrated_database, "p1@example.com", approval="pending")
    make_user(client, migrated_database, "p2@example.com", approval="pending")
    make_user(client, migrated_database, "r@example.com", approval="rejected")

    body = client.get(f"{BASE}/counts", headers=admin).json()

    assert body == {"all": 4, "pending": 2, "approved": 1, "rejected": 1, "deactivated": 0}


# ---------- approve / reject ----------


def test_approving_a_pending_account_unlocks_the_app(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    user_id, user = make_user(client, migrated_database, "w@example.com", approval="pending")
    assert client.get("/api/v1/users/me/profile", headers=user).status_code == 403

    response = client.post(f"{BASE}/{user_id}/approve", headers=admin)

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "approved"
    assert body["approved_at"] is not None
    assert body["approved_by"] is not None
    assert client.get("/api/v1/users/me/profile", headers=user).status_code == 200


def test_rejecting_stores_the_reason_and_signs_the_user_out(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    user_id, _ = make_user(client, migrated_database, "w@example.com", approval="pending")

    response = client.post(
        f"{BASE}/{user_id}/reject", json={"reason": "Not part of the pilot"}, headers=admin
    )

    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"
    assert response.json()["rejection_reason"] == "Not part of the pilot"
    assert login(client, "w@example.com").json()["error"]["code"] == "ACCOUNT_REJECTED"
    open_sessions = db(
        migrated_database,
        "SELECT count(*) FROM auth_refresh_tokens WHERE user_id = :id AND revoked_at IS NULL",
        id=user_id,
    )
    assert open_sessions == [(0,)]


def test_only_pending_accounts_can_be_rejected(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    user_id, _ = make_user(client, migrated_database, "ok@example.com")

    response = client.post(f"{BASE}/{user_id}/reject", json={}, headers=admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS"


def test_rejected_accounts_can_still_be_approved_later(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    user_id, _ = make_user(client, migrated_database, "r@example.com", approval="rejected")

    body = client.post(f"{BASE}/{user_id}/approve", headers=admin).json()

    assert body["approval_status"] == "approved"
    assert body["rejection_reason"] is None


# ---------- deactivate / reactivate ----------


def test_deactivation_blocks_the_user_immediately(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    user_id, user = make_user(client, migrated_database, "u@example.com")

    response = client.post(f"{BASE}/{user_id}/deactivate", headers=admin)

    assert response.json()["is_active"] is False
    assert client.get("/api/v1/users/me", headers=user).json()["error"]["code"] == (
        "ACCOUNT_DEACTIVATED"
    )

    client.post(f"{BASE}/{user_id}/reactivate", headers=admin)
    assert login(client, "u@example.com").status_code == 200


def test_admin_cannot_deactivate_or_demote_themselves(
    client: TestClient, migrated_database: str
) -> None:
    admin_id, admin = make_user(client, migrated_database, "admin@example.com", role="admin")

    deactivate = client.post(f"{BASE}/{admin_id}/deactivate", headers=admin)
    demote = client.patch(f"{BASE}/{admin_id}/role", json={"role": "user"}, headers=admin)

    assert deactivate.json()["error"]["code"] == "CANNOT_MODIFY_SELF"
    assert demote.json()["error"]["code"] == "CANNOT_MODIFY_SELF"


# ---------- roles ----------


def test_promoting_a_user_gives_admin_access(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    user_id, user = make_user(client, migrated_database, "u@example.com")

    response = client.patch(f"{BASE}/{user_id}/role", json={"role": "admin"}, headers=admin)

    assert response.json()["role"] == "admin"
    assert client.get(BASE, headers=user).status_code == 200


def test_pending_accounts_cannot_become_admins(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    user_id, _ = make_user(client, migrated_database, "p@example.com", approval="pending")

    response = client.patch(f"{BASE}/{user_id}/role", json={"role": "admin"}, headers=admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS"


def test_admin_actions_are_audited(
    client: TestClient, migrated_database: str, admin: dict[str, str]
) -> None:
    user_id, _ = make_user(client, migrated_database, "w@example.com", approval="pending")
    client.post(f"{BASE}/{user_id}/approve", headers=admin)
    client.post(f"{BASE}/{user_id}/deactivate", headers=admin)

    rows = db(
        migrated_database,
        "SELECT action, actor_type FROM audit_logs WHERE entity_id = :id AND actor_type = 'admin' "
        "ORDER BY created_at",
        id=user_id,
    )
    assert rows == [("user.approve", "admin"), ("user.deactivate", "admin")]
