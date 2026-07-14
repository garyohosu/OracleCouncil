# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分や未追跡ファイルがある場合は、勝手にreset・stash・削除・移動せず、差分を保護して状況を報告してください。

## X-8.19: S-8 子CLI process exit codeとOracle exit codeの分離

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.18でL-5を通常実装した。

```text
X-8.18 implementation commit:
8bbc0769896725aaa59365cc6bc20b931acae031

baseline pytest:
267 passed, 6 deselected
```

現在は次の曖昧さが残っている。

- `AgentExecutionRecord.exit_code`は子Claude/Codex processの終了コードを表す想定だが、ほぼ未使用
- `RunResult.exit_code`とCLI JSONトップレベル`exit_code`はOracle Council自身の終了コードを表す
- 同じ名前のため、Adapter、Orchestrator、保存記録、CLI利用者が両者を混同できる
- `AgentResult`と`AgentFailure`から子process return codeをOrchestratorへ伝える正式経路がない

X-8.19ではS-8を仕様確定し、通常実装とFake/transport/CLIテストへ反映する。

正式名称:

```text
process_exit_code: 個々の子AI CLI processのOS終了コード
oracle_exit_code: Oracle Council CLI全体の外部終了コード
```

意味的な結果は従来どおり次で表し、終了コードだけから推測しない。

```text
AgentExecutionStatus
AgentErrorCode
RunStatus
ResultClassification
```

今回は実Claude、実Codex、WebSearch、実HTTP、live評価を実行しない。Claude Codeは実装担当として使用してよいが、Oracle Councilの実Agent呼び出しを行わない。

## 並行作業禁止

X-8.19と次を並行で進めない。

```text
q03 DNS failure-boundary修正
S-9 configured/selected participant多重度
S-10 probe/capability snapshot
L-3 INVALID_OUTPUT自動修復
Clarifier
Responder並列化
X-8 live評価
```

S-8以外の挙動変更を入れない。

## 作業前確認

最初に次を読む。

```text
QandA.md                R-1、S-2、S-8
SPEC.md                 §8.2、§8.5、§13.4、§14、§15.7、§15.8
CLASS.md                AgentResult、AgentExecution、RunResult、RunMetadataRecord
TESTCASE.md             CLI終了コード、Adapter Contract、AgentExecution診断
FIX_PLAN.md
src/oracle_council/models.py
src/oracle_council/orchestrator.py
src/oracle_council/cli.py
src/oracle_council/adapters/base.py
src/oracle_council/adapters/claude.py
src/oracle_council/adapters/codex.py
src/oracle_council/fakes.py
既存のadapter、orchestrator、CLI JSON、storageテスト
hikitsugi.md
instructions/result.md
```

PowerShell:

```powershell
cd C:\PROJECT\OracleCouncil

git status --short
git pull --ff-only
git status --short

git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main

git merge-base --is-ancestor 8bbc076 HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.18 implementation commit 8bbc076." }

git merge-base --is-ancestor 217867f HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.17 implementation commit 217867f." }
```

合格条件:

- branchが`main`
- `git status --short`が完全に空
- HEADと`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.19`
- HEADに`8bbc076`と`217867f`が含まれる

不一致がある場合は変更を開始せず報告する。

## 変更前baseline

```powershell
py -m pytest
git diff --check
git status --short
```

基準:

```text
267 passed, 6 deselected
```

件数が変わっていても、通常テストが全件passし、live/expensiveが除外されていればよい。

## 1. S-8の正式仕様

### 1.1 process_exit_code

`process_exit_code`は1回の`AgentExecution`に対応する子processの終了コードだけを表す。

規則:

- 子processが正常終了した場合は`0`
- 子processが非0で終了した場合は、その実際の整数return code
- 子processが起動していない、またはOS終了コードを取得できない場合は`None`
- `FileNotFoundError`、起動前エラーは`None`
- `subprocess.TimeoutExpired`は最終return codeを確実に取得できないため`None`
- Fake Agentは子processを生成しないため`None`
- 子processが`0`で終了した後にJSON parse/schema validationが失敗した場合は、`error_code=INVALID_OUTPUT`かつ`process_exit_code=0`
- `process_exit_code=0`は意味的成功を保証しない
- `process_exit_code!=0`だけから公開`AgentErrorCode`を決めず、既存の分類処理を維持する

