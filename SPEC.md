# Oracle Council 仕様書

- 文書バージョン: 0.3.7
- ステータス: MVP設計方針確定版
- 対象: MVP（Minimum Viable Product）
- リポジトリ: `garyohosu/OracleCouncil`
- 最終更新: 2026-07-10

## 1. 概要

Oracle Councilは、ユーザーの質問をそのまま1つのAIへ渡すのではなく、次の工程を自動化するAIオーケストレーターである。

1. 不完全・曖昧・誤った前提を含む質問を整理する
2. 既定2つ、設定上最大4つのAI CLIへ独立して回答させる
3. 回答から検証対象となるClaimを抽出する
4. Oracle Council自身が外部Evidenceを収集・照合する
5. 1つのAIがEvidenceを参照しながら全回答を批評する
6. 根拠を優先して最終回答を統合する
7. 別のAIが最終回答を監査する
8. 監査状況、検証状況、不確実な点をユーザーへ示す

表向きの価値は「AI同士が会議すること」ではなく、次の一点に置く。

> 質問を入力するだけで、AIの間違いと質問の曖昧さを自動確認し、根拠のある回答を返す。

ただし、Oracle Councilは「ハルシネーションが絶対に発生しない」とは保証しない。情報源自体の誤り、未公開情報、取得不能、解釈の違いなどは残るため、確認できない内容を無理に断定しないことを重視する。

## 2. 基本方針

### 2.1 多数決を真実とみなさない

複数のAIが同じ回答をしても、同じ誤情報を共有している可能性がある。AI間の一致は参考情報とし、外部根拠との一致を優先する。

優先順位は次のとおりとする。

1. 一次資料・公式資料による裏付け
2. 複数の信頼できる独立資料による裏付け
3. Evidenceと回答の論理的な整合性
4. AI間の論理的な整合性
5. AIの多数意見

### 2.2 分からない場合は保留できる

根拠が不足している場合、情報源が競合する場合、または重大な反対意見を解消できない場合は、次のいずれかで返す。

- `verified`: 検証済み
- `partially_verified`: 一部検証済み
- `unverified`: 未確認
- `conflicting`: 情報が競合
- `withheld`: 回答保留

### 2.3 内部は複雑でも操作は簡単にする

一般ユーザーには質問入力欄と最終回答を中心に見せる。AIごとの回答、批評、投票、Evidence一覧などは「検証の詳細」として任意表示にする。

### 2.4 AI CLIと検索機能を交換可能にする

特定のAIサービスや検索サービスへ強く依存しない。AI CLIは`AgentAdapter`、Evidence収集は`EvidenceProvider`として分離する。

### 2.5 暗黙の機能縮退を行わない

`verify`または`strict`でEvidence収集が利用できない場合、外部検証済みであるかのように回答してはならない。処理を停止するか、ユーザーが明示的に`quick`へ切り替える。

## 3. MVPの目標

- Claude CodeとCodex CLIを公式サポートし、既定2 Agent、設定上最大4 Agentを並列実行できる
- AIごとの利用可否、タイムアウト、利用上限を判定できる
- 不完全な質問に対して必要な場合だけ追加質問できる
- 各AIが他の回答を見ずに独立回答できる
- 回答から検証対象となるClaimを抽出できる
- Oracle Council側でEvidenceを収集し、Claimと紐付けられる
- Evidenceを参照した統合批評を1 Agentで実行できる
- 根拠のある主張を優先して最終回答を生成できる
- 最終回答を別Agentが監査できる
- 監査状況と検証状況を分けて表示できる
- 内容を含まない実行メタデータをRun単位のJSONLへ保存できる
- 主要な処理をJSON出力で外部連携できる

## 4. MVPの対象外

- ハルシネーション完全ゼロの保証
- AIの内部思考過程や非公開Chain of Thoughtの取得・表示
- AIが生成した任意のシェルコマンドの自動実行
- 医療、法律、金融分野における専門家判断の代替
- すべての有料AI CLIの利用枠を一元管理する機能
- 自律的に長時間動き続ける無制限討論
- SQLiteバックエンド
- 本格的なWeb UI
- AI CLI組み込み検索だけを根拠とする検証
- 3つ目以降の公式サポートCLI
- 全Agentによる批評、Voter、Quorum、再投票
- JavaScriptレンダリング、PDF、OCR、paywall資料のEvidence取得
- 中断Runの再開
- OSレベルの強制sandbox

## 5. 用語

- **Agent**: Oracle Councilから呼び出されるAI CLI
- **Council**: その実行で参加可能なAgentの集合
- **Clarifier**: 質問の不足、曖昧さ、前提を検査する役割
- **Responder**: 独立回答を作る役割
- **Claim Extractor**: 回答を検証可能なClaimへ分解する役割
- **Critic**: 回答の矛盾、誤り、弱点を指摘する役割
- **Verifier**: ClaimとEvidenceの対応を判定する役割
- **Synthesizer**: 回答、Evidence、批評を統合して最終回答案を作る役割
- **Auditor**: 最終回答案に未解決の問題がないか監査する役割
- **Voter**: 監査後の最終案を承認または否認する役割
- **Claim**: 真偽を確認可能な最小単位の事実主張
- **Evidence**: Claimを支持または否定する外部資料
- **EvidenceProvider**: 外部資料を検索・取得する交換可能な機能
- **Quorum**: 合意判定に必要な参加Agent数

## 6. アーキテクチャと役割分担

### 6.1 基本構成

```text
CLI
 └─ Orchestrator
     ├─ Clarification Engine
     ├─ Agent Adapters
     ├─ Claim Pipeline
     ├─ Evidence Providers
     ├─ Verification Engine
     ├─ Consensus Engine
     └─ JSONL Storage
```

### 6.2 役割は「Agentの職種」ではなく「フェーズ」

Claudeを常にCritic、Geminiを常にVerifierとするような固定割り当ては行わない。役割は実行フェーズごとにOrchestratorが決定する。

選定はランダムではなく、次を用いた決定的なルールとする。

1. Agentが利用可能である
2. 設定ファイルの`role_priority`に適合する
3. 必要な出力形式やコンテキスト長を扱える
4. 同点の場合は設定順
5. SynthesizerとAuditorは可能な限り別Agentにする

同じ設定、同じ利用可能Agent集合であれば、原則として同じ選定結果になる。

### 6.3 MVPの担当方式

- **Clarifier**: 決定的ルールで不足を判定できない場合だけ1 Agent
- **Responder**: 異なる2 Agent
- **Claim Extractor**: 1 Agent
- **Evidence収集**: Oracle CouncilのEvidenceProvider
- **Verifier**: 1 Agent
- **Critic**: 1 Agent
- **Synthesizer**: 1 Agent
- **Auditor**: Synthesizerとは別の1 Agent

Criticは匿名化された全回答、Claim、Evidenceを受け取り、1回の呼び出しで統合批評を返す。Voter、Quorum、再投票はMVP対象外とし、Auditorの判定を公開可否のゲートにする。

重要度`critical`のClaimは、Verifierの判定に加えてAuditorが再確認する。

`verify`のAI呼び出しは通常7回、Clarifierを含め8回、修正を含め10回を上限とする。一時エラーの再試行はRun全体で2回、同一Executionで1回までとし、再試行を含む絶対上限は12回とする。差分スキャン、コンテキスト縮約、Evidence収集はAI呼び出しに数えない決定的なローカル処理とする。

### 6.4 参加Agentが少ない場合

- 2 Agent以上: 異なる2 AgentをResponderに選び、通常フローを実行する
- 1 Agent以下: 独立回答と別Agent監査を満たせないため回答不能

SynthesizerとAuditorは異なる`agent_id`とする。可能なら異なる`adapter_family`を選ぶ。Auditorを確保できない場合は回答を公開しない。

### 6.5 フェーズ間の汚染対策

各フェーズは原則として新しいCLIプロセスまたは新しいセッションで実行する。前フェーズの会話履歴を自動継承しない。

各Agentへ渡す情報はフェーズごとに明示的に構成し、次のみに制限する。

- 整理後の質問
- 匿名化された回答
- 構造化されたClaim
- 構造化されたEvidence抜粋
- 前フェーズの説明可能な要約

非公開の内部思考過程、不要な会話履歴、他Agent名は渡さない。

## 7. 質問整理エンジン

### 7.1 目的

ユーザーに完全なプロンプト作成を要求せず、雑な質問から回答可能な質問へ整える。既存の「対話型プロンプトメーカー」で採用した反復型の対話設計を参考にするが、必要以上に聞き返さない。

