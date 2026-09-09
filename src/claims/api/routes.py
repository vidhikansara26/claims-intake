"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from claims.models import NotificationRequest
from claims.policy_client import (
    LookupFailureReason,
    PolicyClient,
    PolicyLookupFailed,
    StubPolicyClient,
)
from claims.repository import NotificationRepository
from claims.service import submit_notification

app = FastAPI(title="Claims Intake Service")

_repository = NotificationRepository()

STATUS_BY_CODE: dict[str, int] = {
    "MALFORMED_REQUEST": 400,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "POLICY_CANCELLED": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "TYPE_NOT_COVERED": 422,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_MASTER_TIMEOUT": 504,
    "POLICY_MASTER_UNREACHABLE": 503,
    "POLICY_MASTER_UNPARSABLE": 502,
}

MESSAGES: dict[str, str] = {
    "MALFORMED_REQUEST": "The request could not be interpreted.",
    "POLICY_NOT_FOUND": "The policy master holds no policy with this number.",
    "LOSS_BEFORE_INCEPTION": "The loss date precedes the policy effective date.",
    "POLICY_CANCELLED": "The policy was cancelled on or before the loss date.",
    "LOSS_AFTER_EXPIRY": "The loss date falls after the policy expiry date.",
    "AMOUNT_EXCEEDS_LIMIT": "The estimated amount exceeds the policy limit.",
    "TYPE_NOT_COVERED": "The claim type is not permitted on this policy.",
    "DUPLICATE_NOTIFICATION": (
        "A notification matching this policy, loss date, and claim type already exists."
    ),
    "POLICY_MASTER_TIMEOUT": "The policy master did not respond in time.",
    "POLICY_MASTER_UNREACHABLE": "The policy master could not be reached.",
    "POLICY_MASTER_UNPARSABLE": (
        "The policy master returned a body this service could not parse."
    ),
}


LOOKUP_CODE: dict[LookupFailureReason, str] = {
    "timeout": "POLICY_MASTER_TIMEOUT",
    "unreachable": "POLICY_MASTER_UNREACHABLE",
    "unparsable": "POLICY_MASTER_UNPARSABLE",
}

def get_policy_client() -> PolicyClient:
    return StubPolicyClient()

def get_repository() -> NotificationRepository:
    return _repository

def _json_ready(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f'{value:.2f}'
    if isinstance(value, tuple):
        return [_json_ready(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    return value

def _error_body(code: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "message": MESSAGES[code],
        "detail": _json_ready(detail),
    }


def _error_response(code: str, detail: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS_BY_CODE[code],
        content=_error_body(code, detail),
    )

def _malformed_field_and_issue(exc: RequestValidationError) -> tuple[str | None, str]:
    errors = exc.errors()
    if not errors:
        return None, "uninterpretable"
    err = errors[0]
    err_type = str(err.get("type", ""))
    loc = err.get("loc", ())
    if err_type == "json_invalid":
        return None, "body_not_json"
    field: str | None = None
    for part in loc:
        if part not in {"body", "query", "path"} and not isinstance(part, int):
            field = str(part)
            break
    if err_type == "missing":
        return field, "required_field_absent"
    if err_type == "extra_forbidden":
        return field, "unknown_field"
    return field, err_type


@app.exception_handler(RequestValidationError)
async def request_not_well_formed(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    field, issue = _malformed_field_and_issue(exc)
    return _error_response("MALFORMED_REQUEST", {"field": field, "issue": issue})

@app.post("/notifications")
def create_notification(
    notification: NotificationRequest,
    policy_client: Annotated[PolicyClient, Depends(get_policy_client)],
    repository: Annotated[NotificationRepository, Depends(get_repository)],
) -> JSONResponse:
    try:
        outcome = submit_notification(notification, policy_client, repository)
    except PolicyLookupFailed as exc:
        code = LOOKUP_CODE[exc.reason]
        return _error_response(
            code,
            {"dependency": "policy_master", "reason": exc.reason},
        )
    if outcome.passed:
        return JSONResponse(
            status_code=201,
            content={
                "claim_reference": outcome.claim_reference,
                "status": "recorded",
            },
        )
    assert outcome.code is not None
    return _error_response(outcome.code, outcome.detail)