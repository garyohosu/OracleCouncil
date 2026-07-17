# Grok・agy Adapter追加、4AI評議会（Claude/Codex/Grok/agy）完了報告

## 1. 選択タスクと目的
- **タスク**: OracleCouncilを本来の目標である4AI会議へ進めるため、既存のClaude/Codex Adapterに加えてGrokAdapter・AgyAdapterを追加し、Claude/Codex/Grok/agyの4種類のAIが1つの評議会（council）へ正式参加できるようにする。
- **前提**: S-4（ClarificationEngineからのAgent呼び出し）はecec8b6で完了済み、今回は不改修。J-4には未着手。
- **参照実績**: `C:\PROJECT\werewolf-game`の`scripts/agents.py`・`config/agents.json`・QandA.md（実際に複数回のゲームで4 CLI全てを呼び出した実績）を一次資料として調査し、確認済みの知見を再利用した（コードは無条件にコピーせず、OracleCouncilの既存Adapter Contractへ適合させた）。

## 2. Grok・agyのCLI呼び出し仕様（2026-07-18ライブ確認）
- **Grok**: `grok -p "<prompt>" --output-format json`（プロンプトは引数、werewolf-gameの`prompt_mode: "arg"`と一致）。応答はCLIメタデータ封筒`{"text": "<回答文>", "stopReason": ..., "usage": {...}, ...}`でラップされ、フェーズJSONは`envelope["text"]`という文字列の中にある（Claude Adapterの`envelope["result"]`と同型）。
- **agy**: `agy --print "<prompt>"`（同じく引数渡し）。封筒は一切なく、標準出力がそのままモデルの回答文字列（Codex Adapterと同型の直接パース）。
- 両CLIともネイティブなJSON Schema制約フラグ（grokの`--json-schema`）を持つ場合があるが未使用とし、プロンプト埋め込みのschema hintで統一（werewolf-gameの実績アプローチに合わせ、検証済みでない2つ目のコードパスを増やさないため）。agyにはそもそもネイティブなschema制約フラグが存在しない。
- Grokの応答速度についてはwerewolf-gameのQandA記録に「60秒で不足、120秒で成功」という実測値があり、既存のSPEC §8.4既定180秒が既にこれを余裕を持って上回っているため、Grok専用のタイムアウト値は新設しなかった。

## 3. 実装したAdapter
- `src/oracle_council/adapters/grok.py`（新規）: `GrokAdapter`。Claude型（封筒展開）パターン。
- `src/oracle_council/adapters/agy.py`（新規）: `AgyAdapter`。Codex型（直接パース）パターン。
- 両者とも既存の`AgentAdapter` Contract（`probe`/`execute`/`cancel`）、`classify_cli_error`、`validate_phase_output`、キャンセル対応`subprocess.run`差し替えパターンをClaude/Codexと共通化し、Grok/agyをClaudeAdapter/CodexAdapterの別名にはしていない。
- `src/oracle_council/adapters/__init__.py`・`cli.py`（Agent構築ループへgrok/agy分岐追加）を更新。

## 4. 4AIの設定内容（`config/agents.yaml`）
既存2体（claude-code: respond/synthesize/audit最優先、codex-cli: respond/verify/audit最優先）に加え、grok-cli（claim_extract/clarify最優先）とagy-cli（criticize/clarify最優先）を追加し、4体すべて`enabled: true`とした。既存のS-9由来`ranked[:4]`参加者上限とちょうど4体で一致するため、4体全員が選出される構成にした。

## 5. 4AI会議の統合テスト結果
`tests/unit/test_orchestrator.py::test_four_ai_council_all_participate`（新規）: Scripted Adapterで4体それぞれ異なる役割を割り当て、`result.participants`が4体全て（claude-code, codex-cli, grok-cli, agy-cli）であること、各Adapterが期待どおりのフェーズ列（claude-code: respond→synthesize、codex-cli: respond→verify→audit、grok-cli: claim_extract、agy-cli: criticize）で実際に呼ばれることを決定的に検証。**成功**。

