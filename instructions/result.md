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

## X-8.16 M-5 / S-5 代替Agent・ExecutionPlan仕様確定 (2026-07-14)

- X-8.15 q08のClaude `synthesize`における`QUOTA_EXCEEDED`を具体例として、M-5とS-5を相互依存のまま同時確定した。文書変更のみであり、live、実CLI、HTTP、評価、source/test/config/runner変更は実施していない。
- retryは同じAgent・同じ論理slot・同じphaseの新Execution（`retry_of`）。slotあたり最大1回、Run全体最大2回。substitutionは異なるAgentが同じslot/phaseを引き継ぐ新Execution（`substitute_for`）で、Run全体最大1回、retry枠とは別。両者は別BudgetReservationで、`retry_of`と`substitute_for`は排他的。代替後のretryと2人目のsubstituteは行わない。
- 全AI呼び出し上限は12回で、`TokenBudget.reserve()`を唯一の正本とする。13回目はAgent呼び出し前に`BUDGET_EXCEEDED`で拒否する。
- retry対象は`TIMEOUT`/`RATE_LIMITED`のみ。`AUTH_REQUIRED`、`QUOTA_EXCEEDED`、`COMMAND_NOT_FOUND`、`UNSUPPORTED_VERSION`、`UNSAFE_CAPABILITY`はRun全体unavailableとして同一Agent retryなしで候補探索し、`EXECUTION_ERROR`はslot-local substitutionとする。`INVALID_OUTPUT`、`CONTEXT_OVERFLOW`、`BUDGET_EXCEEDED`、`CANCELLED`、Evidence障害、Run生成前CLI/DNS/設定例外はM-5 substitution対象外。
- S-5の正式モデルはRun開始時に決定する`ExecutionPlan`、`PhaseAssignment`、`RunAgentAvailability`。候補順はprobe/capability適格、`role_priority`降順、設定順tie-break、失敗・hard unavailable除外、phase独立性制約の順。Responderは異なる2 Agent、Synthesizer/Auditorは常に別Agentとし、Synthesizer候補に別Auditor候補をlook-aheadで確保する。
- 既定2 AgentでSynthesizerのquota障害後に代替すると別Auditorが残らない場合は、既存の分離要件を破って救済せずRunをfailedにする。q03のDNS失敗はM-5とは別のfailure-boundary課題として維持する。
- 更新文書: `QandA.md`、`SPEC.md` v0.3.9、`CLASS.md`、`SEQUENCE.md`、`STATE.md`、`TESTCASE.md`、`FIX_PLAN.md`、`hikitsugi.md`、本書。次作業はM-5/S-5実装、その後L-5、S-8。

## X-8.17 M-5 / S-5 ExecutionPlan・Agent substitution実装 (2026-07-14)

- 実行前HEAD: `d59be6a`。X-8.16仕様`554602d`、X-8.15結果`599d3d0`を祖先として確認した。
- `assignment.py`に不変`ExecutionPlan`、`PhaseAssignment`、`RunAgentAvailability`、`build_execution_plan()`を追加。Run開始時の適格Agent snapshotを候補順の入力とし、`role_priority`降順・設定順tie-breakでrespond 2 slot、claim_extract、verify、criticize、synthesize、auditを固定した。旧AssignmentPlan APIは互換維持。
- `orchestrator.py`は同一PlanをRun終了まで使用し、Run全体retry=2、substitution=1を分離管理。`TokenBudget.reserve()`の12回上限は変更せず、別counterで13回目を許可しない。retry/substitutionは別Execution・別Reservation。
- `TIMEOUT`/`RATE_LIMITED`は同一Agent retry。`AUTH_REQUIRED`、`QUOTA_EXCEEDED`、`COMMAND_NOT_FOUND`、`UNSUPPORTED_VERSION`、`UNSAFE_CAPABILITY`はRun全体unavailable、`EXECUTION_ERROR`はslot-local除外。`INVALID_OUTPUT`、`BUDGET_EXCEEDED`等のM-5対象外は代替しない。
- `AgentExecutionRecord`とCLI JSON `executions[]`に`substitute_for`を追加し、`retry_of`との排他をモデルで強制。`agent_substitute_selected`/`agent_substitution_unavailable`を安全なmetadataのみで保存した。
- Responderの異なる2 Agent制約、成功済みResponderの代替禁止、Synthesizer/Auditor look-ahead分離、revision時のcurrent担当preferredを実装。
- Fake結果: TIMEOUT retry失敗後の3 Agent substitution成功、2 Agent synthesize quota failureは別Auditor不足で救済不能、3 Agentでは代替Synthesizer＋別Auditorで継続、substitution eventにraw情報なし。Plan決定性とcall/retry/substitution境界も確認。
- targeted tests: `55 passed`。通常pytest: `264 passed, 6 deselected`。`git diff --check`: 成功。
- 変更: `src/oracle_council/assignment.py`、`orchestrator.py`、`models.py`、`cli.py`、`tests/unit/test_assignment.py`、`tests/unit/test_orchestrator.py`、`FIX_PLAN.md`、`hikitsugi.md`、本書。実Claude/Codex、WebSearch、実HTTP、live/expensive評価、評価データ再実行は未実施。
- q03 DNS failure-boundary、S-9/S-10、L-5、S-8は未解決。次作業はL-5、その後S-8。

