# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分や未追跡ファイルがある場合は、勝手にreset・stash・削除・移動せず、差分を保護して状況を報告してください。

## X-8.17: M-5 / S-5 ExecutionPlan・Agent substitution実装

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.16でM-5とS-5を同時に仕様確定した。

```text
仕様コミット:
554602d2f8c2a2723e2519a96fe83a2963bb1c75

確定値:
same-agent retry: Run全体で最大2回
substitution: Run全体で最大1回
AI call: TokenBudget.reserve()を正本として最大12回
retry対象: TIMEOUT / RATE_LIMITED
```

X-8.17では、確定仕様を通常実装とFakeテストへ反映する。

主な実装対象:

- 決定的な`ExecutionPlan` / `PhaseAssignment`
- Run内Agent可用性
- 同一Agent retryと別Agent substitutionの分離
- `substitute_for`
- Responderの独立性
- Synthesizer/Auditor分離とlook-ahead
- substitutionイベント
- 12回上限との統合

今回は実Claude、実Codex、WebSearch、実HTTP、live評価を実行しない。

## 前提として確定済みのbaseline

M-5導入前の評価結果は記録済みであり、再実行しない。

```text
X-8.14 result: 0ec758a
X-8.15 result: 599d3d0

q01: verified / acceptance met
q02: verified / acceptance met
q03: Run生成前 internal_error / getaddrinfo failed
q05: verified / acceptance met
q06: partially_verified / acceptance met
q07: withheld / acceptance met
q08: synthesize QUOTA_EXCEEDED / failed
```

q08はM-5を具体化した事例だが、既定2 Agentでは別Auditorが残らないため、M-5導入後も必ず救済できるとは限らない。

q03のDNS失敗はRun生成前であり、本作業の対象外とする。

## 並行作業禁止

X-8.17と次を並行で進めない。

```text
L-5
S-8
q03 failure-boundary修正
S-9
S-10
Clarifier
Responder並列化
```

結果を見てlive評価や追加の機能実装へ進まない。

## 作業前確認

最初に次を読む。

```text
QandA.md                M-5、S-5、M-2、S-7、T-1
SPEC.md                 §6.2〜§6.4、§8.2〜§8.7、§15.7、§15.8
CLASS.md                ExecutionPlan、PhaseAssignment、RunAgentAvailability
SEQUENCE.md             retry / substitution異常系
STATE.md                AgentExecution、availability、Budget
TESTCASE.md             UT-ORCH-02、04〜07、13、TokenBudget関連
FIX_PLAN.md
src/oracle_council/assignment.py
src/oracle_council/orchestrator.py
src/oracle_council/models.py
src/oracle_council/budget.py
src/oracle_council/cli.py
src/oracle_council/fakes.py
config/agents.yaml
tests/unit/test_assignment.py
tests/unit/test_orchestrator.py
CLI JSON出力関連テスト
tests/unit/test_budget.py
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

git merge-base --is-ancestor 554602d HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.16 specification commit 554602d." }

git merge-base --is-ancestor 599d3d0 HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.15 result commit 599d3d0." }
```

合格条件:

- branchが`main`
- `git status --short`が完全に空
- HEADと`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.17`
- HEADに`554602d`と`599d3d0`が含まれる

不一致がある場合は実装を開始せず報告する。

## 変更前baseline

```powershell
py -m pytest
git diff --check
git status --short
```

基準:

```text
259 passed, 6 deselected
```

件数が変わっていても通常テストが全件passし、live/expensiveが除外されていればよい。

## 現行アーキテクチャとの橋渡し

S-9とS-10は未解決のため、本作業でprobe lifecycleやconfigured/selected participant多重度を再設計しない。

現行CLIはRun開始前に各Adapterをprobeし、`OK`のAgentだけを`Orchestrator`へ渡している。

X-8.17では次の扱いとする。

- `Orchestrator`へ渡された`RegisteredAgent` tupleをRun開始時の適格Agentスナップショットとする
- `build_execution_plan()`内で実CLIの`probe()`を再実行しない
- Run途中で設定ファイルを再読込しない
- `configured_agent_ids`は現行実装上、Orchestratorへ渡されたRun開始時適格Agent IDsを保持する
- この橋渡しをS-9/S-10の解消とは記載しない
- capabilitiesの本格的なphase適格判定を新設しない
- 現在の`role_priority`と設定順を候補順の正本とする

