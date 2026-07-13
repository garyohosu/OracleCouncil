# Oracle Council

Oracle Council is an experimental, auditable multi-agent verification CLI.

It asks multiple AI CLI adapters for independent answers, extracts factual
claims, collects external evidence, verifies the claims, synthesizes an answer,
and audits the result before publishing it. The current MVP supports a fully
deterministic fake mode for normal development and an opt-in real mode that can
use Claude Code, Codex CLI, Claude Code WebSearch, and HTTP evidence fetching.

## Current Status

The MVP has completed these milestones:

- Real Claude + real Codex + real Web Evidence end-to-end run completed.
- `CliSearchProvider` is wired into `oracle ask` behind explicit
  `--evidence-provider cli-search`.
- `WebEvidenceProvider.collect()` supports the Phase 0 compatibility path.
- JSON output includes sanitized Evidence summaries.
- `evidence_collect` records elapsed time, search/fetch counts, outcomes, and
  error-code metrics.
- Non-ASCII evidence URLs are normalized before HTTP fetching.
- Invalid adapter output can expose only fixed-format, allowlisted structural
  diagnostics.
- False-premise claims can be separated from proposed-answer claims with
  `claim_role`.
- X-8 fixed evaluation set and guarded runner are available.

This is still an MVP. The full SPEC §10.2 evidence engine, counter-search,
authority classification, viewer support, and automated large-scale evaluation
are not complete.

## Requirements

- Python 3.11 or newer
- `py` launcher on Windows
- Development dependencies from `.[dev]`

Install locally:

```powershell
py -m pip install -e ".[dev]"
```

Run the normal test suite:

```powershell
py -m pytest
```

The default pytest configuration excludes `live` tests.

## Basic Usage

Fake mode is deterministic and does not invoke external AI or network access:

```powershell
py -m oracle_council.cli ask "富士山の標高は何メートルですか？" `
  --adapter-mode fake `
  --json `
  --no-store
```

Manual evidence can be supplied with `--evidence-file`. If neither
`--evidence-file` nor `--evidence-provider` is specified, the CLI keeps the
historical default and uses `FakeEvidenceProvider`.

## Experimental Web Evidence

The experimental web path is enabled only when explicitly selected:

```powershell
py -m oracle_council.cli ask "富士山の標高は何メートルですか？" `
  --adapter-mode fake `
  --evidence-provider cli-search `
  --json `
  --no-store
```

`cli-search` builds:

```python
WebEvidenceProvider(
    fetcher=SafeHttpFetcher(),
    searcher=CliSearchProvider(),
)
```

This path can invoke Claude Code WebSearch and external HTTP fetching. Do not
run it in normal unit tests. Tests must mock subprocesses and HTTP access.

## Real Agent Run

A full real run consumes external AI usage and network access:

```powershell
py -m oracle_council.cli ask "富士山の標高は何メートルですか？" `
  --adapter-mode real `
  --evidence-provider cli-search `
  --json `
  --no-store
```

Use this only as an intentional live check. Do not retry failed live runs
without recording that a run was attempted.

## JSON Output Boundaries

Top-level `evidence` contains only sanitized summaries:

- `evidence_id`
- `claim_id`
- `url`
- `title`
- `source`
- `rank`
- `content_type`
- `retrieved_at`
- `excerpt`

Evidence body content, prompts, raw stdout/stderr, headers, cookies, tokens,
environment values, diagnostics, and unknown keys are not exposed.

`phases[].metrics` contains counters and code-count dictionaries only. URLs,
queries, excerpts, titles, and raw exception text are not stored in metrics.

## X-8 Evaluation Runner

The fixed evaluation set is in:

```text
evaluation/x8/eval-set-v1.json
```

Dry-run example:

```powershell
py scripts/run_x8_evaluation.py `
  --eval-set evaluation/x8/eval-set-v1.json `
  --output-dir C:\PROJECT\OracleCouncil-evals\x8\<HEAD> `
  --expected-head <HEAD> `
  --all `
  --dry-run
```

Live evaluation results must be written outside the repository, conventionally:

```text
C:\PROJECT\OracleCouncil-evals\x8\<HEAD>\
```

Each question is one-run-only per output directory. The runner writes
`attempted.json` before launching the external command, and failed attempts must
not be deleted or retried. Generated evaluation outputs must not be committed.

## Development Notes

- Use `py`, not `python`, in this Windows environment.
- Keep storage format changes explicit and reviewed.
- Do not run `claude`, `codex`, WebSearch, or live/expensive tests unless a task
  explicitly asks for a live check.
- Do not edit saved X-8 evaluation results; treat them as immutable baseline
  data.
- Commit only intentional source, test, and documentation changes.
