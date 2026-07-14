# Oracle Council 次作業指示書

> **ローカルPCで開始する前の注意**
> この指示書はGitHub側で更新されている。
> 作業開始前に対象リポジトリのルートで`git status --short`と`git pull --ff-only`を実行し、pull成功後にこのファイルを読んでください。
> 未コミット差分や未追跡ファイルがある場合は、勝手にreset・stash・削除・移動せず、差分を保護して状況を報告してください。

## X-8.18: L-5 フェーズ別構造化出力Schemaの正式化・実装

対象リポジトリ:

```text
C:\PROJECT\OracleCouncil
```

## 目的

X-8.17でM-5 / S-5のExecutionPlanとAgent substitutionを通常実装した。

```text
X-8.17 implementation commit:
217867f273cb376f78eb94bb9f83b8eae68368cb

pytest:
264 passed, 6 deselected
```

次のブロッカーはL-5である。

現状、フェーズ出力の契約が複数箇所へ分散している。

- `CodexAdapter`にはCodexへ渡すphase別JSON Schema相当の定義がある
- `ClaudeAdapter`にはphase別のJSON例・追加制約がある
- `adapters/base.py`の`validate_phase_output()`にはrequired field、型、Enumの独自判定がある
- `AgentRequest`はSPEC上`output_schema`必須だが、現行モデルにはまだ正式フィールドがない

このため、プロンプト、Codexの`--output-schema`、Adapter後段validatorが将来ずれる可能性がある。

X-8.18では、6フェーズの正式JSON Schemaを唯一の構造契約として作成し、AgentRequest、Claude、Codex、共通validatorを同じSchemaへ接続する。

対象フェーズ:

```text
respond
claim_extract
verify
criticize
synthesize
audit
```

今回は通常実装とFake/transport/contractテストだけを行う。実Claude、実Codex、WebSearch、実HTTP、live評価は実行しない。

## 並行作業禁止

X-8.18と次を並行で進めない。

```text
L-3 INVALID_OUTPUT回復・AI再依頼
S-8 processExitCode / oracleExitCode分離
q03 DNS failure-boundary修正
S-9 configured/selected participant多重度
S-10 probe/capability snapshot再設計
Clarifier
Responder並列化
X-8 live評価
```

L-5は出力Schemaの定義・伝達・検証だけを扱う。

- fenced JSONや前後説明の決定的抽出は現行挙動を維持する
- schema不適合は従来どおり`INVALID_OUTPUT`
- `INVALID_OUTPUT`をretry/substitution対象へ追加しない
- AIへ修復を再依頼しない
- call count、retry、substitutionの仕様を変更しない

## 作業前確認

最初に次を読む。

```text
QandA.md                L-3、L-5、M-5
SPEC.md                 §8.3、§8.5、§8.6、§15.5〜§15.8
CLASS.md                AgentRequest、AgentResult、AgentExecution
TESTCASE.md             Adapter Contract、INVALID_OUTPUT、phase schema関連
FIX_PLAN.md
src/oracle_council/models.py
src/oracle_council/orchestrator.py
src/oracle_council/adapters/base.py
src/oracle_council/adapters/claude.py
src/oracle_council/adapters/codex.py
src/oracle_council/fakes.py
src/oracle_council/cli.py
pyproject.toml
既存adapter/schema/transportテスト
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

git merge-base --is-ancestor 217867f HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain X-8.17 implementation commit 217867f." }

git merge-base --is-ancestor 554602d HEAD
if ($LASTEXITCODE -ne 0) { throw "HEAD does not contain M-5/S-5 specification commit 554602d." }
```

合格条件:

- branchが`main`
- `git status --short`が完全に空
- HEADと`refs/remotes/origin/main`が一致
- pull後の作業名が`X-8.18`
- HEADに`217867f`と`554602d`が含まれる

不一致がある場合は実装を開始せず報告する。

## 変更前baseline

```powershell
py -m pytest
git diff --check
git status --short
```

基準:

```text
264 passed, 6 deselected
```

件数が変わっていても、通常テストが全件passし、live/expensiveが除外されていればよい。

## 1. 正式Schemaの保存場所

次のpackage resourceを新設する。

```text
src/oracle_council/schemas/__init__.py
src/oracle_council/schemas/respond.json
src/oracle_council/schemas/claim_extract.json
src/oracle_council/schemas/verify.json
src/oracle_council/schemas/criticize.json
src/oracle_council/schemas/synthesize.json
src/oracle_council/schemas/audit.json
```

