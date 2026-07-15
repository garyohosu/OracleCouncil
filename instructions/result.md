# S-10: probe結果とcapabilitiesの正本統一 完了報告

## 1. 変更前のprobe／capabilities取得経路
- **probe**:
  - CLIのRun開始前事前確認において各Agentの `probe()` が呼び出され、かつ `Adapter.execute()` の内部で実行開始時に再probeが実行されていました。これにより、1コマンド/1 Run内で同一のAgentに対して重複してprobeが行われていました。
  - `agents status` や `agents validate` の実行時に、設定された実Adapterではなく `FakeAgentAdapter` が再生成されて実行されていました。
- **capabilities**:
  - `config/agents.yaml` の `capabilities` と、Adapterが提供する `capabilities()` が分離しており、どちらが正本であるか定義が曖昧でした。また、statusとcapabilitiesが別々の時点で取得されていました。

## 2. 採用した正本モデル
- **`AgentProbeSnapshot`** モデルを `oracle_council.models` に導入。
  - `agent_id`
  - `status` (利用可能性)
  - `capabilities` (能力スナップショット)
  - `probed_at` (測定日時)
  - `error_code` (エラー/理由コード)
- を含みます。このスナップショットを不変のスナップショット（正本）として扱います。

## 3. snapshotの生成箇所
- `cli.py` 内に導入した共通ヘルパー `probe_agents()` によって、CLIエントリポイント（`cmd_ask` などのRun開始直前）で enabled な全Agentについて1回だけAdapterの `probe()` と `capabilities()` を呼び出して生成されます。

## 4. snapshotのライフサイクル
- 1 Runの開始前に `probe_agents()` により一括生成され、`ExecutionPlan` および `Orchestrator` のコンストラクタへ渡されます。
- Runの開始時に `run_created` イベントの payload (`agent_snapshots`) に記録され、監査記録として不変の状態で永続化されます。
- Runの終了時に `RunMetadataRecord` および `RunResult` に不変の状態で保存されます。

## 5. config capabilitiesの位置づけ
- 実Adapterの実行時 `capabilities()` の値を正本（ベース）としつつ、config側で `capabilities` が明示設定されている場合は、config側の値でAdapter側の能力を上書き（マージ）したものをスナップショットの `capabilities` として保存します。以降のRuntime中はこの不変スナップショットの値のみを参照します。

## 6. execute時の再probeをどう扱ったか
- 各 Adapter (`ClaudeAdapter`, `CodexAdapter`, `FakeAgentAdapter`) に `_probe_cache` メンバーを追加し、初回の `probe()` の結果をキャッシュする仕組みを導入しました。
- `execute()` 内で `self.probe()` が呼び出された際には、キャッシュされた結果を即座に返すため、外部CLIプロセス（`claude --version`など）の無駄な再実行を完全に回避しつつ、Adapter自身での fail-closed 保証を維持しました。

## 7. agents status／validateの修正
- **`agents status`**:
  - 共通の `probe_agents()` ヘルパー経由で実設定に基づいた Adapter を生成し、1回だけ probe/capabilities を呼び出してスナップショットを取得・表示するように修正しました。実Adapterを `FakeAgentAdapter` に置き換える問題が解消されました。
- **`agents validate`**:
  - 静的検証（IDの重複など）を最初に行い、その後に `probe_agents()` によるAdapter生成可能性・動的確認を行うよう構造を分離しました。1コマンド中に同じprobeが重複実行されることはありません。

## 8. 変更ファイル
- `C:\PROJECT\OracleCouncil\QandA.md` (AUTO_DECIDEDの追記)
- `C:\PROJECT\OracleCouncil\src\oracle_council\models.py` (スナップショットモデル・永続化フィールドの追加)
- `C:\PROJECT\OracleCouncil\src\oracle_council\assignment.py` (ExecutionPlanでの snapshot 保持と互換生成)
- `C:\PROJECT\OracleCouncil\src\oracle_council\adapters\claude.py` (ClaudeAdapterへのプローブキャッシュ追加)
- `C:\PROJECT\OracleCouncil\src\oracle_council\adapters\codex.py` (CodexAdapterへのプローブキャッシュ追加)
- `C:\PROJECT\OracleCouncil\src\oracle_council\cli.py` (FakeAgentAdapterプローブキャッシュ、create_adapter/probe_agents共通化、cmd_ask/status/validateリファクタリング)
- `C:\PROJECT\OracleCouncil\src\oracle_council\orchestrator.py` (Orchestratorでの snapshot 引き回し、永続化イベント・結果への設定)

## 9. 追加・更新したテスト
- `C:\PROJECT\OracleCouncil\tests\unit\test_s10_probe_snapshot.py` を新規追加。
  - **`test_adapter_probe_caching`**: ClaudeAdapter, CodexAdapter, FakeAgentAdapterの各probeキャッシュ機構の動作を検証。
  - **`test_snapshot_creation_and_merge`**: `probe_agents` でのAdapter生成、config capabilitiesとのマージ規則の正当性を検証。
  - **`test_snapshot_lifecycle_in_orchestrator`**: Orchestrator生成からRun終了までの不変スナップショットライフサイクルが正しく保存されることを検証。

## 10. probe回数を検証した結果
- 新規テスト `test_adapter_probe_caching` において、`probe()` を複数回呼んでも `subprocess.run` (CLIコマンド実行) が高々1回しか呼び出されないことが検証され、要件を完全に満たしています。

## 11. 全通常テスト結果
- `py -m pytest` を実行し、全299件のテストが正常にパスすることを確認しました (299 passed)。
- `git diff --check` による空白チェックもすべてパスしています。

## 12. S-9を壊していないこと
- S-9 に関連する `test_assignment.py` 内の決定性テストや選定ロジックが正常にパスしていることを確認し、最大2..4人の参加上限などの既存仕様を壊していないことを確認しました。

## 13. S-10以外へ踏み込んでいないこと
- 非対象に指定されていた S-9の再実装やDNS rebinding (T-3) などの別タスクへの踏み込みは一切行っていません。

## 14. 未解決事項
- 特になし。すべての S-10 要件を完了しました。

## 15. 次の推奨タスク
- **`L-5`** (フェーズ別出力スキーマの確定・検証) または **`M-4`** (Evidence収集の状態モデル確定) への移行を推奨します。
