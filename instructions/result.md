# 実施結果

## X-8.8 AUTH_REQUIRED部分一致の廃止（2026-07-13）

1. **問題**: `classify_cli_error()`の`"auth" in lowered`と`"login" in lowered`が、`authoritative`、`authentic`、説明文中の`login`などを認証失敗として誤分類し得た。
2. **実装**: 構造化401/403と`unauthorized`は維持し、自由文は境界付きの固定allowlistへ変更した。対象は`not logged in`、`login required`、`please log in`、`authentication required`、`invalid api key`、`missing api key`、`access token expired`、refresh token失効・再利用等。
3. **負例**: `authoritative source`、`authority lookup`、`authentic response`、`author field`、`OAuth documentation`、`login page documentation`、単独の`authorization policy`は`AUTH_REQUIRED`にならず、未知の非ゼロ終了は`EXECUTION_ERROR`へフォールバックする。
4. **回帰**: 構造化401/403、unauthorized、QUOTA_EXCEEDED、RATE_LIMITED、既存固定summaryを維持。probe、login status、認証情報、stdin transport、Storage Contract、公開境界は変更していない。
5. **テスト**: 明示的認証失敗10例と誤分類防止7例を追加。
6. **検証**: `py -m pytest` = **255 passed, 6 deselected**。`git diff --check`成功。
7. **実行禁止事項**: live、expensive、q04、実CLI、`codex login status`、WebSearch、HTTPは実行していない。
8. **未解決事項**: X-8.7のAUTH_REQUIREDが実認証切れか旧部分一致の誤分類かは、保存済みsanitized情報だけでは確定できない。
9. **次の推奨作業**: ユーザー承認後、`codex login status`をローカル確認するか、別HEADでq04を1回限定再評価する。

## X-8.7 Codex stdin化後のq04 1回限定live再評価（2026-07-13）

1. **実行HEAD**: `177abc4`。main、worktree clean、origin/main一致。`55044cc`を含む。
2. **出力先**: `C:\PROJECT\OracleCouncil-evals\x8\177abc4-q04-stdin`。
3. **承認**: ユーザーの「X-8.7のq04 live実行を1回だけ承認します」を確認済み。外部実行は1回のみで、再試行・別ディレクトリ実行なし。
4. **評価セット/PYTHONPATH**: `evaluation/x8/eval-set-v1.json`を使用し、実行中だけ`src`を`PYTHONPATH`へ追加。import smoke test成功。
5. **dry-run**: q04のみ、real adapter、CLI search、JSON、`--no-store`、timeout 600秒、HEAD/origin一致、出力先リポジトリ外を確認。
6. **結果**: process exit `1`、Run status `failed`、classification `unverified`、run_id `017fbc93-58b1-4026-a23e-12910ef0d44e`、timed_out `false`。
7. **参加/call**: `codex-cli`、`claude-code`が参加。`agent_call_count=4`。
8. **Phase**: respond 2成功、claim_extract 1成功、evidence_collect 1成功、verify 失敗。verifyは`AUTH_REQUIRED`、summaryは`verify execution ended with AUTH_REQUIRED.`。stdin化後のverifyは過去の短時間`EXECUTION_ERROR`ではなく、認証要求で停止したため、verify通過・後続criticize/synthesize/auditには到達していない。
9. **Evidence**: 14件。search 5、candidate 25、fetch 23、成功14、失敗9、`FETCH_FAILED=6`、`UNSUPPORTED_CONTENT_TYPE=3`、target claim 5、claims with evidence 5、outcome `partial_evidence`。
10. **q04受入確認**: 最終回答まで到達しなかったため、18歳への訂正、20歳との混同回避、飲酒・喫煙等との区別は未評価。classificationは`unverified`で許容範囲外。
11. **再現性の判断**: 以前のverify即時`EXECUTION_ERROR`は今回の条件では再現しなかった。ただしstdin化が根本原因を解決したとは断定しない。今回は`AUTH_REQUIRED`で停止したため比較不能な外部条件が残る。
12. **安全性**: `json_parse_status=valid`、`leakage_check=passed_structural_check`。raw stdout/stderr、prompt、環境変数、認証情報はGitへ保存・公開していない。
13. **未解決事項/次の作業**: 実Codexの認証状態を含む外部要因、verify以降のstdin化動作は未確認。追加liveは承認なしに実行せず、まずFake/Contractで認証切れ時の停止を評価する。