### 7.2 判定ステータス

- `ready`: 追加情報なしで回答可能
- `ready_with_assumptions`: 仮定を明示すれば回答可能
- `needs_clarification`: 不足情報により結論が大きく変わる
- `premise_issue`: 誤りまたは未確認の前提を含む
- `unsupported`: 現在の機能では適切に処理できない
- `safety_blocked`: 安全上の理由で処理できない

### 7.3 追加質問の条件

次のいずれかに該当する場合のみ追加質問を行う。

- 不足情報により結論が逆転する
- 対象、期間、地域、目的を複数通りに解釈できる
- 医療、法律、金融、安全など高リスク分野である
- 推奨内容が予算や用途によって大きく変わる
- 誤った前提を受け入れると誤解を拡大する

### 7.4 対話ルール

- 一度に提示する質問は最大3問
- MVPでは追加質問を最大2ラウンドとする
- 選択肢で回答可能な場合は選択肢を優先する
- 回答に必須でない好みは仮定として明示して進める
- ユーザーはいつでも「この条件で進める」を選べる
- 整理後の質問と仮定を確認可能にする

### 7.5 非対話モードの仮定生成

`--no-interactive`では次の順に仮定を決める。

1. 地域、通貨、日時などの決定的な規定値
2. 質問種別ごとのテンプレート規則
3. Clarifier Agentによる構造化された仮定案

次の場合は自動仮定せず、終了コード`2`で`needs_clarification`を返す。

- 結論が逆転する不足情報
- 医療、法律、金融、安全に関わる重要条件
- 個人を特定する必要がある質問
- Clarifierが`importance: critical`とした不足情報

AIが生成した仮定は実行記録へ保存する。完全な再現性は保証しないが、同じテンプレート、低いランダム性、対応CLIでのseed指定を用いて変動を抑える。

## 8. Agent管理

### 8.1 設定例

```yaml
agents:
  - id: claude
    adapter: claude
    enabled: true
    role_priority:
      synthesize: 100
      audit: 80

  - id: codex
    adapter: codex
    enabled: true
    role_priority:
      claim_extract: 90
      verify: 90

  - id: gemini
    adapter: gemini
    enabled: false

  - id: agent4
    adapter: custom
    enabled: false
```

既定で有効にするのは公式サポートの2 Agentのみとし、3つ目以降は利用者が明示的に有効化する。

### 8.2 Agent状態

- `OK`
- `AUTH_REQUIRED`
- `QUOTA_EXCEEDED`
- `RATE_LIMITED`
- `TIMEOUT`
- `CONTEXT_OVERFLOW`
- `INVALID_OUTPUT`
- `COMMAND_NOT_FOUND`
- `UNSUPPORTED_VERSION`
- `UNSAFE_CAPABILITY`
- `CANCELLED`
- `EXECUTION_ERROR`

### 8.3 再試行

- 利用枠超過、認証切れ、CLI未導入は再試行しない
- 一時的なタイムアウトとレート制限は同一Executionにつき最大1回のみ再試行できる
- 再試行は新しいAgentExecutionを作り、`retry_of`で元Executionを参照する
- Run全体の再試行は2回、全AI呼び出しは12回を絶対上限とする
- コンテキスト超過は決定的縮約を1回適用し、収まらなければ`BUDGET_EXCEEDED`で終了する
- 無限再試行は禁止する
- 失敗後の代替Agent選定は`role_priority`順で1回だけ許可する

### 8.4 タイムアウト

タイムアウトはAgent単位とフェーズ単位の両方を持つ。

既定値:

| モード | 1 Agent・1呼び出し | 1フェーズ全体 | 1実行全体 |
|---|---:|---:|---:|
| `quick` | 90秒 | 120秒 | 5分 |
| `verify` | 180秒 | 240秒 | 10分 |
| `strict` | 300秒 | 420秒 | 20分 |

- Agent単位タイムアウトで該当Agentを`TIMEOUT`にする
- フェーズ単位タイムアウトで未完了Agentを棄権扱いにする
- 全体タイムアウトで`partial`または`failed`として終了する
- 値は設定ファイルとCLIオプションで変更可能にする

### 8.5 AgentAdapter Contract

```python
class AgentAdapter(Protocol):
    async def probe(self) -> ProbeResult: ...
    def capabilities(self) -> AgentCapabilities: ...
    async def execute(self, request: AgentRequest) -> AgentResult: ...
    async def cancel(self, execution_id: str) -> None: ...
```

`AgentRequest`は`execution_id`、`phase`、`system_instructions`、`input`、`output_schema`、`timeout_ms`、`max_output_tokens`、`working_directory`を必須とする。

`AgentCapabilities`は次を持つ。

- `adapter_family`
- `adapter_version`
- `cli_version`
- `supported_phases`
- `structured_output`
- `max_context_tokens`
- `supports_seed`
- `supports_read_only`
- `supports_no_tools`

`AgentResult`は`status`、`structured_output`、`raw_output_hash`、`usage`、`exit_code`、`started_at`、`finished_at`、`error_code`、`error_summary`を持つ。入力はUTF-8のstdinまたはAdapter管理の一時ファイルを使う。stdoutは結果、stderrは診断専用とし、Orchestratorへ返す前にschema検証とsecret redactionを行う。

未知のCLIバージョン、`supports_no_tools=false`、`supports_read_only=false`、schema不適合はfail closedとする。`custom` AdapterはPython entry pointで登録し、Adapter Contract Testに合格したものだけを読み込む。MVPで公式サポートするのはClaude CodeとCodex CLIの2種類とする。

### 8.6 トークン予算と縮約

共通推定式を次とする。

```text
estimated_tokens = max(Unicode code point数, ceil(UTF-8 byte数 / 4))
```

- 1 AgentExecution: 入力12,000推定tokenを目標、16,000を絶対上限、出力4,000推定token
- 1 Run: 入力96,000、出力24,000推定token
- CLIが返すusageは記録用とし、予算判定には共通推定値を使う
- Run残出力予算が4,000未満なら新しいExecutionを開始しない

1つのフェーズへ全情報を渡さず、フェーズごとに入力を正規化する。

- Responderの構造化回答は6,000文字を上限とする
- VerifierへはClaim単位でEvidence抜粋を渡す。1件1,200文字、1 Claimあたり2件を上限とする
- CriticとSynthesizerへ渡す各回答は最大3,000文字へ正規化する
- CriticとSynthesizerへ渡すEvidence抜粋は1件最大500文字とし、`content_hash`で重複除去した後、Run全体で最大8件とする
- CriticとSynthesizerへ渡すClaimは`critical`と`major`だけとし、`minor` ClaimはVerifierの判定結果のみを渡す

正規化後も上限を超える場合、AIを呼ばず次の順で削る。回答の要約より先にEvidenceを削る。

1. `content_hash`が同じEvidenceを除去する
2. HTML等の非本文を除去する
3. Evidence件数を減らす。importanceの低いClaimに紐づくEvidenceから除去する
4. `major` Claimをimportance、回答内出現数、claim_idの順で残す
5. 回答の正規化上限を3,000文字から2,000文字へ下げる

`critical` Claimとその反証Evidenceは削除しない。上限内に収まらなければ`BUDGET_EXCEEDED`とする。

### 8.7 TokenBudget Contract

`TokenBudget`はRun単位で生成し、推定入力token、推定出力token、AI呼び出し回数を同じ排他制御下で予約・精算する。公開メソッドは次とする。

- `reserve(request: BudgetRequest) -> BudgetReservation | BudgetExceededError`
- `commit(reservation_id, actual_usage: Usage | null) -> BudgetReservation`
- `release(reservation_id) -> BudgetReservation`
- `snapshot() -> BudgetSnapshot`

`BudgetReservation`の正式フィールドは`reservation_id`、`run_id`、`execution_id`、`phase`、`estimated_input_tokens`、`estimated_output_tokens`、`reserved_call_count`（常に1）、`status`（`reserved` / `committed` / `released`）、`actual_input_tokens`、`actual_output_tokens`、`created_at`、`finished_at`とする。

`reserve`は入力・出力・call countの「committed済み＋reserved中＋今回要求」が各上限以下の場合だけ成功する。判定と予約追加は単一のlock/transaction内で原子的に行う。上限不足時は予約を作らず`BudgetExceededError`を返す。12回上限も同じ予約処理で判定し、別カウンタとの競合を作らない。

予約の所有者はOrchestratorとし、各Executionについて必ず次のどちらかを呼ぶ。

