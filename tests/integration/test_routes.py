from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator, cast

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import app, get_policy_client, get_repository
from claims.policy_client import StubPolicyClient, LookupFailureReason
from claims.repository import NotificationRepository

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")


def _payload(payload_id: str) -> dict[str, Any]:
    for filename in ("fnol_valid.json", "fnol_invalid.json", "fnol_edge.json"):
        enteries = json.loads((DATA_DIR / filename).read_text())
        for entry in enteries:
            if entry["id"] == payload_id:
                return dict(cast(dict[str, Any], entry["payload"]))
    raise KeyError(f"No entry found for {payload_id}")


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


@pytest.fixture
def client(repository: NotificationRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_policy_client] = lambda: StubPolicyClient()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _post(client: TestClient, body: dict[str, Any] | str) -> Any:
    if isinstance(body, str):
        return client.post(
            "/notifications", 
            content=body, headers={"Content-Type": "application/json"},
        )
    return client.post("/notifications", json=body)


def test_accepted_notification_returns_201_with_claim_reference(client: TestClient) -> None:
    response = _post(client, _payload("VALID-01"))
    assert response.status_code == 201
    body = response.json()
    assert CLAIM_REFERENCE.fullmatch(body["claim_reference"]) is not None
    assert body["status"] == "recorded"


@pytest.mark.parametrize(
    ("payload_id", "status", "code", "detail_keys"),
    [
        ("INVALID-01", 422, "POLICY_NOT_FOUND", ("policy_number",)),
        ("INVALID-02", 422, "LOSS_BEFORE_INCEPTION", ("loss_date", "effective_date")),
        ("INVALID-03", 422, "LOSS_AFTER_EXPIRY", ("loss_date", "expiry_date")),
        ("INVALID-04", 422, "AMOUNT_EXCEEDS_LIMIT", ("estimated_amount", "limit")),
        ("INVALID-05", 422, "TYPE_NOT_COVERED", ("claim_type", "permitted_claim_types")),
        ("INVALID-07", 422, "POLICY_CANCELLED", ("loss_date", "cancellation_date")),
    ],
)
def test_each_rule_refusal_matches_the_contract_row(
    client: TestClient,
    payload_id: str,
    status: int,
    code: str,
    detail_keys: tuple[str, ...],
) -> None:
    response = _post(client, _payload(payload_id))
    assert response.status_code == status
    body =response.json()
    assert body["code"] == code
    for key in detail_keys:
       assert key in body["detail"]
       assert body["detail"][key] is not None


def test_duplicate_notification_returns_409_with_existing_reference(client: TestClient) -> None:
    first = _post(client, _payload("VALID-01"))
    assert first.status_code == 201
    recorded = first.json()["claim_reference"]

    second = _post(client, _payload("INVALID-06"))
    assert second.status_code == 409
    assert second.json()["code"] == "DUPLICATE_NOTIFICATION"
    assert second.json()["detail"]["claim_reference"] == recorded

def test_missing_required_field_returns_400_not_a_rule_code(client: TestClient) -> None:
    response = _post(client, _payload("EDGE-08"))
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["detail"]["field"] == "estimated_amount"
    assert body["detail"]["issue"]


def test_extra_field_is_rejected_not_ignored(client: TestClient) -> None:
    body = _payload("VALID-01")
    body["unexpected"] = True
    response = _post(client, body)
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "MALFORMED_REQUEST"
    assert payload["detail"]["field"] == "unexpected"


def test_claim_type_outside_vocabulary_is_malformed_not_v5(client: TestClient) -> None:
    response = _post(client, _payload("EDGE-11"))
    assert response.status_code == 400
    assert response.json()["code"] == "MALFORMED_REQUEST"

def test_amount_with_wrong_scale_is_malformed(client: TestClient) -> None:
    response = _post(client, _payload("EDGE-12"))
    assert response.status_code == 400
    assert response.json()["code"] == "MALFORMED_REQUEST"


def test_body_that_is_not_json_returns_400_with_null_field(client: TestClient) -> None:
    response = _post(client, "not a json string")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["detail"]["field"] is None
    assert body["detail"]["issue"] is not None


@pytest.mark.parametrize(
    ("reason", "status", "code"),
    [
       ("timeout", 504, "POLICY_MASTER_TIMEOUT"),
        ("unreachable", 503, "POLICY_MASTER_UNREACHABLE"),
        ("unparsable", 502, "POLICY_MASTER_UNPARSABLE"), 
    ],
)
def test_policy_lookup_failure_returns_distinct_5xx(repository: NotificationRepository,
    reason: LookupFailureReason,
    status: int,
    code: str,
) -> None:
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_policy_client] = lambda: StubPolicyClient(
        fail_with=reason
    )
    with TestClient(app) as client:
        response = _post(client, _payload("VALID-01"))
    app.dependency_overrides.clear()
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["detail"]["dependency"] == "policy_master"
    assert body["detail"]["reason"] == reason
    assert status >= 500