加えて、Schemaを読み込み、コピーして返し、検証する共通moduleを追加する。

推奨名:

```text
src/oracle_council/phase_schema.py
```

実装名はPython規約に合わせてよいが、責務を分散させない。

### 1.1 package resource

`importlib.resources`を使い、インストール後もSchemaを読めるようにする。

`pyproject.toml`のpackage-data設定が必要なら追加する。

要件:

- filesystemのカレントディレクトリへ依存しない
- import時に一度だけ読み込んでよい
- 呼び出し側へはdeep copyを返し、共有Schemaを変更させない
- 未知phaseは黙って空Schemaを返さず、固定型の例外または`KeyError`でfail closed
- Schemaファイルの破損・欠落は起動時または最初の取得時に明確に失敗
- user入力、prompt、環境変数、CLI出力をSchemaへ混ぜない

### 1.2 JSON Schema dialect

実CLIとの互換性を優先した、Codex structured outputで扱えるJSON Schema subsetを使用する。

使用してよい主なkeyword:

```text
type
properties
required
additionalProperties
enum
items
minLength
maxLength
minItems
maxItems
```

`$ref`、外部参照、remote schema、任意コード実行につながる仕組みは使用しない。

全objectで次を必須にする。

```json
"additionalProperties": false
```

Schema自体へ秘密情報や実行固有値を入れない。

## 2. 6フェーズの正式Schema

以下を正式契約として実装する。別のfield名・Enumへ変更しない。

### 2.1 respond

```text
object
required: answer
additionalProperties: false

answer:
  type: string
  minLength: 1
  maxLength: 6000
```

### 2.2 claim_extract

```text
object
required: claims
additionalProperties: false

claims:
  type: array
  minItems: 0
  maxItems: 20
  items: ClaimExtraction

ClaimExtraction object:
  required:
    - claim_id
    - importance
    - status
    - claim_role
    - text
  additionalProperties: false

claim_id:
  type: string
  minLength: 1
  maxLength: 128
importance:
  enum: critical | major | minor
status:
  enum: unverified
claim_role:
  enum: user_premise | proposed_answer | contextual
text:
  type: string
  minLength: 1
  maxLength: 1200
```

`claim_extract.status`は初期状態の`unverified`だけを許可する。Verifier前にモデルが`verified`等を確定してはならない。

### 2.3 verify

```text
object
required: claims
additionalProperties: false

claims:
  type: array
  minItems: 0
  maxItems: 20
  items: ClaimVerification

ClaimVerification object:
  required:
    - claim_id
    - importance
    - status
  additionalProperties: false

claim_id:
  type: string
  minLength: 1
  maxLength: 128
importance:
  enum: critical | major | minor
status:
  enum:
    - verified
    - supported
    - contradicted
    - conflicting
    - unverified
    - not_applicable
```

Claim IDの既存Claimとの対応、順序fallback、重複ID等の意味検証は既存Orchestrator責務を維持する。本作業でK-4等を解決しない。

### 2.4 criticize

```text
object
required: critique
additionalProperties: false

critique:
  type: string
  minLength: 1
  maxLength: 6000
```

### 2.5 synthesize

```text
object
required: answer
additionalProperties: false

answer:
  type: string
  minLength: 1
  maxLength: 6000
```

### 2.6 audit

```text
object
required:
  - status
  - issues
additionalProperties: false

status:
  enum: approved | changes_required | blocked
issues:
  type: array
  minItems: 0
  maxItems: 20
  items: AuditIssueOutput

AuditIssueOutput object:
  required:
    - issue_id
    - issue_type
    - severity
    - claim_id
  additionalProperties: false

issue_id:
  type: string
  minLength: 1
  maxLength: 128
issue_type:
  type: string
  minLength: 1
  maxLength: 128
severity:
  enum: critical | major | minor
claim_id:
  type: string
  minLength: 1
  maxLength: 128
```

`approved`ならissuesが空であること等の意味規則は、Schemaへ複雑なconditionalを追加せず、既存audit適用ロジックまたは別のsemantic validatorで扱う。L-5では構造契約を正本化する。

## 3. AgentRequestへoutput_schemaを追加

`src/oracle_council/models.py`の`AgentRequest`へ正式フィールドを追加する。

```text
output_schema: dict[str, Any]
```

要件:

