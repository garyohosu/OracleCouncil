# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分や未追跡ファイルがある場合は、勝手にreset・stash・削除・移動せず、差分を保護して状況を報告してください。

## X-8.16: M-5 / S-5 代替Agent選定・再試行仕様の確定

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.14 / X-8.15で、M-5導入前のholdout baselineを取得した。

```text
q01: verified / acceptance met
q02: verified / acceptance met
q03: Run生成前 internal_error / getaddrinfo failed
q05: verified / acceptance met
q06: partially_verified / acceptance met
q07: withheld / acceptance met
q08: synthesizeでQUOTA_EXCEEDED / failed / acceptance not assessable
```

X-8.15の結果コミット:

```text
599d3d0 docs: record q05-q08 X-8 holdout evaluation
```

q08ではClaude担当の`synthesize`が`QUOTA_EXCEEDED`となり、Codexは利用可能だった。ただし、既定2 Agent構成ではCodexを代替Synthesizerにすると、Synthesizerとは別のAuditorが残らない。したがって「失敗したら単純に他方へ切り替える」だけではSPEC §6.3、§6.4の独立監査条件を破る。

M-5はS-5の実行計画表現に依存する。本作業ではM-5とS-5を同時に仕様確定し、代替Agent、同一Agent再試行、Run全体の2回再試行枠、Run全体の1回代替枠、12回絶対上限、Responderの独立性、Synthesizer/Auditor分離を矛盾なく文書化する。

今回は**設計仕様の確定だけ**を行う。source、test実装、config、runner、実CLI、live評価は変更・実行しない。

## X-8.15から確定した事実

- q05〜q08は各1回実行済みで、再実行しない
- q08は`respond`から`criticize`まで成功し、`synthesize`で`QUOTA_EXCEEDED`
- q08のRunは6 Agent callsを消費し、retryは0
- q03の`getaddrinfo failed`はRun生成前の外部ネットワーク障害であり、Agent代替だけで解消するとみなさない
- M-5はq08型の障害を扱うが、既定2 Agentで必ず救済できるとは限らない
- 不正確な回答が公開されたbaseline問題は0件

## 作業前確認

最初に次を読む。

```text
QandA.md                M-5、S-5、M-2、S-7、T-1
SPEC.md                 §6.2〜§6.4、§8.2〜§8.7、§15.2、§15.7、§15.8
CLASS.md                Orchestrator、AgentExecution、TokenBudget
SEQUENCE.md             正常系、監査修正、Responder timeout
STATE.md                Run / Phase / AgentExecution / Budget
TESTCASE.md             UT-ORCH-02、04〜07、10、TokenBudget関連
FIX_PLAN.md
src/oracle_council/assignment.py
src/oracle_council/orchestrator.py
src/oracle_council/budget.py
src/oracle_council/models.py
config/agents.yaml
tests/unit/test_assignment.py
tests/unit/test_orchestrator.py
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

git merge-base --is-ancestor 599d3d0 HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.15 result commit 599d3d0." }

git merge-base --is-ancestor 0ec758a HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.14 result commit 0ec758a." }
```

合格条件:

- branchが`main`
- `git status --short`が完全に空
- HEADと`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.16`
- HEADに`599d3d0`と`0ec758a`が含まれる

不一致がある場合は文書変更を開始せず報告する。

## 現行実装の確認事項

次をコードから確認し、結果へ記録する。

1. `assignment.py`は`role_priority`降順、設定順tie-breakで決定的にrankする
2. `plan_assignments()`はResponder 2名とSynthesizer/Auditor分離を固定する
3. `rank(..., exclude=...)`は候補除外を扱えるが、Orchestratorから動的代替に使われていない
4. `Orchestrator._execute_phase()`は`TIMEOUT`と`RATE_LIMITED`だけ同一Agentで再試行する
5. 同一Execution相当の再試行は最大1回、Run全体の再試行は2回
6. 現在は代替Agent実行が未実装
7. `TokenBudget.reserve()`がcall limitを原子的に判定し、13回目を開始前に拒否できる
8. retryは別Execution、別BudgetReservationとして記録される
9. q08の`QUOTA_EXCEEDED`は現行では再試行されずRun終了する

## 確定する仕様

以下をM-5 / S-5の正式回答として採用する。別案へ変更しない。文書間の表現差だけ調整してよい。

### 1. retryとsubstitutionを別概念にする

- **retry**: 同じAgent、同じ論理実行slot、同じphaseを再実行する
- **substitution**: 失敗したAgentとは異なるAgentが、同じ論理実行slotとphaseを引き継ぐ
- retryとsubstitutionはどちらも新しい`AgentExecution`と新しい`BudgetReservation`を作る
- retryは`retry_of`で直前の同一Agent実行を参照する
- substitutionは`substitute_for`で置換対象Executionを参照する
- `retry_of`と`substitute_for`は同一Executionで同時に設定しない
- substitution後のAgentに対して、さらに同一Agent retryを行わない。1つの論理slotで許可される追加実行は「同一Agent retry 1回」または「substitute 1回」を順番に最大限使っても、代替Agentの再retryは行わない