CLI preflight、Adapterの`probe()`、`capabilities()`、認証処理を不必要に変更しない。

## 1. ExecutionPlanモデル

### 1.1 assignment.pyへ正式モデルを追加

最低限、次の意味を持つ型を追加する。

```text
ExecutionPlan
- run_id: str
- configured_agent_ids: tuple[str, ...]
- phase_assignments: tuple[PhaseAssignment, ...]
- agent_availability: RunAgentAvailability collection
- max_run_retries: int = 2
- max_run_substitutions: int = 1
- max_agent_calls: int = 12

PhaseAssignment
- phase: str
- slot_index: int
- required_success_count: int
- candidate_agent_ids: tuple[str, ...]
- constraints: immutable typed value

RunAgentAvailability
- agent_id: str
- status: available | run_unavailable
- reason_code: str | None
```

Python上の具体的なcollectionやhelper methodは実装に合わせてよいが、外から書き換え可能な共有mutable dictを正本にしない。

### 1.2 build_execution_plan

`build_execution_plan(run_id, agents)`または同等の純粋な関数を追加する。

必須assignment:

```text
respond slot 0
respond slot 1
claim_extract slot 0
verify slot 0
criticize slot 0
synthesize slot 0
audit slot 0
```

候補順:

1. phaseの`role_priority`降順
2. 同点は元の設定順
3. ランダム処理なし

Plan生成時点では全候補順を固定し、Run途中にpriorityを再計算しない。

### 1.3 互換性

既存の`rank()`は維持してよい。

既存テストやimportを壊さないため、`AssignmentPlan` / `plan_assignments()`は互換wrapperとして残してよい。ただし、`Orchestrator`の実行正本は新しい`ExecutionPlan`にする。

古い`AssignmentPlan`を維持する場合も、同じ候補順規則から生成し、二重の選定ロジックを作らない。

## 2. AgentExecutionRecord

`src/oracle_council/models.py`の`AgentExecutionRecord`へ次を追加する。

```python
substitute_for: str | None = None
```

条件:

- `retry_of`と`substitute_for`は排他的
- 両方がnon-nullのrecord生成を拒否する
- 既存recordの互換性を維持する
- metadata-onlyの正式フィールドとして扱う
- raw診断や質問本文を含めない

CLI `--json`の`executions[]`にも`substitute_for`を追加する。

既存`retry_of`の出力を変更しない。

S-8は未確定なので、この作業で`exit_code`名を`process_exit_code`へ変更しない。

## 3. Run開始時のPlan構築

現在は`plan_assignments()`をRun作成前に呼び出している。

`ExecutionPlan`が`run_id`を持つため、次の順へ変更する。

1. `run_id`を生成
2. `ExecutionPlan`を構築
3. Plan構築が不可能ならRunイベントを保存せずpreflight停止
4. Plan成功後に`run_created`
5. 以後は同じPlanをRun終了まで使用

`run_created`のparticipantsはRun開始時適格Agent snapshotを用いる。

## 4. Run内Agent可用性

Run stateへ最低限、次を保持する。

```text
run_retries_used
run_substitutions_used
agent availability / reason
successful responder agent IDs
current synthesizer agent ID
current auditor agent ID
```

### Run全体でrun_unavailableにするエラー

```text
AUTH_REQUIRED
QUOTA_EXCEEDED
COMMAND_NOT_FOUND
UNSUPPORTED_VERSION
UNSAFE_CAPABILITY
```

これらを返したAgentは、そのRunの後続phase候補から除外する。

### 論理slotだけから除外するエラー

```text
TIMEOUT
RATE_LIMITED
EXECUTION_ERROR
```

これらは失敗した同じslotの候補から除外するが、後続phaseでの利用を自動禁止しない。

### M-5対象外

```text
INVALID_OUTPUT
CONTEXT_OVERFLOW
BUDGET_EXCEEDED
CANCELLED
SearchError
EvidenceProvider障害
Run生成前のCLI・DNS・設定例外
```

これらではM-5 substitutionを開始しない。

`INVALID_OUTPUT`の回復はL-3のまま未確定とし、勝手に代替実行しない。

## 5. retry処理

同一Agent retry対象:

```text
TIMEOUT
RATE_LIMITED
```