## X-8.18 L-5 phase schema実装 (2026-07-14)

6フェーズの正式Schema resource、共通validator、AgentRequestへのdeep-copy注入、Claude/Codex共有、Fake/Contract/Unitテストを実装した。全objectをclosedとし、必須項目、Enum、文字数・件数上限、固定安全summaryを確定した。L-3の自動修復/retryは実装していない。通常pytestは全件成功、live系は未実行。次はS-8。

## X-8.19 S-8 process/Oracle exit code分離 (2026-07-14)

- 実行前HEAD: `86e17dd`。X-8.18実装`8bbc076`、X-8.17実装`217867f`を祖先として確認した。baseline: `267 passed, 6 deselected`。
- **変更前の曖昧さ**: `AgentExecutionRecord.exit_code`（子CLI process想定・ほぼ未使用）と`RunResult.exit_code`／CLI JSONトップレベル`exit_code`（Oracle自身）が同名で混同可能。AgentResult/AgentFailureから子process return codeを伝える正式経路がなかった。
- **正式仕様（QandA S-8確定、SPEC v0.3.10）**: 子CLI processのOS終了コードは`process_exit_code`、Oracle Council全体の外部終了コードは`oracle_exit_code`。意味的結果は`AgentExecutionStatus`/`AgentErrorCode`/`RunStatus`/`ResultClassification`のまま、終了コードから推測しない。
- **モデル**: `AgentResult.process_exit_code`（既定None）、`AgentFailure.process_exit_code`を追加。`AgentExecutionRecord.exit_code`→`process_exit_code`へ正式rename（曖昧な`exit_code`は残さない）。`RunResult.exit_code`→`oracle_exit_code`へrename（読み取り専用compatibility property `exit_code`を残す）。`RunMetadataRecord.oracle_exit_code`を追加し`to_dict()`とterminal Run event metadataへ含めた。
- **Adapter**: Claude/Codex両方で成功時`AgentResult(..., process_exit_code=res.returncode)`。分類済みエラー・非0終了は`process_exit_code=res.returncode`。process 0後のCLI envelope不正・phase JSON不正・Schema不適合は`INVALID_OUTPUT`かつprocess 0（base.pyのschema検証AgentFailureにはAdapter側で付与）。command not found・timeout・起動失敗はNone。エラー分類・redaction・stdin transport・Schema処理は不変。
- **Orchestrator**: 成功/失敗Executionへ`process_exit_code`を記録。retry/substitutionの各Executionに個別記録。`agent_execution_succeeded`/`agent_execution_failed` eventは`process_exit_code`フィールドを常に持ちnull許容。`_finish()`引数を`oracle_exit_code`へrename。StorageWriteError直接経路も更新。
- **CLI**: `output_run_result`と`exit_stop`はトップレベル`oracle_exit_code`＋互換エイリアス`exit_code`（全経路で同値）、戻り値も`oracle_exit_code`。`executions[]`は`process_exit_code`だけを出力し`exit_code`を出力しない。R-1の0/1/2/3/4/130の実際の終了値は不変（130はS-6/T-2待ちの文書契約のまま）。
- **テスト結果**: 新規`tests/unit/test_exit_code_separation.py` 25件——成功returncode 0→AgentResult 0（Claude/Codex）、非0=17→AgentFailure 17保持、returncode 0＋malformed/schema不正→INVALID_OUTPUTかつprocess 0、FileNotFound→COMMAND_NOT_FOUNDでNone、TimeoutExpired→TIMEOUTでNone、Fake成功→None記録、意味的status/errorの非上書き、retry/substitution個別コード、metadata eventにraw情報なし、CLI JSON（成功/failed/withheld/exit_stop）で`oracle_exit_code == exit_code`・戻り値一致・`executions[].process_exit_code`存在・`executions[]`に`exit_code`なし。既存argv/stdin・Schema・redactionテスト維持。
- **検証**: `py -m pytest` = **292 passed, 6 deselected**。`git diff --check`成功。`git grep exit_code -- src`の残存は互換property（models.py）と`assignment.py`の`InsufficientAgentsError.exit_code = 3`（Oracle側の値・cli.pyから未参照・今回の許可変更範囲外のため未変更）のみ。
- **文書**: QandA.md（S-8回答確定）、SPEC.md v0.3.10（§8.5/§13.4/§14/§15.8）、CLASS.md（processExitCode/oracleExitCode）、TESTCASE.md（S-8 BLOCKED解除3箇所）、FIX_PLAN.md（0-9追加、§2からL-5/S-8行を解消済み表記へ）、hikitsugi.md、本書。
- **実行禁止事項の遵守**: 実Claude、実Codex、`claude -p`、`codex exec`、WebSearch、実HTTP、`ORACLE_COUNCIL_LIVE=1`、live/expensive pytest、q01〜q08は実行していない。config/、evaluation/、scripts/、評価セットは未変更。
- **未解決**: q03 DNS failure-boundary、S-9/S-10、L-3、J-3、S-4、S-6、T-2、T-3、J-4。次作業は別の指示書で決める。