## X-8.6 Codexの長いPhase入力をstdinへ移行（2026-07-13）

1. **現行構造**: Codex本実行は`codex exec`の位置引数へPhase入力全文を渡していた。`verify`ではClaimとEvidenceを含むため、前段より長い入力になることを確認した。
2. **実装**: prompt本文をargvから除去し、`cmd`を`codex(.cmd) exec -s read-only --ephemeral --output-schema <schema-path> [--model <model>] -`の構造に変更した。末尾の`-`でstdin入力を指定する。
3. **stdin方式**: `subprocess.run(input=question, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)`を使用し、本実行で`stdin=DEVNULL`は併用しない。probeは従来どおり維持。
4. **長文テスト**: 50,000文字超の質問、Claim、Evidenceを作成し、全文がstdinへ渡り、argv長が入力長に比例せず、識別文字列がargvに存在しないことを検証した。
5. **schema**: 一時ファイルはプログラム生成のJSON Schemaのみ。質問、Claim、Evidence、秘密文字列を含まず、成功・失敗後とも`finally`で削除される。
6. **回帰**: EXECUTION_ERROR固定summary、TIMEOUT、QUOTA_EXCEEDED、RATE_LIMITED、AUTH_REQUIRED、INVALID_OUTPUTの既存分類を維持。
7. **変更ファイル**: `src/oracle_council/adapters/codex.py`、`tests/unit/test_codex_transport.py`、`tests/unit/test_adapter_unicode.py`、`FIX_PLAN.md`、`hikitsugi.md`、`instructions/result.md`。
8. **検証**: `py -m pytest` = **238 passed, 6 deselected**。`git diff --check`成功。
9. **実行禁止事項**: codex/claude実呼び出し、WebSearch、HTTP、live、expensive、q04、8問評価は実行していない。
10. **仮説の扱い**: Windowsコマンドライン長または引数受け渡しが原因であることは未確認。今回の変更は原因候補を除去しただけで、根本原因特定やlive成功を意味しない。
11. **O-6**: CodexAdapter側のprompt transportはstdin化済み。ClaudeAdapter/CliSearchProviderを含む全体方針は未完了。
12. **次の推奨作業**: ユーザー承認後、新HEADでq04のlive再評価を1回だけ行い、verify到達とsummaryを確認する。

## X-8.5 EXECUTION_ERROR summary誤ラップ修正（2026-07-13）

1. **根本原因**: `_failure_summary()`が`failure.error_code`を確認せず、`public_summary`を常に`<phase> invalid output: ...`へラップしていた。
2. **修正**: `EXECUTION_ERROR`は`safe_error_summary()`で検証し、summary内のphaseが一致する場合は固定実行診断をそのまま使用する。phase不一致・不正形式は`<phase> execution ended with EXECUTION_ERROR.`へフォールバックする。`INVALID_OUTPUT`のみ`safe_public_summary()`で従来の構造診断ラップを行う。
3. **修正後の例**: `verify process exited with a non-zero status.`（`invalid output`なし、二重ピリオドなし）。
4. **互換性**: `criticize invalid output: missing field: critique.`、TIMEOUT、RATE_LIMITED、QUOTA_EXCEEDED、AUTH_REQUIRED等の既存固定summaryを維持。
5. **安全性**: raw stdout/stderr、prompt、モデル出力、コマンド、パス、環境変数、秘密情報をsummaryへ出さない。Storage ContractとJSONL形式は不変。
6. **追加テスト**: Fake AdapterでEXECUTION_ERRORのPhase/Execution summary、ラップ除去、二重ピリオド除去、秘密情報非混入、phase不一致フォールバックを検証。
7. **検証**: `py -m pytest` = **236 passed, 6 deselected**。`git diff --check`成功。
8. **禁止事項の遵守**: live、expensive、q04、実CLI、WebSearch、HTTP、8問評価は実行していない。
9. **変更ファイル**: `src/oracle_council/orchestrator.py`、`tests/unit/test_orchestrator.py`、`hikitsugi.md`、`instructions/result.md`。
10. **未解決事項**: X-8.4で記録した実Codex非ゼロ終了の根本原因は未特定。今回はsummary経路のみ修正。
11. **次の推奨作業**: 既存評価結果を変更せず、別途承認された実機評価で修正後summaryを確認する。