### 2. Run全体の上限

独立した3つの上限を持つ。

```text
same-agent retry: Run全体で最大2回
substitution: Run全体で最大1回
AI call: retry・substitution・Clarifier・監査修正を含め最大12回
```

- substitutionはRun全体のretry 2回枠を消費しない
- retryとsubstitutionは両方とも12回call上限を消費する
- 12回上限は`TokenBudget.reserve()`を唯一の正本とする
- 13回目が必要になった場合、Agentを呼ぶ前に`BUDGET_EXCEEDED`
- 通常7回ならretry 2回＋substitution 1回をすべて使っても10回
- Clarifierと監査修正を含む基本10回のRunでは、追加枠3回を予約しない。実行順にreserveし、12回へ達した後の追加実行を拒否する
- 将来の監査用callを暗黙に予約しない。先行retryで予算を使い切りAuditorを呼べなければ、T-1に従い承認済み回答がないRunはfailedになる

### 3. 同一Agent retry対象

同一Agent retryを許可するのは次だけ。

```text
TIMEOUT
RATE_LIMITED
```

条件:

- 同じ論理slotにつき最大1回
- Run全体のretry使用数が2未満
- 12回call上限とtoken予算を満たす

同一Agent retryが失敗した場合、条件を満たせばRun全体で1回だけsubstitutionへ進める。

### 4. 即時substitution対象

次は同一Agent retryをせず、直ちにsubstitution候補を探す。

```text
AUTH_REQUIRED
QUOTA_EXCEEDED
COMMAND_NOT_FOUND
UNSUPPORTED_VERSION
UNSAFE_CAPABILITY
EXECUTION_ERROR
```

Run全体のsubstitution枠が未使用で、別の適格Agentがあり、12回上限内の場合だけ実行する。

次はM-5のsubstitution対象外とする。

```text
INVALID_OUTPUT      # L-3で回復方針を別途確定
CONTEXT_OVERFLOW    # 決定的縮約を1回、失敗時BUDGET_EXCEEDED
BUDGET_EXCEEDED
CANCELLED
SearchError / EvidenceProvider障害
Run生成前のCLI・DNS・設定例外
```

### 5. Agent可用性のscope

Run内でAgentの可用性を次の2種類に分ける。

**Run全体でunavailableにするエラー:**

```text
AUTH_REQUIRED
QUOTA_EXCEEDED
COMMAND_NOT_FOUND
UNSUPPORTED_VERSION
UNSAFE_CAPABILITY
```

これらを返したAgentは、そのRunの後続phase候補から除外する。

**その論理slotだけから除外するエラー:**

```text
TIMEOUT
RATE_LIMITED
EXECUTION_ERROR
```

これらは将来phaseでの利用を自動禁止しない。ただし失敗した同じ論理slotのsubstitute候補にはしない。

### 6. ExecutionPlanと候補順

S-5の回答として、単一`selectAgent(phase)`を正式モデルにしない。

Run開始時に決定的な`ExecutionPlan`を作る。

最低限の正式モデル:

```text
ExecutionPlan
- run_id
- configured_agent_ids
- phase_assignments
- max_run_retries = 2
- max_run_substitutions = 1
- max_agent_calls = 12

PhaseAssignment
- phase
- slot_index
- required_success_count
- candidate_agent_ids  # role_priority降順、設定順tie-break
- constraints

RunAgentAvailability
- agent_id
- status: available | run_unavailable
- reason_code
```

実装時の型名はPython規約に合わせてよいが、責務とフィールド意味は変えない。

候補順:

1. Run開始時にprobe/capabilityを満たしたAgentだけ
2. phaseの`role_priority`降順
3. 同点は設定順
4. 失敗Agent自身を除外
5. `run_unavailable` Agentを除外
6. phase固有の独立性制約を適用

ExecutionPlanは候補順の正本であり、失敗後にランダム選定やモデル変更をしない。設定ファイルをRun途中で再読込しない。

### 7. Responder制約

- 2つのResponder slotは異なる`agent_id`で成功しなければならない
- 一方のResponderが失敗した場合、もう一方で成功済みのAgentをsubstituteに使わない
- 3つ目以降の適格Agentがある場合だけResponder substitutionが可能
- 既定2 Agent構成では、Responderの同一Agent retryも失敗した場合にsubstituteは存在せず、respond PhaseとRunはfailed
- 1 Agentの回答だけで継続しない

