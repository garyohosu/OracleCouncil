# Oracle Council シーケンス図

- 対象仕様: `SPEC.md` v0.3.3
- 対象ユースケース: `USECASE.md`
- 対象範囲: MVPの`verify`モードと周辺操作
- Agent役割の割当は§8.1の`role_priority`設定例に基づく一例。実際の割当は§6.2の決定的ルールによる

## 前提

- `quick`の実行グラフはQandA J-3が未回答のため、本書では図示しない
- CLI終了コードはSPEC §13.4の対応表（0 / 1 / 2 / 3 / 4 / 130）に従う
- ユーザー応答待ちと全体タイムアウトの関係はQandA R-3が未回答のため、図では応答待ちを時間計測外として仮置きする

## 1. 正常系: `verify`（対話モード・監査一発承認・AI呼び出し7回）

```mermaid
sequenceDiagram
    actor U as 利用者
    participant CLI as oracle CLI
    participant O as Orchestrator
    participant CE as Clarification Engine
    participant A as Adapter A（Claude Code）
    participant B as Adapter B（Codex CLI）
    participant EP as EvidenceProvider（web）
    participant F as SafeHttpFetcher
    participant S as JSONL Storage

    U->>CLI: oracle ask "質問"（既定: verify）
    CLI->>A: probe()
    A-->>CLI: OK
    CLI->>A: capabilities()
    A-->>CLI: capabilities
    CLI->>B: probe()
    B-->>CLI: OK
    CLI->>B: capabilities()
    B-->>CLI: capabilities
    Note over CLI: config capabilitiesをマージしてAgentProbeSnapshotを生成
    CLI->>O: Run作成（snapshotsを渡す）
    O->>S: run_created / running イベント（snapshotsを含む）

    O->>CE: 決定的ルールで質問を検査
    CE-->>O: ready（追加質問・Clarifier不要）

    par AI呼び出し1・2（Responder並列・独立セッション）
        O->>A: execute(respond)
        A-->>O: 構造化回答A（6,000文字以内）
    and
        O->>B: execute(respond)
        B-->>O: 構造化回答B（6,000文字以内）
    end
    Note over O: 決定的な回答差分スキャン（ローカル処理・AI呼び出しに数えない）

    O->>B: execute(claim_extract)（AI呼び出し3）
    B-->>O: Claim一覧＋重要度案

    Note over O: evidence_collect Phase開始（AgentExecutionなし・Phaseレコードのみ）
    loop 主要Claim最大5件（検索10回・fetch12文書・90秒のRun上限内）
        O->>EP: search(中立クエリ)
        EP-->>O: 上位5件
        O->>EP: search(反証クエリ)
        EP-->>O: 上位5件
        O->>EP: fetch(SearchResult)
        EP->>F: fetch(候補URL)（必ず委譲・直接HTTP禁止）
        F->>F: https:443限定・DNS/IP検証・2MB上限
        F-->>EP: 取得本文
        EP-->>O: EvidenceDocument（Claimごと成功3文書まで）
    end
    Note over O: Phase.status（処理の成否）とEvidenceOutcome（根拠の結果）を分離記録

    O->>B: execute(verify)（AI呼び出し4）
    B-->>O: Evidence分類（authority / directness / stance / freshness）
    Note over O: Claim状態はOrchestratorが決定規則で確定（§10.5）

    O->>A: execute(criticize)（AI呼び出し5・正規化済み入力）
    A-->>O: 統合批評
    O->>A: execute(synthesize)（AI呼び出し6）
    A-->>O: 最終回答案
    O->>B: execute(audit)（AI呼び出し7・Synthesizerと別Agent）
    B-->>O: approved（未解決Critical Issueなし）

    O->>S: run_completed（既定はRunMetadataRecordのみ）
    O-->>CLI: 回答・検証状況・監査状況
    CLI-->>U: 最終回答＋verified_claims / total_claims
```

## 2. 質問整理と高リスク確認（Q-1反映）