## X-8.4 q04 1回限定live再評価（2026-07-13）

1. **実行HEAD**: `bca0c90`。`main`、worktree clean、`origin/main`と一致。
2. **出力先**: `C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83`（リポジトリ外）。
3. **dry-run**: q04のみ、`--adapter-mode real --evidence-provider cli-search --json --no-store`、HEAD一致、cleanを確認。
4. **外部実行回数**: 1回。失敗後の再試行・別ディレクトリ実行なし。
5. **結果**: process exit `1`、Run status `failed`、classification `unverified`、run_id `7e891cbe-12f3-4568-bf3f-ea829dc0f962`、timed_out `false`。
6. **参加と呼び出し**: `claude-code`、`codex-cli`が参加。`agent_call_count=4`。
7. **Phase**: `respond` 2成功、`claim_extract` 1成功、`evidence_collect` 1成功、`verify` 失敗。verifyの`error_code=EXECUTION_ERROR`、sanitized summaryは`verify invalid output: verify process exited with a non-zero status..`。固定診断から非ゼロ終了相当と判別できるが、既存Orchestratorのラップにより文言が二重化している。詳細原因は未特定。
8. **Evidence**: 14件。`search_count=5`、`candidate_count=25`、`fetch_attempt_count=18`、`fetch_success_count=14`、`fetch_failure_count=4`、`FETCH_FAILED=3`、`UNSUPPORTED_CONTENT_TYPE=1`、`target_claim_count=5`、`claims_with_evidence_count=5`。
9. **受入確認**: 法定成人年齢の訂正、20歳との混同回避、飲酒・喫煙等との区別はverify失敗により最終回答まで到達せず、未評価。許容classification条件は結果`unverified`のため満たさない。
10. **前回EXECUTION_ERROR**: 再現した。今回はX-8.3の固定診断相当が出力された。
11. **漏えい**: `json_parse_status=valid`、`leakage_check=passed_structural_check`。raw stdout/stderr、prompt、環境変数、認証情報はGitへ保存していない。
12. **未解決事項**: `verify`での非ゼロ終了の根本原因、sanitized summaryの`invalid output`ラップ。評価指示によりソース修正は行わない。
13. **次の推奨作業**: Orchestratorの固定summaryラップをFakeテストで再現し、`EXECUTION_ERROR`のsummaryが`invalid output`にならないことを通常テストで修正・確認する。実CLIの再実行は別途承認が必要。

今回の変更は`instructions/result.md`と`hikitsugi.md`のみ。

## 1. 現在のEXECUTION_ERROR経路

Claude/Codex Adapterは、既知のCLIエラーを`classify_cli_error`で分類し、該当しない非ゼロ終了を`EXECUTION_ERROR`としてOrchestratorへ渡していた。従来は外部向け`error_summary`が固定の終了文だけで、失敗構造を区別できなかった。

## 2. 実装した固定診断カテゴリ

- `subprocess_nonzero_exit`: `<phase> process exited with a non-zero status.`
- `process_launch_failure`: `<phase> process could not be started.`
- `known_error_pattern_not_matched`: 固定文言生成ヘルパーで許可
- `unknown_execution_failure`: 固定文言生成ヘルパーで許可

実際のAdapter経路では、認識不能な非ゼロ終了と起動時`OSError`をそれぞれ前2者へ分類する。既知のTIMEOUT、RATE_LIMITED、QUOTA_EXCEEDED、AUTH_REQUIRED、INVALID_OUTPUTは従来分類を維持した。

## 3. 機密情報漏えい防止

