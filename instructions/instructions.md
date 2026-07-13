# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業を始める前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分がある場合は、勝手にreset・stash・削除せず、差分を保護して状況を報告してください。

## X-8.5: EXECUTION_ERROR summaryの誤ラップ修正

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.4のq04 live再評価で、`verify`の失敗自体は正しく`EXECUTION_ERROR`かつ「非ゼロ終了」と判別できたが、外部向けsummaryが次のように誤って`invalid output`としてラップされた。

```text
verify invalid output: verify process exited with a non-zero status..
```

`EXECUTION_ERROR`と`INVALID_OUTPUT`は別の失敗種別であるため、Orchestratorのsummary生成を修正し、EXECUTION_ERRORでは固定実行診断をそのまま出し、INVALID_OUTPUTだけが従来どおり構造診断ラップを使うようにする。

今回はsummary経路だけを修正する。実CLI、WebSearch、HTTP、X-8 live評価は実行しない。

## 現在地・確認済み原因

X-8.4はHEAD `bca0c90`でq04を1回だけ実行し、次を確認した。

- Run: `failed` / exit 1 / classification `unverified`
- `respond`、`claim_extract`、`evidence_collect`は成功
- Evidence 14件
- `verify`は`EXECUTION_ERROR`
- 固定診断は非ゼロ終了相当
- JSON parse valid
- leakage check passed
- 再試行なし

文言二重化の直接原因は`src/oracle_council/orchestrator.py`の`_failure_summary()`である。

現行実装は`failure.public_summary`が存在する場合、error codeを見ずに常に次の形式へ変換している。

```python
return f"{phase} invalid output: {public_summary}."[:200]
```

そのため、既にphaseと末尾ピリオドを含むEXECUTION_ERRORの固定summaryもINVALID_OUTPUTとして包まれ、意味の誤りと二重ピリオドが発生する。

## 作業前確認

最初に次を確認する。

```text
src/oracle_council/orchestrator.py
src/oracle_council/models.py
src/oracle_council/adapters/base.py
tests/unit/test_orchestrator.py
tests/unit/test_adapter_schema.py
scripts/run_x8_evaluation.py
hikitsugi.md
instructions/result.md
```

特に次の契約を確認する。

- `AgentFailure.error_code`
- `AgentFailure.public_summary`
- `safe_public_summary()`
- `safe_error_summary()`
- `_failure_summary()`
- `INVALID_OUTPUT`の既存構造診断
- `EXECUTION_ERROR`の固定診断
- CLI JSONとX-8 runnerの`phase_summary`

## 実装要件

### 1. error codeごとにsummary生成を分離する

`_failure_summary()`を修正し、少なくとも次の挙動にする。

#### INVALID_OUTPUT

`failure.error_code == "INVALID_OUTPUT"`かつ安全な`public_summary`がある場合だけ、従来形式を維持する。

```text
<phase> invalid output: <構造診断>.
```

例:

```text
criticize invalid output: missing field: critique.
```

#### EXECUTION_ERROR

`failure.error_code == "EXECUTION_ERROR"`かつ安全な固定実行summaryがある場合は、`invalid output`を付けず、そのsummaryを外部向けに使う。

期待例:

```text
verify process exited with a non-zero status.
verify process could not be started.
verify execution failed without a recognized error pattern.
verify execution failed unexpectedly.
```

次を満たすこと。

- `invalid output`を付けない
- ピリオドを二重にしない
- summary内のphaseが現在のphaseと一致することを確認する
- `safe_error_summary()`または同等のallowlist検証を通す
- phase不一致、不正形式、任意文字列なら採用しない

#### その他のerror code

安全な専用処理が定義されていないerror codeは、従来どおり次の固定形式へフォールバックする。

```text
<phase> execution ended with <ERROR_CODE>.
```

### 2. Adapter分類は変更しない

今回、次は変更しない。

- Claude/Codex Adapterのコマンドライン引数
- `classify_cli_error()`の既知エラー判定
- EXECUTION_ERRORを生成する条件
- timeout値
- retry条件
- phase schema
- prompt内容
- Evidence処理