### 8. Synthesizer / Auditor分離

- SynthesizerとAuditorは常に異なる`agent_id`
- self-auditへ暗黙縮退しない
- Synthesizer候補を選ぶ時点で、その候補とは異なる適格Auditor候補が最低1名残ることをlook-ahead条件にする
- Auditor substitutionでは現在のSynthesizerを候補から除外する
- hard unavailableにより別Auditorを確保できない場合、回答を公開しない
- Auditor未承認の最終案が存在しても公開しない

q08への適用:

- Claudeの`QUOTA_EXCEEDED`はClaudeをRun全体でunavailableにする
- Codexをsubstitute Synthesizerにすると別Auditorが残らない
- 既定2 Agent構成ではeligible substituteなしとなり、q08を必ず救済できるわけではない
- 3 Agent以上で別Auditorが残る場合はsubstitutionで継続できる
- M-5を「2 Agentならquota障害を必ず救済する仕様」と記載しない

### 9. substitution不能・失敗時

- eligible substituteがない場合、元のPhase error codeを保持してRunをfailedにする
- 新しい公開AgentErrorCodeを追加しない
- metadata eventとして`agent_substitution_unavailable`を記録し、phase、failed_execution_id、original_agent_id、固定reasonを保持する
- raw診断、prompt、質問、回答、環境変数をeventへ入れない
- substituteを選んだ場合は`agent_substitute_selected`を記録する
- substitute Executionが失敗した場合、2人目のsubstituteは選ばず、その失敗codeでPhaseとRunをfailedにする
- 元Executionとretry/substitute Executionをすべて履歴へ残す

### 10. Run / Phase / call count

- 失敗したExecutionも子process開始後ならcall countへ含む
- retry/substitutionのreserve、commit/releaseはS-7に従う
- substitute成功後、Phaseの`success_count`は通常成功と同様に加算する
- 最低成功数を満たした場合だけPhase succeeded/degradedへ進める
- required successを満たさなければfailed
- substitutionが使われても最終classification規則は変更しない

## q03の扱い

q03の`[Errno 11001] getaddrinfo failed`はRun生成前であり、M-5 / S-5のAgentExecution substitution対象に含めない。

- QandA、SPEC、FIX_PLANへ「別のfailure-boundary課題」と明記する
- 本作業でq03修正案を実装しない
- M-5解消済みの根拠にq03を含めない

## 文書更新

### QandA.md

- M-5の`回答`を上記仕様で確定する
- S-5の`回答`をExecutionPlan / PhaseAssignment / RunAgentAvailabilityで確定する
- M-5とS-5が相互依存のため同時確定したことを記録する
- q08の2 Agent制約とq03別課題を追記する

### SPEC.md

- 文書バージョンを次版へ更新する
- §6.2〜§6.4へExecutionPlan、候補順、ResponderとSynth/Audit制約を追加
- §8.3へretry/substitutionの定義、対象error表、Run全体2 retry / 1 substitution / 12 callsを追加
- §8.7へretry/substitutionが別Reservationであることを維持
- §15.7 / §15.8へ`substitute_for`、イベント、可用性scopeを追加
- q08型の2 Agent制約を例として記載してよいが、実行結果固有のrun_id等はSPECへ入れない

### CLASS.md

- `Orchestrator.selectAgent()`を正本表現から外し、`buildExecutionPlan()`または同等責務へ変更
- `ExecutionPlan`、`PhaseAssignment`、`RunAgentAvailability`を追加
- `AgentExecution`へ`substituteFor`を追加
- TokenBudgetが12回上限の正本である依存を維持
- S-9、S-10を解消済みにしない

### SEQUENCE.md

最低限、次を図示する。

1. `TIMEOUT` → 同一Agent retry → retry失敗 → substitute選定
2. `QUOTA_EXCEEDED` → 同一Agent retryなし → substitute候補確認
3. 3 Agent構成で代替成功し、別Auditorが残る例
4. 2 Agentのsynthesize quota failureで別Auditorが残らずRun failedとなる例
5. 13回目reserve拒否でAgentを呼ばない例

### STATE.md

- AgentExecutionのretry/substitute関係を追加
- RunAgentAvailabilityの`available -> run_unavailable`を追加
- terminal Executionを再利用せず、新Executionを作ること
- substitution不能時のPhase/Run failed遷移
- Budget 12回境界を追加

### TESTCASE.md

M-5 / S-5起因のBLOCKEDを解除し、期待値を一意にする。

最低限、次を正式ケースとして定義する。