- 子CLIプロセスの生成前に中止、起動失敗、cancelされた場合: `release`
- 子CLIプロセス生成後に成功、失敗、timeout、cancelとなった場合: `commit`

usage不明のtimeout・強制終了は`actual_usage=null`で`commit`し、予約した推定量を予算消費量として維持する。usageが得られた場合も、予算判定用の消費量は予約した推定量で確定し、実測値は観測情報として別フィールドへ記録する。実測値で過去の予算判定を遡及変更しない。

retryと代替Agent実行は必ず別の`execution_id`と別の`BudgetReservation`を作る。元予約を再利用しない。`committed -> released`、`released -> committed`は禁止する。同じ終端操作の再呼び出しは状態と数値を変えず同じ結果を返す冪等動作とし、異なる終端操作は`InvalidReservationTransition`を返す。

存在しない`reservation_id`は`ReservationNotFound`を返す。同一commitを異なる`actual_usage`で再呼び出しても初回結果を変更せず、初回の`actual_usage`を返す。Run終端時に`reserved`を残してはならず、Orchestratorはfinally相当の処理で全Reservationが`committed`または`released`であることをassertする。

## 9. 評議会の処理フロー

### 9.1 基本フロー

```text
ユーザーが質問
  ↓
質問整理・前提検査
  ↓
2 Responderが独立回答
  ↓
決定的な回答差分スキャン
  ↓
Claim抽出と重要度判定
  ↓
EvidenceProviderによる検索・取得
  ↓
VerifierによるClaim判定
  ↓
1 CriticがEvidence参照付き統合批評
  ↓
Synthesizerが最終回答案を作成
  ↓
Auditorが重大問題を監査
  ↓
必要なら1回だけ修正・再監査
  ↓
回答・検証状況・未確認事項を表示
```

### 9.2 独立回答

各Agentは他Agentの回答を見ずに回答する。

各回答には可能な範囲で次を含める。

- 結論
- 結論の理由
- 前提
- 事実として確認が必要な主張
- 不確実な点
- 参照した資料

### 9.3 匿名化

批評、統合、投票時は、モデル名ではなく`Answer A`、`Answer B`のような識別子を使用する。

### 9.4 批評

Criticは、§8.6で正規化された入力（匿名化された全回答、`critical`と`major`のClaim、重複除去済みEvidence抜粋、`minor` ClaimのVerifier判定結果）を1回の入力で受け取り、次を確認する。

- 回答間の矛盾
- 日付、数字、固有名詞の不一致
- Evidenceと矛盾する記述
- 根拠のない断定
- 質問の前提を無批判に受け入れていないか
- 論理の飛躍
- 古い可能性のある情報
- 引用と出典の不一致
- 重要な条件の見落とし

討論はMVPでは1回とする。Auditorが`changes_required`を返した場合のみ、統合案の修正と再監査を1回許可する。

## 10. Evidence収集とハルシネーション対策

### 10.1 Evidence収集の責任範囲

Oracle Council自身の`EvidenceProvider`をEvidence収集の正本とする。

AI CLIの組み込み検索結果は補助情報として利用できるが、次を満たさない限り`verified`の根拠には数えない。

- URLまたは一意な資料識別子を取得できる
- Oracle Councilが資料へ直接アクセスできる
- Claimに対応する箇所を取得できる
- 取得日時と資料メタデータを記録できる

### 10.2 EvidenceProvider

MVPでは交換可能なインターフェースを先に実装する。

```python
class EvidenceProvider(Protocol):
    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        ...

    async def fetch(self, result: SearchResult) -> EvidenceDocument:
        ...
```

最低限、次のProviderを想定する。

- `none`: 外部検索なし。`quick`専用
- `web`: 外部検索APIまたは検索コマンド
- `manual`: テスト用の固定Evidence

最初に採用する実検索サービスは設定可能にし、サービス固有コードをOrchestratorへ埋め込まない。

取得の依存方向は`Orchestrator → EvidenceProvider → SafeHttpFetcher`とする。`web`の`fetch()`はDIされた`SafeHttpFetcher`へ必ず委譲し、HTTPクライアントを直接保持してよいのは`SafeHttpFetcher`だけとする。OrchestratorはEvidenceProvider以外のHTTP取得機能を参照しない。`manual`の`fetch()`は固定資料を返し、`none`の`search()`は空を返す。`none`の`fetch()`は通常呼ばれず、呼ばれた場合は型付き例外を送出する。直接HTTP接続がないことは、SafeHttpFetcherへの委譲確認、socketモックによる直接通信検査、アーキテクチャルールの静的検査を組み合わせたContract Testで確認する。

MVPでは`critical`と`major`を合わせて最大5 Claimを、importance、claim_idの順で検索する。

- 1 Claim: 中立クエリ1回、反証クエリ1回、各上位5結果、fetch成功3文書
- 1 Run: 検索10回、fetch 12文書、展開後本文24MB、Evidence 10件、Evidence処理90秒
- 1文書: 展開後2MB
- 1 Evidence抜粋: 1,200文字

中立検索で`verified`相当になっても、反証検索を1回実行してから確定する。Claimは`verified`または`contradicted`確定、2クエリ消費、fetch成功3件、Run上限、90秒のいずれかで停止する。検索回数、fetch数、文書量、Evidence件数の収集上限到達時は`EvidenceErrorCode.BUDGET_EXHAUSTED`、90秒の時間上限到達時は`EvidenceErrorCode.EVIDENCE_TIMEOUT`を記録する。いずれも一部Claimを処理済みならPhaseは`degraded`、EvidenceOutcomeは`partial_evidence`、未処理Claimは`unverified`とする。`critical`が`unverified`なら回答を`withheld`とする。

### 10.3 Claim抽出

特に次を優先して抽出する。

- 人名、組織名、製品名
- 日付、数量、価格、割合
- 法律、制度、規格
- 「最初」「最大」「唯一」などの比較・最上級表現
- 科学的・医学的効果
- 引用文
- 現在の役職、価格、仕様、提供条件

### 10.4 Claim重要度

`importance`は次のEnumとする。

- `critical`: 誤りが安全、健康、法律、重大な金銭損失に直結する
- `major`: 質問への中心的な結論を構成する
- `minor`: 補足説明や細部である

「主要Claim」は`critical`または`major`を指す。

Claim Extractorが初期値を提案し、VerifierがEvidenceとの関係を踏まえて確定する。Auditorは重要度の誤判定を指摘できる。

### 10.5 Claim状態

- `verified`: 高品質な根拠で確認できた
- `supported`: 有力な根拠があるが完全な確認ではない
- `contradicted`: 信頼できる根拠と矛盾する
- `conflicting`: 信頼できる資料同士が競合する
- `unverified`: 確認できない
- `not_applicable`: 意見、提案、創作など事実検証の対象外

Evidenceは次のEnumで分類する。

- `authority`: `primary_authoritative` / `official_subject` / `independent_expert` / `reputable_secondary` / `other`
- `directness`: `direct` / `indirect`
- `stance`: `supports` / `contradicts` / `neutral`
- `freshness`: `current` / `stale` / `unknown`

独立資料と数えるのはregistrable domainと原資料IDが両方異なる場合だけとし、転載は同一資料とする。

状態はOrchestratorが次の規則で決定する。

- `verified`: `direct`かつ`current`で、`primary_authoritative` 1件、または相互独立な`independent_expert`以上2件が支持し、同等以上の反証が0件
- `supported`: `direct`かつ`current`の`official_subject`、`independent_expert`、`reputable_secondary`が1件以上支持し、同等以上の反証が0件だが`verified`条件を満たさない
- `conflicting`: 同等以上の支持と反証が各1件以上
- `contradicted`: 反証側だけが`verified`条件を満たす
- `unverified`: 上記以外

`official_subject` 1件だけで`verified`にできるのは、発売日、価格、提供条件など当事者が正本となる事実だけとし、効果、安全性、優位性には適用しない。VerifierはEvidence分類を構造化出力し、Claim状態を自由判断しない。

鮮度期限は価格・在庫24時間、現職・サービス状態7日、製品仕様・提供条件30日とする。法令は施行日と取得日における有効性を確認する。その他は期限なしとする。時点依存資料で`published_at`が不明なら`freshness: unknown`とし、`verified`に使わない。

### 10.6 Evidence情報