条件:

- 同じphase・同じ論理slot
- 同じAgent
- slotごとに最大1回
- Run全体で最大2回
- 新しい`execution_id`
- 新しいBudgetReservation
- `retry_of`は直前の失敗Executionを参照
- `substitute_for`はnull

既存のretry成功経路と履歴を維持する。

retryが失敗した場合、最終失敗codeがsubstitution対象であり条件を満たす場合だけsubstitution候補探索へ進む。

## 6. substitution処理

substitution候補探索へ進めるcode:

```text
TIMEOUT             # same-agent retry後も失敗、またはretry枠なし
RATE_LIMITED        # same-agent retry後も失敗、またはretry枠なし
AUTH_REQUIRED
QUOTA_EXCEEDED
COMMAND_NOT_FOUND
UNSUPPORTED_VERSION
UNSAFE_CAPABILITY
EXECUTION_ERROR
```

条件:

- Run全体のsubstitution使用数が0
- 失敗Agentとは異なる候補
- failed slotで既に失敗したAgentではない
- run_unavailable Agentではない
- phase固有の独立性制約を満たす
- TokenBudgetのreserveが成功する

substitution Execution:

- 新しい`execution_id`
- 新しいBudgetReservation
- `substitute_for`は置換対象となった最後の失敗Executionを参照
  - retryが失敗してsubstitutionへ進んだ場合は、失敗したretry Executionを参照
  - retryなしの場合は元Executionを参照
- `retry_of`はnull
- substitution後のAgentにsame-agent retryを行わない
- substituteが失敗しても2人目のsubstituteを選ばない
- substitute成功時は通常成功と同様にPhase `success_count`を増やし、出力をstateへ適用する

Run全体のsubstitution使用数は、substituteを選びExecutionを開始する直前に1回だけ消費する。

候補が見つからない場合は消費しない。

## 7. substitutionイベント

### 候補を選んだ場合

```text
agent_substitute_selected
```

最低限のmetadata:

```text
phase
slot_index
failed_execution_id
original_agent_id
substitute_agent_id
```

### 候補がない場合

```text
agent_substitution_unavailable
```

最低限のmetadata:

```text
phase
slot_index
failed_execution_id
original_agent_id
reason: fixed enum/string
```

禁止:

- raw stdout/stderr
- 例外本文
- prompt
- 質問本文
- 回答本文
- Claim/Evidence本文
- CLI command
- path
- env
- token/API key

eligible substituteがない場合、元のAgentFailure codeをPhase/Runへ保持する。

substitute Executionが失敗した場合、そのsubstituteのfailure codeをPhase/Runへ記録する。

新しい公開AgentErrorCodeは追加しない。

## 8. Responder制約

Responder 2 slotは異なるAgentで成功しなければならない。

実行時の条件:

- slot 0とslot 1の成功Agent IDが異なる
- 一方のslotで成功済みのAgentを、もう一方のsubstituteに使わない
- 失敗Agent自身をsubstituteに使わない
- 3つ目以降の適格Agentがある場合だけResponder substitution可能
- 既定2 Agentでretry後もResponderが失敗した場合はrespond Phase / Run failed
- 1件の回答だけで後続phaseへ進まない

既存コードのResponder逐次実行を、本作業で並列化しない。UT-ORCH-03の並列化は別課題である。

## 9. Synthesizer / Auditor分離

常に次を守る。

```text
current_synthesizer_agent_id != current_auditor_agent_id
```

### Synthesizer選定

候補を選ぶ時点で、その候補とは異なる適格Auditor候補が最低1名残ることをlook-aheadする。

initial selectionとsubstitutionの両方へ適用する。

### Auditor選定

現在のSynthesizerを候補から除外する。

Auditor substitutionでもSynthesizerを除外する。

### 2 Agent q08型

```text
Agent A: synthesizeでQUOTA_EXCEEDED -> run_unavailable
Agent B: substitute Synthesizer候補
別Auditor: 0名
```

この場合はeligible substituteなしとして、分離を破らずRun failedとする。

### 3 Agent構成

```text
Agent A: synthesizeでQUOTA_EXCEEDED
Agent B: substitute Synthesizer
Agent C: Auditor
```

候補順とpriorityがこの配置を許す場合、substitutionで継続できることをFakeテストする。