- 決定的候補順と設定順tie-break
- TIMEOUT同一Agent retry成功
- TIMEOUT retry失敗後、3 Agent目へsubstitute成功
- QUOTA_EXCEEDEDは同一Agent retryせずsubstitute
- AUTH_REQUIREDでAgentがRun全体unavailable
- EXECUTION_ERRORでslot-local substitute
- INVALID_OUTPUTはM-5でsubstituteしない（L-3 BLOCKEDを維持）
- Responderは成功済みのもう一方を代替に使わない
- 2 Agent responder失敗は代替なしでfailed
- Synthesizer substitute時に別Auditorをlook-ahead確保
- 2 Agent synthesize quota failureはeligible substituteなし
- 3 Agent synthesize quota failureは代替と別Auditorで継続
- Auditor substituteはSynthesizerを除外
- Run全体substitutionは1回のみ
- Run全体same-agent retryは2回のみ
- retry 2回とsubstitution 1回は別カウンタ
- 12回目まで実行可、13回目はreserve前拒否
- retry/substituteごとに別execution_id・別reservation
- `retry_of`と`substitute_for`の排他
- metadata eventにraw情報が入らない
- substitute失敗後に2人目を選ばない

既存`UT-ORCH-02`、`UT-ORCH-04`、`UT-ORCH-06`、`UT-ORCH-07`を更新し、必要なら新しいIDを追加する。既存IDを重複させない。

### FIX_PLAN.md

- M-5とS-5を「仕様確定済み・実装未着手」として解消済み側へ移す
- 次実装作業がM-5/S-5実装であることを明記する
- L-5、S-8、q03 failure-boundaryは未解決のまま
- q03をM-5で解消したと書かない

### hikitsugi.md / instructions/result.md

X-8.16として次を記録する。

- X-8.15 baseline要約
- q08がM-5の具体例になったこと
- 2 Agentでは別Auditor不足により必ず救済できないこと
- retryとsubstitutionの定義
- 2 retry / 1 substitution / 12 calls
- error code別の処理
- ExecutionPlanモデル
- q03は別課題
- 更新文書一覧
- pytest / diff check結果
- live未実行
- 次がM-5/S-5実装で、その後L-5、S-8であること

## 変更禁止

今回は次を変更しない。

```text
src/
tests/
config/
evaluation/
scripts/
pyproject.toml
```

既存評価artifactを変更、削除、再構築しない。

実行しないもの:

```text
claude
codex
WebSearch
実HTTP
ORACLE_COUNCIL_LIVE=1
live / expensive pytest
X-8評価
q01〜q08
```

## 検証

文書変更後に実行する。

```powershell
py -m pytest
git diff --check
git status --short
```

期待値の基準:

```text
259 passed, 6 deselected
```

件数が増減していても通常テストが全件passし、live/expensiveが除外されていればよい。

文書間で次が一致することを確認する。

- retry 2回はRun全体
- substitution 1回もRun全体
- retryとsubstitutionは別枠
- call上限12はTokenBudget reserveが正本
- retry対象はTIMEOUT/RATE_LIMITEDのみ
- hard unavailable errorはRun後続候補から除外
- Synthesizer/Auditorは常に別Agent
- 2 Agent q08型障害を必ず救済するとは書かない
- q03は別課題

## commit前確認

```powershell
git status --short
git diff --check
git diff -- QandA.md SPEC.md CLASS.md SEQUENCE.md STATE.md TESTCASE.md FIX_PLAN.md hikitsugi.md instructions/result.md
```

許可される変更は次だけ。

```text
QandA.md
SPEC.md
CLASS.md
SEQUENCE.md
STATE.md
TESTCASE.md
FIX_PLAN.md
hikitsugi.md
instructions/result.md
```

それ以外の変更があればcommitせず報告する。

## commitとpush

```powershell
git add QandA.md SPEC.md CLASS.md SEQUENCE.md STATE.md TESTCASE.md FIX_PLAN.md hikitsugi.md instructions/result.md
git commit -m "docs: define deterministic agent substitution policy"
git push origin main

git status --short
git rev-parse --short HEAD
git rev-parse --short refs/remotes/origin/main
```

完了条件:

- M-5とS-5の回答が確定
- SPEC、CLASS、SEQUENCE、STATE、TESTCASEに矛盾なく反映
- source/test/config/runner未変更
- 通常テスト全件pass
- `git diff --check`成功
- live未実行
- commit/push成功
- worktree clean
- HEADとorigin/main一致

## 最終報告

次を簡潔に報告する。

1. 作業前HEADと結果commit
2. M-5 / S-5の確定内容
3. retry/substitution/call上限
4. error code別の処理
5. ResponderとSynthesizer/Auditor制約
6. q08型障害を2 Agentでは必ず救済できないこと
7. q03を別課題として維持したこと
8. 更新文書
9. pytestと`git diff --check`
10. live未実行
11. commit/push/clean状態
12. 次作業がM-5/S-5実装、その後L-5、S-8であること
