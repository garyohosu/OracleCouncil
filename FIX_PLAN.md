# FIX_PLAN — SPEC v0.3.9 反映版

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

## 0-5. X-8.13で解消済み

| # | 内容 | 反映箇所 |
|---|---|---|
| O-6 | stdin限定と一時ファイル許可の矛盾。`CodexAdapter`・`ClaudeAdapter`・`CliSearchProvider`のuser-derived入力（Phase入力、検索クエリ）はすべてargvではなくstdin経由で渡し、argvには固定フラグのみを含める。Codexのtemp fileは`--output-schema`用JSON Schemaのみに限定 | `src/oracle_council/adapters/claude.py`・`adapters/codex.py`、Fakeテスト（X-8.10〜X-8.12）、実機live確認（X-8.13、HEAD `8fcdeaf`、q04で`exit_code=0`/`classification=verified`/全7フェーズ成功） |

## 0-6. X-8.16で仕様確定済み

| # | 内容 | 反映箇所 |
|---|---|---|
| M-5 / S-5 | `ExecutionPlan`、決定的候補順、retry=Run全体2回、substitution=Run全体1回、AI call=12回、error code別処理、Responder独立性、Synthesizer/Auditor分離とlook-ahead、可用性scopeを同時確定 | QandA、SPEC §6.2〜§6.4/§8.3、CLASS、SEQUENCE、STATE、TESTCASE |

## 0-7. X-8.17で通常実装・Fakeテスト完了

## 0-8. X-8.18でL-5通常実装・Fakeテスト完了

6 phase JSON Schema resource、共通validator、AgentRequestへのSchema注入、Claude/Codex共有、Fake/Contract/Unitテストを実装した。実CLI、live評価、WebSearch、実HTTPは未実行。次はS-8。

| # | 内容 | 反映箇所 |
|---|---|---|
| M-5 / S-5 | ExecutionPlanを実行正本化、Run内availability、retry/substitution、`substitute_for`、イベント、Responder独立性、Synth/Audit look-ahead、2/3 Agent境界Fake、12回境界を実装・検証 | `src/oracle_council/assignment.py`、`orchestrator.py`、`models.py`、`cli.py`、unit tests |

実Claude/Codex、live評価、q03 DNS、S-9/S-10は未着手（L-5は0-8、S-8は0-9で完了）。

## 0-9. X-8.19でS-8仕様確定・通常実装・Fake/transport/CLIテスト完了

| # | 内容 | 反映箇所 |
|---|---|---|
| S-8 | 子CLI processのOS終了コードを`process_exit_code`（`AgentResult`／`AgentFailure`／`AgentExecutionRecord`）、Oracle Council全体の外部終了コードを`oracle_exit_code`（`RunResult`／`RunMetadataRecord`／CLI JSONトップレベル）へ分離。取得不能・Fake Agentはnull、process 0後のparse/schema失敗は`INVALID_OUTPUT`かつprocess 0。旧トップレベル`exit_code`はschema 1.x互換エイリアスとして`oracle_exit_code`と常に同値。`executions[]`は`process_exit_code`のみ出力。R-1の0/1/2/3/4/130対応表は不変 | QandA S-8、SPEC v0.3.10 §8.5/§13.4/§14/§15.8、CLASS、TESTCASE、`src/oracle_council/models.py`・`orchestrator.py`・`cli.py`・`adapters/claude.py`・`adapters/codex.py`、`tests/unit/test_exit_code_separation.py` |

実CLI、live評価、q03 DNS failure-boundary、S-9/S-10、L-3は引き続き未着手。

## 0-10. X-8.20でq03 DNS failure-boundaryをFake再現・通常実装・テストで解消済み

X-8.14 q03 holdout（`internal_error` / `[Errno 11001] getaddrinfo failed`）の漏出経路をFakeで再現・確定し、最小のネットワーク境界修正で通常実装・テスト完了した。実live q03再確認は未実施。T-3（DNS rebinding対策・resolver pinning）、S-9/S-10は本項の対象外で未解決のまま。

