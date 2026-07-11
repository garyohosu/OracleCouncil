# FIX_PLAN — SPEC v0.3.6 反映版

> 設計レビュー、USECASE/SEQUENCE/CLASS/TESTCASE/STATE作成、R-1・M-4・S-1・U-1（v0.3.3）、S-2・T-5（v0.3.4）、V-1〜V-3（v0.3.5）、M-3・S-3・S-7・T-1・T-4（v0.3.6）確定後の状態。

## 0-1. v0.3.3で解消済み

| # | 内容 | 反映箇所 |
|---|---|---|
| R-1 | oracleExitCode対応表（0/1/2/3/4/130、withheld=4独立） | SPEC §13.4、TESTCASE全CLI境界ケース |
| M-4 | `evidence_collect` Phaseと2軸モデル（PhaseStatus × EvidenceOutcome、EvidenceErrorCode） | SPEC §15.7、CLASS.md Enum、SEQUENCE §1 |
| S-1 | Provider内部委譲（Orchestrator → EvidenceProvider → SafeHttpFetcher） | SPEC §10.2、CLASS.md依存線、SEQUENCE §1 |
| U-1 | withheld開示境界（final_answer非公開、Claim検証結果は「確認状態→確認対象→扱い」で開示） | SPEC §11.5、TESTCASE IT-E2E-36 |

## 0-2. v0.3.4で解消済み

| # | 内容 | 反映箇所 |
|---|---|---|
| S-2 | Phase / AuditIssue正式モデル（AuditIssue.statusはMVPでopen/resolvedの2値、accepted_riskは制約付き将来対応。error_summaryは定型文のみmetadata、raw_diagnostic/commentはcontent） | SPEC §11.2・§15.8、CLASS.md §2・§4 |
| T-5 | Run分類の二段判定（1. 公開可能か → 2. どの分類か。withheld確定時はcriticize以降skipped・Run completed・exit 4） | SPEC §15.2・§15.3、TESTCASE IT-E2E-15/16/17/36 |

## 0-3. v0.3.5で解消済み

| # | 内容 | 反映箇所 |
|---|---|---|
| V-1 | 事前停止はRunを生成・保存せず、`run_id: null`のCLI結果を返す | SPEC §14・§15.1、STATE §1、TESTCASE CLI境界 |
| V-2 | `partial`は公開可能な`partially_verified`だけ。withheldは`completed + exit 4` | SPEC §15.2、STATE §1・§5、TESTCASE UT-ORCH-14 |
| V-3 | 収集上限=`BUDGET_EXHAUSTED`、90秒=`EVIDENCE_TIMEOUT`、AI予算=`BUDGET_EXCEEDED` | SPEC §10.2・§15.7、STATE §2、TESTCASE UT-EP-06 |

## 0-4. v0.3.6で解消済み

| # | 内容 | 反映箇所 |
|---|---|---|
| M-3 / S-3 | StorageBackend Contract、Storage採番、原子的append、同時書込み、破損規則 | SPEC §15.1、CLASS §1、TESTCASE UT-SB/CT-SB |
| S-7 | BudgetReservationの3状態、原子的reserve、開始前release、開始後commit、retry別予約 | SPEC §8.7、CLASS §1・§4、STATE §6、TESTCASE UT-TB |
| T-1 | reserve失敗後のpartial/failed分岐、公開条件、exit 0/1 | SPEC §15.2、STATE §1・§6、TESTCASE UT-TB-09/IT-E2E-22 |
| T-4 | 保存有効時のappend失敗は全時点でfail closed、`--no-store`だけ呼出し0回 | SPEC §15.1・§15.2、TESTCASE UT-SB/IT-E2E-25 |

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
5. R-1・M-4・S-1・U-1の確定とSPEC v0.3.3反映（済）
6. S-2・T-5の確定とSPEC v0.3.4反映（済）
7. 状態遷移図の作成（Run / Phase / AgentExecution / Claim / AuditIssue）（済）
   - 要件: withheld確定でsynthesize/auditをskipする経路でも、U-1用のClaim検証結果が生成済みであること（verify Phase完了がwithheld終端の前提）を図へ明示する