### 1.2 oracle_exit_code

`oracle_exit_code`はOracle Council CLI自身の外部終了コードだけを表す。

R-1の対応表を変更しない。

```text
0   公開可能な回答あり
1   実行失敗
2   入力・追加判断が必要
3   実行環境を整える必要あり
4   回答保留
130 ユーザーキャンセル
```

子CLIのreturn codeをOracleの終了コードとして流用しない。

### 1.3 JSON互換性

CLI JSONの正本フィールドを次とする。

```json
{
  "oracle_exit_code": 0,
  "exit_code": 0,
  "executions": [
    {
      "process_exit_code": 0
    }
  ]
}
```

- トップレベル`oracle_exit_code`を新しい正式フィールドとする
- 既存利用者のため、schema version 1.xではトップレベル`exit_code`を互換エイリアスとして残す
- `exit_code`と`oracle_exit_code`は全経路で必ず同値
- `executions[]`には`process_exit_code`を出力する
- `executions[]`へ曖昧な`exit_code`を出力しない
- `exit_stop()`でRunが生成されない場合も`oracle_exit_code`と互換`exit_code`を出力する
- `process_exit_code`がない場合はJSONで`null`としてよい
- schema versionを今回の都合だけで2.0へ上げない

## 2. モデル変更

### 2.1 AgentResult

`AgentResult`へ追加する。

```text
process_exit_code: int | None = None
```

Fake/既存呼び出しとの互換のため既定値は`None`でよい。

### 2.2 AgentFailure

`AgentFailure`へ追加する。

```text
process_exit_code: int | None = None
```

既存の`error_code`、安全な`public_summary`との責務を変えない。raw stderrや例外本文を新フィールドへ入れない。

### 2.3 AgentExecutionRecord

現在の保存フィールド`exit_code`を次へ正式にrenameする。

```text
process_exit_code: int | None = None
```

- dataclassの保存フィールドとして曖昧な`exit_code`を残さない
- 全constructor、test、serializationを更新する
- `retry_of`、`substitute_for`との関係は変更しない
- 外部JSONではこれまでAgent executionの`exit_code`を公開していないため、execution側の互換aliasは作らない

### 2.4 RunResult

現在の`RunResult.exit_code`を正式には次へrenameする。

```text
oracle_exit_code: int
```

Python内部の既存参照を一度に壊さないため、必要なら次の読み取り専用compatibility propertyを設けてよい。

```python
@property
def exit_code(self) -> int:
    return self.oracle_exit_code
```

ただし、保存されるdataclass fieldの正本は`oracle_exit_code`だけとし、新規コードは`.oracle_exit_code`を使う。

### 2.5 RunMetadataRecord

metadata snapshotへ追加する。

```text
oracle_exit_code: int
```

- `to_dict()`へ含める
- terminal Run eventのmetadataにも含まれる
- child process codeをRun metadata直下へ集約しない

## 3. Adapter変更

ClaudeAdapterとCodexAdapterで、実際の`subprocess.CompletedProcess.returncode`を伝える。

### 成功

```text
AgentResult(..., process_exit_code=res.returncode)
```

通常は0だが、0と決め打ちせず実値を渡す。

### CLIが非0終了または分類済みエラー

`res`が存在する経路で`AgentFailure`を送出する場合は、次を渡す。

```text
process_exit_code=res.returncode
```

対象例:

- AUTH_REQUIRED
- QUOTA_EXCEEDED
- RATE_LIMITED
- EXECUTION_ERROR
- 非0終了

### processは0だが出力不正

次も`process_exit_code=0`を保持する。

- CLI envelope JSON不正
- phase JSON不正
- 正式Schema不適合
- unexpected/extra field

### return codeなし

次は`None`。

- command not found
- timeout
- process launch failureでreturn code取得不能

エラー分類、stderr redaction、stdin transport、Schema処理を変更しない。

