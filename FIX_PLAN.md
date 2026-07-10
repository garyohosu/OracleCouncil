# FIX_PLAN — SPEC v0.3.2 およびクラス・テスト設計レビュー反映版

> 2026-07-10 v0.3.0レビュー → レビュアー回答反映（v0.3.1） → ユースケースQ-1〜Q-3反映（v0.3.2） → USECASE.md承認・SEQUENCE.md作成 → CLASS.md設計レビュー（REQUEST_CHANGES: S-4〜S-10追加） → TESTCASE.md初版およびテスト設計疑問（T-1〜T-4追加）反映後の状態。

## 0. v0.3.1で解消済み

| # | 内容 | SPEC反映箇所 |
|---|---|---|
| J-5 | Critic入力の予算超過 → 上限を上げず入力を削る。回答3,000字、Evidence 500字×最大8件（重複除去後・Run全体）、critical/majorのみCriticへ、入力12,000目標/16,000絶対上限、超過時はEvidenceから先に削る | §8.6、§9.4 |
| O-5 | RunRuntime（実行時）とRunMetadataRecord（永続化）を分離。既定保存はRunMetadataRecordのみ、contentは`--store-content`時のみ | §15.1、§15.8 |
| L-4 | 実装前spikeで公式2 CLIのcapability（非対話・ツール無効・読み取り専用・出力安定性・seed）を確認し`docs/adapter-spike.md`へ記録 | §21 Phase 0前spike |

---

## 1. 合意した処理順（設計書ルート）

1. J-5、O-5、L-4 のSPEC反映（済）
2. Q-1〜Q-3の回答とUSECASE.mdの確定（済）
3. SEQUENCE.md の作成と承認（済）
4. TESTCASE.mdの正式テスト仕様化とT-1〜T-5レビュー（済）
5. **実装開始前ブロッカーの回答とSPEC反映** ← 現在地
6. 状態遷移図の作成（Run / Phase / AgentExecution / Evidence。R-1、M-4、S-2、T-5が前提）
7. CLASS.md の修正と再レビュー（S-1〜S-10を反映）
8. 全文書の横断レビュー
9. L-4 Adapter spike（実装開始のゲート）
10. Phase 0実装開始

---

## 2. 実装開始前に確定（ブロッカー）

以下の項目は、実装を開始する前に設計判断および仕様確定を必要とする。

| ID | 項目 | 概要 | 依存するテスト設計領域 |
|---|---|---|---|
| **J-3** | `quick`の実行グラフ | フェーズ一覧・呼び出し数・出力の確定 | `quick`結合テスト |
| **L-5** | フェーズ別の構造化出力スキーマ | 6フェーズ分のJSON Schema | 各Adapter / JSON Schema Contract Test |
| **M-4** | Evidence収集フェーズの状態モデル | Phase enumへの追加、全断時の挙動定義 | Evidence結合テスト |
| **M-5** | 代替Agent選定と再試行・12回上限 | 呼び出し上限と代替選定の競合解消 | Agent呼び出し上限テスト |
| **O-6** | stdin限定と一時ファイル許可の矛盾 | セキュリティ隔離と一時ディレクトリ要件の整理 | Adapterセキュリティテスト |
| **R-1** | CLI終了コード一覧 | 各種停止・エラー状態での oracleExitCode 確定 | CLI Contract Test |
| **S-1** | fetchの責務境界 | `EvidenceProvider`と`SafeHttpFetcher`の依存方向 | EvidenceProvider / SafeHttpFetcher Contract Test |
| **S-4** | ClarificationEngineからのAgent呼び出し | Clarifier Agentの呼び出し経路とデータフロー確定 | 質問整理結合テスト |
| **S-5** | Agent選定・代替表現 | 複数担当・代替候補アロケーションのクラス表現 | Agent選定単体テスト |
| **S-6** | Runキャンセル時のExecutionRegistry | 実行中executionIdの所有権とキャンセル管理 | Ctrl+C・process treeテスト |
| **S-7** | TokenBudgetの原子性 | 並列予約の排他制御、Reservationオブジェクト設計 | 予算超過・並列予約テスト |
| **S-8** | CLI終了コードの分離 | `processExitCode` と `oracleExitCode` のフィールド分離 | CLI / Adapter Contract Test |
| **S-2** | Phase / AuditIssue正式モデル | 状態集約と監査Issue追跡の永続化区分 | 状態遷移・履歴テスト |
| **S-3** | StorageBackend Contract | append/load/delete/purge、sequence、障害契約 | 永続化Contract Test |
| **T-1** | TokenBudget予約不足時 | reserve失敗後のRun状態、公開可否、予約精算 | 予算超過テスト |
| **T-2** | cancel合格基準 | 非同期伝播、冪等性、5秒kill、残留process 0件 | Ctrl+C・process treeテスト |
| **T-3** | DNS Rebinding試験境界 | resolver/pinned transportの依存注入 | SafeHttpFetcher Security/Contract Test |
| **T-4** | Storage障害時の製品挙動 | fail closedか縮退継続か | Storage障害テスト |
| **T-5** | Run全体の結果分類 | Claim状態からresult_classificationを導出する表 | Claim/Evidence結合・JSONテスト |

