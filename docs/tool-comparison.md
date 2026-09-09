# Tool comparison

## The task

I wrote the `Dockerfile` myself in the Cursor editor. The rest of Day 4 (the section 6 mapping, the HTTP tests, the README) I took from the Cursor Agent in this chat and used human-in-the-loop as review and approved in. I did not run a second coding agent on this lab, so the comparison is those two ways of working, not two products I did not open.

## What the Cursor Agent made easy

It turned the assignment into a closed table: eleven codes, three `PolicyLookupFailed` reasons, and the FastAPI default of 422 for a bad body, which the contract names `MALFORMED_REQUEST` / 400. I could paste `routes.py` and `test_routes.py` and `uv run pytest` reported 117 passed. For a mapping that already lives in `docs/api-contract.md`
section 6, missing a row is the failure mode, and the agent held the whole table in one pass.

## What the Cursor Agent made awkward

It does not know the machine it is talking about. It gave
`docker buildx build --platform linux/amd64` as if this container had Docker. This container prints `Linux aarch64` and `docker: command not found`. It also emitted a full `Dockerfile` in the chat, which I first pasted into the shell, so bash tried to run `FROM` and `COPY` as commands. Ask mode could not write `README.md` either; I had to copy the file out of the chat, wrapping fences included. The agent is cheap
when the contract is the spec, and expensive when the next step is a fact about this environment.

## What writing the Dockerfile in the editor made easy

One file, no rule table, no test matrix. I could see `COPY src` and `COPY data` and check them against how `StubPolicyClient` resolves `Path(__file__).parents[2] / "data" / "policies.json"`. When `docker` was missing I could stop, commit the recipe, and leave the image build for a Mac that actually has Docker, instead of waiting for the agent to discover the 127.

## What writing it in the editor made awkward

Nothing in the editor tells you that this workspace has no Docker CLI. I only learned that by running the command. The editor also does not draft the platform paragraph; that sentence is why the host is ARM and the target is amd64, and I still had the agent write it.

## Preference

I would take a **closed mapping against a written contract** (status codes, error envelopes, a test per rule) to the Cursor Agent, because the decisions are already in section 6 and the cost of doing it by hand is omitting a row.

I would take a **single file whose correctness depends on the machine in front of me** (a Dockerfile, a commit, a "is Docker even installed" check) into the editor myself. The agent will happily generate a command that cannot run here; I am the one who sees `uname -sm` and `command not found`. That is not a claim that both are fine for everything. It is which failure I would rather own.