```mermaid
sequenceDiagram
    actor U as 利用者
    participant CLI as oracle CLI
    participant O as Orchestrator
    participant CE as Clarification Engine
    participant A as Clarifier Agent

    U->>CLI: oracle ask "質問"
    CLI->>O: Run作成
    O->>CE: 決定的ルールで不足・前提を検査

    opt 決定的ルールで判定できない場合のみ
        O->>A: execute(clarify)（条件付きAI呼び出し・上限はClarifier込み8回）
        A-->>O: 判定ステータス＋構造化された追加質問または仮定案
    end

    alt ready / ready_with_assumptions
        O-->>CLI: 整理後の質問と仮定を表示
        Note over O: 独立回答フェーズへ進む
    else needs_clarification（対話）
        CLI-->>U: 追加質問（最大3問・最大2ラウンド）
        U->>CLI: 回答または「この条件で進める」
        CLI->>O: 追加情報を反映
        Note over O,CE: 2ラウンド目にClarifierを再呼び出すかはJ-4未回答
    else needs_clarification（非対話）
        O-->>CLI: 終了コード2で needs_clarification を返す
    else unsupported / safety_blocked
        O-->>CLI: 処理不能理由を返して停止
    end

    opt 高リスク分野を検出（医療・法律・金融・安全）
        alt 対話モード
            CLI-->>U: strictを推奨
            alt 利用者が承認
                U->>CLI: 承認
                Note over O: strictで続行
            else 利用者が拒否
                U->>CLI: 拒否
                Note over O: verifyで続行するか終了を選択
            end
        else 非対話モードで mode 未指定
            O-->>CLI: strict_required で停止
        end
    end
```

## 3. 監査で修正が必要な場合（修正・再監査は1回だけ）

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant Syn as Synthesizer Agent
    participant Aud as Auditor Agent（別Agent）
    participant S as JSONL Storage

    O->>Aud: execute(audit)
    Aud-->>O: 構造化されたissues
    Note over O: Critical IssueはOrchestratorが導出（§11.2）

    alt approved
        O->>S: run_completed（completed）
        Note over O: 回答を公開
    else changes_required
        O->>Syn: execute(synthesize) 修正（AI呼び出し+1）
        Syn-->>O: 修正済み回答案
        O->>Aud: execute(audit) 再監査（AI呼び出し+1・修正込み上限10回）
        alt 再監査でapproved
            O->>S: run_completed（completed または partial）
        else 依然として未承認
            O->>S: run_completed（failed）
            Note over O: 回答を公開しない
        end
    else blocked
        O->>S: run_completed（failed）
    end
```

## 4. 異常系

### 4a. EvidenceProvider利用不能（暗黙のquick切替禁止）

```mermaid
sequenceDiagram
    actor U as 利用者
    participant CLI as oracle CLI
    participant O as Orchestrator
    participant EP as EvidenceProvider

    O->>EP: 利用可否確認
    EP-->>O: 利用不能

    alt 対話モード
        CLI-->>U: quickへ切り替えるか確認
        alt 承認
            U->>CLI: 承認
            Note over O: quickで続行（external_verification: false を必ず出力）
        else 拒否
            O-->>CLI: 停止
        end
    else 非対話モード
        alt allow-unverified-fallback 指定あり
            Note over O: quickへ切替（明示許可のため可）
        else 指定なし
            O-->>CLI: verification_unavailable で終了
        end
    end
```

### 4b. Responderのタイムアウトと脱落

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Adapter A
    participant B as Adapter B
    participant C as Adapter C（第三候補）
    participant S as JSONL Storage

    par Responder並列
        O->>A: execute(respond)
        A-->>O: 構造化回答A（succeeded）
    and
        O->>B: execute(respond)
        Note over B: Agent単位タイムアウト（verify: 180秒）
        B-->>O: TIMEOUT
    end

    O->>S: AgentExecution timed_out を記録
    O->>B: execute(respond) retry（同一slotにつき1回・retry_of参照・新Execution）

    alt 再試行成功
        B-->>O: 構造化回答B（succeeded）
        Note over O: respond Phase succeeded として続行
    else 再試行も失敗
        B-->>O: TIMEOUT または EXECUTION_ERROR
        O->>O: ExecutionPlanの3人目候補を確認
        alt 適格substituteあり
            O->>S: agent_substitute_selected
            O->>C: execute(respond) substitute_for（新Execution）
            C-->>O: 構造化回答C（succeeded）
        else 代替なし
            Note over O: 成功済みResponderを代替に再利用しない
            O->>S: agent_substitution_unavailable / respond failed / Run failed
        end
    end
```