### 3. 公開境界を維持する

次を外部summary、CLI JSON、Phase metrics、X-8 summaryへ出さない。

```text
stdout
stderr
prompt
モデル出力本文
コマンド全文
ファイルパス
ユーザー名
環境変数
APIキー
認証情報
Cookie
HTTP header
検索クエリ
例外本文
任意のCLI出力文字列
```

Storage ContractとJSONL形式は変更しない。

### 4. 既存結果を変更しない

次の保存済み評価結果は基準記録として扱い、変更・削除・再構築しない。

```text
C:\PROJECT\OracleCouncil-evals\x8\6a55ede
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live
C:\PROJECT\OracleCouncil-evals\x8\9dd2407-q04-live2
C:\PROJECT\OracleCouncil-evals\x8\bca0c90-q04-x83
```

## テスト要件

FakeまたはScripted Adapterだけで再現する通常テストを追加する。

最低限、次を固定する。

1. verify phaseで`AgentFailure("EXECUTION_ERROR", ..., public_summary="verify process exited with a non-zero status.")`を発生させる
2. PhaseRecordの`error_code`が`EXECUTION_ERROR`
3. PhaseRecordの`error_summary`が正確に次となる

```text
verify process exited with a non-zero status.
```

4. AgentExecutionRecordの`error_summary`も同じ固定summary
5. `invalid output`を含まない
6. `..`の二重ピリオドを含まない
7. raw messageや秘密文字列を含まない
8. `process could not be started`など他の固定実行summaryも許可される
9. phase不一致のsummaryは拒否または安全な一般summaryへフォールバックする
10. 任意文字列・改行・制御文字・長すぎるsummaryは拒否する
11. INVALID_OUTPUTは従来どおり次の形式を維持する

```text
criticize invalid output: missing field: critique.
```

12. TIMEOUT、RATE_LIMITED、QUOTA_EXCEEDED、AUTH_REQUIRED等の既存summaryを壊さない
13. CLI JSON化後も`safe_error_summary()`を通過する
14. X-8 runnerの`phase_summary()`でも修正後summaryが保持される

必要なら`tests/unit/test_orchestrator.py`、`tests/unit/test_adapter_schema.py`、`tests/unit/test_x8_evaluation.py`へ分けて追加する。

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
q04再実行
8問フル評価
scripts/run_x8_evaluation.pyのlive実行
```

X-8.4の失敗原因を推測してAdapter仕様を変更しない。

## 検証

実装後、次を実行する。

```powershell
py -m pytest
git diff --check
git status --short
```

合格条件:

- 通常テスト全件pass
- live / expensiveは既定設定で除外
- `git diff --check`成功
- 意図しないファイル変更なし
- EXECUTION_ERROR summaryから`invalid output`と二重ピリオドが消える
- INVALID_OUTPUTの既存summaryは変わらない

## ドキュメント更新

`hikitsugi.md`へX-8.5として次を記録する。

- X-8.4で確認した誤ラップ
- 根本原因が`_failure_summary()`の無条件ラップだったこと
- 修正後のerror code別summary規則
- 公開境界とStorage Contractが不変であること
- 追加テスト
- pytest結果
- live再実行をしていないこと

## コミットとpush

全テスト通過後、意図したsource、test、documentだけをコミットし、`origin/main`へpushする。

コミットメッセージ例:

```text
fix: preserve execution error summaries
```

`instructions/result.md`も結果記録コミットへ含める。

## 結果出力

作業完了後、結果を次へ必ず出力する。

```text
instructions/result.md
```

チャット上の報告だけで完了扱いにしない。

最低限、次を記載する。

1. 誤ラップの根本原因
2. 修正したsummary分岐
3. EXECUTION_ERRORの修正後summary
4. INVALID_OUTPUTの互換性確認
5. phase不一致・不正summaryの扱い
6. 機密情報漏えい防止
7. 変更ファイル一覧
8. 追加テスト一覧
9. pytest結果
10. `git diff --check`結果
11. live / expensive / q04を実行していないこと
12. commit hash
13. push結果
14. 未解決事項
15. 次の推奨作業
