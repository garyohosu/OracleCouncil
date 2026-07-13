# 実施結果

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

未解決の根本原因は外部CLIへ再実行していないため不明。ユーザー承認後、新しい評価ディレクトリでq04を1回限定再評価する。既存の保存済み評価結果は変更しない。
