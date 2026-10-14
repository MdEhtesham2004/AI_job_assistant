"""Profile, settings and name — always the signed-in user's own data."""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import make_user

PROFILE = {
    "phone": "+91 90000 00000",
    "location": "Hyderabad",
    "headline": "React Native Developer",
    "links": {"linkedin": "https://www.linkedin.com/in/someone", "github": "https://github.com/x"},
    "timezone": "Asia/Kolkata",
}


def test_profile_starts_empty_with_default_timezone(
    client: TestClient, migrated_database: str
) -> None:
    _, headers = make_user(client, migrated_database, "a@example.com")

    response = client.get("/api/v1/users/me/profile", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "phone": None,
        "location": None,
        "headline": None,
        "links": {},
        "timezone": "Asia/Kolkata",
        "notice_period": None,
        "expected_salary": None,
    }


def test_profile_can_be_updated(client: TestClient, migrated_database: str) -> None:
    _, headers = make_user(client, migrated_database, "a@example.com")

    response = client.put("/api/v1/users/me/profile", json=PROFILE, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["headline"] == "React Native Developer"
    assert body["links"] == {
        "linkedin": "https://www.linkedin.com/in/someone",
        "github": "https://github.com/x",
    }
    assert client.get("/api/v1/users/me/profile", headers=headers).json() == body


@pytest.mark.parametrize(
    "change",
    [
        {"timezone": "Mars/Olympus"},
        {"links": {"linkedin": "not a url"}},
        {"phone": "1" * 31},
    ],
)
def test_profile_input_is_validated(
    client: TestClient, migrated_database: str, change: dict
) -> None:
    _, headers = make_user(client, migrated_database, "a@example.com")

    response = client.put("/api/v1/users/me/profile", json={**PROFILE, **change}, headers=headers)

    assert response.status_code == 422


def test_name_can_be_changed(client: TestClient, migrated_database: str) -> None:
    _, headers = make_user(client, migrated_database, "a@example.com")

    response = client.patch("/api/v1/users/me", json={"full_name": "  New Name  "}, headers=headers)

    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"


def test_settings_have_documented_defaults(client: TestClient, migrated_database: str) -> None:
    _, headers = make_user(client, migrated_database, "a@example.com")

    body = client.get("/api/v1/users/me/settings", headers=headers).json()

    assert body["threshold_use_master"] == 85
    assert body["threshold_tailor"] == 65
    assert body["score_weights"] == {
        "skills": 40,
        "experience": 25,
        "technology": 20,
        "education": 10,
        "location": 5,
    }
    assert body["daily_send_cap"] == 25
    assert body["automation_enabled"] is False
    assert body["monthly_ai_budget_usd"] == "5.00"


def test_settings_partial_update_keeps_other_values(
    client: TestClient, migrated_database: str
) -> None:
    _, headers = make_user(client, migrated_database, "a@example.com")

    response = client.patch(
        "/api/v1/users/me/settings", json={"daily_send_cap": 10}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["daily_send_cap"] == 10
    assert response.json()["threshold_use_master"] == 85


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"threshold_tailor": 90}, "INVALID_THRESHOLDS"),
        (
            {
                "score_weights": {
                    "skills": 50,
                    "experience": 25,
                    "technology": 20,
                    "education": 10,
                    "location": 5,
                }
            },
            "VALIDATION_ERROR",
        ),
        ({"send_interval_seconds": 5}, "VALIDATION_ERROR"),
    ],
)
def test_settings_are_validated(
    client: TestClient, migrated_database: str, change: dict, code: str
) -> None:
    _, headers = make_user(client, migrated_database, "a@example.com")

    response = client.patch("/api/v1/users/me/settings", json=change, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/users/me/profile"),
        ("get", "/api/v1/users/me/settings"),
        ("patch", "/api/v1/users/me"),
    ],
)
def test_pending_accounts_cannot_use_profile_or_settings(
    client: TestClient, migrated_database: str, method: str, path: str
) -> None:
    _, headers = make_user(client, migrated_database, "p@example.com", approval="pending")

    response = client.request(method, path, json={"full_name": "x"}, headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_PENDING"