self-auditへ縮退しない。

## 10. 監査修正フローとの統合

既存の`changes_required`後の再synthesize・再auditを壊さない。

- revision synthesizeは、通常は現在のSynthesizerをpreferred Agentとする
- re-auditは、通常は現在のAuditorをpreferred Agentとする
- それぞれ新しいbase Executionであり、`retry_of`/`substitute_for`は通常nullから開始する
- 失敗した場合は同じM-5規則を適用する
- Run全体retry/substitution/call上限は初回phaseと共有する
- Auditor承認のない回答は公開しない

未来のcall枠を予約しない。先行retry/substitutionでcall予算を使い、後のaudit reserveが失敗した場合は既存T-1規則へ従う。

## 11. TokenBudget

`TokenBudget.reserve()`を12回上限の唯一の正本として維持する。

- ExecutionPlanに`max_agent_calls=12`を記録する
- 別の独立call counterで13回目を判定しない
- retry/substitutionも別Reservation
- 子process開始後の失敗は既存どおりsafe-side commit
- reserve失敗時はAgentを呼ばない
- Run終了時にreserved 0

`TokenBudget`の既定`call_limit=12`を変更しない。

## 12. Orchestrator実装上の注意

`_execute_phase()`は現在単一Agentを引数に取る。ExecutionPlanの候補とslot制約を扱えるように責務を整理する。

実装形は任せるが、巨大な1関数へ全規則を追加しない。

候補:

```text
_select_candidate(...)
_mark_agent_unavailable(...)
_can_retry(...)
_can_substitute(...)
_execute_attempt(...)
```

要件:

- 選定は決定的
- Planの候補順を変更しない
- retry/substitutionのrecordとeventを分離
- error summaryは既存の固定安全形式
- `_failure_summary()`のX-8.5挙動を維持
- Evidence収集、Claim merge、withheld判定、audit gateを変更しない

## 13. CLI JSON

`executions[]`へ次を追加する。

```json
"substitute_for": null
```

substitution Executionでは参照先execution IDを返す。

- `retry_of`と両方non-nullにならない
- error summary sanitizationを維持
- raw診断を出さない
- schema_versionを変更しない
- S-8のフィールド名変更は行わない

## 14. 必須Fakeテスト

実CLI、実WebSearch、実HTTPは使用しない。

### A. ExecutionPlan

- 同じ3〜4 Agent入力で10回構築して完全一致
- `role_priority`降順
- 同点は設定順
- respond slot 0/1、claim_extract、verify、criticize、synthesize、auditが存在
- retry=2、substitution=1、call=12
- candidate IDsがimmutable順序
- initial SynthesizerとAuditorが異なる

### B. 既存retry回帰

- `TIMEOUT` -> 同一Agent retry成功
- 新しいexecution ID
- `retry_of`設定
- `substitute_for is None`
- Run retry使用数1
- substitution 0
- 既存AgentExecution履歴を保持

### C. retry失敗後substitution

3 Agent構成で:

```text
primary: TIMEOUT
retry: TIMEOUT
substitute: success
```

確認:

- 同一Agent call 2回
- substitute Agent call 1回
- substituteの`substitute_for`は失敗retry execution ID
- Run retry 1、substitution 1
- Phase成功
- 3件すべて履歴へ残る

### D. 即時substitution

`QUOTA_EXCEEDED`で:

- 同一Agent retry 0
- eligible substituteを1回実行
- 元Agentをrun_unavailable
- 後続phase候補から元Agentを除外
- eventを保存

`AUTH_REQUIRED`、`COMMAND_NOT_FOUND`、`UNSUPPORTED_VERSION`、`UNSAFE_CAPABILITY`も少なくともparameterized testでrun_unavailable処理を確認する。

### E. EXECUTION_ERRORはslot-local

- primaryが`EXECUTION_ERROR`
- 別Agentへsubstituteしてslot成功
- 元Agentは後続の別phaseでpriorityに従い再利用可能
- Run全体unavailableにならない

### F. M-5対象外

少なくとも次を確認する。

```text
INVALID_OUTPUT
BUDGET_EXCEEDED
```

- substitution 0
- 元codeで失敗
- `agent_substitute_selected`なし

`CONTEXT_OVERFLOW`の既存処理が未実装またはL-3/L-5依存なら、新しい回復動作を追加せず既存挙動を維持する。