```json
{
  "evidence_id": "evidence-001",
  "claim_id": "claim-001",
  "url": "https://example.com/source",
  "title": "Source title",
  "publisher": "Publisher",
  "published_at": "2026-01-01",
  "retrieved_at": "2026-07-10T12:00:00+09:00",
  "authority": "primary_authoritative",
  "directness": "direct",
  "stance": "supports",
  "freshness": "current",
  "excerpt": "Claimに対応する短い抜粋",
  "content_hash": "sha256:...",
  "notes": "Claimを直接裏付ける"
}
```

### 10.7 情報源の優先順位

1. 法令本文、官公庁、規格本文、原著論文、公式仕様などの一次資料
2. 大学、公的機関、専門学会、企業公式発表
3. 信頼できる報道・専門媒体
4. 一般解説記事
5. 個人ブログ、SNS、掲示板

下位資料しか存在しない場合は、そのことを明示する。

### 10.8 出典確認

URLが存在するだけでは根拠とみなさない。

- ページへアクセスできるか
- Claimに対応する内容が実際に記載されているか
- 発行日または更新日は適切か
- 引用文が原文と一致するか
- 二次資料が一次資料を正しく参照しているか
- 同じ情報の転載を複数の独立資料として数えていないか

### 10.9 最終回答への反映

- `verified`: 通常文として使用可能
- `supported`: 断定を弱めて使用する
- `conflicting`: 複数説として示す
- `unverified`: 原則削除するか未確認と明示する
- `contradicted`: 採用しない
- 引用: 原文一致を確認できない限り引用符付きで使用しない

## 11. 監査ゲート

### 11.1 MVPの判定方式

MVPではVoter、Quorum、再投票を実行しない。`consensus_status`は常に`not_applicable`とし、次を別々に表示する。

- `audit_status`: `approved` / `changes_required` / `blocked`
- `result_classification`: Claimの検証状態
- `verified_claims / total_claims`

AuditorはSynthesizerとは異なる`agent_id`を使う。`approved`だけを回答公開可能とする。監査結果ごとの遷移は次とする。

- 初回`approved`: そのまま公開して完了する
- 初回`changes_required`: Synthesizerを1回だけ再実行し、同じAuditorで再監査する。再監査は1回だけ
- 再監査`approved`: 公開可能
- 再監査`changes_required`または`blocked`: `withheld`とする。`final_answer`は公開せず、§11.5の開示範囲だけを返す。Runは`completed`、終了コードは4
- 初回`blocked`: 修正フェーズへ進まず、即`withheld`とする（同上）
- Auditorを確保できない場合: Runを`failed`とする（実行環境の問題であり保留ではない）

修正と再監査はAI呼び出し2回を追加する（通常7回→9回、Clarifier込みで最大10回）。一時エラーの再試行はこれとは別枠で数え、絶対上限12回は変わらない。修正フローでは`revision_started`、`synthesis_revised`、`reaudit_started`、`reaudit_completed`をイベントとして記録する。AuditIssueは初回監査で`open`として作成し、再監査で解消が確認されたものだけを`resolved`へ遷移させる。解消されないIssueは`open`のまま残す。

### 11.2 Critical Issue

`critical_issue`はAgentが自由文だけで決める値ではなく、構造化された`issues`からOrchestratorが導出する。

次のいずれかが未解決ならCritical Issueとする。

- `critical` Claimが`contradicted`または`unverified`
- 中心結論を構成する`major` Claimが`contradicted`
- 捏造または内容不一致の引用・出典
- 質問の誤った前提をそのまま採用
- 安全、法律、重大な金銭損失につながる欠落
- 最終回答内部の致命的な論理矛盾
- Evidence由来のプロンプトインジェクションの影響が疑われる
- 安全ポリシー違反

AgentはIssueを提案し、OrchestratorがEnum、Claim状態、監査結果に基づいて未解決かを管理する。IssueはMVPでは`open` / `resolved`の2値で追跡し、再監査で`open`が`resolved`になったかを確認する。

`accepted_risk`（危険を承知の上で受容する状態）はMVPでは提供しない。将来導入する場合も次を必須とする。

- `critical` severityには設定できない
- 安全違反、捏造引用、プロンプトインジェクション影響には設定できない
- 公開可否判定上、`resolved`と同一扱いにしない
- 誰が、どの理由で受容したかを記録する
- 自動設定せず、明示的なユーザー操作または管理操作に限定する

### 11.3 回答公開条件

- 2 Responderの有効な独立回答がある
- Auditorが`approved`を返す
- 未解決のCritical Issueがない
- `critical` Claimに`contradicted`または`unverified`がない
- `major` Claimに`contradicted`がない

### 11.4 根拠とAgent意見が衝突した場合

信頼できるEvidenceで裏付けられた少数意見を多数意見より優先する。採用理由を決定ログへ記録する。

### 11.5 withheld時の開示範囲

統合された最終回答本文の公開ゲート（Auditor承認）と、Claim検証結果の開示ゲートを分離する。Runが`withheld`または`failed`で回答本文を公開しない場合でも、次は開示する。

- Claim本文、`status`、`importance`、採否、短い理由
- Evidenceのタイトル、発行者、URL、Claimとの対応関係の概要
- 保留理由

次は開示しない。

- 監査前の`final_answer`
- Evidence本文の長い抜粋
- 内部プロンプト、Agentの生出力

表示は誤情報の再掲を避けるため、Claim本文を先頭にせず「確認状態 → 確認対象 → 扱い」の順で構成する。

```text
確認状態: 未確認
確認対象: 「製品Aは2025年に発売された」
扱い: この主張は回答に採用していません
```

`contradicted`のClaimは「信頼できる資料と矛盾。回答から除外しました」まで表示する。AIによる部分回答の再生成は行わない。verifiedなClaimだけを文章として再構成する機能は将来対応とする。`--json`と履歴表示でも同じ開示境界を守る。

## 12. 検証モードと性能目標

### 12.1 `quick`

- 質問整理
- 独立回答
- 簡易比較
- 統合回答
- 外部Evidence収集なし

出力へ`external_verification: false`を必ず含める。

### 12.2 `verify`（既定）

- 質問整理
- 独立回答
- Claim抽出
- 主要ClaimのEvidence収集と判定
- Evidence参照付き統合批評
- 統合、監査

### 12.3 `strict`

- 重要Claimは一次資料または高品質資料を必須とする
- 確認できない主要Claimは最終回答から除外する
- 根拠不足の場合は回答を保留する
- 医療、法律、金融、安全に関する質問では自動提案する

自動提案は暗黙のモード変更ではない（§2.5）。

- 対話モード: 高リスク質問を検出したら`strict`を推奨し、ユーザーが承認すれば`strict`で続行、拒否すれば`verify`で続行するか終了を選べる
- 非対話モード: `--mode`の明示指定がなければ`strict_required`で停止する。`--mode verify`または`--mode strict`が明示されていればそれに従う

### 12.4 待ち時間目標

AI CLIと検索サービスの速度に依存するため保証値ではないが、開発上の目標を次とする。

- `quick`: 中央値90秒以内
- `verify`: 中央値5分以内
- `strict`: 中央値10分以内

MVPではフェーズ名、完了Agent数、経過時間を表示する。トークン単位のストリーミング表示や詳細プログレスバーは将来対応とする。

## 13. CLI・UX

### 13.1 コマンド案

```bash
oracle ask "富士山の標高は？"
oracle ask "おすすめのノートPCは？" --mode verify
oracle ask "この制度は現在も使える？" --mode strict
oracle ask "質問" --mode quick
oracle ask "質問" --no-interactive
oracle ask "質問" --json
oracle ask "質問" --timeout-agent 240
oracle agents status
oracle agents validate
oracle history list
oracle history show <run-id>
```

Agent設定はユーザーが設定ファイルを直接編集し、`oracle agents status`と`oracle agents validate`で確認する。`agents add|enable|disable`等の管理コマンドはMVP対象外とする。設定はRun開始時にスナップショット（ハッシュ）を取り、実行途中の変更は当該Runへ反映せず次のRunから反映する。

### 13.2 既定モード

既定は`verify`とする。Oracle Councilの主要価値が外部根拠確認だからである。

EvidenceProviderが利用できない場合は、次のいずれかとする。

- 対話モード: `quick`へ切り替えるか確認する
- 非対話モード: `verification_unavailable`で終了する
- `--allow-unverified-fallback`指定時のみ`quick`へ切り替える

暗黙の切り替えは禁止する。

### 13.3 進捗表示例