| # | 内容 | 反映箇所 |
|---|---|---|
| q03 DNS failure-boundary | `SafeHttpFetcher._validate_url()`のSSRF事前チェックが`self._resolver(hostname)`をtry/exceptの外で呼んでおり、`socket.gaierror`が`fetch()`外へ生のまま漏れ、`WebEvidenceProvider`/`Orchestrator`のいずれの型付きハンドラにも捕捉されず、CLIの汎用`except Exception`まで到達していた。resolver呼び出しを`try/except socket.gaierror`で囲み、既存の一般的network failure code `FETCH_FAILED`へ変換するよう修正した（新規public codeは追加していない）。`URLError(socket.gaierror(...))`側は既存の`except (URLError, TimeoutError, OSError)`で従来から正しく変換されており、その契約を回帰テストで明示的に固定した | `src/oracle_council/evidence.py`（`SafeHttpFetcher._validate_url`）、`tests/unit/test_evidence.py`、`tests/unit/test_cli.py` |

## 0-11. X-8.21でS-9仕様確定・通常実装・Fake/integrationテスト完了

| # | 内容 | 反映箇所 |
|---|---|---|
| S-9 | configured adapters (0..*) と selected participants (2..4) をモデル上で分離。build_execution_plan 構築時に priority（role_priority最大値、設定順タイブレーク）に基づいて先頭最大4件の selected participants を選定し、各フェーズの割り当て計算対象をその参加者のみに制限。run_created イベント、RunMetadataRecord、CLI JSONトップレベルで participants を selected participants へ統一し、executions からの逆算を廃止。 | QandA S-9, SPEC v0.3.11 §6.2/§6.3/§15.8, CLASS.md, TESTCASE.md, `src/oracle_council/models.py`・`orchestrator.py`・`cli.py`・`assignment.py`、`tests/unit/test_assignment.py`・`test_orchestrator.py` |

## 0-12. S-10仕様確定・通常実装・Fake/単体テスト完了

| # | 内容 | 反映箇所 |
|---|---|---|
| S-10 | `probe()`と`capabilities()`の二重化を解消。`AgentAdapter`の`capabilities()`メソッドを廃止し、`probe()`が`ProbeResult`オブジェクトを返すように統一。`ProbeResult`は`status`（OKなどの文字列）と`capabilities`（`AgentCapabilities`データクラス、失敗時はNone）を保持し、プローブと同時に能力スナップショットをアトミックに取得して「正本」として扱うように修正した。 | QandA S-10, SPEC v0.3.11 §8.5, CLASS.md, TESTCASE.md, `src/oracle_council/models.py`・`adapters/claude.py`・`adapters/codex.py`・`cli.py`、`tests/unit/test_adapter_capabilities.py` |

## 0-13. X-8.22でT-3（DNS Pinning）仕様確定・通常実装・Fakeテスト完了

| # | 内容 | 反映箇所 |
|---|---|---|
| T-3 | `SafeHttpFetcher` にてDNS解決後の安全なIP接続先をピン留めするDNS Pinningを実装。以降のHTTP接続でそのピン留めされたIPへの接続を強制しつつ、HostヘッダーおよびHTTPS/TLS証明書検証では元のホスト名を使用するようにした。CIでDNS Rebinding対策の有効性を検証するFakeテストを追加。 | QandA T-3, SPEC §16.2, CLASS.md, TESTCASE.md, `src/oracle_council/evidence.py`, `tests/unit/test_evidence.py` |

未解決: 実live q03再評価。

## 0-14. X-8.23でL-3（構造化出力失敗時の回復）仕様確定・通常実装・Fakeテスト完了

| # | 内容 | 反映箇所 |
|---|---|---|
| L-3 | テキスト上の決定的なクレンジング（Markdownコードフェンスの除去、前後の不要な説明テキストのトリミング）のみをAdapter共通処理 `extract_json_object` として共通化して実行し、それ以上のスキーマ違反等の修復やAIへの再試行・再送は行わずに直ちに `INVALID_OUTPUT` とするよう整理。 | QandA L-3, SPEC §8.5, `src/oracle_council/adapters/base.py`・`claude.py`・`codex.py`, `tests/unit/test_adapter_schema.py`・`test_claude_envelope.py` |