- Orchestratorが各Agent呼び出しを作る時点で、phaseに対応するSchemaのdeep copyを設定
- retryとsubstitutionも同じlogical phase Schemaを持つ
- AdapterがSchemaを変更しても、次Executionやregistryへ影響しない
- request payloadへSchemaを混ぜず、独立fieldにする
- Schemaをstorage eventやCLI JSONへ全文出力しない
- call count、budget、execution_id、retry_of、substitute_forへ影響させない

既存の直接`AgentRequest(...)`を作るunit/contract testは全て更新する。

互換性のための`None`既定や空Schema既定を設けない。phase Schemaなしで実行する経路を残さない。

## 4. 共通validatorをSchema駆動へ変更

`adapters/base.py`の`validate_phase_output()`は、hard-codeされたphase別required/Enum表を正本にしない。

正式Schemaを取得し、そのSchemaに対して決定的に検証する。

### 4.1 外部dependencyを追加しない

今回のSchema keyword subsetは小さいため、新しいthird-party JSON Schema dependencyを追加しない。

`phase_schema.py`内へ必要最小限の再帰validatorを実装してよい。

対応必須keyword:

```text
type
properties
required
additionalProperties
enum
items
minLength
maxLength
minItems
maxItems
```

未対応keywordがSchemaへ入った場合に無視せずfail closedにする。

### 4.2 エラー順序

複数不一致がある場合も、同じ入力には常に同じ最初のエラーを返す。

推奨順:

1. root type
2. required field
3. unexpected field
4. property type
5. enum
6. string length
7. array length
8. array itemをindex順

辞書順へ勝手に依存せず、Schemaの`required`・`properties`記載順を使う。

### 4.3 公開エラーsummary

Schema不適合は`AgentFailure("INVALID_OUTPUT", ...)`を維持する。

`public_summary`は固定・200文字以下・field allowlist付きにする。

既存summaryを壊さない。

```text
malformed JSON
missing field: <field>
invalid enum for field: <field>
invalid type for field: <field>; expected <type>; actual <type>
```

追加してよい固定形式:

```text
unexpected field: <field>
string too short for field: <field>
string too long for field: <field>
too few items for field: <field>
too many items for field: <field>
```

`models.py`の`safe_public_summary()` / `safe_error_summary()`に必要なallowlist・固定patternを追加する。

公開summaryへ次を入れない。

```text
実際のfield値
回答本文
質問本文
prompt
raw stdout/stderr
path
環境変数
token
API key
```

内部例外messageに値を含める場合でもmetadataへ保存しない既存境界を維持する。

## 5. CodexAdapterを正式Schemaへ接続

`CodexAdapter`内のphase別Schema重複定義を削除する。

要件:

- `request.output_schema`をCodexの`--output-schema`用一時JSONへ書く
- 一時ファイルはUTF-8
- user-derived phase入力は引き続きstdin
- Schema file path以外のuser-derived値をargvへ戻さない
- Schema fileは既存finallyで必ず削除
- `additionalProperties: false`は正式Schema側に含め、Adapterだけで別の構造契約を作らない
- `_strict_schema()`を残す場合は、入力Schemaを変更せずdeep copyし、正式Schemaと構造が変わらないことをテストする
- 可能なら不要な変換を削除し、正式Schemaをそのまま書く
- Adapter後段でも同じ正式Schemaでvalidationする

transportテストで一時Schema JSONが`request.output_schema`とdeep-equalであることを確認する。

## 6. ClaudeAdapterを正式Schemaへ接続

`ClaudeAdapter`内の`_PHASE_SCHEMA_HINT`等、field/Enumを重複定義するmapを削除する。

Claudeには正式Schemaをstdin prompt内で明示する。

推奨:

```text
Respond with ONLY one JSON object that validates against this JSON Schema.
<compact JSON serialization of request.output_schema>
```

要件:

- Schema JSONは`json.dumps(..., ensure_ascii=False, separators=(",", ":"), sort_keys=True)`等で決定的に生成
- phase入力とSchemaはstdin
- argvは固定フラグだけ
- Schemaと異なるEnum説明を別途hard-codeしない
- false-premise guidance等、Schema以外の既存semantic guidanceは維持してよい
- CLI envelope抽出とphase JSON抽出の現行挙動を維持
- 抽出後は共通Schema validatorを通す

Claude transportテストで、全6phaseの正式Schemaがpromptへ入り、旧重複定義がないことを確認する。

## 7. FakeAdapter・Orchestratorとの整合

Fake出力を全て正式Schemaへ適合させる。

特に:

- `claim_extract`は5 required fieldを全て返す
- `claim_extract.status`は`unverified`
- `audit`は`issues`を常に返す
- issueを返す場合は4 required fieldを全て返す

Orchestrator適用側の既存意味を変えない。

- claim merge規則を変更しない
- classification規則を変更しない
- audit revision回数を変更しない
- M-5 retry/substitutionを変更しない
- Schema不適合`INVALID_OUTPUT`はsubstitutionしない

## 8. 正式Contractテスト

新規test moduleを作ってよい。

推奨名:

```text
tests/unit/test_phase_schema.py
```

最低限、次をテストする。

### 8.1 Schema resource

- 6ファイルがpackage resourceとして取得できる
- JSONとしてparseできる
- rootはobject Schema
- 全object nodeで`additionalProperties=false`
- 未知phaseはfail closed
- 取得結果を変更しても次の取得結果が変わらない
- package cwd外から取得できる

### 8.2 valid fixture

6phaseの最小valid fixtureが通る。

- empty claimsはclaim_extract/verifyでvalid
- approved + empty issuesはauditでvalid
- changes_required + 1 issueはvalid
- 日本語、Unicodeを含むanswer/text/critiqueがvalid

### 8.3 invalid fixture

各phaseで最低限確認する。

- root array/string/null
- required欠落
- extra property
- wrong type
- Enum外
- empty string
- maxLength超過
- maxItems超過
- nested itemのrequired欠落

全て`INVALID_OUTPUT`となり、公開summaryは固定形式でraw値を含まない。

### 8.4 phase固有

- claim_extract status=`verified`を拒否
- claim_extract importance=`high`を拒否
- claim_extract claim_role Enum外を拒否
- verifyの6 statusは全て許可
- audit status Enum外を拒否
- audit issue severity Enum外を拒否

### 8.5 Adapter統合

- Codexがrequest Schemaを一時ファイルへdeep-equalで渡す
- Claudeがrequest Schemaをstdin promptへ含める
- Claude/Codexの正常出力が同じvalidatorを通る
- 一方のAdapterだけが許可するfield/Enumが存在しない
- schema不適合はAdapter境界で`INVALID_OUTPUT`
- Schemaや入力がargvへ漏れない
- temp Schema file cleanupを維持

### 8.6 AgentRequest

- Orchestratorが全6phaseへ正しいSchemaを設定
- respond slot 0/1は同じrespond Schemaだが別dict instance
- retry requestは同じ構造Schema・別dict instance
- substitution requestも同じ構造Schema・別dict instance
- Adapterによるrequest Schema変更がregistryへ影響しない

## 9. 文書更新

### QandA.md

L-5を確定回答へ変更する。

最低限記録:

- 6phaseの正式Schemaをpackage resourceとして保持
- AgentRequest.output_schema必須
- Claude prompt、Codex output-schema、共通validatorが同一Schemaを使用
- all object closed
- field、Enum、件数、文字数上限
- schema不適合はINVALID_OUTPUT
- L-3の回復方針は未回答のまま

### SPEC.md

- 文書versionを次版へ更新
- §8.5へAgentRequest.output_schemaと正式Schema registryを反映
- phase別Schemaを付録または表として記録
- Schema source pathを明記
- `INVALID_OUTPUT`回復はL-3へ残す

### CLASS.md

- AgentRequestへoutputSchemaを反映
- PhaseSchemaRegistryまたは同等責務を追加
- Claude/Codexが同じSchemaを参照する依存を表現

### TESTCASE.md

- L-5起因BLOCKEDを解除
- 6phase Schema Contract Testを正式ケース化
- schema drift、closed object、Unicode、境界長、extra fieldを含める
- L-3依存ケースはBLOCKEDを維持

### FIX_PLAN.md

- L-5を仕様・通常実装・Fake/Contractテスト完了側へ移す
- 次作業をS-8とする
- q03、S-9/S-10、L-3は未解決のまま

### hikitsugi.md / instructions/result.md

X-8.18として次を記録する。

- 実行前HEAD
- 正式Schema保存場所
- 6phaseのfield/Enum/上限
- AgentRequest.output_schema
- Claude/Codex/common validator統合
- driftテスト
- pytest / diff check
- live未実行
- 次はS-8

## 10. 変更を許可する範囲

最低限想定:

```text
src/oracle_council/schemas/__init__.py
src/oracle_council/schemas/*.json
src/oracle_council/phase_schema.py
src/oracle_council/models.py
src/oracle_council/orchestrator.py
src/oracle_council/adapters/base.py
src/oracle_council/adapters/claude.py
src/oracle_council/adapters/codex.py
src/oracle_council/fakes.py
src/oracle_council/cli.py                 # AgentRequest等の影響が必要な場合だけ
pyproject.toml                            # package-dataが必要な場合だけ
tests/unit/test_phase_schema.py
既存adapter/orchestrator/transport test
QandA.md
SPEC.md
CLASS.md
TESTCASE.md
FIX_PLAN.md
hikitsugi.md
instructions/result.md
```

`STATE.md`、`SEQUENCE.md`はL-5の説明に本当に必要な最小変更だけ許可する。状態遷移自体は変更しない。

## 11. 変更禁止

次を変更しない。

```text
config/agents.yaml
evaluation/
scripts/x8*
既存評価artifact
TokenBudgetの上限
retry/substitution error code表
Run/Phase終端規則
classification規則
Evidence判定規則
SafeHttpFetcher / WebEvidenceProvider
```

実行禁止:

```text
claude
codex
WebSearch
実HTTP
ORACLE_COUNCIL_LIVE=1
live / expensive pytest
q01〜q08評価
```

## 12. 検証

まずtargeted testを実行する。

例:

```powershell
py -m pytest tests/unit/test_phase_schema.py
py -m pytest tests/unit/test_claude_transport.py tests/unit/test_codex_transport.py
py -m pytest tests/unit/test_orchestrator.py
```

実在するtest file名へ合わせること。存在しない名前をそのまま実行しない。

その後:

```powershell
py -m pytest
git diff --check
git status --short
```

基準:

```text
変更前: 264 passed, 6 deselected
変更後: 通常テスト全件pass
live/expensive: 未実行・deselected
```

次を明示確認する。

- 6 Schemaが唯一の構造契約
- Claude/Codex/base validator間のfield/Enum driftなし
- all objectでadditionalProperties=false
- AgentRequest.output_schemaが全Executionに設定
- retry/substitutionでも同じphase Schema
- Schema instance共有によるmutationなし
- INVALID_OUTPUTの公開summaryにraw値なし
- user-derived入力はstdinのまま
- Codex temp fileはSchemaだけ
- live実行なし

## 13. commit前確認

```powershell
git status --short
git diff --check
git diff --stat
git diff
```

次を確認する。

- evaluation、config、live artifactに変更なし
- L-3、S-8、q03へ無関係な変更なし
- Schemaのfield/Enum/上限が文書とコードで一致
- Claude/Codex独自のphase schema mapが残っていない
- raw prompt/stdout/stderrをテストfixture以外へ保存していない

## 14. commitとpush

全条件を満たした場合だけcommit/pushする。

推奨commit message:

```text
feat: centralize phase output schemas
```

```powershell
git add src tests pyproject.toml QandA.md SPEC.md CLASS.md TESTCASE.md FIX_PLAN.md hikitsugi.md instructions/result.md

git status --short
git diff --cached --check
git diff --cached --stat

git commit -m "feat: centralize phase output schemas"
git push origin main

git status --short
git rev-parse HEAD
git rev-parse refs/remotes/origin/main
```

存在しない新規pathや、変更していない`pyproject.toml`を無理にaddする必要はない。

完了条件:

- L-5の回答が確定
- 6phase正式Schemaがpackage resourceとして存在
- AgentRequest.output_schema必須化
- Claude/Codex/common validatorが同一Schemaを使用
- hard-codeされた重複phase schema定義を除去
- Schema Contract Testが全件pass
- 通常pytest全件pass
- `git diff --check`成功
- 実CLI/live/HTTP未実行
- commit/push成功
- worktree clean
- HEADとorigin/main一致
- 次作業がS-8と明記

## 最終報告

`instructions/result.md`へ記録し、ユーザーへ次を報告する。

1. 実行前HEAD
2. commit SHA
3. 追加したSchema file一覧
4. 6phaseの正式field/Enum/上限要約
5. AgentRequest.output_schemaの実装内容
6. Claude/Codex/common validatorの統合内容
7. 削除した重複Schema定義
8. targeted test結果
9. 全pytest結果
10. `git diff --check`結果
11. 変更file一覧
12. live/実CLI/実HTTP未実行
13. L-3、S-8、q03、S-9/S-10の未解決維持
14. commit/push/clean/HEAD同期結果
15. 次はS-8