## 6. 実CLI smoke test結果（2026-07-18ライブ実行）
本機にはClaude Code・Codex CLI・Grok・agyの4 CLI全てがインストール・認証済みであることを確認した上で、`probe()`と`respond`フェーズの`execute()`を実行:
- **Claude**: probe OK、execute OK（`{"answer": "Blue"}`）
- **Codex**: probe OK、execute OK（`{"answer": "blue"}`）
- **Grok**: probe OK、execute OK（`{"answer": "blue"}`）
- **agy**: probe OK、execute OK（`{"answer": "blue"}`）

これらは`tests/contract/test_adapters.py`へ`@pytest.mark.live`テストとして恒久化した（`test_grok_adapter_live_probe`/`test_grok_adapter_live_execute`/`test_agy_adapter_live_probe`/`test_agy_adapter_live_execute`）。`pytest -m live`実行結果は**8 passed, 2 skipped**（skip 2件は別ファイル`tests/e2e/test_real_adapter_e2e.py`の`ORACLE_COUNCIL_LIVE`環境変数ゲート付きテストで、Claude/Codex専用の既存テスト・今回変更対象外）。

## 7. 失敗・skipの理由
今回は4 CLI全てが利用可能だったため、恒久的な失敗・skipは発生していない。ただし追加したliveテストは`probe()`が`OK`以外（`QUOTA_EXCEEDED`/`COMMAND_NOT_FOUND`/`TIMEOUT`）を返した場合、あるいは`execute()`が`QUOTA_EXCEEDED`/`AUTH_REQUIRED`/`RATE_LIMITED`で失敗した場合は、失敗ではなくその1 Adapterのみを`pytest.skip`する設計にしてあり、他AIを巻き込んで停止させない（指示どおり）。

## 8. 全テスト結果
- `py -m pytest`（既定スイート、`-m "not live"`）: **373 passed, 10 deselected**（Task D着手前の370 passed, 6 deselectedから、4AI統合テスト+1、grok/agy live probe/execute各2×2=4個の新規liveテストで純増）。
- `pytest -m live`: **8 passed, 2 skipped**。
- `git diff --check`: 成功。
- APIキー・認証情報の読み出し・記録は一切行っていない。環境変数はサブプロセスへそのまま引き継ぐのみで、内容をログ・テスト・commitへ書き出していない。

## 9. 変更ファイル
- 新規: `src/oracle_council/adapters/grok.py`、`src/oracle_council/adapters/agy.py`
- 変更: `src/oracle_council/adapters/__init__.py`、`src/oracle_council/cli.py`、`config/agents.yaml`
- テスト変更: `tests/unit/test_orchestrator.py`（4AI統合テスト新規追加）、`tests/contract/test_adapters.py`（grok/agy live test新規追加、既存Claude/Codex liveテストの`ProbeResult`比較バグも修正）
- 文書変更: `QandA.md`（Y-1/Y-2/Y-3新規）、`SPEC.md`（§3/§8.1/§8.5/§20.2）、`CLASS.md`（クラス図）、`TESTCASE.md`（§2.4・CT-AA-LIVE-02）、`FIX_PLAN.md`（§0-18）、`hikitsugi.md`（§0-21）、本ファイル

## 10. 文書更新
上記9項目のとおり、SPEC.md/CLASS.md/TESTCASE.md/QandA.md/FIX_PLAN.md/hikitsugi.md/本ファイルを全て更新済み。

## 11. commit hashとpush結果
（本メッセージ作成時点ではまだcommit前。次のステップでcommit・push予定。commit後にこの節を実際のhashで更新する。）

## 12. HEADとorigin/mainの一致
（push後に確認予定。）

## 13. git status
（commit後に確認予定。）

## 14. 4AIによる実会議までに残る課題
- 今回の実CLI smoke testは各Adapter単独での`respond`フェーズ1回実行に留めた（コスト・実行時間の都合）。4体同時参加でのRun全体（clarify→respond×2→claim_extract→verify→criticize→synthesize→audit、Evidence収集含む）を実CLI 4種同時実行で完走させる実機E2Eはまだ実施していない。
- J-4（対話モードでの2ラウンド質問整理）は引き続き未着手。
- critical ambiguity検出パターンはS-4時点の4種類の保守的な実装のままで、grok/agy追加による変更はない。
- `instructions/instructions.md`のfront matterは引き続き人間が次タスクを書き込む必要がある（AutoLoop側のPlanner未導入課題として別途記録済み）。