## X-8.20 q03 DNS failure-boundaryの修正 (2026-07-14)

- 実行前HEAD: `f13b043`。X-8.19コミット`f13b043`到達、`cd8422e`/`8bbc076`祖先確認済み、`git status --short`完全に空、branch `main`、`origin/main`一致を確認した。実Claude、実Codex、WebSearch、実HTTP、live評価、q03再実行は行っていない。baseline: `292 passed, 6 deselected`。
- **q03漏出の正確な原因箇所**: `SafeHttpFetcher.fetch()`の各redirect hop先頭で呼ばれる`_validate_url()`が、SSRF事前チェックのため`self._resolver(parsed.hostname)`（既定`socket.getaddrinfo`）をどのtry/exceptにも囲まれずに直接呼んでいた。DNS解決失敗（`socket.gaierror`）はここで生のまま`fetch()`外へ漏れ、`WebEvidenceProvider.fetch()`／`collect_with_metrics()`（`except EvidenceFetchError`のみ）、`Orchestrator._collect_evidence()`／`_apply_output()`／`_execute_phase()`（いずれも`except SearchError`のみ）のどの型付きハンドラにも捕捉されず、CLIの`except Exception as e: return exit_stop("internal_error", 1, str(e), args.json)`まで到達していた。X-8.14 q03の`message: "[Errno 11001] getaddrinfo failed"`はこの`str(socket.gaierror(...))`そのものだったことをFakeで確定した。
- **再現した例外形**: `socket.gaierror(11001, "getaddrinfo failed")`（resolver直接失敗、修正前は生のまま漏れることを確認）と`urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))`（HTTP層に包まれた形、修正前から既存の`except (URLError, TimeoutError, OSError)`で正しく変換されることを確認・回帰固定）の両方をテストした。
- **修正した境界**: `SafeHttpFetcher._validate_url()`内の`self._resolver(parsed.hostname)`呼び出しを`try/except socket.gaierror`で囲み`EvidenceFetchError("FETCH_FAILED", "DNS resolution failed")`へ変換する1箇所のみを変更した。`WebEvidenceProvider`、`Orchestrator`、`cli.py`、`models.py`は無変更。CLIへの`except socket.gaierror`や広い`except OSError`は追加していない。
- **採用した公開error codeと根拠**: 新規codeは追加せず既存の`FETCH_FAILED`を採用した。同じ`fetch()`内で`URLError`/`TimeoutError`/`OSError`を捕捉する既存パスが既に`FETCH_FAILED`を使っており、DNS解決失敗も同種の一般的network failureであるため。SPEC §10.8も非UTF-8デコード失敗等の他の接続時例外を`FETCH_FAILED`に分類しており、DNS専用の別public codeは定義されていない。
- **partial-evidence・metrics挙動**: `EvidenceFetchError`化後は`WebEvidenceProvider.collect_with_metrics()`の既存per-candidate loopがそのまま処理する。1候補DNS失敗＋1候補成功で`fetch_attempt_count=2`／`fetch_success_count=1`／`fetch_failure_count=1`／`fetch_error_codes={"FETCH_FAILED":1}`、成功分のEvidenceを保持し次候補へ継続することをテストで確認した。全候補DNS失敗時は既存no-evidence契約（`evidence_collect`は`succeeded`・`success_count=1`・`outcome=no_evidence`）どおりであることをCLI JSONレベルで確認した。
- **CLIでのFake結果**: `--evidence-provider cli-search`で`CliSearchProvider`をFakeに、`socket.getaddrinfo`を`gaierror(11001, "getaddrinfo failed")`で常時失敗させるFakeにした（`SafeHttpFetcher`自体は実クラス、実HTTP・実DNSなし）。結果は`status="completed"`・`exit_code=0`・`oracle_exit_code==exit_code`・有効な`run_id`・`evidence=[]`・`evidence_collect`が`succeeded`/`success_count=1`/`outcome="no_evidence"`/`fetch_error_codes={"FETCH_FAILED":1}`で、`internal_error`にもならなかった。
- **raw情報非公開確認**: CLIテストで出力JSON全体（`json.dumps`）に`"getaddrinfo"`、`"11001"`、`"gaierror"`、テスト用hostnameが含まれないことをassertした。unit testでも`EvidenceFetchError`の`str()`に同様の情報が含まれないことを確認した。
- **変更ファイル**: `src/oracle_council/evidence.py`（`SafeHttpFetcher._validate_url`）、`tests/unit/test_evidence.py`（DNS単体3件追加）、`tests/unit/test_cli.py`（DNS CLI回帰1件追加）、`FIX_PLAN.md`（§0-10追加）、`hikitsugi.md`、本書。
- **追加テスト**: `test_dns_resolution_failure_from_resolver_becomes_typed_fetch_error`、`test_dns_resolution_failure_wrapped_in_urlerror_becomes_typed_fetch_error`、`test_collect_with_metrics_continues_after_raw_dns_failure_and_records_typed_code`、`test_cli_ask_dns_resolution_failure_does_not_become_internal_error`。
- **検証**: 修正前は追加した4件のDNSテストのうち3件が失敗し漏出を再現した（`URLError(gaierror)`側の1件のみ修正前から成功）。修正後は対象テスト（`tests/unit/test_evidence.py`＋`tests/unit/test_cli.py`）72 passed。全体`py -m pytest`は**296 passed, 6 deselected**（baseline 292から+4）、`git diff --check`成功、`git status --short`は変更ファイルのみ。
- **実行禁止事項の遵守**: 実Claude、実Codex、WebSearch、実HTTP、`ORACLE_COUNCIL_LIVE=1`、live/expensive pytest、q01〜q08、q03再実行は行っていない。commit/pushは行っていない。config/、evaluation/、scripts/、Agent assignment/retry/substitution仕様、oracle/process exit-code契約は未変更。
- **未解決**: T-3（DNS rebinding対策、resolver pinning）、S-9/S-10は本作業の対象外のまま。q03の実live再評価は未実施（別途明示承認が必要）。
- **次の推奨作業**: ユーザー承認を得た上でのq03 1回限定live再評価、またはS-9/S-10の設計確定。この場では次へ進まず停止する。
