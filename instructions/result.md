# S-4 (ClarificationEngineからのAgent呼び出し) 完了報告

## 1. 選択タスクと解決したブロッカー
- **タスク**: `ClarificationEngine`から実際にClarifier Agentを呼び出し、応答を既存仕様に従って後続処理へ渡す配線（S-4）。
- **解決したブロッカー**: 2026-07-17の再着手調査で判明した4つの未回答質問（QandA S-4.1〜S-4.4: `inspect()`の責務分離、SPEC §7.5第1・第2段階の具体化、Clarifier Agent呼び出し条件・判定主体、CLI進捗表示の7/8切り替え）を、ユーザーが正式決定。決定に従い実装・テスト・文書更新まで完了した。

## 2. 正式決定（ユーザー決定、2026-07-18）した仕様と実装内容
- **責務分離（S-4.1）**: `ClarificationEngine.inspect(question, context=None)` は決定的既定値・テンプレート規則・critical ambiguity検出のみを行い、Agent不要なら`ClarificationResult`を、必要なら`ClarificationPreCheck`（agent_required/assumptions/ambiguities/provisional status）を返す。`evaluate_agent_output(question, context, output)` はClarifier Agentの構造化出力をclarify schemaで検証し、SPEC §7.2/§7.5の決定規則を適用する。
- **第1・第2段階（S-4.2）**: 出力形式・対象読者・長さ・言語・タイムゾーン・時点の既定値補完（tier1）と、要約/説明/比較/一覧/コード作成/校正/調査の7テンプレート（tier2）。いずれもAgentを呼ばず、補完内容はassumptionsへ記録する。
- **Clarifier呼び出し条件（S-4.3）**: 判定主体は`ClarificationEngine`。tier1/2で解決できない「critical ambiguity」（6カテゴリに限定）が残る場合だけ、Orchestratorがclarifyのrole_priority最高の適格Agentを決定的に1体選び、`clarify`フェーズのAgentRequestを非対話モードで最大1回実行する。Agent出力評価後の6 status（ready/ready_with_assumptions/needs_clarification/premise_issue/unsupported/safety_blocked）とAgent呼び出し失敗時の分類（`auth_required`/`clarification_unavailable`、ともにexit 3）を実装。
- **CLI進捗表示（S-4.4）**: `ClarificationEngine().inspect()`の結果から動的に`[1/7]`/`[1/8]`を計算。死んだコードだった`clarify_trigger`マジック文字列分岐を削除し、新しい`--clarify`フラグは追加していない。

## 3. 変更ファイル
- 新規: `src/oracle_council/clarification.py`、`src/oracle_council/schemas/clarify.json`、`tests/unit/test_clarification.py`
- 変更: `src/oracle_council/phase_schema.py`、`models.py`、`assignment.py`、`orchestrator.py`、`cli.py`
- テスト変更: `tests/unit/test_orchestrator.py`、`test_cli.py`、`test_assignment.py`、`test_adapter_capabilities.py`
- 文書変更: `QandA.md`（S-4.1〜S-4.4を確定として記録）、`SPEC.md`（§7.5詳細化、§13.4 exit codeテーブル更新）、`CLASS.md`（API分離・新データ型）、`TESTCASE.md`（§2.3更新）、`FIX_PLAN.md`（§0-17でS-4解消済みへ）、`hikitsugi.md`（§0-20）、本ファイル

## 4. テスト結果
- `py -m pytest`: **370 passed, 6 deselected**（既存310件は無傷のまま、純増60件）。
- `git diff --check`: 成功。
- 実Claude・実Codex呼び出し、Web検索、実HTTPアクセスは一切行っていない（Fake/Scriptedアダプターのみ使用）。

## 5. 未解決事項
- J-4（対話モードでの2ラウンド質問整理、`ClarificationEngine.applyAnswers`の実装）は今回の対象外で未着手。
- critical ambiguity検出は、QandA S-4.3が定める6カテゴリのうち4パターンを保守的な正規表現で実装した初期版。網羅性は今後の拡張余地。
- `instructions/instructions.md`のfront matterは引き続き人間が次タスクを書き込む必要がある（AutoLoop側のPlanner未導入課題として別途記録済み、本タスクの対象外）。

## 6. 次の推奨タスク
J-4（Clarifier対話モードの2ラウンド実装）。現時点でFIX_PLAN.md §2「実装開始前に確定（ブロッカー）」に残っている項目はない。
