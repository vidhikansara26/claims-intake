# Agent decision log (Day 3)

## Accepted: keep POLICY_RULES free of the repository

**Produced.** The implementation commit (`1fae3e3`) put V-2, V-7, V-3, V-4, and V-5 in `POLICY_RULES` as `(notification, policy) -> ValidationOutcome` functions. `evaluate_notification` walks that table and returns `RuleFailure | None`. `submit_notification` converts `PolicyNotFound` to V-1, then runs the same table, then calls `repository.find_matching` for V-6, then records.

**Decision.** Accept that split. Do not put `find_matching` in `POLICY_RULES`.

**Reason.** Contract section 4.1 fixes the order as V-1, V-2, V-7, V-3, V-4, V-5, V-6. V-6 can only see *recorded* notifications (WI-0151 AC-3: a rejected submission is not a duplicate). A repository lookup inside `POLICY_RULES` would make `evaluate_notification` perform I/O, so a later HTTP layer could not call `evaluate_notification(notification, policy)` without a store. Leaving V-6 in `submit_notification` keeps that order without mixing deciding and persisting.

## Rejected: evaluate_notification taking the client and the repository

**Produced.** The starter (and the stub commit `b6a5dd5`) defined

`evaluate_notification(notification, policy_client, repository) -> ValidationOutcome`.

Filling that signature would have compiled, preserved section 4.1 if the body called the client first and `find_matching` last, and would have passed a review that only checked rule order.

**Decision.** Reject that signature. Change it to `evaluate_notification(notification, policy) -> RuleFailure | None`. Catch `PolicyNotFound` only in `submit_notification`. Do not catch `PolicyLookupFailed`.

**Reason.** Contract section 6 treats “the master answered and there is no policy” as `POLICY_NOT_FOUND` / 422, and timeout / unreachable / unparsable as three 5xx codes. If `evaluate_notification` owned the client, a broad handler around `get_policy` would turn `PolicyLookupFailed` into V-1, and the tests that assert the exception still has `reason` in `{"timeout", "unreachable", "unparsable"}` would go red. If it owned the repository, V-6 would run even when the function is described as a pure decision, and a refused notification could be compared as if it had been recorded (WI-0151 AC-3).

## Gate observation (step 8)

**What I pushed.** A commit on `feat/day-3-rule-engine` that made one required check fail (ruff, mypy, or pytest).

**What I saw.** Not observed yet. `git push` succeeded; `gh` is not installed in this environment, so the PR was not opened from the CLI. Open https://github.com/vidhikansara26/claims-intake/pull/new/feat/day-3-rule-engine, push a failing commit, and replace this paragraph with whether the Merge button was blocked or still enabled.

**If merge stayed enabled.** Branch protection does not require `checks`. That is a repository-configuration finding, not a workflow defect. Do not add `continue-on-error` or extra jobs to fake a gate.