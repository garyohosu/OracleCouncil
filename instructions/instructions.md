# Oracle Council 次作業指示書

## X-8.3: EXECUTION_ERRORの安全な構造診断追加

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.2適用後のq04実機評価において、`verify` Phaseの`codex-cli`が起動約413ms後に`EXECUTION_ERROR`で失敗した。

現在の外部向け情報は次の定型文のみで、原因の種類を判別できない。

```text
verify execution ended with EXECUTION_ERROR.
```

生のstdout、stderr、prompt、環境変数などを公開せず、次回同様の失敗が発生した際に、少なくとも失敗の構造を判別できる安全な診断情報を残す。

今回は診断経路だけを改善する。q04のlive再実行や、推測に基づくAdapter仕様変更は行わない。

## 作業前確認

最初に次のファイルと現在の実装を確認すること。

```text
SPEC.md
TESTCASE.md
FIX_PLAN.md
hikitsugi.md
src/oracle_council/adapters/
src/oracle_council/orchestrator.py
src/oracle_council/models.py
scripts/run_x8_evaluation.py
```

特に以下を確認する。

- `classify_cli_error`の現在の分類順序
- Claude/Codex Adapterが`AgentFailure`を生成する箇所
- `AgentFailure.public_summary`のallowlist検証
- `INVALID_OUTPUT`の構造診断実装
- CLI JSONの`error_summary`
- X-8 runnerの`phase_summary`
- TIMEOUT、RATE_LIMITED、QUOTA_EXCEEDEDなど既存分類の優先順位

## 実装要件

### 1. EXECUTION_ERRORへ粗い構造診断を追加する

`EXECUTION_ERROR`発生時に、任意文字列ではなく、プログラム側で確定した固定カテゴリだけを`public_summary`へ設定できるようにする。

最低限、次の種類を区別できるよう検討する。

```text
subprocess_nonzero_exit
process_launch_failure
known_error_pattern_not_matched
unknown_execution_failure
```

既存のTIMEOUT、RATE_LIMITED、QUOTA_EXCEEDED、INVALID_OUTPUTなどに該当する場合は、従来の分類を維持すること。

カテゴリ名または外部向け文言は固定値とし、stderrなどから抽出した文字列を連結しない。

外部向け文言例:

```text
verify process exited with a non-zero status.
verify process could not be started.
verify execution failed without a recognized error pattern.
```

実際の名称は既存コードの命名規則に合わせてよい。

### 2. 機密情報を出さない

次の情報を`public_summary`、CLI JSON、Phase metrics、X-8 summaryへ出力しない。

```text
stdout
stderr
prompt
モデル出力本文
実行コマンド全文
ファイルパス
ユーザー名
環境変数
APIキー
認証情報
Cookie
HTTP header
検索クエリ
例外メッセージ全文
任意のCLI出力文字列
```

終了コードを記録する場合も、外部公開が本当に必要か検討すること。今回の目的には固定カテゴリだけで十分なら、数値終了コードは公開しない。

`--store-content`時の内部診断契約は、必要がなければ変更しない。

### 3. Storage Contractを変更しない

今回の作業ではStorage形式を変更しない。

次を新規保存項目としてJSONLへ追加しないこと。

```text
raw stderr
raw stdout
任意の例外本文
新しいdiagnosticオブジェクト
```

既存の`error_summary`経路だけで対応できる設計を優先する。

Storage Contractの変更が不可避と判断した場合は、実装せず理由を報告すること。

### 4. 既存分類を壊さない

次の既存動作を維持する。

- TIMEOUTはTIMEOUTとして分類される
- RATE_LIMITEDはRATE_LIMITEDとして分類される
- QUOTA_EXCEEDEDはQUOTA_EXCEEDEDとして分類される
- INVALID_OUTPUTの構造診断は従来どおり動作する
- 非一時エラーを勝手に再試行しない
- Runの終了コード、classification、PhaseStatusを変更しない
- `--no-store`の意味を変更しない

一発だけ発生したq04の失敗を根拠に、Codexの引数、schema、prompt内容、タイムアウト値などを推測で変更しないこと。

## テスト要件

少なくとも次の回帰テストを追加する。

### EXECUTION_ERROR

1. subprocessが認識不能な内容で非ゼロ終了した場合、`EXECUTION_ERROR`になる
2. 外部向け`public_summary`には固定文言だけが入る
3. stderr本文が`public_summary`へ混入しない
4. stdout本文が`public_summary`へ混入しない
5. prompt、環境変数、パスが外部JSONへ混入しない
6. CLI JSONの該当ExecutionおよびPhaseにsanitized summaryが出る
7. X-8 runnerの`phase_summary`にも同じ安全な概要が出る

### 既存分類

8. TIMEOUTはEXECUTION_ERRORへ落ちない
9. QUOTA_EXCEEDEDはEXECUTION_ERRORへ落ちない
10. RATE_LIMITEDはEXECUTION_ERRORへ落ちない
11. INVALID_OUTPUTの既存構造診断が変化しない
12. 改行、制御文字、不正surrogate、長すぎる文言などはallowlistを通過しない

必要ならClaude AdapterとCodex Adapterの両方でテストすること。

## 実行禁止事項

今回は次を実行しない。

```text
claude
codex
WebSearch
実HTTP取得
ORACLE_COUNCIL_LIVE=1
liveテスト
expensiveテスト
scripts/run_x8_evaluation.pyのlive実行
q04の再実行
8問フル評価
```

保存済み評価結果にも触れない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
```

変更、削除、再構築を禁止する。

## 検証

実装後、次を実行する。

```powershell
py -m pytest
git diff --check
git status --short
```

全通常テストが通ること。

liveおよびexpensiveテストがpytestの既定設定で除外されていることも確認する。

## ドキュメント更新

`hikitsugi.md`へ次を追記する。

- X-8.3で実装した診断カテゴリ
- 外部へ出す情報と出さない情報
- Storage Contractを変更したか
- 追加したテスト内容
- テスト件数
- q04 live再実行は未実施であること
- 次の作業が「ユーザー承認後のq04 1回限定再評価」であること

必要に応じて`QandA.md`または`TESTCASE.md`も更新する。

SPEC変更が不要なら、SPECのバージョンは上げない。

## コミットとpush

全テスト通過後、意図したsource、test、documentだけをコミットする。

コミットメッセージ例:

```text
feat: add safe execution error diagnostics
```

`origin/main`へpushする。

## 結果出力

作業完了後、結果報告を次のファイルへ必ず出力すること。

```text
instructions/result.md
```

チャット上の報告だけで完了扱いにしない。`instructions/result.md`を作成または更新し、次の内容を記載する。

1. 原因調査で確認した現在のEXECUTION_ERROR経路
2. 実装した固定診断カテゴリ
3. 機密情報漏えいを防ぐ仕組み
4. 変更ファイル一覧
5. 追加テスト一覧
6. pytest結果
7. `git diff --check`結果
8. commit hash
9. push結果
10. q04を再実行していないこと
11. 次回q04を再評価した際に、同じ障害の原因をどこまで識別できるか
12. 未解決事項と次の推奨作業

`instructions/result.md`も今回のコミット対象に含めること。