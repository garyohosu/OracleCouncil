# CLASS.md レビュー

- 対象: `CLASS.md`
- 参照: `SPEC.md` v0.3.2、`QandA.md`
- 判定: **REQUEST_CHANGES**
- 日付: 2026-07-10

責務分割の方向は妥当。ただし、実装前に次の不明点を確定する必要がある。既存S-1〜S-3と重複しないため、QandA.mdへS-4〜S-10として統合する。

## S-4. ClarificationEngineからClarifier Agentを呼ぶ経路がない

**重要度**: Critical  
**箇所**: CLASS §1 / SPEC §6.3、§7

SPECではClarifierを1 Agentが担当するが、`ClarificationEngine`は`AgentAdapter`への依存もAgent選定結果を受け取る引数もない。質問整理を規則だけで行うのか、AI呼び出しを含むのか、OrchestratorがAIを呼んでClarificationEngineが結果を判定するのかを確定する必要がある。

**推奨**: OrchestratorがClarifier用AgentRequestを実行し、ClarificationEngineは構造化結果への決定規則適用を担当する。

**回答**: 未回答。

## S-5. `selectAgent(phase)`では複数担当と代替候補を表現できない

**重要度**: Major  
**箇所**: CLASS §1 / SPEC §6.3 / QandA M-5

Responder 2 Agent、SynthesizerとAuditorの分離、失敗時の代替候補、呼び出し上限を単一の`selectAgent()`では表現しにくい。

**推奨**: `buildExecutionPlan(runContext)`で主担当、並列担当、代替候補、分離制約をまとめて決定する。

**回答**: 未回答。

## S-6. Runキャンセル時に実行中Agentを特定する所有者がない

**重要度**: Major  
**箇所**: `Orchestrator.cancel(runId)` / `AgentAdapter.cancel(executionId)`

Runと実行中executionIdの対応を保持するクラスがない。並列Responder、再試行、通常完了とcancelの競合、process tree終了確認を誰が管理するか未定。

**推奨**: `ExecutionRegistry`を設け、runId、executionId、状態、cancel tokenを管理する。cancelは冪等にする。

**回答**: 未回答。

## S-7. TokenBudgetの並列予約が原子的でない

**重要度**: Major  
**箇所**: `TokenBudget.reserve()` / Responder並列実行

並列タスクが同時に残予算を確認すると、上限超過が起こり得る。予約解除、実使用量との差分、再試行時の扱いも未定。

**推奨**: `reserve()`は`BudgetReservation`を返し、`commit(actualUsage)`または`release()`で精算する。呼び出し回数とトークン量を同じ排他制御下で更新する。

**回答**: 未回答。

## S-8. Oracle CLI終了コードと子CLI終了コードが混在する

**重要度**: Major  
**箇所**: `AgentExecution.exitCode` / `AgentResult.exitCode` / QandA R-1

R-1の終了コードは`oracle`コマンドの外部契約。一方、クラス図のexitCodeはClaude CodeやCodex CLIのprocess exit codeと考えられる。同じ名前ではログとJSON出力で混同する。

**推奨**: 子CLIは`processExitCode`、Oracle全体は`oracleExitCode`、意味的結果は`AgentExecutionStatus`と`AgentErrorCode`へ分離する。

**回答**: 未回答。

## S-9. Adapter設定数とRun参加数の多重度が混同されている

**重要度**: Major  
**箇所**: `Orchestrator o-- "2..4" AgentAdapter`

設定済みAdapter数、probe成功数、そのRunの参加数は別概念。利用不能時もAdapter自体は存在するため、常に2〜4保持する表現は不正確。

**推奨**: Orchestratorは`0..* configured adapters`を保持し、ExecutionPlanまたはCouncilに`2..4 selected participants`を持たせる。

**回答**: 未回答。

## S-10. `probe()`と`capabilities()`の正本が二重化している

**重要度**: Minor  
**箇所**: AgentAdapter / ProbeResult / AgentCapabilities / QandA R-4

`probe()`がcapabilitiesを返す一方、`capabilities()`も存在する。CLI更新や設定変更後に値が食い違う可能性がある。

**推奨**: probe結果を実行開始時のcapability snapshotとして正本化し、そのsnapshotをAgent選定と履歴保存に使う。

**回答**: 未回答。

## 既存S-1〜S-3への所見

- **S-1**: `WebEvidenceProvider.fetch()`が`SafeHttpFetcher`へ委譲し、OrchestratorはEvidenceProviderだけを見る構成を推奨する。
- **S-2**: Phaseはmetadata保存対象。AuditIssueもtype、severity、status、claimIdをmetadata保存し、comment本文は`--store-content`時のみ保存する。
- **S-3**: sequence採番はStorageBackend側で原子的に行う。RunEventには`schemaVersion`と`eventId`を追加し、破損行や未知バージョンを履歴表示で警告する。

## 優先順位

実装前ブロッカー: S-1、S-4、S-5、S-6、S-7、S-8  
該当クラス実装前: S-2、S-3、S-9、S-10

上記確定後にCLASS.mdを修正し、再レビューする。