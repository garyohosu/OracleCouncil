# J-3 (quickモードの実行グラフ) 完了報告

## 1. 選択タスクと解決したブロッカー
- **タスク**: `quick` モード（簡易比較・統合回答）に関する実行グラフの仕様確定、およびその実装・テスト。
- **解決したブロッカー**: 未回答であった QandA `J-3` の仕様を自動決定（AUTO_DECIDED）し、実装・テストを完了させた。これにより MVP における `quick` モードの動作とフェーズ遷移の仕様が完全に固定された。

## 2. 自動決定（AUTO_DECIDED）した仕様と決定理由
- **実行グラフ（フェーズ一覧と実行順）**:
  フェーズは `respond` (スロット0) -> `respond` (スロット1) -> `compare` -> `synthesize` の順で実行される（合計4回のエージェント呼び出し）。
  外部Evidence収集 (`evidence_collect`)、Claim抽出 (`claim_extract`)、Claim検証 (`verify`)、および最終監査 (`audit`) は行わない。
- **決定理由**:
  - `quick` モードの定義（簡易比較・統合回答・外部Evidence収集なし）と整合させるため。
  - 最終監査（`audit`）フェーズが存在しないため、`synthesize` フェーズでの auditor との分離制約が不要になり、2 Agent 構成でも正常に動作可能にするため。
  - 外部検証を行わないため、結果は保留 (`withheld`) にせず常に `ResultClassification.UNVERIFIED` ("unverified") として回答を返すため。

## 3. 出力メタデータと進捗表示
- **出力 JSON**: `"mode": "quick"` と `"external_verification": false` を含むようにし、外部検証がされていないことを明示する。
- **進捗表示**: `quick` の 4ステップに合わせた進捗表示（`[1/4] 2 Agentが独立回答中...`）を CLI 実行時に出力する。

## 4. 変更ファイル
- **ソースコード**:
  - [src/oracle_council/assignment.py](file:///C:/project/OracleCouncil/src/oracle_council/assignment.py)
  - [src/oracle_council/orchestrator.py](file:///C:/project/OracleCouncil/src/oracle_council/orchestrator.py)
  - [src/oracle_council/cli.py](file:///C:/project/OracleCouncil/src/oracle_council/cli.py)
  - [src/oracle_council/models.py](file:///C:/project/OracleCouncil/src/oracle_council/models.py)
  - [src/oracle_council/phase_schema.py](file:///C:/project/OracleCouncil/src/oracle_council/phase_schema.py)
- **新規追加ファイル (JSONスキーマ)**:
  - [src/oracle_council/schemas/compare.json](file:///C:/project/OracleCouncil/src/oracle_council/schemas/compare.json)
- **設計資料**:
  - [QandA.md](file:///C:/project/OracleCouncil/QandA.md)
  - [SPEC.md](file:///C:/project/OracleCouncil/SPEC.md)
  - [CLASS.md](file:///C:/project/OracleCouncil/CLASS.md)
  - [TESTCASE.md](file:///C:/project/OracleCouncil/TESTCASE.md)
  - [FIX_PLAN.md](file:///C:/project/OracleCouncil/FIX_PLAN.md)
  - [hikitsugi.md](file:///C:/project/OracleCouncil/hikitsugi.md)
- **テスト**:
  - [tests/unit/test_assignment.py](file:///C:/project/OracleCouncil/tests/unit/test_assignment.py)
  - [tests/unit/test_orchestrator.py](file:///C:/project/OracleCouncil/tests/unit/test_orchestrator.py)
  - [tests/unit/test_cli.py](file:///C:/project/OracleCouncil/tests/unit/test_cli.py)

## 5. 追加・更新したテスト
1. **`test_quick_plan_contains_correct_slots`** (tests/unit/test_assignment.py)
   - quickモード用の ExecutionPlan が正しいフェーズ構成 (`respond` * 2, `compare`, `synthesize`) となり、かつ auditor との分離制約が不要であることを検証。
2. **`test_quick_mode_flow_success`** (tests/unit/test_orchestrator.py)
   - quickモードの実行フロー、結果の `ResultClassification.UNVERIFIED` および終了コード 0 を検証。
3. **`test_cli_ask_quick_mode_success`** (tests/unit/test_cli.py)
   - CLI 実行時の出力 JSON が `mode: quick`、`external_verification: false` であり、フェーズリストが正しく構成されていることを検証。

## 6. 対象テスト結果
- 追加した J-3 関連テストはすべて正常にパスした。

## 7. 全通常テスト結果
- `py -m pytest -q` を実行し、全 **311 passed** で成功。
- `git diff --check` で whitespace 等の警告がないことを確認。

## 8. 未解決事項
- 実 live 評価（Claude/Codex APIの呼び出しを伴う live 評価）は未実施。

## 9. 次の推奨タスク
- **S-4**: ClarificationEngineからのAgent呼び出しの仕様確定および実装。
