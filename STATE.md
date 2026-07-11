# Oracle Council 状態遷移図

- 対象仕様: `SPEC.md` v0.3.5
- 参照順: SPEC → QandA確定回答 → SEQUENCE → CLASS → TESTCASE → FIX_PLAN
- 対象範囲: MVPのRun、Phase、AgentExecution、AuditIssue、公開可否・結果分類
- 原則: 処理状態、公開可否、結果分類、CLI終了コードを別軸として扱う

## 1. Run状態遷移

`withheld`、`needs_clarification`等は`RunStatus`ではない。図中の`cli_*`はRun状態ではなく、CLIが返す`result.status`と終了コードを表す。

```mermaid
stateDiagram-v2
    [*] --> pending: Run生成
    pending --> running: 実行開始

    running --> completed: 全必須Phaseが許容終端<br/>公開回答あり
    running --> completed: verify完了後にwithheld確定<br/>final_answer非公開 / exit 4
    running --> partial: 監査済み回答あり<br/>非critical劣化またはmajor未確認 / exit 0
    running --> failed: 必須Phase最低成功数未達<br/>監査未完了またはaudit blocked / exit 1
    running --> cancelled: SIGINTまたは明示cancel / exit 130

    completed --> [*]
    partial --> [*]
    failed --> [*]
    cancelled --> [*]

    state "CLI事前停止（RunStatusではない）" as preflight {
        [*] --> cli_input: needs_clarification / strict_required<br/>unsupported / safety_blocked / exit 2
        [*] --> cli_environment: verification_unavailable<br/>insufficient_agents / exit 3
        cli_input --> [*]
        cli_environment --> [*]
    }

    note right of preflight
      Runは生成・保存しない。run_id=null。
      JSONへstatus / exit_code / messageを必ず返す。
      history showの対象外。--no-storeでも保存しない。
    end note
    note right of failed
      Storage障害の終端は BLOCKED: QandA S-3, T-4
      予算不足後のRun終端は BLOCKED: QandA S-7, T-1
    end note
    note left of completed
      completedでもwithheld / exit 4になり得る。
      Run.statusと公開可否・終了コードは別軸。
      verified / conflicting / unverifiedの公開回答はexit 0。
    end note
```

許可するRunStatus遷移は`pending -> running -> completed | partial | failed | cancelled`だけであり、終端状態から再遷移しない。`partially_verified`、`conflicting`、`unverified`は`ResultClassification`でありRunStatusではない。終端判定順は`cancelled -> failed -> withheldを伴うcompleted -> partial -> completed`。`partial`はAuditor承認済みの公開可能な回答があり、分類が`partially_verified`の場合だけ使用する。

## 2. Phase状態遷移

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running: Phase開始
    pending --> skipped: 対象外または先行判定で不要
    pending --> cancelled: 開始前cancel

    running --> succeeded: 最低成功数を満たし全処理成功
    running --> degraded: 最低成功数を満たすが一部失敗
    running --> failed: 最低成功数未達または機能全断
    running --> cancelled: cancel伝播

    succeeded --> [*]
    degraded --> [*]
    failed --> [*]
    skipped --> [*]
    cancelled --> [*]

    state "evidence_collectの二軸判定" as evidence_collect {
        [*] --> evidence_processing
        evidence_processing --> evidence_ok_none: 検索正常 / 資料0件
        evidence_processing --> evidence_budget: 一部処理 / 収集上限到達
        evidence_processing --> evidence_timeout: 一部処理 / 90秒到達
        evidence_processing --> evidence_broken: 検索・取得機能が実行中に全断
        evidence_ok_none --> [*]: Phase=succeeded<br/>Outcome=no_evidence
        evidence_budget --> [*]: Phase=degraded<br/>Outcome=partial_evidence<br/>Error=BUDGET_EXHAUSTED
        evidence_timeout --> [*]: Phase=degraded<br/>Outcome=partial_evidence<br/>Error=EVIDENCE_TIMEOUT
        evidence_broken --> [*]: Phase=failed<br/>EvidenceErrorCodeを記録
    }

    note right of evidence_collect
      Phase.statusは処理成否、EvidenceOutcomeは根拠の結果。
      evidence_found / conflicting_evidenceもPhase成功と両立する。
      evidence_collectはAgentExecutionを生成しない。
      未処理Claimはunverified。
      AI/token予算不足のBUDGET_EXCEEDEDとは別コード。
    end note
    note left of skipped
      verify完了後にwithheld確定:
      criticize / synthesize / audit = skipped
    end note