## 4. Orchestrator変更

`_attempt()`と`_execution_record()`を更新する。

- 成功Executionは`result.process_exit_code`を記録
- 失敗Executionは`failure.process_exit_code`を記録
- retry/substitutionそれぞれのExecutionに個別記録
- call count、BudgetReservation、retry/substitution上限を変更しない
- `process_exit_code`をPhase error codeやRun statusの代わりにしない

イベント:

- `agent_execution_succeeded`
- `agent_execution_failed`

へ`process_exit_code`を追加する。値が取得不能なら`null`または省略のどちらかに統一する。推奨はフィールドを常に持ち`null`にする。

イベントへraw stderr、prompt、質問、回答、環境変数、path、secretを追加しない。

`_finish()`の引数・ローカル変数は`oracle_exit_code`へrenameし、`RunResult`と`RunMetadataRecord`へ渡す。

StorageWriteErrorなど直接`RunResult`を生成する経路も更新する。

## 5. CLI変更

### output_run_result

- return値は`result.oracle_exit_code`
- 分岐条件も`result.oracle_exit_code`
- JSONトップレベルに`oracle_exit_code`
- 互換`exit_code`は同値
- `executions[]`に`process_exit_code`
- status、classification、error_codeとの意味を混ぜない

### exit_stop

引数名を`oracle_exit_code`へrenameしてよい。

JSON:

```text
oracle_exit_code
exit_code  # compatibility alias
```

関数returnも`oracle_exit_code`。

R-1の実際の終了値を変更しない。

## 6. テスト

最低限、次を自動テストする。

### モデル

1. `AgentResult.process_exit_code`の既定値は`None`
2. `AgentFailure.process_exit_code`を保持
3. `AgentExecutionRecord.process_exit_code`を保持
4. `RunResult.oracle_exit_code`を保持
5. compatibility propertyを設けた場合、`RunResult.exit_code == RunResult.oracle_exit_code`
6. `RunMetadataRecord.to_dict()`に`oracle_exit_code`

### Adapter transport

Monkeypatchされたsubprocessで検証する。

1. Claude成功returncode 0 → AgentResult 0
2. Codex成功returncode 0 → AgentResult 0
3. 非0 returncode 17 → AgentFailure 17を保持
4. returncode 0＋malformed/schema不正 → INVALID_OUTPUTかつprocess 0
5. FileNotFound → COMMAND_NOT_FOUNDかつprocess None
6. TimeoutExpired → TIMEOUTかつprocess None
7. argv/stdin、Schema、redactionの既存テストを維持

実Claude/Codexを呼ばない。

### Orchestrator

1. Fake successはprocess NoneでExecutionへ記録
2. failureにprocess codeがあれば失敗Executionへ保持
3. retry/substitutionの各Executionが個別のprocess codeを持てる
4. semantic error/statusがprocess codeだけで上書きされない
5. metadata eventにprocess codeはあるがraw情報はない

### CLI JSON

成功、failed、withheld、Run未生成の`exit_stop`を検証する。

```text
payload["oracle_exit_code"] == payload["exit_code"]
process return value == payload["oracle_exit_code"]
executions[i]["process_exit_code"] が存在
executions[i]に"exit_code"が存在しない
```

R-1の0/1/2/3/4契約に回帰がないことを確認する。130は既存キャンセル経路が未実装・BLOCKEDなら、S-6/T-2へ踏み込まず文書上の契約維持だけでよい。

## 7. 文書更新

### QandA.md

S-8の`回答`を確定する。

- child: `process_exit_code`
- Oracle: `oracle_exit_code`
- semantic status/errorは別
- top-level旧`exit_code`はschema 1.x互換alias

R-1の表は変更しない。

### SPEC.md

文書バージョンを次版へ更新し、最低限次へ反映する。

- §8.5 AgentResult / AgentFailure
- §13.4 Oracle exit code
- §14 JSON出力
- §15.7 / §15.8 AgentExecution、RunResult、RunMetadataRecord

### CLASS.md

- AgentResult.processExitCode
- AgentExecution.processExitCode
- RunResult.oracleExitCode
- RunMetadataRecord.oracleExitCode