`AgentFailure.public_summary`と`safe_error_summary`に固定文言のallowlistを追加した。stdout、stderr、prompt、モデル出力、実行コマンド、ファイルパス、ユーザー名、環境変数、APIキー、認証情報、Cookie、HTTP header、検索クエリ、例外本文はpublic summary、CLI JSON、Phase metrics、X-8 summaryへ出力しない。Storage ContractとJSONL形式は変更していない。

## 4. 変更ファイル

- `src/oracle_council/adapters/base.py`
- `src/oracle_council/adapters/claude.py`
- `src/oracle_council/adapters/codex.py`
- `src/oracle_council/models.py`
- `tests/unit/test_adapter_error_classification.py`
- `tests/unit/test_adapter_schema.py`
- `hikitsugi.md`
- `instructions/result.md`

## 5. 追加テスト

- 固定診断文言の生成とallowlist
- Claude/Codex双方の認識不能な非ゼロ終了
- Claude/Codex双方のプロセス起動失敗
- stderr/stdout、prompt、パス、秘密情報のsummary混入拒否
- 既存TIMEOUT、RATE_LIMITED、QUOTA_EXCEEDED、INVALID_OUTPUT分類の回帰

## 6. pytest結果

`py -m pytest`: **234 passed, 6 deselected**（既定設定でliveを除外）。

## 7. git diff --check

成功。

## 8. commit hash

`5312124`（最終的なamend後のSHAはpush確認時点で更新）。

## 9. push結果

`origin/main`へpush成功（`5312124`の実装コミットと`835a5d5`の結果記録コミット）。

## 10. q04再実行

q04 live、実CLI、実WebSearch、実HTTP、expensive評価、X-8 runnerのlive実行は行っていない。

## 11. 次回q04で識別できる範囲

同じ障害が再発した場合、既知エラー分類に該当するか、少なくとも非ゼロ終了かプロセス起動失敗かを安全な固定summaryで識別できる。stdout/stderr等の原文は保存・公開しないため、引数やサービス側理由の詳細までは特定できない。

## 12. 未解決事項と次の作業

## X-8.9 q04 live re-evaluation (2026-07-13)

- HEAD and `origin/main`: `0bdf5ca`; worktree was clean.
- Import smoke test and dry-run passed.
- One approved live run was executed in `C:\\PROJECT\\OracleCouncil-evals\\x8\\0bdf5ca-q04-authfix`.
- Result: `exit_code=1`, `status=failed`, `classification=unverified`, `timed_out=false`.
- Run ID: `d462fda2-85f6-4702-80d0-0d8ae560989e`; agent calls: `6`; participants: `codex-cli`, `claude-code`.
- `respond`, `claim_extract`, `evidence_collect`, `verify`, and `criticize` succeeded. `synthesize` failed with `COMMAND_NOT_FOUND` and sanitized summary `synthesize execution ended with COMMAND_NOT_FOUND.`; `audit` was not reached.
- Evidence: 15 items; searches 5; candidates 25; fetch attempts 20; fetch successes 15; fetch failures 5; outcome `partial_evidence`.
- `json_parse_status=valid`; `leakage_check=passed_structural_check`; acceptance was `not_assessed`.
- The run did not reproduce `AUTH_REQUIRED`; this does not prove the X-8.7 cause. Raw stdout/stderr, prompts, tokens, and external evaluation artifacts were not added to Git.
- No source or test changes were made from this live result. The remaining issue is external CLI availability for the `synthesize` phase.

The live re-evaluation was completed once after user approval. The remaining unresolved issue is external CLI availability during `synthesize`; existing evaluation artifacts were not modified.
## X-8.10 Claude phase input stdin transport (2026-07-13)

