# X-8 Fixed Evaluation Set

X-8 measures reliability of the audited Web Evidence MVP with a fixed set of eight questions. It is not a feature test and should not be retried to improve results.

## Question Classes

- `q01 stable_fact`: simple factual answer.
- `q02 stable_legal_fact`: stable legal/date fact.
- `q03 recent_award_fact`: recent public fact.
- `q04 false_premise`: question contains a false premise.
- `q05 contested_fact`: sources or definitions may conflict.
- `q06 terminology_correction`: modern terminology correction.
- `q07 likely_no_evidence`: likely unverifiable/private fact.
- `q08 current_fact`: date-sensitive current fact.

The JSON file `eval-set-v1.json` is the source of truth for question text, order, expected behavior, and acceptance checks. The runner records its SHA-256 in `manifest.json`, `attempted.json`, and `record.json`.

## One-Run Rule

Each question may be executed at most once per output directory. The runner writes `attempted.json` immediately before starting the external command. If the command fails, times out, emits invalid JSON, or the process is interrupted, the attempt still counts and must not be deleted or retried.

`attempted.json` is written through a same-directory temporary file and an exclusive final link. If an empty or corrupted `attempted.json` exists, treat it as an unknown attempted run and do not rerun that question.

## Preconditions

- Worktree is clean.
- `HEAD` matches `--expected-head`.
- `HEAD` matches local `origin/main`.
- Output directory is outside this repository.
- Do not run live or expensive pytest markers as part of this evaluation.

The `origin/main` check compares only the local `refs/remotes/origin/main` reference already present in the clone. It does not fetch from the network and does not prove that the remote server currently has the same commit.

## Output Location

Default project convention:

```powershell
C:\PROJECT\OracleCouncil-evals\x8\<HEAD>\
```

Raw stdout and stderr are saved outside the repository. Do not add generated evaluation results to Git.

The runner creates `manifest.json` in the output directory before the first live question. Existing manifests are reused only when `eval_set_sha256`, `expected_head`, `actual_head`, and `question_ids` match. Reusing an output directory for another HEAD or another question set is rejected.

Per question:

- `attempted.json`: one-run reservation.
- `stdout.json`: raw stdout from `oracle ask`.
- `stderr.txt`: raw stderr from `oracle ask`.
- `record.json`: sanitized extracted run record.

Whole evaluation:

- `summary.jsonl`: one JSON object per completed/recovered record.
- `summary.csv`: same summary columns, UTF-8 with BOM for spreadsheet compatibility.

`record.json` and summaries do not copy stderr contents, model prompts, environment variables, credentials, or Evidence full body content. `acceptance_checks` are not automatically graded; records use `acceptance_status: not_assessed`.

## Dry Run

Dry run performs safety checks and prints the planned question order and commands without running Oracle Council and without writing `attempted.json`, `manifest.json`, stdout/stderr, records, or summaries. During development, dry run reports a dirty worktree or local `origin/main` mismatch instead of rejecting it; non-dry-run evaluation still rejects both conditions.

```powershell
py scripts/run_x8_evaluation.py `
  --eval-set evaluation/x8/eval-set-v1.json `
  --output-dir C:\PROJECT\OracleCouncil-evals\x8\b990707 `
  --expected-head b990707 `
  --all `
  --dry-run
```

## Live Run

Run each question once under the same condition. Default timeout is 600 seconds per question. A timeout keeps `attempted.json`, writes a timeout record when possible, and stops `--all`; the question must not be rerun. Python child I/O is forced to UTF-8 with `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`. The runner uses Python `subprocess.run(..., timeout=...)`; on Windows this handles the direct child process but does not guarantee termination of every descendant process tree.

```powershell
py scripts/run_x8_evaluation.py `
  --eval-set evaluation/x8/eval-set-v1.json `
  --output-dir C:\PROJECT\OracleCouncil-evals\x8\b990707 `
  --expected-head b990707 `
  --all `
  --timeout-seconds 600
```

To run only one question:

```powershell
py scripts/run_x8_evaluation.py `
  --eval-set evaluation/x8/eval-set-v1.json `
  --output-dir C:\PROJECT\OracleCouncil-evals\x8\b990707 `
  --expected-head b990707 `
  --question-id q01
```

If a question fails, do not rerun it in the same output directory. For a new HEAD, use a separate directory such as `C:\PROJECT\OracleCouncil-evals\x8\<new-head>\`.

## Stop Rules

With `--all`, normal question-level outcomes are recorded and the runner continues:

- `completed`
- `withheld`
- `unverified`
- Evidence `no_evidence`
- Evidence `partial_evidence` with individual fetch failures

Systemic failures stop `--all` before creating attempts for remaining questions:

- subprocess spawn failure
- timeout
- invalid stdout JSON
- `status` is `internal_error`, `configuration_error`, or `verification_unavailable`
- `run_id` is null
- runner exception or git state mismatch

## Recovery

If the runner stops after `attempted.json` was written, do not delete it. Use summary rebuild mode to reconstruct records from existing `attempted.json`, `stdout.json`, `stderr.txt`, and `record.json` without running `oracle ask`:

```powershell
py scripts/run_x8_evaluation.py `
  --eval-set evaluation/x8/eval-set-v1.json `
  --output-dir C:\PROJECT\OracleCouncil-evals\x8\b990707 `
  --expected-head b990707 `
  --all `
  --rebuild-summary
```

If only `attempted.json` exists, the recovered record is marked `indeterminate`; the attempt still counts.

## Leakage Check

`leakage_check` is a limited structural check. It verifies that parsed stdout JSON does not contain forbidden keys such as `content`, `body`, `raw_content`, `prompt`, `stdout`, `stderr`, `environment`, `headers`, `cookies`, `tokens`, `diagnostics`, and `notes`. Values are `passed_structural_check`, `failed_structural_check`, or `json_invalid`. It is not a guarantee that every possible credential leak has been detected.