```text
[1/7] 質問を整理しています
[2/7] 2 Agentが独立回答中 ... 1/2完了
[3/7] Claimを抽出しています
[4/7] Evidenceを収集中 ... 3/5完了
[5/7] Claimを検証しています
[6/7] 評議会が批評しています
[7/7] 最終回答を統合・監査しています
```

### 13.4 終了コード

Oracle Council自身の終了コード（oracleExitCode）は次の6値とする。詳細はJSON出力の`status`、`result_classification`、`errors[]`を正本とし、終了コードは大分類のみを表す。

| oracleExitCode | 意味 | 対応する`result.status` |
|---:|---|---|
| 0 | 公開可能な回答あり | `completed`、`partial`（公開可能な`final_answer`が存在する場合だけ） |
| 1 | 実行失敗 | `failed`、`internal_error` |
| 2 | 入力・追加判断が必要 | `needs_clarification`、`strict_required`、`invalid_arguments`、`unsupported`、`safety_blocked` |
| 3 | 実行環境を整える必要あり | `verification_unavailable`、`insufficient_agents`、`auth_required`、`configuration_error` |
| 4 | 回答保留 | `withheld` |
| 130 | ユーザーキャンセル | `cancelled_by_user` |

- `withheld`は必ず4を返す。処理失敗ではなく、検証の結果として回答を止めたことを表す
- CLI引数不正は`invalid_arguments`として2に含め、`needs_clarification`とはJSONの`status`で区別する
- 子AI CLIの終了コードは`AgentResult.exit_code`として記録し、Oracle Council自身の終了コードと混在させない
- 130はOracle CouncilがSIGINT相当のキャンセルとして返す慣例値であり、子プロセスの終了コードを流用しない。Windowsでも同値を返す
- 新しい停止理由は既存6値のいずれかへ割り当て、終了コードを増やさない

## 14. JSON出力スキーマ

JSON出力は内部データモデルの無加工出力ではなく、外部連携用の安定したスキーマとする。

トップレベル:

```json
{
  "schema_version": "1.0",
  "run_id": "run-...",
  "status": "completed",
  "mode": "verify",
  "question": {
    "original": "元の質問",
    "refined": "整理後の質問",
    "clarification_status": "ready_with_assumptions",
    "assumptions": []
  },
  "participants": [],
  "answer": {
    "text": "最終回答",
    "result_classification": "partially_verified",
    "consensus_status": "not_applicable",
    "audit_status": "approved",
    "external_verification": true
  },
  "claims": [],
  "evidence": [],
  "votes": [],
  "warnings": [],
  "errors": [],
  "timing": {
    "started_at": "2026-07-10T12:00:00+09:00",
    "finished_at": "2026-07-10T12:03:00+09:00",
    "elapsed_ms": 180000
  }
}
```

互換性を壊す変更では`schema_version`のメジャー番号を上げる。`votes`は将来互換用の予約フィールドであり、MVPでは常に空配列とする。

Run生成前に停止する場合も、CLIは停止理由を構造化結果として必ず返す。`run_id`は`null`とし、`status`と`exit_code`を正本にする。

```json
{
  "schema_version": "1.0",
  "run_id": null,
  "status": "needs_clarification",
  "exit_code": 2,
  "message": "追加情報が必要です"
}
```

`strict_required`は終了コード2、`verification_unavailable`と`insufficient_agents`は終了コード3で同じ形を返す。これらはRunが存在しないため`history show`の対象にならない。

## 15. データモデルとストレージ

### 15.1 ストレージ方針

MVPはJSONLのみを実装する。

- Run単位の追記型イベントログ: `data/runs/<run-id>/events.jsonl`
- 1行に1イベント
- `run_id`と`sequence`で実行を再構成する
- 完了時に`run_completed`イベントへ最終スナップショットを含める。既定（metadata保存）ではRunMetadataRecordのみを含め、content区分フィールドは`--store-content`指定時だけ含める
- ストレージは`StorageBackend`インターフェースで抽象化する
- SQLiteはデータモデルが安定した後に追加する
- `--no-store`ではStorageBackendを呼び出さず、Runディレクトリを作成しない

Runは、引数・設定検証、質問整理、mode判定、EvidenceProvider利用可否、最低Agent数の事前検査が全て通過し、最初のPhaseを開始する直前に生成する。`needs_clarification`、`strict_required`、`verification_unavailable`、`insufficient_agents`等で事前停止する場合はRunを生成せず、履歴へ保存しない。`--no-store`では事前停止結果も保存せず、Run生成後のイベントも永続化しない。

#### StorageBackend Contract

公開メソッドは次とする。

- `append(run_id, event_without_sequence) -> RunEvent`
- `load(run_id) -> StorageLoadResult`
- `delete(run_id) -> DeleteResult`
- `purge() -> PurgeResult`

`sequence`はStorageBackendが所有する。`append`は同一Runの排他lock/transaction内で、既存の最大sequenceを検証し、`max + 1`（初回は1）を採番し、schema-validなJSON 1行を追記して永続媒体へflushした後、採番済み`RunEvent`を返す。採番、追記、可視化は1回の原子的操作であり、失敗時に完全行を成功扱いしない。同一Runへのthread/process間同時書込みでもsequenceの重複・欠番・行の混在を許さない。異なるRunは独立して書き込める。

`load`はsequence昇順のイベントとwarningを持つ`StorageLoadResult`を返す。末尾の改行されていない不完全な1行だけは`TRUNCATED_TAIL` warningとして無視し、それ以前の完全行を返す。中間の不正JSON、schema違反、sequence重複・欠番・逆転は`StorageCorruptionError`とし、破損行を飛ばして正常履歴として返さない。破損Runへの追加appendも拒否する。MVPでは中断Runを再開せず、完全行までの履歴閲覧だけを許す。

存在しない`run_id`の`load`は空配列ではなく`StorageNotFoundError`を返す。これにより「履歴なし」と「イベント0件のRun」を混同しない。

`delete`は指定Runの全metadata/content/一時ファイルを削除し、対象なしでも成功する冪等操作とする。`purge`は全Runを同じ規則で削除し、削除件数を返す。実行中Runと競合した場合はlock取得に失敗させ、書込み中のデータを削除しない。

保存モード境界はOrchestratorが適用する。metadata-onlyではcontent区分キーをStorageへ渡さず、`--store-content`時だけredaction済みcontentを渡す。`--no-store`ではStorageBackendを生成・参照・呼び出さず、`append/load/delete/purge`の呼び出し回数は0とする。

保存が有効なRunで`append`が失敗した場合はfail closedとする。初回`run_created`、途中イベント、最終`run_completed`のどの失敗でも、以後のappendを停止し、in-memory Runを`failed`、`error_code=STORAGE_WRITE_FAILED`、final_answer非公開、oracleExitCode=1とする。保存失敗を記録するための再帰的appendは行わず、redaction済みstderrだけで通知する。最終回答生成後の保存失敗でも回答を公開しない。`--no-store`だけは保存なしを選択済みの正常経路であり、この規則の対象外とする。

`load`の`StorageCorruptionError`は対象履歴の表示を失敗させ、`STORAGE_CORRUPTED`を返す。他のRunや新規Runの処理は継続できる。

`StorageErrorCode`は`STORAGE_WRITE_FAILED` / `STORAGE_CORRUPTED` / `STORAGE_LOCK_FAILED` / `STORAGE_NOT_FOUND`とし、自由文字列をerror_codeに使わない。末尾切断はエラーではなく`StorageWarning.TRUNCATED_TAIL`とする。

### 15.2 Run.status

- `pending`
- `running`
- `completed`
- `partial`
- `failed`
- `cancelled`

遷移は`pending -> running -> completed | partial | failed | cancelled`と、初回保存失敗時の`pending -> failed`だけを許可する。終端状態からの遷移は禁止する。

- `completed`: (a) Auditorが`approved`した公開可能な回答があり`result_classification`が`verified`、`conflicting`または`unverified`、または (b) §15.3第1段で`withheld`が確定し§11.5の検証結果開示を返した
- `partial`: Auditorが`approved`した公開可能な回答があり、品質劣化を示す`result_classification=partially_verified`である場合だけ使用する
- `failed`: 必須Phaseが最低成功数を満たさない、または監査を完了できない（監査の`blocked`は`failed`ではなく`withheld`終端。§11.1）
- `cancelled`: ユーザー中断または明示cancel

RunStatusは処理終端、result_classificationは検証品質であり混同しない。判定順は`cancelled`、`failed`、`withheldを伴うcompleted`、`partial`、`completed`とする。Phaseが`degraded`でも公開可能な回答がなければ`partial`にせず`failed`とする。Evidence収集の一部不足等がClaimの未確認として残り、監査済みの公開可能な部分回答がある場合は`partial + partially_verified + exit 0`とする。

