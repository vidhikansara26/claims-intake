"""Rule tests written from docs/api-contract.md section 4, before implementation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import NotificationRequest, Policy, RuleFailure
from claims.policy_client import PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import (
    ValidationOutcome,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
    evaluate_loss_after_inception,
    evaluate_loss_before_cancellation,
    evaluate_loss_before_expiry,
    evaluate_notification,
    submit_notification,
)


def _policy(**overrides: object) -> Policy:
    body: dict[str, object] = {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": ("collision", "theft", "glass", "liability", "weather"),
    }
    body.update(overrides)
    return Policy.model_validate(body)


def _notification(**overrides: object) -> NotificationRequest:
    body: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 6, 15),
        "claim_type": "collision",
        "estimated_amount": Decimal("1000.00"),
    }
    body.update(overrides)
    return NotificationRequest.model_validate(body)


def _assert_failed(
    result: ValidationOutcome, rule: str, code: str, **detail: object
) -> None:
    assert result.passed is False
    assert result.rule == rule
    assert result.code == code
    for key, value in detail.items():
        assert result.detail[key] == value


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


# --- V-2, V-7, V-3, V-4, V-5: pure rules (notification + policy only) ---


@pytest.mark.parametrize(
    "loss_date, should_pass",
    [
        pytest.param(date(2026, 2, 28), False, id="loss_before_inception"),
        pytest.param(date(2026, 3, 1), True, id="loss_on_inception"),
        pytest.param(date(2026, 3, 2), True, id="loss_after_inception"),
    ],
)
def test_v2_loss_date_against_inception(loss_date: date, should_pass: bool) -> None:
    policy = _policy(effective_date=date(2026, 3, 1))
    notification = _notification(loss_date=loss_date)
    result = evaluate_loss_after_inception(notification, policy)
    if should_pass:
        assert result.passed is True
    else:
        _assert_failed(
            result,
            "V-2",
            "LOSS_BEFORE_INCEPTION",
            loss_date=loss_date,
            effective_date=policy.effective_date,
        )


@pytest.mark.parametrize(
    "cancellation_date, loss_date, should_pass",
    [
        pytest.param(
            date(2026, 6, 1), date(2026, 6, 2), False, id="loss_after_cancellation"
        ),
        pytest.param(
            date(2026, 6, 1), date(2026, 6, 1), False, id="loss_on_cancellation"
        ),
        pytest.param(
            date(2026, 6, 1), date(2026, 5, 31), True, id="loss_before_cancellation"
        ),
        pytest.param(None, date(2026, 6, 15), True, id="cancellation_date_absent"),
    ],
)
def test_v7_loss_date_against_cancellation(
    cancellation_date: date | None, loss_date: date, should_pass: bool
) -> None:
    policy = _policy(cancellation_date=cancellation_date)
    notification = _notification(loss_date=loss_date)
    result = evaluate_loss_before_cancellation(notification, policy)
    if should_pass:
        assert result.passed is True
    else:
        _assert_failed(
            result,
            "V-7",
            "POLICY_CANCELLED",
            loss_date=loss_date,
            cancellation_date=cancellation_date,
        )


@pytest.mark.parametrize(
    "loss_date, should_pass",
    [
        pytest.param(date(2027, 3, 1), False, id="loss_after_expiry"),
        pytest.param(date(2027, 2, 28), True, id="loss_on_expiry"),
        pytest.param(date(2027, 2, 27), True, id="loss_before_expiry"),
    ],
)
def test_v3_loss_date_against_expiry(loss_date: date, should_pass: bool) -> None:
    policy = _policy(expiry_date=date(2027, 2, 28))
    notification = _notification(loss_date=loss_date)
    result = evaluate_loss_before_expiry(notification, policy)
    if should_pass:
        assert result.passed is True
    else:
        _assert_failed(
            result,
            "V-3",
            "LOSS_AFTER_EXPIRY",
            loss_date=loss_date,
            expiry_date=policy.expiry_date,
        )


@pytest.mark.parametrize(
    "amount, should_pass",
    [
        pytest.param(Decimal("50000.01"), False, id="amount_above_limit"),
        pytest.param(Decimal("50000.00"), True, id="amount_equal_to_limit"),
        pytest.param(Decimal("49999.99"), True, id="amount_below_limit"),
    ],
)
def test_v4_amount_against_limit(amount: Decimal, should_pass: bool) -> None:
    policy = _policy(limit=Decimal("50000.00"))
    notification = _notification(estimated_amount=amount)
    result = evaluate_amount_within_limit(notification, policy)
    if should_pass:
        assert result.passed is True
    else:
        _assert_failed(
            result,
            "V-4",
            "AMOUNT_EXCEEDS_LIMIT",
            estimated_amount=amount,
            limit=policy.limit,
        )


@pytest.mark.parametrize(
    "claim_type, permitted, should_pass",
    [
        pytest.param(
            "collision",
            ("theft", "glass", "weather", "liability"),
            False,
            id="type_not_permitted",
        ),
        pytest.param(
            "theft",
            ("theft", "glass", "weather", "liability"),
            True,
            id="type_in_permitted_set",
        ),
        pytest.param(
            "collision",
            ("collision", "theft", "glass", "liability", "weather"),
            True,
            id="type_permitted_on_standard",
        ),
    ],
)
def test_v5_claim_type_against_product(
    claim_type: str, permitted: tuple[str, ...], should_pass: bool
) -> None:
    policy = _policy(permitted_claim_types=permitted)
    notification = _notification(claim_type=claim_type)
    result = evaluate_claim_type_covered(notification, policy)
    if should_pass:
        assert result.passed is True
    else:
        _assert_failed(
            result,
            "V-5",
            "TYPE_NOT_COVERED",
            claim_type=claim_type,
            permitted_claim_types=policy.permitted_claim_types,
        )


# --- evaluate_notification: first failure only, no I/O ---


def test_evaluate_notification_returns_none_when_policy_rules_pass() -> None:
    assert evaluate_notification(_notification(), _policy()) is None


def test_evaluate_notification_returns_rule_failure_for_v2() -> None:
    notification = _notification(loss_date=date(2026, 2, 28))
    assert evaluate_notification(notification, _policy()) == RuleFailure(
        rule="V-2", code="LOSS_BEFORE_INCEPTION"
    )


def test_evaluate_notification_reports_v7_before_v3_when_both_fail() -> None:
    # WI-0158 AC-4: cancelled policy keeps original expiry; caller must see POLICY_CANCELLED.
    policy = _policy(
        effective_date=date(2025, 6, 1),
        expiry_date=date(2026, 5, 31),
        cancellation_date=date(2026, 1, 15),
    )
    notification = _notification(loss_date=date(2026, 6, 1))
    assert evaluate_notification(notification, policy) == RuleFailure(
        rule="V-7", code="POLICY_CANCELLED"
    )


# --- V-1 and V-6 live in submit_notification, not POLICY_RULES ---


@pytest.mark.parametrize(
    "policy_number, should_pass",
    [
        pytest.param("NO-SUCH-POLICY", False, id="policy_absent"),
        pytest.param("mot-4471", False, id="policy_number_wrong_case"),
        pytest.param("MOT-4471", True, id="policy_present"),
    ],
)
def test_v1_policy_must_exist_in_the_master(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    policy_number: str,
    should_pass: bool,
) -> None:
    notification = _notification(policy_number=policy_number)
    outcome = submit_notification(notification, policy_client, repository)
    recorded = repository.find_matching(
        notification.policy_number, notification.loss_date, notification.claim_type
    )
    if should_pass:
        assert outcome.passed is True
        assert outcome.claim_reference is not None
        assert recorded is not None
        assert recorded.claim_reference == outcome.claim_reference
    else:
        _assert_failed(
            outcome, "V-1", "POLICY_NOT_FOUND", policy_number=policy_number
        )
        assert recorded is None


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param("exact_match", id="all_three_keys_match"),
        pytest.param("different_policy", id="same_date_and_type_different_policy"),
        pytest.param("different_date", id="same_policy_and_type_different_date"),
        pytest.param("different_type", id="same_policy_and_date_different_type"),
        pytest.param("after_rejection", id="rejected_notification_is_not_duplicate"),
    ],
)
def test_v6_duplicate_of_recorded_notifications_only(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    scenario: str,
) -> None:
    first = _notification(
        policy_number="MOT-4471",
        loss_date=date(2026, 6, 15),
        claim_type="collision",
        estimated_amount=Decimal("1000.00"),
    )

    if scenario == "after_rejection":
        rejected = first.model_copy(update={"estimated_amount": Decimal("99999.99")})
        refused = submit_notification(rejected, policy_client, repository)
        assert refused.passed is False
        assert refused.code == "AMOUNT_EXCEEDS_LIMIT"
        retry = submit_notification(first, policy_client, repository)
        assert retry.passed is True
        assert repository.find_matching(
            first.policy_number, first.loss_date, first.claim_type
        ) is not None
        return

    first_outcome = submit_notification(first, policy_client, repository)
    assert first_outcome.passed is True
    assert first_outcome.claim_reference is not None

    second = first
    expect_duplicate = True
    if scenario == "different_policy":
        second = first.model_copy(update={"policy_number": "MOT-4472"})
        expect_duplicate = False
    elif scenario == "different_date":
        second = first.model_copy(update={"loss_date": date(2026, 6, 16)})
        expect_duplicate = False
    elif scenario == "different_type":
        second = first.model_copy(update={"claim_type": "theft"})
        expect_duplicate = False

    outcome = submit_notification(second, policy_client, repository)
    if expect_duplicate:
        _assert_failed(
            outcome,
            "V-6",
            "DUPLICATE_NOTIFICATION",
            claim_reference=first_outcome.claim_reference,
        )
    else:
        assert outcome.passed is True
        assert outcome.claim_reference != first_outcome.claim_reference


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("timeout", id="timeout"),
        pytest.param("unreachable", id="unreachable"),
        pytest.param("unparsable", id="unparsable"),
    ],
)
def test_policy_lookup_failed_propagates_with_reason_intact(
    repository: NotificationRepository, reason: str
) -> None:
    client = StubPolicyClient(fail_with=reason)  # type: ignore[arg-type]
    with pytest.raises(PolicyLookupFailed) as exc_info:
        submit_notification(_notification(), client, repository)
    assert exc_info.value.reason == reason
    assert (
        repository.find_matching(
            _notification().policy_number,
            _notification().loss_date,
            _notification().claim_type,
        )
        is None
    )