- X-8.9 context: `synthesize` was assigned to Claude and failed with sanitized `COMMAND_NOT_FOUND`; no live rerun was performed.
- `ClaudeAdapter.execute()` now removes the user-derived Phase prompt from argv and passes the complete prompt through `subprocess.run(input=prompt, ...)`.
- The production Phase invocation no longer uses `stdin=subprocess.DEVNULL`; `probe()` and `CliSearchProvider` were unchanged.
- Added `tests/unit/test_claude_transport.py` covering a 50,000-character `synthesize` input, argv exclusion, stdin contents, command flags, JSON envelope parsing, and Phase output validation.
- Updated the existing Unicode transport test to assert Claude input is carried by stdin rather than argv.
- `py -m pytest`: **258 passed, 6 deselected**; `git diff --check`: passed.
- Live, real Claude, real Codex, q04, WebSearch, HTTP, and expensive evaluation were not executed.
- Changed files: `src/oracle_council/adapters/claude.py`, `tests/unit/test_claude_transport.py`, `tests/unit/test_adapter_unicode.py`, `instructions/result.md`, and `hikitsugi.md`.
## X-8.11 q04 Claude stdin live re-evaluation (2026-07-13)

- HEAD and `origin/main`: `05714b7`; precheck, import smoke test, dry-run, and normal tests passed.
- `py -m pytest`: **258 passed, 6 deselected**; `git diff --check`: passed before live execution.
- One approved live run was executed in `C:\\PROJECT\\OracleCouncil-evals\\x8\\05714b7-q04-claude-stdin`.
- Result: `exit_code=4`, `status=completed`, `classification=withheld`, `timed_out=false`, `acceptance_status=not_assessed`.
- Run ID: `7d42b9c7-a0c5-4df3-9ad8-92f5340b7e31`; agent calls: `9`; participants: `claude-code`, `codex-cli`.
- `respond`, `claim_extract`, `evidence_collect`, `verify`, `criticize`, `synthesize`, and `audit` all succeeded. `synthesize` had `success_count=2`; `audit` had `success_count=2`. The X-8.9 `synthesize COMMAND_NOT_FOUND` did not recur.
- Evidence: 14 items; searches 5; candidates 25; fetch attempts 23; fetch successes 14; fetch failures 9; outcome `partial_evidence`.
- `json_parse_status=valid`; `leakage_check=passed_structural_check`; no error codes were reported.
- The q04 acceptance status remained `not_assessed`; no claim was made from raw model output. Raw stdout/stderr, prompts, tokens, and evaluation artifacts were not added to Git.
## X-8.12 CliSearchProvider search prompt stdin transport (2026-07-13)

- HEAD and `origin/main`: `12bc2df`; worktree was clean before implementation, and required ancestors `193706d` and `1152bcf` were present.
- `CliSearchProvider.search()` now removes the user-derived search prompt from argv and passes it through `subprocess.run(input=prompt, ...)`; production search no longer uses `stdin=subprocess.DEVNULL`.
- Search result parsing, source validation, limit handling, malformed-item skipping, timestamps, error mapping, timeout behavior, and SafeHttpFetcher boundaries were unchanged.
- Added Fake coverage for a 50,000-character Japanese query, asserting query absence from argv, complete prompt presence in stdin, fixed WebSearch flags, UTF-8 handling, and no `stdin` kwarg.
- Updated O-6 progress in `FIX_PLAN.md` to record Codex, Claude Phase, and CliSearchProvider stdin transport completion.
- `py -m pytest`: **259 passed, 6 deselected**; `git diff --check`: passed.
- Real Claude, WebSearch, q04, live, HTTP, and expensive evaluation were not executed.
- Changed files: `src/oracle_council/adapters/claude.py`, `tests/unit/test_cli_search_provider.py`, `FIX_PLAN.md`, `instructions/result.md`, and `hikitsugi.md`.
## X-8.13 q04 live re-evaluation with all three stdin transports (2026-07-14)