---

## 3. 該当Phase開始前に確定

以下の項目は、それぞれの実装フェーズまたはモジュール実装が開始される前に確定すればよい。

| ID | 項目 | 決めるPhase | 依存するテスト設計領域 |
|---|---|---|---|
| **J-4** | Clarifier 2ラウンドと上限8回 | Phase 1 (質問整理) | 質問整理結合テスト |
| **L-3** | 構造化出力失敗時の回復 | Phase 2 (Adapter実装) | Adapter例外・復帰テスト |
| **O-2** | 認証情報マスキングの境界 | Phase 2 (Adapter実装) | secret redactionテスト |
| **R-4** | `probe()`の実行方式とカウント | Phase 2 (Adapter実装) | Probe・カウント検証テスト |
| **M-3** | JSONL破損・同時実行・ディスクフル | Phase 0〜1 (Storage) | Storage Backend 障害テスト |
| **N-3** | 障害注入テストの契約 | Phase 2〜3 | ネットワーク・遅延障害テスト |
| **K-2** | Web取得で扱える資料範囲 | Phase 3 (Evidence) | WebEvidenceProvider Contract Test |
| **K-4** | Claim分割とEvidence多対多 | Phase 3 (Evidence) | Evidence共有・マッピングテスト |
| **K-5** | `critical` 6件以上のwithheld | Phase 3 (Evidence) | 保留判定基準テスト |
| **K-6** | `freshness`判定手順と既定値 | Phase 3 (Evidence) | 鮮度バリデーションテスト |
| **K-7** | Evidence処理90秒と並列度 | Phase 3 (Evidence) | 並行取得タイムアウトテスト |
| **S-9** | Adapter設定数とRun参加数多重度 | Phase 0 (モデル設計) | 構成検証・フォールバックテスト |
| **S-10**| `probe()`と`capabilities()`正本化 | Phase 2 (Adapter/Orchestrator) | アダプター能力検知テスト |
| **N-2** | 非決定的AI判定のgolden dataset | Phase 5 (品質検証) | 精度ベンチマークテスト |
| **R-2** | `--json`時の進捗表示の出力先 | Phase 5 (UX) | CLI標準出力検証テスト |
| **R-3** | ユーザー応答待ちと全体タイムアウト | Phase 1 (対話実装) | 対話応答タイムアウトテスト |

---

## 4. 実装後の実験で決める項目（実験・記事用）

以下の評価・分析タスクは、実装完了後にテストスイートおよび実験計画に基づいて測定を行う。

- **P-1**: 多数決との比較によるCouncil検証の正当性評価（`majority_vote` 衝突テスト）
- **P-2**: 保留率の製品指標評価（`withheld` 挙動とユーザー有用性のバランス）
- **P-3**: 匿名化セッションの効果測定（同調バイアスの定量的検証）
- **P-4**: 品質向上とコスト増の打ち切り点分析（各フェーズの費用対効果）

---

## 5. テスト依存関係

| 未決ID | 先に確定する内容 | 解除されるテスト領域 |
|---|---|---|
| R-1 | `oracleExitCode`対応表 | CLI Contract、非対話停止、cancel、Agent不足 |
| M-4 | Evidence検索・取得・分類のPhase/状態 | Evidence部分成功・全断・timeout結合テスト |
| S-1 | fetchの唯一の所有者とSafeHttpFetcher委譲 | EvidenceProvider / SafeHttpFetcher Contract |
| S-2 | Phase / AuditIssue属性、metadata/content区分 | 状態遷移、監査再実行、履歴イベントテスト |
| S-3 | StorageBackendの操作・sequence・例外Contract | JSONL/SQLite互換Contract、破損・同時書込テスト |
| T-1 | reserve失敗後のRun状態と予約精算 | TokenBudget超過、12回上限テスト |
| T-2 | cancel伝播期限・冪等性・残留判定 | Ctrl+C、process tree、cancel競合テスト |
| T-3 | Fake resolver/pinned transport境界 | DNS Rebinding、redirect再検証ST/CT |
| T-4 | append失敗時のRun/CLI挙動 | disk full、permission、途中保存失敗テスト |
| T-5 | Claim集合からRun分類への決定表 | contradicted/conflicting/unverified、JSON結果テスト |

依存IDが未回答のケースは削除せず、TESTCASE.mdで`BLOCKED: QandA <ID>`として収集する。仕様確定前に仮の期待値でpassさせない。