`withheld`はRun失敗ではない（§13.4でexit 4をexit 1と分離）。§15.3第1段で`withheld`が確定した場合、以降の`criticize`、`synthesize`、`audit`は`skipped`とし、`completed + withheld + exit 4`で終了する。監査対象の統合回答を作らないため、未承認回答の漏えいは構造的に起きない。

#### 保存・予算障害の終端決定表

| 発生イベント | Storage操作・結果 | BudgetReservation操作 | Phase.status | Run.status | result_classification | final_answer | CLI | 保存イベント |
|---|---|---|---|---|---|---|---:|---|
| 初回保存失敗 | `append(run_created)`失敗 | 未予約なら操作なし。予約済み未開始はrelease | 未開始Phaseは`cancelled` | `failed` | `unverified` | 非公開 | 1 | 追加保存なし。stderrに`STORAGE_WRITE_FAILED` |
| Run途中の保存失敗 | event append失敗 | 未開始予約はrelease。開始済みExecutionはcommit | 実行中Phaseは`failed` | `failed` | その時点の分類を公開結果に使わない | 非公開 | 1 | 失敗したappend以後は保存なし |
| 最終保存だけ失敗 | `append(run_completed)`失敗 | 全予約は既に終端 | 完了済みPhaseは変更しない | `failed` | 内部値は保持するが公開結果に使わない | 非公開 | 1 | 再帰的保存なし。stderrに`STORAGE_WRITE_FAILED` |
| reserve失敗・Auditor承認済み回答あり | `budget_exceeded`をappend。成功必須 | 予約は作られない | 次の未開始Phaseは`skipped` | `partial` | `partially_verified`へ保守的に設定 | 公開 | 0 | `budget_exceeded`、`run_partial` |
| reserve失敗・承認済み回答なし | `budget_exceeded`をappend。成功必須 | 予約は作られない | 対象Phaseは`failed` | `failed` | `unverified` | 非公開 | 1 | `budget_exceeded`、`phase_failed`、`run_failed` |
| Claim検証で安全保留 | 通常append | 全予約を規則どおり終端 | criticize以降`skipped` | `completed` | `withheld` | 非公開。Claim検証結果は公開 | 4 | `claims_classified`、skipped Phase、`run_completed` |

reserve失敗後は新しいAgent呼び出し、retry、代替Agent実行を開始しない。`partial`を許す「Auditor承認済み回答」は、現在のRunでAuditorが`approved`を返したschema-validなfinal_answerに限る。未監査回答、`changes_required`中の回答、過去Runの回答は使用しない。予算不足による`partial`は、未実行の必須処理が残った品質劣化を明示するため`result_classification=partially_verified`とする。

`BUDGET_EXCEEDED`はAI呼び出し・token・コンテキスト予算に限定する。Evidence収集上限の`EvidenceErrorCode.BUDGET_EXHAUSTED`、Evidence時間上限の`EVIDENCE_TIMEOUT`とは別である。

### 15.3 result_classification

- `verified`
- `partially_verified`
- `unverified`
- `conflicting`
- `withheld`

Run全体の分類は、AIの自由判断ではなくOrchestratorが二段判定で導出する。

**第1段（公開可能かの安全判定）**: `verify` Phaseが完了し、全対象Claimの検証状態が確定した後、次のいずれかに該当すれば`withheld`とし、回答本文を公開せず§11.5の開示範囲だけを返す。

1. `critical` Claimに`unverified`または`contradicted`が1件でもある
2. `major` Claimに`contradicted`が1件でもある

**第2段（公開可能な場合の分類）**: 上から順に最初に一致した行を採用する。

| 条件 | 分類 |
|---|---|
| `critical`または`major`に`conflicting`がある | `conflicting` |
| 主要Claim（critical＋major）が1件以上あり、その全てが`unverified` | `unverified` |
| `major`に`unverified`がある | `partially_verified` |
| `minor`に`unverified`、`conflicting`または`contradicted`がある | `partially_verified` |
| 検証対象Claimが1件以上あり、その全てが`verified`または`supported` | `verified` |
| 検証対象Claimが0件（全て`not_applicable`） | `unverified` |

優先順位は`withheld` > `conflicting` > `unverified` > `partially_verified` > `verified`とする。安全判定を先に行うため、`withheld`と分類が混ざらない。

### 15.4 consensus_status

- `reached`
- `not_reached`
- `not_applicable`

### 15.5 AgentExecution.phase

- `clarify`
- `respond`
- `claim_extract`
- `verify`
- `criticize`
- `synthesize`
- `audit`
- `vote`

`vote`は将来互換用の予約値であり、MVPでは生成しない。

AgentExecutionは「1 Agentの1回の呼び出し」ごとに1レコードとする。同じAgentが複数フェーズを担当した場合は複数レコードになる。

### 15.6 AgentExecution.status

- `pending`
- `running`
- `succeeded`
- `unavailable`
- `failed`
- `timed_out`
- `cancelled`

遷移は`pending -> running -> succeeded | unavailable | failed | timed_out | cancelled`だけを許可する。`succeeded`はschema-validな出力あり、`unavailable`はquota、auth、未導入等で実行不能、`failed`は実行したが有効出力なしを表す。再試行は新しいAgentExecutionを作成する。詳細な原因は`error_code`へ保存する。

### 15.7 Phase.status

- `pending`
- `running`
- `succeeded`
- `degraded`
- `failed`
- `skipped`
- `cancelled`

遷移は`pending -> running | skipped | cancelled`、`running -> succeeded | degraded | failed | cancelled`だけを許可する。最低成功数は`respond`=2、`claim_extract`=1、`verify`=1、`criticize`=1、`synthesize`=1、`audit`=1とする。最低数を満たし一部Executionが失敗した場合は`degraded`、満たさなければ`failed`とする。Clarifyは不要なら`skipped`とする。

Evidence収集は`evidence_collect` Phaseとして`claim_extract`と`verify`の間に置く。AI呼び出しではないためAgentExecutionを作らず、Phaseレコードだけで管理する。`evidence_collect`は「処理が正常に終わったか」（Phase.status）と「根拠が見つかったか」（EvidenceOutcome）を分離して記録する。

- Phase.status: 検索・取得処理そのものの成否
  - `succeeded`: 検索対象の主要Claim全件を停止条件まで処理した。資料が1件も見つからなくても処理が正常ならPhase失敗ではない
  - `degraded`: 一部Claimが収集上限または90秒上限で未処理。未処理Claimは`unverified`とし、収集上限なら`BUDGET_EXHAUSTED`、90秒上限なら`EVIDENCE_TIMEOUT`を記録して続行する
  - `failed`: Evidence収集機能そのものが実行不能（実行中の全断）。§2.5に従いRunを`failed`とする。Run開始前の利用不能は`verification_unavailable`として区別する
  - `skipped`: `quick`等でEvidence収集を行わない場合
- EvidenceOutcome: `evidence_found` / `partial_evidence` / `no_evidence` / `conflicting_evidence` / `not_applicable`
- EvidenceErrorCode: `SEARCH_UNAVAILABLE` / `ALL_FETCH_BLOCKED` / `EVIDENCE_TIMEOUT` / `BUDGET_EXHAUSTED` / `FETCH_FAILED`

`EvidenceErrorCode.BUDGET_EXHAUSTED`は検索回数、fetch数、文書量、Evidence件数の収集上限に使用する。Evidence処理の90秒上限は`EvidenceErrorCode.EVIDENCE_TIMEOUT`を使用する。AI呼び出し回数、入力・出力token、コンテキスト縮約後の不足には`AgentErrorCode.BUDGET_EXCEEDED`を使用し、Evidence収集上限と混在させない。

検索が正常終了して資料が見つからなかった場合は`succeeded`＋`no_evidence`＋Claim `unverified`である。「根拠が見つからなかった」と「Evidence機能が壊れて調べられなかった」を分けて記録・表示する。

Ctrl+Cでは子process treeをterminateし、5秒後も残る場合はkillする。実行中のExecution、Phase、Runを`cancelled`として保存する。

### 15.8 主要エンティティ

以下は実行時（in-memory）モデルであり、そのまま永続化しない。永続化は保存区分に従う。

