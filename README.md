# Claims Intake Service

A service that accepts a first notice of loss from the claims portal, validates
it against the policy master and the rule table in `docs/api-contract.md`, and
either records the notification and issues a claim reference or refuses it with
a specific reason.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. The authority. |
| `docs/requirements-brief.md` | The open work items and their acceptance criteria. |
| `docs/payload-triage.md` | Day 1 classification of the edge payloads. |
| `data/` | Synthetic policies and notification payloads. |
| `src/claims/` | The service. |
| `tests/` | Unit tests mirror `src/claims/`. Integration tests exercise HTTP. |

## Working in this repository

You are inside a Linux container. Confirm it before you start:

```
uname -sm     # Linux aarch64
pwd           # /workspaces/claims-intake
```

Dependencies are already installed. There is no install step. If a tool you
need is missing, that is a defect in the image specification and should be
reported rather than worked around.

## Run the service

From the repository root:

```
uv run uvicorn claims.api.routes:app --host 0.0.0.0 --port 8000
```

Submit a valid notification:

```
curl -sS -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{"policy_number":"MOT-4471","loss_date":"2026-04-02","claim_type":"collision","estimated_amount":"4200.00","description":"Rear ended at a junction."}'
```

A well-formed, admissible notification returns `201` and a `claim_reference`
of the form `CLM-YYYY-NNNNNN`. A refusal uses the envelope in contract
section 5 and the status in section 6.

## Run the tests

```
uv run pytest
uv run ruff check .
uv run mypy
```

## Why the image is built for linux/amd64

`uname -sm` in this container prints `Linux aarch64`. That is the machine
you are typing on: ARM. The image this service ships as has to run on
amd64, which is the architecture of the runners and hosts it will actually
be deployed to.

Docker builds for the architecture of the machine you are on unless you
say otherwise. On this host that would produce an ARM image. That image
would not start on an amd64 host, or would only run under emulation, which
is not the same as shipping the architecture you meant to ship.

`--platform linux/amd64` names the *target* architecture when it is not
the architecture of the laptop or codespace you are working from.

```
docker buildx build --platform linux/amd64 -t claims-intake:day4 --load .
docker run --rm -p 8000:8000 claims-intake:day4
```

You do not need that image to work in this repository. The `uv run`
commands above already start the service and the tests.

## Data

Everything in `data/` is synthetic and was authored for this program. It
contains no real client data and no named clients.