### 4c. Agent substitutionと12回上限（X-8.16）

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as 失敗Agent
    participant B as 代替候補
    participant C as 別Auditor候補
    participant TB as TokenBudget

    O->>A: execute(synthesize)
    A-->>O: QUOTA_EXCEEDED
    Note over O: 同一Agent retryなし。AgentをRun全体unavailableへ変更
    O->>O: ExecutionPlan候補をlook-ahead確認
    alt 3 Agent構成・別Auditorが残る
        O->>TB: reserve（substitution用の別Reservation）
        TB-->>O: 成功（call count <= 12）
        O->>B: execute(synthesize) substitute_for
        B-->>O: synthesis succeeded
        Note over O: Auditor候補CをSynthesizerから分離して維持
    else 2 Agent構成・別Auditorが残らない
        O->>O: agent_substitution_unavailable
        Note over O: Synthesizer/Auditor分離を破らずRun failed
    end
```

### 4d. 13回目の予約拒否（X-8.16）

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant TB as TokenBudget
    participant A as AgentAdapter
    O->>TB: reserve（committed + reserved = 12）
    TB-->>O: BUDGET_EXCEEDED
    Note over O: AgentAdapter.executeは呼ばない。13回目のAI callなし
```

### 4e. キャンセル（Ctrl+C）

```mermaid
sequenceDiagram
    actor U as 利用者
    participant CLI as oracle CLI
    participant O as Orchestrator
    participant ER as ExecutionRegistry
    participant Ad as AgentAdapter
    participant P as 実行中の子CLIプロセス
    participant S as JSONL Storage

    U->>CLI: Ctrl+C
    CLI->>O: cancel(runId)
    O->>ER: get_active_executions(runId)
    ER-->>O: [(executionId, adapter), ...]
    Note over O: 各アクティブな execution に対して並行して cancel を呼び出す
    par 並行キャンセル
        O->>Ad: cancel(executionId)
        Ad->>P: proc.terminate()
        alt 5秒以内に終了
            P-->>Ad: 終了
        else 5秒後も残存
            Ad->>P: proc.kill()
        end
    end

    Note over O: 実行中スレッドの AgentAdapter.execute() が AgentFailure("CANCELLED") を投げて終了する
    O->>S: 実行中のExecution / Phase / Runをcancelledとして保存
    O-->>CLI: RunResult (status=cancelled, oracle_exit_code=130)
```

## 5. 履歴表示（Q-2反映・metadataのみのRun）

```mermaid
sequenceDiagram
    actor Op as ローカル運用者
    participant CLI as oracle CLI
    participant S as JSONL Storage

    Op->>CLI: oracle history show run-123
    CLI->>S: data/runs/run-123/events.jsonl を読む
    S-->>CLI: イベント列

    alt content保存あり（store-content指定で実行されたRun）
        CLI-->>Op: metadata＋質問・最終回答・Claim・Evidence抜粋
    else metadataのみ（既定）
        CLI-->>Op: run_id・状態・結果区分・件数等＋content_saved: false
        Note over CLI: 本文欄は「本文は保存されていません」と表示（null・空文字を返さない）
    end
```

## 6. 図に反映していない未確定事項

- J-3: `quick`の実行グラフ（未回答のため図なし）
- J-4: 追加質問2ラウンド目のClarifier再呼び出しの有無
- M-5/S-5: X-8.16で確定済み（図4b/4c/4dへ反映）
- R-2: `--json`時の進捗表示の出力先
- R-3: ユーザー応答待ち時間と全体タイムアウトの関係
- R-4: `probe()`の実行方式とカウント。S-10で事前プローブキャッシュおよび `AgentProbeSnapshot` が導入され、各エージェントにつきプローブは1回のRunあたり1回（外部CLIプロセス呼び出しは1回）に制限され、AI呼び出しの課金予算や実行回数にはカウントしない（execute実行前に行われる）ことで確定した。

M-4（`evidence_collect` Phaseと2軸モデル）、R-1（終了コード表）、S-1（Provider内部委譲）はSPEC v0.3.3、S-10（プローブキャッシュとスナップショット）はv0.3.11で確定し、本書へ反映済み。