### G. Responder独立性

1. 3 Agent構成で一方のResponderが失敗し、成功済みResponder以外の3番目へsubstitute
2. 2 Agent構成で一方が失敗し、成功済みの他方をsubstituteへ使わずRun failed
3. 最終的な2 responsesのagent IDが異なる

### H. 2 Agent synthesize quota failure

- Synthesizerが`QUOTA_EXCEEDED`
- 他方だけが残る
- 別Auditorを確保できない
- substitute Executionを開始しない
- `agent_substitution_unavailable`
- Phase error codeは`QUOTA_EXCEEDED`
- final answer非公開
- Run failed

### I. 3 Agent synthesize substitution

- primary Synthesizerが`QUOTA_EXCEEDED`
- substitute Synthesizer成功
- 別Auditor成功
- SynthesizerとAuditorが異なる
- final answer公開条件を満たす
- substitution 1

### J. Auditor substitution

- primary Auditorがsubstitution対象codeで失敗
- current Synthesizerを候補から除外
- 3番目のAgentがAuditorとして成功
- self-auditなし

### K. Run全体substitution 1回

- 早いphaseでsubstitution成功
- 後のphaseで再びsubstitution対象failure
- 2回目のsubstituteを開始しない
- `agent_substitution_unavailable`
- 元failure codeでRun failed

### L. substitute失敗

- substituteが失敗
- substituteへのretryなし
- 2人目substituteなし
- substitute failure codeでRun failed

### M. retry上限と別カウンタ

- Run全体retryは既存どおり最大2回
- retry 2回使用後でもsubstitution枠が未使用なら1回使える
- substitution使用後もretry枠の数値を増やさない

### N. 12回上限

TokenBudgetで:

- 12個のReservationをcommit可能
- 13個目は`BudgetExceededError`
- 13個目のAdapter executeは呼ばれない
- reserved 0

既存Orchestratorの低いcall_limitによるreserve前拒否テストも維持する。

### O. record/event安全性

- `retry_of`と`substitute_for`を同時指定すると拒否
- substitution eventにraw secret fixtureが入らない
- fixed metadataのみ
- metadata-only storageにraw diagnosticなし

### P. CLI JSON

- 通常Executionは`substitute_for: null`
- substitution Executionは参照ID
- `retry_of`と排他
- JSON parse可能
- raw診断なし

## 15. 回帰要件

次を壊さない。

- happy path 7 calls
- withheld short-circuit 4 calls
- audit changes_requiredの9 calls
- Evidence snapshot
- storage fail-closed
- timeout retry
- run retry 2回上限
- false premise correction
- AUTH_REQUIRED分類hardening
- EXECUTION_ERROR固定summary
- Claude/Codex stdin transport
- CliSearchProvider stdin transport
- no-store
- TokenBudget settlement

## 16. 変更禁止

今回は次を変更しない。

```text
src/oracle_council/adapters/claude.py
src/oracle_council/adapters/codex.py
src/oracle_council/adapters/base.py
src/oracle_council/evidence.py
config/agents.yaml
evaluation/
scripts/run_x8_evaluation.py
pyproject.toml
```

必要性が生じた場合も、勝手にscopeを広げず停止して報告する。

既存評価artifactを変更、削除、再構築しない。

## 17. 実行禁止

```text
claude
codex
WebSearch
実HTTP
ORACLE_COUNCIL_LIVE=1
live pytest
expensive pytest
X-8評価
q01〜q08再実行
```

通常pytest内のFake subprocessは可。

## 18. 許可される主な変更

```text
src/oracle_council/assignment.py
src/oracle_council/orchestrator.py
src/oracle_council/models.py
src/oracle_council/cli.py
src/oracle_council/fakes.py             # test fixture支援が必要な場合のみ
tests/unit/test_assignment.py
tests/unit/test_orchestrator.py
tests/unit/test_budget.py
CLI JSON関連の既存unit test
FIX_PLAN.md
hikitsugi.md
instructions/result.md
```

新規unit testファイルは、責務が明確で既存ファイルを肥大化させない場合のみ可。

QandA.md、SPEC.md、CLASS.md、SEQUENCE.md、STATE.md、TESTCASE.mdはX-8.16で仕様確定済みである。実装中に明白な矛盾や誤植を見つけた場合だけ最小修正し、resultへ理由を記録する。