- **metadata区分**: 既定で保存する。RunMetadataRecordと§17.1の項目に限る
- **content区分**: `--store-content`指定時だけ保存する。Run.`original_question` / `refined_question` / `final_answer`、AgentExecution.`response`、Claim.`text` / `notes`、Evidence.`url` / `title` / `publisher` / `excerpt` / `notes`、AuditIssue.`comment`が該当する

#### RunMetadataRecord（既定で永続化する唯一のRunレコード）

- `run_id`
- `created_at`
- `mode`
- `risk_level`
- `status`
- `result_classification`
- `consensus_status`
- `participant_count`
- `claim_count`
- `evidence_count`
- `error_codes`
- `elapsed_ms`

#### Run

- `run_id`
- `created_at`
- `original_question`
- `refined_question`
- `mode`
- `risk_level`
- `status`
- `final_answer`
- `result_classification`
- `consensus_status`
- `elapsed_ms`

#### Phase

- `phase_id`
- `run_id`
- `phase`（`clarify` / `respond` / `claim_extract` / `evidence_collect` / `verify` / `criticize` / `synthesize` / `audit`）
- `status`
- `started_at`
- `finished_at`
- `minimum_success_count`
- `success_count`
- `error_code`（`PhaseErrorCode`。`evidence_collect`では`EvidenceErrorCode`も使用可能）
- `error_summary`
- `raw_diagnostic`（content区分）
- `outcome`（EvidenceOutcome。`evidence_collect`のみ使用）

`error_summary`はOracle Councilが生成した定型文のみをmetadata保存する。最大200文字、secret redaction済みとし、子CLIのstderr、例外本文、質問・回答・Evidence断片、コマンド文字列、ファイルパスを直接保存しない。「Responder timed out after one retry.」は保存してよいが、コマンド文字列や質問全文を含むエラーは保存してはならない。生のstderr・例外を残す場合は`raw_diagnostic`へ分離し、redaction済みかつ`--store-content`時のみ保存する。同じ規則はAgentExecutionの`error_summary`と`raw_diagnostic`にも適用する。`raw_diagnostic`以外のPhaseフィールドはmetadata区分とする。

`PhaseErrorCode`は`MINIMUM_SUCCESS_NOT_MET` / `PHASE_TIMEOUT` / `PHASE_CANCELLED` / `BUDGET_EXCEEDED`とする。`evidence_collect`ではM-4で確定した`EvidenceErrorCode`も使用できる。自由文字列を`error_code`へ保存しない。

#### AuditIssue

- `issue_id`
- `run_id`
- `audit_execution_id`
- `issue_type`
- `severity`
- `claim_id`
- `status`（MVPでは`open` / `resolved`）
- `comment`（content区分）
- `created_at`
- `resolved_at`

AuditIssueは`comment`以外をmetadata区分とする。

#### AgentExecution

- `execution_id`
- `run_id`
- `agent_id`
- `phase`
- `status`
- `started_at`
- `finished_at`
- `elapsed_ms`
- `exit_code`
- `response`
- `error_code`
- `error_summary`
- `raw_diagnostic`（content区分）

#### Claim

- `claim_id`
- `run_id`
- `text`
- `importance`
- `status`
- `notes`

#### Evidence

- `evidence_id`
- `claim_id`
- `url`
- `title`
- `publisher`
- `published_at`
- `retrieved_at`
- `authority`
- `directness`
- `stance`
- `freshness`
- `excerpt`
- `content_hash`

#### Vote

- `run_id`
- `agent_id`
- `round`
- `vote`
- `issues`
- `comment`

## 16. セキュリティ

### 16.1 CLI実行

- `shell=True`を使用しない
- コマンドと引数を分離する
- ユーザー入力をシェルコマンドとして解釈しない
- 各Executionは新規の空一時ディレクトリをcwdとする
- 質問とEvidenceはstdinで渡し、作業ファイルへ保存しない
- 環境変数は`PATH`、OS動作用最小変数、Adapter宣言済み認証変数のallowlistから新規構築し、親環境を継承しない
- 非対話、ツール無効、ファイル変更無効、セッション非永続の固定引数をAdapterが付ける
- `supports_no_tools=true`かつ`supports_read_only=true`をprobeで確認できなければ`UNSAFE_CAPABILITY`で起動しない
- 子プロセスをprocess groupまたはjob objectへ入れ、timeout/cancel時に子孫を含めて終了する
- ユーザー指定cwd、任意コマンド、任意追加引数を許可しない
- AI出力をJSON SchemaまたはPydanticモデルで検証する

MVPは同一OSユーザーの敵対コードに対するOSレベル隔離を保証しない。containerまたはsandbox runnerはMVP対象外とする。

### 16.2 Evidence由来のプロンプトインジェクション対策

HTMLタグ除去だけでは対策にならないため、次を組み合わせる。

1. Evidenceは「信頼できない外部データ」として扱う
2. Web取得は専用`SafeHttpFetcher`だけを使い、EvidenceProviderによる直接HTTP接続を禁止する
3. schemeは`https`、portは443だけを許可し、userinfo、IP literal、fragmentを拒否する
4. script、style、formなどの能動要素を除去する
5. ページ全文ではなくClaimに対応する短い抜粋だけを渡す
6. URL、題名、発行者、日時、抜粋を構造化JSONにする
7. 抜粋内の命令文へ従わないことをVerifierへ明示する
8. Evidenceからツール実行、ファイルアクセス、追加URLアクセスを許可しない
9. 最大文字数と最大資料数を制限する
10. 取得本文のハッシュを保存する

`SafeHttpFetcher`は次を満たす。

- proxyおよび`HTTP_PROXY`等の環境変数を使用しない
- IDNA正規化したhostnameの全A/AAAAを検査し、`ipaddress.is_global == true`でないIPを1つでも含めば拒否する
- 許可IPへ接続先を固定し、HTTP Host、TLS SNI、証明書検証には元hostnameを使う
- redirectは自動追従せず最大3回、各hopでURL、DNS、IPを再検証する
- 接続3秒、応答10秒、全体20秒、展開後2MBで打ち切る
- `text/html`、`text/plain`、`application/json`以外を拒否する
- subresourceを取得せず、JavaScriptを実行しない

拒否理由は`URL_SCHEME_BLOCKED`、`URL_PORT_BLOCKED`、`DNS_PRIVATE_ADDRESS`、`DNS_REBINDING_BLOCKED`、`REDIRECT_LIMIT`、`RESPONSE_TOO_LARGE`、`CONTENT_TYPE_BLOCKED`、`FETCH_TIMEOUT`とする。企業内URLと明示proxyはMVP対象外とする。

### 16.3 機密情報

- APIキー、認証情報、セッション情報をログへ保存しない
- エラーメッセージから認証情報を除去する
- 保存データの削除方法を用意する
- 公開ログとローカル詳細ログを分離する

## 17. ログと透明性

### 17.1 既定ログ

既定は`metadata`保存とし、質問、プロンプト、回答本文、Evidence URL/本文/抜粋、stdout、stderrを永続化しない。保存対象は次に限定する。

- run/execution ID、時刻、状態、phase
- adapter family/version、CLI version、モデル識別子
- 推定/実測usage、Claim/Evidence件数、elapsed_ms
- `error_code`と固定テンプレートの`error_summary`

非公開の内部思考過程は要求・保存しない。

`--store-content`指定時だけ質問、構造化回答、Claim、Evidence抜粋、最終回答を保存する。対話時は確認し、非対話時は`--yes`を必須とする。`--no-store`ではmetadataも保存しない。

metadataのみのRunに対する`oracle history show`は正常表示とし、run_id、実行日時、モード、状態、参加Agent、Claim数、Evidence数、結果区分、所要時間、エラーコード、`content_saved: false`を表示する。本文欄には「本文は保存されていません」と明示する。JSON出力ではcontent区分フィールドを省略し（空文字やnullを最終回答として返さない）、`content_saved`フラグを必ず含める。保持期間はmetadata 30日、content 7日とし、CLI起動時に期限切れRunを削除する。`oracle history delete <run-id>`と`oracle history purge --yes`をMVPで提供する。telemetryとクラッシュレポート送信は実装しない。

### 17.2 詳細ログ

生プロンプトは既定で保存しない。保存する場合は明示的な二段階指定を必要とする。

```bash
oracle ask "質問" --store-content --log-level debug --include-prompts
```

- 対話実行では「質問内容や取得資料が保存される」と警告する
- 非対話実行では追加で`--yes`を必須とする
- ファイル権限は可能なOSで所有者のみ読書き可能にする
- 認証情報のマスキングは詳細ログでも解除しない
- 詳細ログはローカルのみで、公開を前提としない