```

最低成功数は`respond=2`、`claim_extract=1`、`verify=1`、`criticize=1`、`synthesize=1`、`audit=1`。`clarify`は不要なら`skipped`、`evidence_collect`は`quick`等で対象外なら`skipped`とする。

## 3. AgentExecution状態遷移

再試行は同じレコードの再遷移ではなく、新しい`AgentExecution`を作り、`retry_of`で元Executionを参照する。

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running: 子CLI起動
    pending --> cancelled: 起動前cancel

    running --> succeeded: exitと構造化出力が有効
    running --> unavailable: 実行不能
    running --> failed: 実行したが有効出力なし
    running --> timed_out: timeout
    running --> cancelled: Ctrl+C / cancel

    unavailable --> [*]: AUTH_REQUIRED / QUOTA_EXCEEDED<br/>CLI_NOT_FOUND / UNSUPPORTED_VERSION
    failed --> retry_pending: RATE_LIMITEDまたは一時障害<br/>再試行枠あり
    timed_out --> retry_pending: 再試行枠あり
    failed --> compact_pending: CONTEXT_OVERFLOW<br/>決定的縮約が未実施
    retry_pending --> pending_retry: 新Execution作成 / retry_of設定
    compact_pending --> pending_retry: 決定的縮約を1回適用
    pending_retry --> running_retry: 子CLI再起動
    running_retry --> retry_succeeded: 有効出力
    running_retry --> retry_failed: 再失敗 / 追加再試行なし
    retry_succeeded --> [*]
    retry_failed --> [*]: failed / timed_out / unavailable<br/>またはBUDGET_EXCEEDED
    succeeded --> [*]
    failed --> [*]: INVALID_OUTPUT / EXECUTION_ERROR<br/>再試行対象外または枠消費済み
    timed_out --> [*]: 再試行枠消費済み
    cancelled --> process_tree_stop: terminate process tree
    process_tree_stop --> [*]: 5秒後も残存ならkill<br/>残留process 0件

    note right of retry_pending
      同一Execution由来の再試行は最大1回。
      Run全体の再試行は2回、AI呼出しは12回上限。
    end note
    note right of compact_pending
      縮約後も収まらなければBUDGET_EXCEEDED。
      予算予約・精算とRun終端は
      BLOCKED: QandA S-7, T-1
    end note
```

`error_code`は`AUTH_REQUIRED`、`QUOTA_EXCEEDED`、`RATE_LIMITED`、`CONTEXT_OVERFLOW`、`INVALID_OUTPUT`、`BUDGET_EXCEEDED`等の正式Enumを使う。`error_summary`は制限付きmetadata、生診断は`raw_diagnostic` contentへ分離する。

## 4. AuditIssue状態遷移

```mermaid
stateDiagram-v2
    [*] --> open: 監査Issue生成
    open --> resolved: 修正後の再監査で解消
    open --> open: 再監査でも未解消
    resolved --> [*]

    note right of open
      未解決open Critical Issueが残れば公開不可。
      再監査後もopenならaudit blocked、Run failed。
    end note
    note right of resolved
      MVP Enumはopen / resolvedのみ。
      accepted_riskは将来構想であり状態へ含めない。
    end note
```

`accepted_risk`を将来導入しても`resolved`と同一扱いにせず、critical、安全違反、捏造引用、プロンプトインジェクション影響には使用しない。

## 5. 公開可否・結果分類

第1段の安全判定を先に実行し、公開可能な場合だけ第2段の分類を行う。

```mermaid
stateDiagram-v2
    [*] --> verify_complete: verify Phase完了<br/>全対象Claim状態確定
    verify_complete --> safety_gate

    safety_gate --> withheld: criticalにunverified/contradicted<br/>またはmajorにcontradicted
    safety_gate --> publishable: 上記なし

    withheld --> skip_later: criticize / synthesize / auditをskipped
    skip_later --> completed_withheld: Run.status=completed / exit 4
    completed_withheld --> claims_disclosed: final_answer非公開<br/>Claim検証結果・Evidence概要を公開
    claims_disclosed --> [*]

    publishable --> conflicting: criticalまたはmajorにconflicting
    publishable --> unverified: majorが1件以上かつ全てunverified
    publishable --> partially_verified: majorにunverified<br/>またはminorにunverified/conflicting/contradicted
    publishable --> verified: 検証対象1件以上<br/>全てverified/supported
    publishable --> unverified: Claim 0件または全not_applicable

    conflicting --> completed_public: Auditor approved / exit 0
    unverified --> completed_public: Auditor approved / exit 0
    verified --> completed_public: Auditor approved / exit 0
    partially_verified --> partial_public: Auditor approved / exit 0
    completed_public --> [*]: Run.status=completed<br/>final_answer公開
    partial_public --> [*]: Run.status=partial<br/>final_answer公開

    note right of safety_gate
      優先順位:
      withheld > conflicting > unverified
      > partially_verified > verified
    end note
    note left of completed_withheld
      「処理成功」と「回答公開可否」は別軸。
      Run completedでも回答保留になり得る。
    end note
    note right of verify_complete
      Evidence処理成否（Phase.status）と
      EvidenceOutcomeも別軸。
    end note
```

公開可能な分類でも、Auditorが`approved`でなければ`final_answer`を公開しない。`changes_required`は修正と再監査を1回だけ行い、再監査でも未解決Critical Issueが残る場合は`blocked`としてRunを`failed`へ送る。

## 6. 未確定境界

| QandA | 状態図への影響 | 本書での扱い |
|---|---|---|
| S-3 / T-4 | Storage障害時のRun終端・イベント保証 | Run図へBLOCKED注記。遷移は確定しない |
| S-7 / T-1 | TokenBudget予約不足時のRun終端・予約精算 | Run/AgentExecution図へBLOCKED注記。遷移は確定しない |