## 19. 検証

最初にtargeted testsを実行する。

例:

```powershell
py -m pytest tests/unit/test_assignment.py
py -m pytest tests/unit/test_orchestrator.py
py -m pytest tests/unit/test_budget.py
```

CLI JSON関連の変更を行った場合は該当テストを実行する。

その後:

```powershell
py -m pytest
git diff --check
git status --short
```

合格条件:

- 通常テスト全件pass
- live/expensiveは既定で除外
- `git diff --check`成功
- 実CLI/WebSearch/HTTP未実行
- 既存評価artifact未変更
- 変更範囲がX-8.17内

## 20. FIX_PLAN更新

M-5 / S-5を次の状態へ更新する。

```text
X-8.16: 仕様確定
X-8.17: 通常実装・Fakeテスト完了
live確認: 未実施
```

M-5/S-5を「実装済み」として扱ってよいが、次を明示する。

- q08を再実行していない
- 2 Agent synthesize quota failureは仕様上救済不能
- 3 Agent以上の代替成功はFake確認
- S-9/S-10未解決
- q03 failure-boundary未解決
- L-5、S-8未解決

次作業はL-5とする。

## 21. hikitsugi.md / instructions/result.md

X-8.17としてsanitizedな実装結果を記録する。

必須項目:

- 実行前HEAD
- X-8.16仕様コミット`554602d`
- ExecutionPlanの実装型と候補順
- current architecture bridge（Orchestratorへ渡されたAgentを適格snapshotとしたこと）
- retry/substitutionの実装
- run_unavailable / slot-localの区別
- `substitute_for`
- events
- Responder制約
- Synthesizer/Auditor look-ahead
- 2 Agent q08型Fake結果
- 3 Agent substitution Fake結果
- retry 2 / substitution 1 / call 12
- 追加・更新テスト
- pytest結果
- `git diff --check`
- live・実CLI・HTTP未実行
- q03未修正
- S-9/S-10未解決
- 次がL-5、その後S-8

raw Agent出力、質問、prompt、Evidence本文、secret fixtureを文書へ記載しない。

## 22. commit前確認

```powershell
git status --short
git diff --check
git diff --stat
git diff -- src/oracle_council/assignment.py src/oracle_council/orchestrator.py src/oracle_council/models.py src/oracle_council/cli.py tests FIX_PLAN.md hikitsugi.md instructions/result.md
```

次が変更されていないことを確認する。

```text
adapters
Evidence実装
config
evaluation
run_x8_evaluation.py
```

意図しない変更があればcommitせず報告する。

## 23. commitとpush

推奨commit message:

```text
feat: add deterministic agent substitution
```

```powershell
git add src/oracle_council/assignment.py `
        src/oracle_council/orchestrator.py `
        src/oracle_council/models.py `
        src/oracle_council/cli.py `
        tests `
        FIX_PLAN.md `
        hikitsugi.md `
        instructions/result.md

# fakes.pyを変更した場合だけ追加
git status --short
git commit -m "feat: add deterministic agent substitution"
git push origin main

git status --short
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main
```

`git add tests`で無関係ファイルが入らないことを事前に確認する。

完了条件:

- ExecutionPlanが実行正本
- retry/substitutionが仕様どおり分離
- Run全体retry 2、substitution 1
- TokenBudget call 12上限維持
- Responder独立性維持
- Synthesizer/Auditor分離維持
- 2 Agent救済不能Fakeテストpass
- 3 Agent代替成功Fakeテストpass
- q03変更なし
- 全通常テストpass
- diff check成功
- live未実行
- commit/push成功
- worktree clean
- HEADとorigin/main一致

## 24. 最終報告

次を簡潔に報告する。

1. 実装commit SHA
2. ExecutionPlan / PhaseAssignmentの概要
3. retry/substitution counters
4. error code別可用性処理
5. `substitute_for`とevent
6. Responder制約
7. 2 Agent q08型Fake結果
8. 3 Agent substitution Fake結果
9. 12回上限テスト
10. pytest件数
11. diff check
12. 変更ファイル
13. live・実CLI・HTTP未実行
14. q03、S-9/S-10未解決
15. commit/push/clean状態
16. 次がL-5、その後S-8