## 18. 開発環境・テスト・ライセンス

### 18.1 Pythonとパッケージ管理

- 最低Python: 3.11
- ビルド設定: `pyproject.toml`
- 開発時推奨: `uv`
- 利用者向け: `pip install -e .`もサポート
- 外部ライブラリは必要性を説明できるものに限定する
- 標準ライブラリ縛りにはしない

候補:

- Typer: CLI
- Pydantic: 構造化出力と検証
- httpx: 非同期HTTP
- PyYAML: 設定ファイル
- pytest / pytest-asyncio: テスト

### 18.2 テスト戦略

- 単体テストは`FakeAgentAdapter`と`FakeEvidenceProvider`を使用する
- AI CLIの出力例は認証情報を除去したfixtureとして固定する
- Adapterごとに状態分類とJSON契約のContract Testを用意する
- 通常CIでは実AI CLIや有料APIを呼び出さない
- Live Integration Testは`live`マーカー付きで明示実行する
- Live TestはローカルまたはSecretsを設定した手動・定期Workflowだけで実行する
- PRの必須チェックはFakeを使った単体・統合テストとする

### 18.3 ライセンス

Oracle Council本体はMIT Licenseとする。

AI CLI、検索API、取得資料は別サービス・別著作物であり、Oracle CouncilのMIT Licenseに含まれない。利用者は各サービスの利用規約、商用利用条件、料金、再配布条件を確認する。

## 19. 推奨ディレクトリ構成

```text
OracleCouncil/
├─ SPEC.md
├─ QandA.md
├─ README.md
├─ LICENSE
├─ pyproject.toml
├─ config/
│  └─ agents.example.yaml
├─ data/
│  └─ .gitkeep
├─ src/
│  └─ oracle_council/
│     ├─ cli.py
│     ├─ orchestrator.py
│     ├─ clarification.py
│     ├─ consensus.py
│     ├─ claims.py
│     ├─ verification.py
│     ├─ synthesis.py
│     ├─ storage.py
│     ├─ models.py
│     ├─ prompts/
│     ├─ adapters/
│     │  ├─ base.py
│     │  ├─ claude.py
│     │  ├─ codex.py
│     │  ├─ gemini.py
│     │  └─ custom.py
│     └─ evidence/
│        ├─ base.py
│        ├─ none.py
│        ├─ manual.py
│        └─ web.py
├─ tests/
│  ├─ fixtures/
│  ├─ unit/
│  ├─ contract/
│  ├─ integration/
│  └─ live/
└─ web/
   └─ README.md
```

将来のWeb UIは同一リポジトリの`web/`へ置くモノレポ方針とする。Web UIの開発・リリースが独立する必要が生じた時点で分離を再検討する。

## 20. MVP受け入れ条件

### 20.1 質問整理

- 明確な質問は追加質問なしで進む
- 不完全な質問には最大3問の追加質問を出せる
- 誤った可能性のある前提を検出して確認できる
- 非対話モードでは仮定または処理不能理由を返せる
- 高リスクな不足情報を自動仮定しない

### 20.2 Agent実行

- Claude CodeとCodex CLIの2 Adapterで独立回答を生成できる
- Orchestratorと設定スキーマは最大4 Agentを扱える
- Responder 2件を得られない場合は継続しない
- 利用上限、認証切れ、タイムアウトを区別できる
- Agent単位とフェーズ単位のタイムアウトを適用できる
- 通常7回、Clarifier込み8回、修正込み10回、再試行込み12回の上限を超えない
- 各フェーズを独立セッションで実行できる
- Adapter Contract Testでprobe、成功、error、timeout/cancel、schema違反、権限capabilityを検証できる

### 20.3 Evidenceと検証

- 回答からClaimを抽出できる
- Claimへ`critical`、`major`、`minor`を設定できる
- EvidenceProviderを交換できる
- ClaimとEvidenceを紐付けられる
- Evidence本文を構造化された短い抜粋としてAgentへ渡せる
- `verified`、`contradicted`、`unverified`を区別できる
- 未確認の断定を最終回答から除外または明示できる
- `verify`でEvidenceProviderがない場合に暗黙で`quick`へ落ちない
- 最大5 Claim、検索10回、fetch 12文書、Evidence 10件、90秒の上限を適用できる
- K-1の決定表fixtureでClaim状態が100%一致する
- SSRF拒否fixtureを100%拒否する

### 20.4 監査

- Claim検証数と監査状態を別に表示できる
- `changes_required`後に1回だけ修正・再監査できる
- Critical Issueを構造化されたIssueから導出できる
- Auditorが`approved`でなければ回答を公開しない
- SynthesizerとAuditorを異なるAgentにできない場合は失敗する

### 20.5 記録と出力

- 1実行分のmetadataイベントをRun単位JSONLへ保存できる
- APIキーや認証情報が保存されない
- `--store-content`指定時だけ同じ実行内容を後から表示できる
- `schema_version: 1.0`のJSONを出力できる
- 生プロンプト保存は明示指定時だけ有効になる
- 秘密文字列fixtureが永続ファイルへ0件である
- `--no-store`、Run削除、全削除、保持期限削除が動作する

### 20.6 定量的受け入れ条件

- 固定fixture 30問でRun、Phase、AgentExecutionの終端状態が期待値へ100%一致する
- Evidence判定表fixtureでClaim状態が100%一致する
- secret fixtureが永続ファイルへ0件である
- SSRF拒否fixtureを100%拒否する
- Fake統合テストでAI呼び出し絶対上限12回を超えるRunが0件である
- 手動Live Smoke TestでClaude Code、Codex CLIがそれぞれ10 Run中9 Run以上schema-validな結果を返す

回答内容の正確性ベンチマークはP1とし、MVP公開時は品質評価中の実験的ソフトウェアであることを明示する。

## 21. MVP開発フェーズ

Phase番号は依存関係を示す。質問整理の実装は早期に着手するが、先に共通データモデルとFake Adapterを用意する。

### Phase 0前spike: Adapter capability確認

実装開始前に、公式サポート2 CLI（Claude Code、Codex CLI）で次を手動確認し、結果を`docs/adapter-spike.md`へ記録する。確認できない項目があれば、実装着手前にfail-closed条件（§8.5、§16.1）を見直す。

- 完全非対話で1回の呼び出しを実行できるか
- ツール実行の無効化または拒否を保証できるか
- 読み取り専用または空の一時cwdで実行できるか
- 構造化出力（JSON）を安定して取得できるか
- stdout / stderr / exit codeの分離と安定性
- seed指定の可否（不可なら§7.5のseed記述を「対応CLIのみ」へ限定する）

### Phase 0: 契約と基盤

- Python 3.11プロジェクト
- データモデルとEnum
- JSON Schema
- 設定読み込み
- FakeAgentAdapter
- FakeEvidenceProvider
- Run単位JSONL Storage
- CLI骨格

### Phase 1: 質問整理

- 質問分類
- 不足情報判定
- 対話入力
- 仮定の明示
- 前提検査
- `--no-interactive`

### Phase 2: Agent実行

- 共通Agentインターフェース
- Claude Code Adapter
- Codex CLI Adapter
- 並列実行
- Agent・フェーズタイムアウト
- 状態分類
- 2 Agentの独立回答

### Phase 3: ClaimとEvidence

- Claim抽出
- Claim重要度
- EvidenceProviderインターフェース
- 最初の実検索Provider
- Evidence取得・抜粋
- Claim判定
- インジェクション対策

### Phase 4: 評議会

- 回答匿名化
- Evidence参照付き1 Agent統合批評
- 統合回答
- 別Agent監査
- 修正1回

### Phase 5: UXと品質

- 進捗表示
- 実行履歴
- 詳細表示
- JSON出力
- Contract Test
- Live Test
- READMEとサンプル

## 22. 未決事項

次は実装開始前または該当Phase開始時に決める。

- 最初に実装する実検索EvidenceProvider
- Windows、Linux、macOSの初期サポート範囲

## 23. プロジェクトの説明文案

> Oracle Councilは、不完全な質問を対話で整理し、複数のAI CLIによる独立回答、外部根拠確認、相互批評、監査を経て、検証状況付きの最終回答を返すAIオーケストレーターです。利用上限や認証切れのAIは棄権扱いとし、参加可能なAIだけで処理を継続します。

## 24. キャッチコピー案

> 質問するだけ。AIの間違いチェックは評議会におまかせ。

または:

> AIの回答を、別のAIと根拠資料で確認してから返す。