8. V-1〜V-3の確定とSPEC v0.3.5反映（済）
9. S-3・S-7・T-1の確定（Fake実装移行のゲート）（済）
10. **Phase 0実装開始**（InMemoryStorageBackend / TokenBudget / Fake Adapter・Provider / verify 7回フロー） ← 現在地
11. 残るモジュール別ブロッカーを各Phase開始前に解消
12. L-4 Adapter spike（実CLI実装のゲート）

---

## 2. 実装開始前に確定（ブロッカー）

以下の項目は、実装を開始する前に設計判断および仕様確定を必要とする。

| ID | 項目 | 概要 | 依存するテスト設計領域 |
|---|---|---|---|
| **J-3** | `quick`の実行グラフ | フェーズ一覧・呼び出し数・出力の確定 | `quick`結合テスト |
| **L-5** | フェーズ別の構造化出力スキーマ | 6フェーズ分のJSON Schema | 各Adapter / JSON Schema Contract Test |
| **M-5** | 代替Agent選定と再試行・12回上限 | 呼び出し上限と代替選定の競合解消 | Agent呼び出し上限テスト |
| **O-6** | stdin限定と一時ファイル許可の矛盾 | セキュリティ隔離と一時ディレクトリ要件の整理 | Adapterセキュリティテスト |
| **S-4** | ClarificationEngineからのAgent呼び出し | Clarifier Agentの呼び出し経路とデータフロー確定 | 質問整理結合テスト |
| **S-5** | Agent選定・代替表現 | 複数担当・代替候補アロケーションのクラス表現 | Agent選定単体テスト |
| **S-6** | Runキャンセル時のExecutionRegistry | 実行中executionIdの所有権とキャンセル管理 | Ctrl+C・process treeテスト |
| **S-8** | CLI終了コードの分離 | `processExitCode` と `oracleExitCode` のフィールド分離 | CLI / Adapter Contract Test |
| **T-2** | cancel合格基準 | 非同期伝播、冪等性、5秒kill、残留process 0件 | Ctrl+C・process treeテスト |
| **T-3** | DNS Rebinding試験境界 | resolver/pinned transportの依存注入 | SafeHttpFetcher Security/Contract Test |

---

## 3. 該当Phase開始前に確定

以下の項目は、それぞれの実装フェーズまたはモジュール実装が開始される前に確定すればよい。

| ID | 項目 | 決めるPhase | 依存するテスト設計領域 |
|---|---|---|---|
| **J-4** | Clarifier 2ラウンドと上限8回 | Phase 1 (質問整理) | 質問整理結合テスト |
| **L-3** | 構造化出力失敗時の回復 | Phase 2 (Adapter実装) | Adapter例外・復帰テスト |
| **O-2** | 認証情報マスキングの境界 | Phase 2 (Adapter実装) | secret redactionテスト |
| **R-4** | `probe()`の実行方式とカウント | Phase 2 (Adapter実装) | Probe・カウント検証テスト |
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
| T-2 | cancel伝播期限・冪等性・残留判定 | Ctrl+C、process tree、cancel競合テスト |
| T-3 | Fake resolver/pinned transport境界 | DNS Rebinding、redirect再検証ST/CT |

R-1、M-4、S-1、U-1（v0.3.3）、S-2、T-5（v0.3.4）、V-1〜V-3（v0.3.5）、M-3、S-3、S-7、T-1、T-4（v0.3.6）の行は確定により削除した（解除済み領域は§0-1〜§0-4を参照）。

依存IDが未回答のケースは削除せず、TESTCASE.mdで`BLOCKED: QandA <ID>`として収集する。仕様確定前に仮の期待値でpassさせない。