## 0-15. S-6 / T-2 仕様確定・通常実装・Fakeテスト完了

| # | 内容 | 反映箇所 |
|---|---|---|
| S-6 / T-2 | Orchestratorにスレッドセーフな `ExecutionRegistry` を設け、実行中の `execution_id` と `AgentAdapter` の関係を管理。キャンセル時に並行して `AgentAdapter.cancel(execution_id)` を伝播。アダプターは `subprocess.Popen` の `terminate()` を呼び、5秒後に `kill()` する「5秒kill」を実装。キャンセル時は Run/Phase/Execution を `cancelled` 状態にし、oracle_exit_code `130` で終了。 | QandA S-6/T-2, SPEC §8.4/§13.4/§15.7/§16.1, `src/oracle_council/orchestrator.py`・`adapters/claude.py`・`adapters/codex.py`, `tests/unit/test_cancellation.py` |

## 0-16. J-3 (quickモードの実行グラフ) 仕様確定・通常実装・Fakeテスト完了

| # | 内容 | 反映箇所 |
|---|---|---|
| J-3 | quickモードにおける実行グラフ（respond * 2 -> compare -> synthesize）を定義。監査・検証・証拠収集フェーズの省略、auditor分離制約のスキップ、常にResultClassification.UNVERIFIEDでの exit 0 終了をサポート。出力JSONに `external_verification: false` を含める。 | QandA J-3, SPEC v0.3.12 §6.3/§12.1, CLASS.md, TESTCASE.md, `src/oracle_council/assignment.py`・`orchestrator.py`・`cli.py`・`phase_schema.py`・`schemas/compare.json`, unit/integration/CLI tests |

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
| **S-4** | ClarificationEngineからのAgent呼び出し | 責務境界・データフローはQandA S-4でAUTO_DECIDED済み（2026-07-15）。実装は2026-07-16に一度試行されテスト10件を破壊したため撤回済み。未実装のまま次回再着手 | 質問整理結合テスト |

J-3は解消済み（0-16参照）。L-5は解消済み（0-8参照）。S-8は解消済み（0-9参照）。

O-6は解消済み（0-5参照）。

S-10は解消済み（0-12参照）。

T-3は解消済み（0-13参照）。

---

## 3. 該当Phase開始前に確定

以下の項目は、それぞれの実装フェーズまたはモジュール実装が開始される前に確定すればよい。

| ID | 項目 | 決めるPhase | 依存するテスト設計領域 |
|---|---|---|---|
| **J-4** | Clarifier 2ラウンドと上限8回 | Phase 1 (質問整理) | 質問整理結合テスト |
| **O-2** | 認証情報マスキングの境界 | Phase 2 (Adapter実装) | secret redactionテスト |
| **R-4** | `probe()`の実行方式とカウント | Phase 2 (Adapter実装) | Probe・カウント検証テスト |
| **N-3** | 障害注入テストの契約 | Phase 2〜3 | ネットワーク・遅延障害テスト |
| **K-2** | Web取得で扱える資料範囲 | Phase 3 (Evidence) | WebEvidenceProvider Contract Test |
| **K-4** | Claim分割とEvidence多対多 | Phase 3 (Evidence) | Evidence共有・マッピングテスト |
| **K-5** | `critical` 6件以上のwithheld | Phase 3 (Evidence) | 保留判定基準テスト |
| **K-6** | `freshness`判定手順と既定値 | Phase 3 (Evidence) | 鮮度バリデーションテスト |
| **K-7** | Evidence処理90秒と並列度 | Phase 3 (Evidence) | 並行取得タイムアウトテスト |
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

R-1、M-4、S-1、U-1（v0.3.3）、S-2、T-5（v0.3.4）、V-1〜V-3（v0.3.5）、M-3、S-3、S-7、T-1、T-4（v0.3.6）の行は確定により削除した（解除済み領域は§0-1〜§0-4を参照）。

依存IDが未回答のケースは削除せず、TESTCASE.mdで`BLOCKED: QandA <ID>`として収集する。仕様確定前に仮の期待値でpassさせない。