- HEAD and `origin/main`: `8fcdeaf`; `py -m pytest` passed (259 passed, 6 deselected, exit 0) before the live run.
- The only worktree diff was the untracked `dream.md` (unrelated to source). It was set aside with `git stash -u` before the dry-run/live run so the eval script's dirty-worktree check ran clean, then restored with `git stash pop` immediately after. This should not become standard practice; future sessions should write `dream.md` after the live run or commit it beforehand instead of stashing.
- Dry-run confirmed HEAD/origin match, clean worktree, and a non-colliding output directory.
- One approved live run was executed in `C:\PROJECT\OracleCouncil-evals\x8\8fcdeaf-q04-clisearch-stdin`.
- Result: `exit_code=0`, `status=completed`, `result_classification=verified`, run ID `18a25201-780e-419c-be72-fd412fb433aa`, `agent_call_count=7`, participants `claude-code` and `codex-cli`.
- All seven phases (`respond` through `audit`) succeeded. None of the earlier failure modes recurred (X-8.4 `EXECUTION_ERROR`, X-8.7 `AUTH_REQUIRED`, X-8.9 `synthesize COMMAND_NOT_FOUND`).
- Correction, not a first: X-8.11 (Claude Phase stdin only) had already completed all seven phases once (`synthesize`/`audit` each succeeded twice), ending `status=completed`/`classification=withheld`. What's new in X-8.13 is that with Codex, Claude Phase, and CliSearchProvider all on stdin transport, q04 reached `verified`/`exit_code=0` with acceptance criteria met — something no prior live attempt achieved.
- Evidence: 12 items; searches 4; candidates 20; fetch attempts 16; fetch successes 12; fetch failures 4 (`FETCH_FAILED`×3, `UNSUPPORTED_CONTENT_TYPE`×1); outcome `partial_evidence`.
- `json_parse_status=valid`; `leakage_check=passed_structural_check`.
- Acceptance criteria were assessed manually from the CLI's own sanitized `--json` output (not raw stdout/stderr): the premise claim (user_premise, "法定成人年齢は現在も20歳") is `contradicted`; the correction claim (2022-04-01, 18歳への引き下げ) is `verified`; and the answer distinguishes the lowered contractual-adulthood age from the still-20 drinking/smoking/public-gambling limits. All three q04 acceptance points are met. `record.json`'s `acceptance_status` field remains the runner's static `not_assessed` — the script does not auto-grade; this is a manual read.
- No source or test changes were made from this live result.
- Documentation updated: `hikitsugi.md` (4-24, with the X-8.11 correction above), `FIX_PLAN.md` (O-6 moved to §0-5, resolved), this file.
- Remaining open items: J-3, L-5, M-5, S-4–S-10, T-2, T-3 (design-gated blockers), J-4 (Clarifier second round), and evaluation of the remaining 7 X-8 questions (q01–q03, q05–q08 — q04 is no longer a clean holdout after repeated transport-debugging use).
## X-8.14 seven-question holdout evaluation, q04 excluded (2026-07-14)

