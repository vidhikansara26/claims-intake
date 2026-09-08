# Agent decision log (Day 3)

## 1. Accepted — V-6 evaluated in submit_notification, not in POLICY_RULES

**Change.** `POLICY_RULES` contains only V-2, V-7, V-3, V-4, and V-5, each a function of a notification and a policy. `evaluate_notification` walks that table and returns `RuleFailure | None`. V-6 runs afterwards in `submit_notification` via `repository.find_matching`.

**Decision.** Accept this placement.

**Reason.** Contract section 4.1 requires the order V-1, V-2, V-7, V-3, V-4, V-5, V-6, and V-6 must compare against recorded notifications only. WI-0151 AC-3: a rejected notification is not a duplicate because nothing was written. Putting `find_matching` in `POLICY_RULES` would make `evaluate_notification` perform I/O, so a refused submission could be treated as a duplicate and the caller would get `DUPLICATE_NOTIFICATION` (409) instead of the rule that actually failed.

## 2. Rejected — evaluate_notification taking the policy client and the repository

**Change.** The starter defined `evaluate_notification(notification, policy_client, repository) -> ValidationOutcome`, so the decision function would look up the policy and the store itself.

**Decision.** Reject that signature. Use `evaluate_notification(notification, policy) -> RuleFailure | None`. Catch only `PolicyNotFound` in `submit_notification`, as V-1. Do not catch `PolicyLookupFailed`.

**Reason.** Contract section 6: the master answering with no match is `POLICY_NOT_FOUND` / 422; timeout, unreachable, and unparsable are 504 / 503 / 502. If `evaluate_notification` owned `get_policy` and caught lookup failure with `PolicyNotFound`, `submit_notification` would report that the policy does not exist when the service does not know, and the three-reason propagation tests would fail. WI-0142 AC-4 also requires that a missing policy is not evaluated as V-2; that conversion belongs at the client boundary, not inside the pure rule table.