曖昧な同名`exitCode`を残さない。

### TESTCASE.md

S-8起因BLOCKEDを解除し、process/Oracle code分離ケースを正式化する。

### FIX_PLAN.md

S-8を「仕様確定・通常実装・Fake/transport/CLIテスト完了」へ移す。

q03、S-9、S-10、L-3等を解消済みにしない。

### hikitsugi.md / instructions/result.md

X-8.19として次を記録する。

- 変更前の曖昧さ
- 正式な2種類の終了コード
- モデル、Adapter、Orchestrator、CLI、metadata変更
- compatibility方針
- テスト結果
- 実CLI/live未実行
- 未解決項目

## 8. 変更禁止

今回変更しないもの:

```text
config/
evaluation/
scripts/
X-8評価セット
Agent割当・retry・substitution仕様
Evidence検索・取得仕様
```

実行しないもの:

```text
claude -p
codex exec
WebSearch
実HTTP
ORACLE_COUNCIL_LIVE=1
live / expensive pytest
q01〜q08
```

`claude --version`や`codex --version`も本作業では不要。Claude Code自体を編集担当として使うこととは別である。

## 9. 検証

まず関連テストを実行し、その後通常テスト全件を実行する。

```powershell
py -m pytest

git diff --check
git status --short
```

期待基準:

```text
通常テスト全件pass
live/expensiveはdeselected
変更前基準: 267 passed, 6 deselected
```

次も検索して確認する。

```powershell
git grep -n "exit_code" -- src tests QandA.md SPEC.md CLASS.md TESTCASE.md FIX_PLAN.md
```

確認事項:

- 子processの保存フィールドが`process_exit_code`
- Run全体の正本が`oracle_exit_code`
- 曖昧な`AgentExecutionRecord.exit_code`が残っていない
- トップレベルJSONの旧`exit_code`だけは互換aliasとして意図的に残る
- `exit_code == oracle_exit_code`
- raw情報漏えいなし

## 10. commit前確認

```powershell
git status --short
git diff --check
git diff
```

許可される変更範囲:

```text
src/oracle_council/models.py
src/oracle_council/orchestrator.py
src/oracle_council/cli.py
src/oracle_council/adapters/base.py
src/oracle_council/adapters/claude.py
src/oracle_council/adapters/codex.py
src/oracle_council/fakes.py
関連するtests/
QandA.md
SPEC.md
CLASS.md
TESTCASE.md
FIX_PLAN.md
hikitsugi.md
instructions/result.md
```

不要なファイル変更があればcommitせず報告する。

## 11. commitとpush

```powershell
git add src/oracle_council tests QandA.md SPEC.md CLASS.md TESTCASE.md FIX_PLAN.md hikitsugi.md instructions/result.md
git commit -m "refactor: separate process and oracle exit codes"
git push origin main

git status --short
git rev-parse HEAD
git rev-parse refs/remotes/origin/main
```

完了条件:

- S-8の回答が確定
- process/oracle exit codeがモデル上分離
- Adapterからprocess codeが伝播
- AgentExecution、event、CLI JSONへprocess codeが記録
- RunResult、metadata、CLI JSONの正本がoracle code
- 旧トップレベル`exit_code`が互換aliasとして同値
- R-1終了値に回帰なし
- 通常テスト全件pass
- `git diff --check`成功
- 実CLI/live未実行
- commit/push成功
- worktree clean
- HEADとorigin/main一致

## 12. 最終報告

次を簡潔に報告する。

1. 変更ファイル一覧
2. `process_exit_code`を追加したモデルと経路
3. `oracle_exit_code`を追加したモデルとJSON
4. compatibility aliasの扱い
5. 成功・非0・INVALID_OUTPUT・timeout・command not foundのテスト結果
6. R-1回帰テスト結果
7. targeted / full pytest件数
8. `git diff --check`
9. 実CLI/live未実行の確認
10. commit SHA、push、worktree、HEAD同期状態
11. 未解決項目

X-8.19完了後、その場でq03、S-9/S-10、live評価へ進まない。次作業は別の指示書で決める。