- Execution HEAD: `e707d9e`; instructions commit: `e707d9e` (`docs: add gated seven-question holdout evaluation instructions`).
- Explicit approval text was confirmed verbatim before any live call: "X-8.14の残り7問holdout live実行を、q01〜q03・q05〜q08各1回、合計最大7回だけ承認します".
- Pre-checks: `git status --short` clean after moving the untracked `dream.md` outside the repo (not `git stash`); `git pull --ff-only` fast-forwarded to `e707d9e`; HEAD matched `origin/main`; `1212c67` and `8fcdeaf` both confirmed as ancestors via `git merge-base --is-ancestor`; `py -m pytest` passed (259 passed, 6 deselected, exit 0); `git diff --check` passed.
- Canonical eval set SHA-256: `35af8d4ba22fcfa7e828986ea5bc1b2f374d85258c56bdc9dcbaaf16eb6c41d5` (unchanged). Derived holdout subset SHA-256: `0511956bc1c6dace85740e0e59ec4f3faed678044f35ed39eaadee70251e7182`, generated outside the repo at `C:\PROJECT\OracleCouncil-evals\x8\e707d9e-holdout7-eval-set.json`. Verified programmatically: question order `q01,q02,q03,q05,q06,q07,q08`, exactly 7 questions, each deep-equal to its canonical counterpart, q04 absent.
- Dry-run confirmed: `adapter-mode real`, `evidence-provider cli-search`, JSON output, `--no-store`, 600s per-question timeout, output directory outside the repo, HEAD/origin match, clean worktree, q04 absent.
- Runner invoked exactly once (`--all` over the 7-question subset) with `ORACLE_COUNCIL_LIVE=1`, run in the background due to expected multi-question runtime. **Runner exit code 1 — systemic stop after q03.** External `oracle ask` calls: 3 total (q01, q02, q03). q04: 0. q05–q08: 0 attempted (no `attempted.json` created for any of them — the stop did not silently continue or retry).
- q01 (stable_fact): `exit_code=0`, `status=completed`, `classification=verified` (allowed), `run_id=0d376b4f-5574-4d81-b032-e7cf8876d531`, `agent_call_count=7`, all 7 phases succeeded, evidence 3 items (fetch 3/5, `UNSUPPORTED_CONTENT_TYPE`×2), outcome `partial_evidence`. Acceptance check (3776m, no conflicting values): **met**.
- q02 (stable_legal_fact): `exit_code=0`, `status=completed`, `classification=verified` (allowed), `run_id=18e73ed9-51e2-4acc-b327-334be89222a2`, `agent_call_count=7`, all 7 phases succeeded, evidence 6 items (fetch 6/8), outcome `partial_evidence`. Acceptance check (2022-04-01 enforcement date, no confusion with the law's separate passage date): **met**.
- q03 (recent_award_fact): `exit_code=1`, `status=internal_error`, `classification=null`, `run_id=null`, no phases/participants recorded — failure occurred before Run creation. The CLI's own structured JSON envelope (not raw stderr) reported `message: "[Errno 11001] getaddrinfo failed"`, a Windows DNS-resolution failure at the OS/socket layer, not a previously catalogued Adapter error code or Phase-level failure. `json_parse_status=valid`, `leakage_check=passed_structural_check`. Acceptance: not assessable (no final answer). This was the systemic-failure trigger the runner correctly halted on.
- Aggregate: attempted 3/7; completed 2/2 attempted-and-reached-Run, both `verified` and within `allowed_classifications`, both acceptance-met; 1 `internal_error` (q03); 0 retries; 0 timeouts; 0 Phase-level failures among questions that reached a Run; q04 executed 0 times; total `agent_call_count` across attempted questions 14 (q01: 7, q02: 7, q03: 0, since no Run was created).
- No source, test, config, runner, or eval-set changes were made. Raw `stdout.json` was read locally only for the sanitized answer/claims fields (acceptance) and the CLI's own structured error message (q03 diagnosis); none of it, the subset file, or other evaluation artifacts were added to Git. `stderr.txt` was not read or recorded. `dream.md` was intentionally left unmodified this session.
- Per instructions, the systemic stop was not resumed or retried in this session. Resuming q05–q08 requires a new task with a new explicit approval.
- Documentation updated: `hikitsugi.md` (4-25), this file. No other files changed.
- Next planned work: M-5 (alternate-agent selection and retry, 12-call cap) design confirmation, then L-5, then S-8, per the agreed non-parallel ordering — pending user direction on whether q05–q08 should be attempted first.
## X-8.15 q05–q08 holdout continuation (2026-07-14)

- Execution HEAD: `78ae55c` (= origin/main); instructions commit: `78ae55c` (`docs: add gated q05-q08 holdout continuation instructions`).
- Explicit approval text confirmed verbatim before any live call: "X-8.15のq05〜q08 holdout live実行を、各1回、合計最大4回だけ承認します".
- Worktree was made completely clean before starting: the untracked `dream.md` was moved outside the repo by hand (no `git stash`), leaving `git status --short` empty. Ancestors `0ec758a`, `1212c67`, `8fcdeaf` confirmed. `py -m pytest`: 259 passed, 6 deselected, exit 0. `git diff --check` passed.
- Canonical eval set SHA-256: `35af8d4ba22fcfa7e828986ea5bc1b2f374d85258c56bdc9dcbaaf16eb6c41d5` (unchanged; asserted inside the subset generator). Derived subset SHA-256: `e3e6e993efc686ea3e4837648cffba3e8bfa9e5266edaf522df81c12d7bba90b`, at `C:\PROJECT\OracleCouncil-evals\x8\78ae55c-holdout4-eval-set.json`. Verified: exactly `q05,q06,q07,q08` in order, 4 questions, each deep-equal to its canonical counterpart, q01–q04 absent.
- Dry-run confirmed: real adapter, cli-search, JSON, `--no-store`, 600s per-question timeout, output outside the repo, HEAD/origin match, clean worktree.
- Runner invoked exactly once (`--all`). **All 4 questions attempted; no systemic stop; 0 retries; 0 timeouts; q01–q04 executed 0 times; external `oracle ask` calls: 4.** Runner process exit code 4 = the first non-zero question exit code (q07's withheld exit 4) per the runner's design, not an evaluation failure.
- q05 (contested_fact): `exit_code=0`, `completed`, `verified` (allowed), `run_id=24f08a2a-16dc-4cd2-b128-d8c3a736bea8`, `agent_call_count=7`, all 7 phases succeeded, evidence 15 (search 5, candidates 25, fetch 15/16, `FETCH_FAILED`×1), `partial_evidence`. Acceptance **met** (Nile/Amazon competition, measurement/definition dependence, no over-assertion). User-premise claim `contradicted` with verified correction claims — the X-8.2 false-premise separation produced a publishable corrected answer.
- q06 (terminology_correction): `exit_code=0`, `completed`, `partially_verified` (allowed), `run_id=fe61e115-a6ee-4335-99b9-21a369bb3a42`, `agent_call_count=7`, all 7 phases succeeded, evidence 15 (search 5, candidates 25, fetch 15/17, `FETCH_FAILED`×2), `partial_evidence`. Two minor claims remained `unverified`. Acceptance **met** (活火山, 休火山 is an obsolete classification, no evidence contradiction).
- q07 (likely_no_evidence): `exit_code=4`, `completed`, `withheld` (allowed), `run_id=75201974-8879-4689-a037-498c1ebcdebf`, `agent_call_count=4` — designed withheld short-circuit (respond×2, claim_extract, evidence_collect, verify; criticize/synthesize/audit `skipped`; `final_answer` text null per U-1). Evidence 12 (search 5, candidates 20, fetch 12/15, `FETCH_FAILED`×3), `partial_evidence`; no evidence confirmed the company exists; critical claims `unverified`. Acceptance **met** (no fabricated figure, insufficiency disclosed, outcome withheld).
- q08 (current_fact): `exit_code=1`, `status=failed`, `classification=unverified` (**not in** allowed set), `run_id=5439873d-547d-4ee8-a1cd-48d31b87d255`, `agent_call_count=6`. respond–criticize succeeded (evidence 14; search 5, candidates 25, fetch 14/23, `FETCH_FAILED`×9), then `synthesize` failed after 3.2s with `QUOTA_EXCEEDED` (fixed sanitized summary `synthesize execution ended with QUOTA_EXCEEDED.`); correctly not retried. Acceptance **not assessable** (no final answer). External quota exhaustion, not a logic defect; directly motivates M-5 alternate-agent selection.
- Aggregate: attempted 4/4; completed 3; verified 1 / partially_verified 1 / withheld 1 / unverified(failed Run) 1; allowed-classification compliance 3/4 attempted; acceptance met 3/3 assessable; evidence fetch success 56/71 (~79%); total `agent_call_count` 24; retry total 0; `json_parse_status=valid` and `leakage_check=passed_structural_check` on all 4.
- Combined M-5-pre baseline (X-8.14 q01–q02 + X-8.15): 6 questions reached a Run, 5/6 within allowed classifications, 5/5 assessable acceptance met, zero incorrect published answers. q03 (pre-Run DNS `getaddrinfo failed`) stays a separate systemic bucket and is not assumed solved by M-5.
- No source, test, config, runner, or eval-set changes. `stdout.json` read only for sanitized structured fields (answer/claims/phases); `stderr.txt` not read. No evaluation artifacts, subset, or raw output added to Git. `dream.md` not modified during the evaluation.
- Documentation updated: `hikitsugi.md` (4-26), this file.
- Next work: M-5 spec confirmation, then L-5, then S-8. The q03 DNS failure is handled as a separate failure-boundary task.
